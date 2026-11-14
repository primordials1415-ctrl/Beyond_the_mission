"""InSight minigame — MARTIAN WHISPER.

Reaction / timing challenge. A seismic trace sweeps across the monitor; press
CAPTURE when the marker reaches the waveform's true peak. Three events with
increasing difficulty share ONE 60-second countdown.

Plugs into the existing challenge interface (see puzzle.py):
    handle_event(e) -> "done" only on victory (EncounterScene then runs the
                       normal Memory Capsule flow), update(dt), draw(surf).
Failure (time out) shows GAME OVER + RETRY and never returns "done", so no
capsule is granted. Duplicate capsules are already blocked by
StoryProgress.recover().

Scoring is tied to the displayed waveform: each trace is generated from data,
its peak is the argmax of that data, and the capture is judged by the time
distance between the marker and that peak.
"""
import math
import random
import time

import pygame

import ui
from settings import SCREEN_W, SCREEN_H, CYAN, TEXT, DIM

# --------------------------------------------------------------------- config
TIME_LIMIT = 60.0
LOW_TIME = 10.0
BANNER_TIME = 1.4       # "EVENT n" banner before each stage (timer keeps running)
RESULT_TIME = 2.4       # result display before the next stage / victory
POINTS = {"PERFECT": 1000, "GOOD": 600, "MISS": 0}
RANKS = [(2700, "S"), (2300, "A"), (1800, "B"), (0, "C")]
SAMPLES = 360

# Difficulty is real gameplay parameters, not cosmetics:
#   cycle     seconds for the marker to sweep the trace (shorter = faster)
#   perfect/good  half-width (seconds) of timing windows around the true peak
#   decoys    amplitudes of competing lower bumps (harder peak detection)
#   lookahead fraction of the trace shown ahead of the marker
#   jitter    irregularity of envelope / frequency
#   freq      carrier oscillations per trace
STAGES = [
    dict(name="FAINT TREMOR", level="EASY", cycle=4.2, perfect=0.22, good=0.55,
         decoys=[], lookahead=1.00, jitter=0.00, freq=12, sigma=0.11),
    dict(name="GROWING TREMOR", level="MEDIUM", cycle=3.2, perfect=0.13, good=0.32,
         decoys=[0.72], lookahead=0.40, jitter=0.15, freq=20, sigma=0.075),
    dict(name="DEEP MARSQUAKE", level="HARD", cycle=2.4, perfect=0.075, good=0.19,
         decoys=[0.85, 0.80], lookahead=0.18, jitter=0.35, freq=32, sigma=0.05),
]

AMBER = (255, 176, 64)
ORANGE = (255, 120, 40)
RED = (255, 80, 70)
GREEN = (110, 255, 170)
SCREEN_BG = (6, 9, 14)

DISP = pygame.Rect(60, 128, 780, 240)
GAUGE = pygame.Rect(864, 128, 32, 240)
CAPTURE_RECT = pygame.Rect(330, 416, 300, 60)

_now = time.monotonic   # overridable in tests


# ------------------------------------------------------------ pure game logic
def judge(delta, stage):
    """Result for a capture `delta` seconds from the true peak."""
    d = abs(delta)
    if d <= stage["perfect"]:
        return "PERFECT"
    if d <= stage["good"]:
        return "GOOD"
    return "MISS"


def rank_for(score):
    for threshold, letter in RANKS:
        if score >= threshold:
            return letter
    return "C"


MIN_MARGIN = 0.12   # the true peak must beat any rival bump by at least this


def build_wave(stage, rng):
    """Generate a trace whose peak is unambiguous (re-rolls until it is)."""
    for _ in range(100):
        wave = _generate(stage, rng)
        n, pi = SAMPLES, int(round(wave["peak_u"] * (SAMPLES - 1)))
        rival = max((wave["env"][i] for i in range(n) if abs(i - pi) > 0.12 * n), default=0.0)
        if wave["env"][pi] - rival >= MIN_MARGIN:
            break
    return wave


def _generate(stage, rng):
    """Generate one seismic trace. Returns dict(env, y, peak_u, peak_t).
    peak_u (0..1 of the trace) is the argmax of the envelope and the carrier is
    phased to have a crest exactly there, so the displayed highest crest IS the
    scoring peak."""
    n = SAMPLES
    main_c = rng.uniform(0.38, 0.70)
    centers = [main_c]
    for _ in stage["decoys"]:
        for _try in range(50):
            c = rng.uniform(0.12, 0.90)
            if all(abs(c - o) > 0.22 for o in centers):
                break
        centers.append(c)
    amps = [1.0] + list(stage["decoys"])
    sig = [stage["sigma"]] + [0.05] * len(stage["decoys"])
    ph = [rng.uniform(0, 6.28) for _ in range(2)]
    jit = stage["jitter"]
    env = []
    for i in range(n):
        u = i / (n - 1)
        e = 0.10
        for c, a, s in zip(centers, amps, sig):
            e += a * math.exp(-((u - c) ** 2) / (2 * s * s))
        e *= 1 + jit * 0.12 * math.sin(2 * math.pi * 5 * u + ph[0]) \
               + jit * 0.08 * math.sin(2 * math.pi * 11 * u + ph[1])
        env.append(e)
    peak_i = max(range(n), key=lambda i: env[i])
    peak_u = peak_i / (n - 1)
    top = env[peak_i]
    env = [e / top for e in env]
    f = stage["freq"]
    wob = lambda u: jit * 0.8 * (math.sin(2 * math.pi * 3 * u) - math.sin(2 * math.pi * 3 * peak_u))
    y = [env[i] * math.cos(2 * math.pi * f * (i / (n - 1) - peak_u) + wob(i / (n - 1)))
         for i in range(n)]
    return dict(env=env, y=y, peak_u=peak_u, peak_t=peak_u * stage["cycle"])


def env_at(wave, u):
    n = len(wave["env"])
    i = max(0, min(n - 1, int(round(u * (n - 1)))))
    return wave["env"][i]


# ---------------------------------------------------------------------- game
class MartianWhisper:
    title = "Martian Whisper"

    def __init__(self, eq=None):
        self.eq = eq
        self._last = _now()
        self.reset()

    # ------------------------------------------------------------ state reset
    def reset(self):
        """Full reset (used on construction and RETRY)."""
        self.phase = "briefing"          # briefing|banner|playing|result|victory|gameover
        self.t = 0.0                     # time in current phase
        self.time_left = TIME_LIMIT
        self.timer_running = False
        self.stage_i = 0
        self.score = 0
        self.shown_score = 0.0
        self.results = []                # verdict per completed event
        self.wave = None
        self.sweep = 0.0                 # seconds into the current trace cycle
        self.captured = False
        self.last = None                 # dict describing the last capture
        self.won = False
        self.buttons = ui.ButtonRow(["START"], 428)
        self.end_buttons = None
        self._last = _now()

    @property
    def stage(self):
        return STAGES[self.stage_i]

    # ----------------------------------------------------------- flow control
    def _begin_stage(self, i):
        self.stage_i = i
        self.wave = build_wave(self.stage, random.Random(random.random()))
        self.sweep = 0.0
        self.captured = False
        self.last = None
        self._set_phase("banner")

    def _set_phase(self, p):
        self.phase, self.t = p, 0.0

    def _fail(self):
        self.timer_running = False
        self.time_left = 0.0
        self.end_buttons = ui.ButtonRow(["Retry"], 372)
        self._set_phase("gameover")

    def _win(self):
        self.won = True
        self.end_buttons = ui.ButtonRow(["Continue"], 432)
        self._set_phase("victory")

    def capture(self):
        """Single capture per event. Ignored unless actively playing."""
        if self.phase != "playing" or self.captured or self.time_left <= 0:
            return
        self.captured = True
        st = self.stage
        delta = self.sweep - self.wave["peak_t"]
        verdict = judge(delta, st)
        pts = POINTS[verdict]
        self.score += pts
        self.results.append(verdict)
        u = self.sweep / st["cycle"]
        self.last = dict(verdict=verdict, points=pts, delta=delta, u=u,
                         magnitude=round(1.0 + 3.5 * env_at(self.wave, u), 1))
        if self.stage_i == len(STAGES) - 1:
            self.timer_running = False       # all events captured: stop the clock
        self._set_phase("result")

    # ------------------------------------------------------------------ input
    def handle_event(self, e):
        if self.phase == "briefing":
            if self.buttons.handle_event(e) == 0:
                self.timer_running = True    # countdown begins with Stage 1
                self._begin_stage(0)
        elif self.phase == "playing":
            if (e.type == pygame.KEYDOWN and
                    e.key in (pygame.K_SPACE, pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_e)) or \
               (e.type == pygame.MOUSEBUTTONDOWN and e.button == 1 and CAPTURE_RECT.collidepoint(e.pos)):
                self.capture()
        elif self.phase == "gameover":
            if self.end_buttons.handle_event(e) == 0:
                self.reset()                 # retry = full reset, back to briefing
        elif self.phase == "victory":
            if self.end_buttons.handle_event(e) == 0:
                return "done"                # -> existing Memory Capsule flow
        return None

    # ----------------------------------------------------------------- update
    def update(self, dt):
        # Real elapsed time keeps the 60 s strict even if frames are slow.
        now = _now()
        step = max(0.0, min(now - self._last, 0.1))
        self._last = now
        self.t += step

        if self.timer_running:
            self.time_left = max(0.0, self.time_left - step)
            if self.time_left <= 0.0:
                self._fail()
                return

        self.shown_score += (self.score - self.shown_score) * min(1.0, step * 6)
        if abs(self.score - self.shown_score) < 1:
            self.shown_score = float(self.score)

        if self.phase == "banner" and self.t >= BANNER_TIME:
            self.sweep = 0.0
            self._set_phase("playing")
        elif self.phase == "playing":
            self.sweep = (self.sweep + step) % self.stage["cycle"]   # loops until captured
        elif self.phase == "result" and self.t >= RESULT_TIME:
            if self.stage_i == len(STAGES) - 1:
                self._win()
            else:
                self._begin_stage(self.stage_i + 1)

    # ---------------------------------------------------------------- drawing
    def draw(self, surf):
        if self.phase == "briefing":
            self._draw_briefing(surf)
        elif self.phase == "victory":
            self._draw_victory(surf)
        elif self.phase == "gameover":
            self._draw_gameover(surf)
        else:
            self._draw_station(surf)

    def _timer_color(self):
        if self.time_left <= LOW_TIME:
            return RED if int(self.t * 4 + self.time_left * 4) % 2 == 0 or not self.timer_running else (255, 150, 120)
        return TEXT

    def _draw_briefing(self, surf):
        r = ui.center_panel(surf, 760, 440)
        ui.draw_title(surf, "MARTIAN WHISPER", r.y + 16, 56)
        ui.draw_title(surf, "InSight  -  Seismic Monitoring Station", r.y + 68, 28, DIM)
        body = r.inflate(-110, 0)
        y = ui.draw_wrapped(surf, "Catch each event at its highest peak. The live marker moves along the trace; the true peak is the tallest cyan crest.", 28, body, r.y + 108)
        p = pygame.Rect(r.centerx - 180, y + 34, 360, 78)
        pygame.draw.rect(surf, SCREEN_BG, p)
        pygame.draw.rect(surf, CYAN, p, 1)
        pygame.draw.line(surf, AMBER, (p.x + 18, p.centery), (p.right - 18, p.centery), 2)
        peak_x = p.x + 248
        pygame.draw.line(surf, CYAN, (peak_x, p.y + 12), (peak_x, p.bottom - 12), 2)
        pygame.draw.circle(surf, CYAN, (peak_x, p.centery - 20), 8, 2)
        pygame.draw.circle(surf, AMBER, (p.x + 120, p.centery), 7)
        ui.draw_title(surf, "Marker", p.x + 20, 20, AMBER)
        ui.draw_title(surf, "Peak", peak_x - 18, 20, CYAN)
        ui.draw_title(surf, "CAPTURE:  SPACE / ENTER / E   or click the button", y + 128, 26, AMBER)
        ui.draw_title(surf, "PERFECT +1000    GOOD +600    MISS +0", y + 160, 22, TEXT)
        self.buttons.draw(surf)

    def _wave_xy(self, i, y):
        n = SAMPLES
        x = DISP.x + 8 + (i / (n - 1)) * (DISP.w - 16)
        return (x, DISP.centery - y * (DISP.h / 2 - 16))

    def _draw_screen_bg(self, surf):
        pygame.draw.rect(surf, SCREEN_BG, DISP)
        for k in range(1, 10):                       # vertical time ticks
            x = DISP.x + k * DISP.w // 10
            pygame.draw.line(surf, (22, 32, 42), (x, DISP.y), (x, DISP.bottom))
        for k in range(1, 6):                        # amplitude grid
            y = DISP.y + k * DISP.h // 6
            pygame.draw.line(surf, (22, 32, 42), (DISP.x, y), (DISP.right, y))
        pygame.draw.line(surf, (60, 80, 95), (DISP.x, DISP.centery), (DISP.right, DISP.centery))
        f = ui.font(20)
        for k, lab in ((0, "+1.0"), (3, "0"), (6, "-1.0")):
            surf.blit(f.render(lab, True, DIM), (DISP.x + 4, DISP.y + k * DISP.h // 6 + (2 if k < 6 else -16)))
        pygame.draw.rect(surf, CYAN, DISP, 1)

    def _draw_trace(self, surf, marker_u, full=False):
        n, w = SAMPLES, self.wave
        mi = int(marker_u * (n - 1))
        ahead = n - 1 if full else min(n - 1, mi + int(self.stage["lookahead"] * n))
        if ahead > mi:   # dim preview of what is coming
            pts = [self._wave_xy(i, w["y"][i]) for i in range(mi, ahead + 1)]
            if len(pts) > 1:
                pygame.draw.lines(surf, (110, 62, 30), False, pts, 1)
        if mi > 0:       # traced (live) part
            pts = [self._wave_xy(i, w["y"][i]) for i in range(0, mi + 1)]
            pygame.draw.lines(surf, AMBER if not full else ORANGE, False, pts, 2)
            env = [self._wave_xy(i, w["env"][i]) for i in range(0, mi + 1)]
            pygame.draw.lines(surf, (150, 70, 40), False, env, 1)

    def _draw_station(self, surf):
        st = self.stage
        ui.draw_panel(surf, pygame.Rect(40, 26, 880, 488), 245)

        # header: event name / progress pips (left), timer (center), score (right)
        surf.blit(ui.font(32).render(f"EVENT {self.stage_i + 1}/3  -  {st['name']}", True, CYAN), (64, 42))
        surf.blit(ui.font(22).render(f"Difficulty: {st['level']}", True, DIM), (64, 74))
        for i in range(3):
            c = pygame.Rect(64 + i * 30, 98, 22, 12)
            if i < len(self.results):
                col = {"PERFECT": CYAN, "GOOD": AMBER, "MISS": RED}[self.results[i]]
                pygame.draw.rect(surf, col, c)
            else:
                pygame.draw.rect(surf, AMBER if i == self.stage_i else DIM, c, 2)
        secs = int(math.ceil(self.time_left))
        tt = ui.font(78).render(f"{secs}", True, self._timer_color())
        surf.blit(tt, tt.get_rect(center=(SCREEN_W // 2, 62)))
        secs_label = ui.font(20).render("SECONDS", True, DIM)
        surf.blit(secs_label, secs_label.get_rect(center=(SCREEN_W // 2, 106)))
        sc = ui.font(44).render(f"{int(round(self.shown_score)):,}", True, AMBER)
        surf.blit(sc, sc.get_rect(topright=(896, 50)))
        surf.blit(ui.font(22).render("SCORE", True, DIM), (896 - ui.font(22).size("SCORE")[0], 36))

        self._draw_screen_bg(surf)
        # intensity gauge
        pygame.draw.rect(surf, SCREEN_BG, GAUGE)
        pygame.draw.rect(surf, CYAN, GAUGE, 1)
        surf.blit(ui.font(18).render("INTENSITY", True, DIM), (GAUGE.x - 14, GAUGE.bottom + 4))

        if self.phase == "banner":
            ui.draw_title(surf, f"EVENT {self.stage_i + 1}: {st['name']}", DISP.centery - 40, 54, AMBER)
            ui.draw_title(surf, "Get ready...", DISP.centery + 14, 30, TEXT)
            self._draw_capture_button(surf, False)
            return

        if self.phase == "playing":
            u = self.sweep / st["cycle"]
            self._draw_trace(surf, u)
            mx = DISP.x + 8 + u * (DISP.w - 16)
            px = DISP.x + 8 + self.wave["peak_u"] * (DISP.w - 16)
            pygame.draw.line(surf, TEXT, (mx, DISP.y), (mx, DISP.bottom), 2)
            pygame.draw.circle(surf, CYAN, (int(px), int(DISP.centery - self.wave["env"][int(self.wave["peak_u"] * (SAMPLES - 1))] * (DISP.h / 2 - 16))), 7, 2)
            pygame.draw.line(surf, CYAN, (px, DISP.y), (px, DISP.bottom), 1)
            level = env_at(self.wave, u)
        else:  # result: show full captured reading with peak + capture lines
            L = self.last
            self._draw_trace(surf, 1.0, full=True)
            px = DISP.x + 8 + self.wave["peak_u"] * (DISP.w - 16)
            cx = DISP.x + 8 + L["u"] * (DISP.w - 16)
            pygame.draw.line(surf, CYAN, (px, DISP.y), (px, DISP.bottom), 2)
            pygame.draw.circle(surf, CYAN, (int(px), int(DISP.centery - self.wave["env"][int(self.wave["peak_u"] * (SAMPLES - 1))] * (DISP.h / 2 - 16))), 8, 3)
            pygame.draw.line(surf, TEXT, (cx, DISP.y), (cx, DISP.bottom), 2)
            surf.blit(ui.font(20).render("PEAK", True, CYAN), (px + 4, DISP.y + 4))
            surf.blit(ui.font(20).render("CAPTURE", True, TEXT), (cx + 4, DISP.bottom - 22))
            level = env_at(self.wave, L["u"])

        fh = int((GAUGE.h - 8) * level)
        col = GREEN if level > 0.9 else (AMBER if level > 0.5 else ORANGE)
        pygame.draw.rect(surf, col, (GAUGE.x + 4, GAUGE.bottom - 4 - fh, GAUGE.w - 8, fh))

        if self.phase == "result":
            L = self.last
            vcol = {"PERFECT": CYAN, "GOOD": AMBER, "MISS": RED}[L["verdict"]]
            pop = min(1.0, self.t / 0.2)
            ui.draw_title(surf, L["verdict"] + "!", DISP.y + 40 - int((1 - pop) * 20), int(40 + 40 * pop), vcol)
            rise = int(min(1.0, self.t / 0.8) * 24)
            ui.draw_title(surf, f"+{L['points']}", DISP.y + 120 - rise, 52, vcol if L["points"] else DIM)
            side = "early" if L["delta"] < 0 else "late"
            ui.draw_title(surf, f"Magnitude {L['magnitude']}   |   {abs(L['delta']) * 1000:.0f} ms {side}",
                          DISP.bottom + 14, 28, TEXT)
            self._draw_capture_button(surf, False)
            ui.draw_title(surf, "Seismic reading recorded", 466, 26, DIM)
        else:
            self._draw_capture_button(surf, True)
            ui.draw_title(surf, "Capture at the PEAK  -  one attempt per event", 466, 26, DIM)

    def _draw_capture_button(self, surf, active):
        r = CAPTURE_RECT
        pulse = 0.5 + 0.5 * math.sin(self.t * 6) if active else 0
        ui.draw_panel(surf, r, 250)
        if active:
            pygame.draw.rect(surf, (int(160 + 95 * pulse), int(90 + 50 * pulse), 30), r.inflate(-10, -10), 3)
        t = ui.font(52).render("CAPTURE", True, AMBER if active else (80, 80, 80))
        surf.blit(t, t.get_rect(center=r.center))

    def _draw_victory(self, surf):
        r = ui.center_panel(surf, 740, 450)
        ui.draw_title(surf, "SEISMIC EVENTS CAPTURED", r.y + 16, 46)
        rank = rank_for(self.score)
        col = {"S": CYAN, "A": GREEN, "B": AMBER, "C": ORANGE}[rank]
        ui.draw_title(surf, "RANK", r.y + 66, 26, DIM)
        ui.draw_title(surf, rank, r.y + 86, 150, col)
        ui.draw_title(surf, f"FINAL SCORE  {self.score:,} / 3,000", r.y + 222, 42, AMBER)
        n = lambda v: self.results.count(v)
        ui.draw_title(surf, f"PERFECT {n('PERFECT')}      GOOD {n('GOOD')}      MISS {n('MISS')}",
                      r.y + 270, 34, TEXT)
        ui.draw_title(surf, f"Time remaining: {self.time_left:.1f} s", r.y + 308, 26, DIM)
        self.end_buttons.draw(surf)

    def _draw_gameover(self, surf):
        r = ui.center_panel(surf, 640, 330)
        ui.draw_title(surf, "GAME OVER", r.y + 24, 72, RED)
        ui.draw_title(surf, "The signal faded before every event was captured.", r.y + 100, 26, DIM)
        ui.draw_title(surf, f"Score: {self.score:,}", r.y + 140, 44, AMBER)
        ui.draw_title(surf, f"Seismic events completed: {len(self.results)} / 3", r.y + 188, 34, TEXT)
        self.end_buttons.draw(surf)


# ----------------------------------------------------- standalone test runner
if __name__ == "__main__":
    pygame.init()
    screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
    pygame.display.set_caption("Martian Whisper (standalone)")
    clock = pygame.time.Clock()
    game = MartianWhisper()
    running = True
    while running:
        dt = clock.tick(60) / 1000
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT or (ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE):
                running = False
            elif game.handle_event(ev) == "done":
                print("VICTORY -> Memory Capsule would be granted here. Rank:", rank_for(game.score))
                game.reset()
        game.update(dt)
        screen.fill((0, 0, 0))
        game.draw(screen)
        pygame.display.flip()
    pygame.quit()
