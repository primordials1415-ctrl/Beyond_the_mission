"""Cinematic opening for Beyond the Mission.

Flow (all driven by Intro.update / Intro.draw from the normal game loop):

    crawl     Star Wars-style perspective crawl over a starfield
    vista     stars fade out, a Martian dusk landscape fades in, the camera
              tilts down toward the ground, dust drifts, then it dissolves
              into the real game ground
    awaken    the Ghost Rover (existing sprites) stirs: gathering particles,
              ghostly flicker, eyes ignite, body lifts, fully appears,
              then the opening line is shown
    reveal    camera settles on the normal gameplay view, the explorer appears
    tutorial  MOVEMENT / INTERACTION / MEMORY CAPSULES, one page at a time

ESC skips everything. Nothing here touches gameplay state: the owner passes
in the existing World, Player and Ghost (used read-only, apart from letting the
Ghost's own animation clock run while it is frozen in place) and an
`on_finish` callback that starts normal play.

Usage:  self.intro = Intro(world, player, ghost, cam, on_finish)
        intro.handle_event(e) / intro.update(dt) / intro.draw(screen)
"""
import math
import random
import pygame

import sprites
import ui
from settings import SCREEN_W, SCREEN_H, MAP_W, MAP_H, CYAN, TEXT, DIM

W, H = SCREEN_W, SCREEN_H
WHITE = (255, 255, 255)
GOLD = (255, 214, 72)

CRAWL_TEXT = [
    "LONG AFTER HUMANITY'S FIRST JOURNEY TO MARS...",
    "The Red Planet holds the remnants of humanity's greatest exploration missions.",
    "Across its vast deserts, forgotten machines remain — silent witnesses to discoveries, "
    "sacrifices, and unfinished journeys.",
    "But their memories have not entirely disappeared.",
    "A mysterious rover awakens on the Martian surface, carrying no memory of its origins.",
    "Scattered across the planet are fragments of the past, waiting to be recovered.",
    "Six lost missions. Six forgotten stories.",
    "And one final journey to uncover the truth.",
]

OPENING_LINES = ["Somewhere between memory and oblivion,", "a forgotten journey begins."]

TUTORIAL = [
    ("MOVEMENT",
     "Use W A S D or the arrow keys to move your explorer across the Martian surface."),
    ("INTERACTION",
     "Press E when a prompt appears to talk to the Ghost Rover and inspect what you find. "
     "Press E or Space to continue a conversation."),
    ("MEMORY CAPSULES",
     "Discover and interact with Memory Capsules to recover lost memories and uncover "
     "the stories of previous Mars missions."),
]

# ---------------------------------------------------------------- timeline
CRAWL_START = 2.0        # seconds of starfield before the text appears
STARS_IN, STARS_OUT = 3.0, 2.5
VISTA_T = 16.0           # tilt-down duration
VISTA_XFADE = 4.5        # dissolve into the real ground at the end of the vista
T_WAKE = 11.5            # awakening moment inside the awaken phase
A_END = 28.0
REVEAL_T = 5.0
MSG_START, MSG_IN, MSG_HOLD, MSG_OUT = 19.0, 1.6, 4.4, 2.0
DORMANT_GRADE, WAKE_GRADE, CALM_GRADE = (46, 44, 74), (88, 80, 114), (132, 118, 142)
BAR_H = 46


# ----------------------------------------------------------------- helpers
def clamp(x, lo=0.0, hi=1.0):
    return lo if x < lo else hi if x > hi else x


def lerp(a, b, x):
    return a + (b - a) * x


def seg(t, a, b):
    return clamp((t - a) / (b - a))


def smooth(x):
    x = clamp(x)
    return x * x * (3 - 2 * x)


def ease(x):
    x = clamp(x)
    return 0.5 - 0.5 * math.cos(math.pi * x)


def lerp_col(a, b, x):
    return tuple(int(lerp(a[i], b[i], x)) for i in range(3))


def _grade_at(t):
    if t < T_WAKE + 3:
        return lerp_col(DORMANT_GRADE, WAKE_GRADE, smooth(seg(t, 0, T_WAKE + 3)))
    return lerp_col(WAKE_GRADE, CALM_GRADE, smooth(seg(t, T_WAKE + 3, 24)))


# ---------------------------------------------------------------- starfield
class _Stars:
    def __init__(self, n=230):
        rng = random.Random(7)
        # x, y, size, brightness, twinkle phase, twinkle speed, drift speed
        self.s = [[rng.uniform(0, W), rng.uniform(0, H), rng.choice((1, 1, 1, 2)),
                   rng.uniform(0.35, 1.0), rng.uniform(0, 6.28), rng.uniform(0.6, 2.2),
                   rng.uniform(1.5, 6.0)] for _ in range(n)]
        self.bright = [s for s in self.s if s[2] == 2][:10]
        self.t = 0.0

    def update(self, dt):
        self.t += dt
        for s in self.s:
            s[0] -= s[6] * dt
            if s[0] < -2:
                s[0] += W + 4

    def draw(self, surf, alpha, ymax=None):
        if alpha <= 0.01:
            return
        for x, y, size, b, ph, sp, _ in self.s:
            if ymax is not None:
                if y > ymax:
                    continue
                fade = 1.0 - y / ymax
            else:
                fade = 1.0
            c = int(255 * b * (0.72 + 0.28 * math.sin(self.t * sp + ph)) * alpha * fade)
            if c <= 4:
                continue
            surf.fill((c, c, min(255, c + 8)), (int(x), int(y), size, size))
        if ymax is None:
            lvl = int(4 * alpha)
            if lvl >= 1:
                for s in self.bright:
                    surf.blit(sprites.glow(7, lvl), (int(s[0]) - 7, int(s[1]) - 7),
                              special_flags=pygame.BLEND_RGB_ADD)


# -------------------------------------------------------------------- crawl
class _Crawl:
    WRAP_W = 660
    LINE, GAP = 48, 44
    K = 560.0                      # perspective strength
    Y_H, Y_B = 70.0, H + 30.0      # horizon / bottom (u = 0) screen rows
    S_FULL, S_GONE = 0.60, 0.28    # scale at which text starts / finishes fading
    SPEED = 64.0                   # world px / second
    START_U = -10.0

    def __init__(self):
        self.span = self.Y_B - self.Y_H
        self.c = self.span / self.K
        body = pygame.font.Font(None, 44)
        body.set_bold(True)
        head = pygame.font.Font(None, 50)
        head.set_bold(True)
        self.lines = []            # [surface, world y of line]
        y = 0
        for i, para in enumerate(CRAWL_TEXT):
            f = head if i == 0 else body
            for ln in ui.wrap(para, f, self.WRAP_W):
                self.lines.append((f.render(ln, True, GOLD), y))
                y += self.LINE
            y += self.GAP
        last_y = self.lines[-1][1]
        u_gone = self.K * (1.0 / self.S_GONE - 1.0)
        self.duration = (u_gone - self.START_U + last_y + 20) / self.SPEED

    def draw(self, surf, t):
        travel = self.SPEED * max(0.0, t)
        for img, y in self.lines:
            u = self.START_U - y + travel
            if u < -40:
                continue
            s = self.K / (self.K + u)
            if s <= self.S_GONE:
                continue
            yc = self.Y_H + self.span * s
            if yc - 40 > H:
                continue
            a = smooth(seg(s, self.S_GONE, self.S_FULL))
            sw = max(1, int(img.get_width() * s))
            sh = int(img.get_height() * self.c * s * s)
            if sh < 2:
                continue
            scaled = pygame.transform.smoothscale(img, (sw, sh))
            scaled.set_alpha(int(255 * a))
            surf.blit(scaled, (W // 2 - sw // 2, int(yc - sh / 2)))


# --------------------------------------------------------- Martian vista
def _stops(stops, x):
    for (x0, c0), (x1, c1) in zip(stops, stops[1:]):
        if x <= x1:
            return lerp_col(c0, c1, (x - x0) / (x1 - x0))
    return stops[-1][1]


class _Vista:
    """Procedural dusk landscape. Layers are pre-rendered once; the camera
    tilt moves nearer layers faster, so the view sinks toward the ground."""
    HY0, HY1 = 400.0, 30.0         # horizon row at start / end of the tilt
    M = 120                        # horizontal margin for the side pan
    SKY_H = 430

    def __init__(self):
        rng = random.Random(21)
        self.sky = self._sky()
        self.far, self.far_top = self._ridge(rng, 110, 12, (132, 66, 62), (230, 150, 104), 5)
        self.mid, self.mid_top = self._ridge(rng, 130, 16, (98, 46, 46), (205, 120, 84), 7)
        self.near, self.near_top = self._ridge(rng, 70, 26, (52, 24, 28), (160, 88, 62), 11)
        self.ground, self.ground_top = self._ground(rng)
        self.haze = self._haze()

    def _sky(self):
        s = pygame.Surface((W, self.SKY_H))
        stops = [(0.0, (12, 8, 26)), (0.42, (56, 26, 52)), (0.78, (150, 66, 62)), (1.0, (244, 156, 100))]
        for y in range(self.SKY_H):
            pygame.draw.line(s, _stops(stops, y / (self.SKY_H - 1)), (0, y), (W, y))
        return s

    def _ridge(self, rng, amp, step, col, rim, octaves):
        w = W + 2 * self.M
        top = amp + 24
        s = pygame.Surface((w, top + 560), pygame.SRCALPHA)
        ph = [rng.uniform(0, 6.28) for _ in range(3)]
        fq = [rng.uniform(150, 240), rng.uniform(70, 110), rng.uniform(28, 46)]
        prof = []
        for x in range(0, w + step, step):
            v = 0.55 * math.sin(x / fq[0] + ph[0]) + 0.3 * math.sin(x / fq[1] + ph[1]) \
                + 0.15 * math.sin(x / fq[2] + ph[2]) + rng.uniform(-0.12, 0.12) * octaves / 5
            h = amp * (0.5 + 0.5 * v)
            prof.append((x, top - h))
        pts = prof + [(w, top + 560), (0, top + 560)]
        pygame.draw.polygon(s, col, pts)
        for (x0, y0), (x1, y1) in zip(prof, prof[1:]):
            pygame.draw.line(s, rim, (x0, y0), (x1, y1), 2)
        return s, top

    def _ground(self, rng):
        gh = 780
        top = 40
        s = pygame.Surface((W + 2 * self.M, gh), pygame.SRCALPHA)
        w = s.get_width()
        stops = [(0.0, (150, 82, 58)), (0.12, (140, 70, 48)), (0.5, (128, 62, 42)), (1.0, (120, 56, 38))]
        for y in range(gh):
            pygame.draw.line(s, _stops(stops, y / (gh - 1)), (0, y), (w, y))
        # perspective-sized stones and dune bands (bigger toward the viewer)
        for _ in range(260):
            y = rng.uniform(top + 10, gh)
            k = (y - top) / (gh - top)
            sz = 2 + k * 26
            x = rng.uniform(0, w)
            col = rng.choice(((82, 38, 30), (170, 98, 62), (98, 46, 34), (70, 30, 26)))
            pygame.draw.ellipse(s, col, (x, y, sz * rng.uniform(1.0, 2.2), sz * 0.5))
        for _ in range(26):
            y = rng.uniform(top + 30, gh - 20)
            k = (y - top) / (gh - top)
            band = pygame.Surface((int(180 + 420 * k), int(10 + 46 * k)), pygame.SRCALPHA)
            pygame.draw.ellipse(band, (226, 140, 86, 26), band.get_rect())
            s.blit(band, (rng.uniform(-100, w - 100), y))
        # undulating top edge
        mask = pygame.Surface((w, gh), pygame.SRCALPHA)
        ph = rng.uniform(0, 6.28)
        edge = [(x, top - 14 * (0.5 + 0.5 * math.sin(x / 130 + ph)) - 6 * math.sin(x / 41 + ph * 2))
                for x in range(0, w + 20, 20)]
        pygame.draw.polygon(mask, (255, 255, 255, 255), edge + [(w, gh), (0, gh)])
        s.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        return s, top

    def _haze(self):
        h = 220
        s = pygame.Surface((W, h), pygame.SRCALPHA)
        for y in range(h):
            k = 1 - abs(y - h * 0.62) / (h * 0.62 if y < h * 0.62 else h * 0.38)
            s.fill((236, 150, 104, int(70 * max(0.0, k) ** 1.6)), (0, y, W, 1))
        return s

    def draw(self, surf, p, stars):
        d = self.HY1 - self.HY0

        def hy(f):
            return self.HY0 + d * p * f

        def px(f):
            return int(-self.M + p * 50 * f)

        surf.fill((0, 0, 0))
        surf.blit(self.sky, (0, int(hy(1.0)) - self.SKY_H))
        stars.draw(surf, 0.9, ymax=max(40.0, hy(1.0) - 40))
        sun_x, sun_y = 690 - 30 * p, int(hy(1.0)) + 4
        surf.blit(sprites.glow(250, 6, (255, 140, 66)), (sun_x - 250, sun_y - 250),
                  special_flags=pygame.BLEND_RGB_ADD)
        surf.blit(sprites.glow(60, 9, (255, 214, 150)), (sun_x - 60, sun_y - 60),
                  special_flags=pygame.BLEND_RGB_ADD)
        surf.blit(self.far, (px(0.3), int(hy(1.0)) - self.far_top))
        surf.blit(self.haze, (0, int(hy(1.0)) - 136))
        surf.blit(self.mid, (px(0.6), int(hy(1.12)) + 10 - self.mid_top))
        surf.blit(self.near, (px(0.95), int(hy(1.25)) + 44 - self.near_top))
        surf.blit(self.ground, (px(1.3), int(hy(1.4)) + 112 - self.ground_top))
        if hy(1.4) + 112 - self.ground_top + self.ground.get_height() < H:
            surf.fill((120, 56, 38), (0, int(hy(1.4)) + 112 - self.ground_top + self.ground.get_height(),
                                      W, H))


# ------------------------------------------------------------ dust / air
class _Dust:
    def __init__(self, n=90):
        rng = random.Random(5)
        # x, y, vx, vy, size, alpha, phase
        self.p = [[rng.uniform(0, W), rng.uniform(0, H), rng.uniform(25, 95), rng.uniform(-6, 6),
                   rng.choice((1, 1, 2, 2, 3)), rng.uniform(0.25, 1.0), rng.uniform(0, 6.28)]
                  for _ in range(n)]
        self.puffs = []
        for r in (70, 100, 140):
            s = pygame.Surface((r * 2, r * 2), pygame.SRCALPHA)
            for i in range(r, 0, -3):
                a = int(22 * (1 - i / r) ** 1.5)
                pygame.draw.circle(s, (214, 140, 98, a), (r, r), i)
            self.puffs.append(s)
        self.clouds = [[rng.uniform(-100, W), rng.uniform(H * 0.45, H), rng.uniform(14, 40),
                        rng.randrange(3)] for _ in range(9)]
        self.t = 0.0

    def update(self, dt):
        self.t += dt
        for d in self.p:
            d[0] += d[2] * dt
            d[1] += d[3] * dt + math.sin(self.t * 0.8 + d[6]) * 6 * dt
            if d[0] > W + 4:
                d[0] = -4
                d[1] = random.uniform(0, H)
        for c in self.clouds:
            c[0] += c[2] * dt
            if c[0] > W + 160:
                c[0] = -160
                c[1] = random.uniform(H * 0.45, H)

    def draw(self, fx, k):
        if k <= 0.02:
            return
        for x, y, vx, vy, size, a, ph in self.p:
            al = int(110 * a * k * (0.6 + 0.4 * math.sin(self.t * 1.7 + ph)))
            if al > 3:
                fx.fill((226, 160, 112, al), (int(x), int(y), size, size))
        for x, y, vx, idx in self.clouds:
            pf = self.puffs[idx]
            pf.set_alpha(int(255 * k))
            fx.blit(pf, (int(x) - pf.get_width() // 2, int(y) - pf.get_height() // 2))


# ---------------------------------------------------------------- player
class _PlayerFade:
    """Draws the existing Player with an alpha (explorer appears at the reveal)."""

    def __init__(self, player):
        self.p = player
        self.alpha = 0.0

    @property
    def sort_y(self):
        return self.p.sort_y

    def draw(self, surf, cam):
        if self.alpha <= 0.01:
            return
        if self.alpha >= 0.99:
            self.p.draw(surf, cam)
            return
        tmp = pygame.Surface((120, 140), pygame.SRCALPHA)
        self.p.draw(tmp, pygame.Vector2(self.p.pos.x - 60, self.p.pos.y - 120))
        tmp.set_alpha(int(255 * self.alpha))
        surf.blit(tmp, (int(self.p.pos.x - 60 - cam.x), int(self.p.pos.y - 120 - cam.y)))


# ----------------------------------------------------------------- tutorial
class _Tutorial:
    def __init__(self):
        self.idx = 0
        self.tp = 0.0
        self.leaving = None            # seconds since the player confirmed
        self.finished = False
        self.layer = pygame.Surface((W, H), pygame.SRCALPHA)
        cap = sprites.draw_capsule()
        self.capsule = pygame.transform.scale(cap, (40, 68))
        self.panel = pygame.Rect(0, 0, 720, 350)
        self.panel.center = (W // 2, H // 2 - 5)

    def confirm(self):
        if self.leaving is None and self.tp > 0.9:
            self.leaving = 0.0

    def update(self, dt):
        self.tp += dt
        if self.leaving is not None:
            self.leaving += dt
            if self.leaving >= 0.5:
                self.idx += 1
                self.tp, self.leaving = 0.0, None
                if self.idx >= len(TUTORIAL):
                    self.finished = True

    def alpha(self):
        a = smooth(seg(self.tp, 0, 0.7))
        if self.leaving is not None:
            a *= 1 - smooth(self.leaving / 0.5)
        return a

    @staticmethod
    def _key(surf, rect, label=None, arrow=None, lit=False):
        pygame.draw.rect(surf, (36, 100, 122) if lit else (16, 30, 42), rect, border_radius=6)
        pygame.draw.rect(surf, CYAN if lit else (50, 110, 130), rect, 2, border_radius=6)
        col = (235, 255, 255) if lit else CYAN
        if label:
            t = ui.font(32).render(label, True, col)
            surf.blit(t, t.get_rect(center=rect.center))
        else:
            cx, cy = rect.center
            pts = {"up": [(cx, cy - 9), (cx - 9, cy + 7), (cx + 9, cy + 7)],
                   "down": [(cx, cy + 9), (cx - 9, cy - 7), (cx + 9, cy - 7)],
                   "left": [(cx - 9, cy), (cx + 7, cy - 9), (cx + 7, cy + 9)],
                   "right": [(cx + 9, cy), (cx - 7, cy - 9), (cx - 7, cy + 9)]}[arrow]
            pygame.draw.polygon(surf, col, pts)

    def _cluster(self, surf, cx, top, kind, lit_idx):
        ks, gap = 48, 6
        cells = {"up": (1, 0), "left": (0, 1), "down": (1, 1), "right": (2, 1)}
        for n, name in enumerate(("up", "left", "down", "right")):
            gx, gy = cells[name]
            r = pygame.Rect(cx - (ks * 3 + gap * 2) // 2 + gx * (ks + gap), top + gy * (ks + gap), ks, ks)
            if kind == "wasd":
                self._key(surf, r, label={"up": "W", "left": "A", "down": "S", "right": "D"}[name],
                          lit=(n == lit_idx))
            else:
                self._key(surf, r, arrow=name, lit=(n == lit_idx))

    def draw(self, screen, t):
        if self.finished:
            return
        a = self.alpha()
        if a <= 0.01:
            return
        L = self.layer
        L.fill((0, 0, 0, 0))
        pr = self.panel
        ui.draw_panel(L, pr, 238)
        title, text = TUTORIAL[self.idx]
        ui.draw_title(L, title, pr.y + 22, 54)
        ui.draw_wrapped(L, text, 30, pygame.Rect(0, 0, pr.w - 100, 10), pr.y + 88)
        vy = pr.y + 190                      # visual area: pr.y+190 .. pr.y+290
        if self.idx == 0:
            lit = int(t * 1.6) % 4
            self._cluster(L, W // 2 - 175, vy, "wasd", lit)
            o = ui.font(30).render("or", True, DIM)
            L.blit(o, o.get_rect(center=(W // 2, vy + 75)))
            self._cluster(L, W // 2 + 175, vy, "arrows", lit)
        elif self.idx == 1:
            ui.draw_prompt(L, (W // 2, vy + 52), "Talk")
            sub = ui.font(24).render("E / SPACE  -  continue dialogue", True, DIM)
            L.blit(sub, sub.get_rect(center=(W // 2, vy + 82)))
        else:
            cx, cy = W // 2, vy + 44
            ring = int(30 + 8 * math.sin(t * 3))
            pygame.draw.circle(L, (80, 235, 255, 70), (cx, cy), ring + 14, 2)
            pygame.draw.circle(L, (80, 235, 255, 120), (cx, cy), ring, 2)
            L.blit(self.capsule, self.capsule.get_rect(center=(cx, cy)))
        last = self.idx == len(TUTORIAL) - 1
        if (pygame.time.get_ticks() // 500) % 2 == 0 and self.tp > 0.9:
            hint = ui.font(24).render("[E] Begin" if last else "[E] Continue", True, CYAN)
            L.blit(hint, (pr.right - hint.get_width() - 20, pr.bottom - 32))
        for i in range(len(TUTORIAL)):
            c = CYAN if i == self.idx else (50, 90, 105)
            pygame.draw.circle(L, c, (pr.centerx + (i - 1) * 22, pr.bottom - 22), 5)
        L.set_alpha(int(255 * a))
        screen.blit(L, (0, 0))


# -------------------------------------------------------------------- Intro
class Intro:
    def __init__(self, world, player, ghost, cam, on_finish):
        self.world, self.player, self.ghost = world, player, ghost
        self.on_finish = on_finish
        self.final_center = pygame.Vector2(cam.x + W / 2, cam.y + H / 2)
        self.done = False
        self.phase = "crawl"
        self.t = 0.0               # time inside the current phase
        self.total = 0.0

        self.stars = _Stars()
        self.crawl = _Crawl()
        self.vista = _Vista()
        self.dust = _Dust()
        self.tutorial = _Tutorial()
        self.vignette = sprites.make_vignette(W, H)
        self.buf = pygame.Surface((W, H))
        self.fx = pygame.Surface((W, H), pygame.SRCALPHA)
        self.pfade = _PlayerFade(player)

        self.crawl_end = CRAWL_START + self.crawl.duration + STARS_OUT + 0.8
        self.gather = []           # [angle, radius, life, age, size, spin]
        self.burst = []            # [x, y, vx, vy, life, age, size]
        self.kick = []             # screen dust kicked up at the awakening
        self.woke = False
        self.ring_t = None
        self.flash = 0.0
        self.rv = (0.0, 0.0, 0.0, 14.0)    # body, aura, eye, offset
        self.pool = 1.0
        self.cam_f, self.zoom = (0.0, 0.0), 1.0
        self.bars = 0.0
        self.msg_cache = None
        self._dt = 0.0
        self._ghost_c = (0.0, 0.0)

    # ------------------------------------------------------------ control
    def finish(self):
        if self.done:
            return
        self.done = True
        self.on_finish()

    def handle_event(self, e):
        if self.done:
            return
        if e.type == pygame.KEYDOWN:
            if e.key == pygame.K_ESCAPE:
                self.finish()
            elif self.phase == "tutorial" and e.key in (pygame.K_e, pygame.K_SPACE, pygame.K_RETURN,
                                                         pygame.K_KP_ENTER):
                self.tutorial.confirm()
        elif e.type == pygame.MOUSEBUTTONDOWN and e.button == 1 and self.phase == "tutorial":
            self.tutorial.confirm()

    def _go(self, phase):
        self.phase, self.t = phase, 0.0

    # ------------------------------------------------------------- update
    def update(self, dt):
        if self.done:
            return
        self._dt = dt
        self.t += dt
        self.total += dt
        self.stars.update(dt)
        self.dust.update(dt)
        # let the Ghost's own animation clock/particles run; frozen=True keeps it in place
        self.ghost.update(dt, self.player.pos, True)
        self.player.update(dt, pygame.Vector2(), [])
        self._tick_effects(dt)

        if self.phase == "crawl":
            if self.t >= self.crawl_end:
                self._go("vista")
        elif self.phase == "vista":
            self.bars = smooth(seg(self.t, 0.2, 1.6))
            if self.t >= VISTA_T:
                self._go("awaken")
        elif self.phase == "awaken":
            self._awaken_state(self.t)
            if self.t >= A_END:
                self._go("reveal")
        elif self.phase == "reveal":
            self.rv = (1.0, 1.0, 0.0, 0.0)
            self.bars = 1.0 - smooth(seg(self.t, 0.0, 1.4))
            self.pfade.alpha = smooth(seg(self.t, 1.6, 3.6))
            self.pool = 1.0 - smooth(seg(self.t, 0.5, 4.2))
            if self.t >= REVEAL_T:
                self._go("tutorial")
        elif self.phase == "tutorial":
            self.rv = (1.0, 1.0, 0.0, 0.0)
            self.pool, self.bars, self.pfade.alpha = 0.0, 0.0, 1.0
            self.tutorial.update(dt)
            if self.tutorial.finished:
                self.finish()

    def _tick_effects(self, dt):
        ghost_c = (self.ghost.pos.x, self.ghost.pos.y - 24)
        for g in self.gather:
            g[3] += dt
        self.gather = [g for g in self.gather if g[3] < g[2]]
        for b in self.burst:
            b[0] += b[2] * dt
            b[1] += b[3] * dt
            b[2] *= 1 - 1.8 * dt
            b[3] *= 1 - 1.8 * dt
            b[5] += dt
        self.burst = [b for b in self.burst if b[5] < b[4]]
        for k in self.kick:
            k[0] += k[2] * dt
            k[1] += k[3] * dt
            k[2] *= 1 - 1.4 * dt
            k[3] *= 1 - 1.4 * dt
            k[4] += dt
        self.kick = [k for k in self.kick if k[4] < k[5]]
        if self.ring_t is not None:
            self.ring_t += dt
            if self.ring_t > 2.0:
                self.ring_t = None
        self.flash = max(0.0, self.flash - dt * 2.2)
        self._ghost_c = ghost_c

    # ---------------------------------------------- awakening choreography
    def _awaken_state(self, t):
        # body opacity: barely visible -> flickering -> fully revealed
        if t < T_WAKE:
            body = 0.035 + 0.075 * smooth(seg(t, 0, T_WAKE))
            for b in (3.2, 5.6, 7.1, 8.3, 9.4, 10.3):
                body += 0.11 * math.exp(-((t - b) / 0.11) ** 2)
        else:
            body = 0.11 + 0.89 * smooth(seg(t, T_WAKE, T_WAKE + 2.8))
        # glow around the body
        if t < T_WAKE:
            aura = 0.5 * smooth(seg(t, 5.0, T_WAKE))
        else:
            aura = lerp(0.5, 1.0, smooth(seg(t, T_WAKE, T_WAKE + 1.6)))
        # eyes: stutter on, flare, settle back to the sprite's own eye light
        eye = 0.0
        for start, dur, peak in ((9.0, 0.28, 0.5), (9.7, 0.22, 0.7), (10.25, 0.4, 0.95)):
            if start <= t < start + dur:
                eye = max(eye, peak * math.sin(math.pi * (t - start) / dur))
        if t >= 10.9:
            eye = max(eye, smooth(seg(t, 10.9, 12.2)))
        if t >= 13.0:
            eye *= 1 - smooth(seg(t, 13.0, 19.0))
        # lift: sunk in the dust, then a springy rise as it wakes
        if t < T_WAKE:
            off = 14 + 1.1 * math.sin(t * 23) * smooth(seg(t, 9.0, T_WAKE))
        else:
            tau = t - T_WAKE
            off = 14 * math.exp(-2.0 * tau) * math.cos(4.4 * tau)
        self.rv = (clamp(body), aura, clamp(eye), off)
        self.pool = 1.0

        # particles gather toward the body, spiralling in
        rate = 26 * smooth(seg(t, 1.0, 9.0)) if t < T_WAKE else 20 * (1 - smooth(seg(t, T_WAKE, T_WAKE + 3)))
        n = rate * self._dt
        while n > 0:
            if random.random() < min(1.0, n):
                life = random.uniform(2.2, 3.4)
                self.gather.append([random.uniform(0, 6.283), random.uniform(90, 175), life, 0.0,
                                    random.choice((3, 3, 4, 5)), random.uniform(-1.6, 1.6)])
            n -= 1
        # awakening moment
        if not self.woke and t >= T_WAKE:
            self.woke = True
            self.ring_t = 0.0
            self.flash = 1.0
            cx, cy = self._ghost_c
            for _ in range(38):
                a = random.uniform(0, 6.283)
                sp = random.uniform(40, 150)
                self.burst.append([cx, cy, math.cos(a) * sp, math.sin(a) * sp * 0.6,
                                   random.uniform(1.0, 1.8), 0.0, random.choice((3, 4, 5))])
            gx = (self.ghost.pos.x - self.cam_f[0]) * self.zoom
            gy = (self.ghost.pos.y - self.cam_f[1]) * self.zoom
            for _ in range(46):
                a = random.uniform(0, 6.283)
                sp = random.uniform(30, 120)
                self.kick.append([gx + random.uniform(-40, 40), gy + random.uniform(-8, 8),
                                  math.cos(a) * sp * 1.4, math.sin(a) * sp * 0.4,
                                  0.0, random.uniform(1.8, 3.2), random.choice((2, 3, 4))])

    def _awaken_view(self, t):
        if t < 17:
            z = lerp(1.35, 1.55, ease(seg(t, 0, 17)))
        else:
            z = lerp(1.55, 1.30, ease(seg(t, 17, A_END)))
        c = pygame.Vector2(self.ghost.pos.x, self.ghost.pos.y - 26)
        c.x += 5 * math.sin(t * 0.37)
        c.y += 4 * math.sin(t * 0.29) + 34 * smooth(seg(t, 17, 23))
        return z, c

    # --------------------------------------------------------------- draw
    def draw(self, screen):
        ph = self.phase
        if ph == "crawl":
            screen.fill((0, 0, 0))
            text_end = CRAWL_START + self.crawl.duration
            a = smooth(seg(self.t, 0, STARS_IN)) * (1 - smooth(seg(self.t, text_end, text_end + STARS_OUT)))
            self.stars.draw(screen, a)
            self.crawl.draw(screen, self.t - CRAWL_START)
        elif ph == "vista":
            self._draw_vista(screen)
        elif ph in ("awaken", "reveal", "tutorial"):
            if ph == "awaken":
                z, c = self._awaken_view(self.t)
                grade = _grade_at(self.t)
            elif ph == "reveal":
                z0, c0 = self._awaken_view(A_END)
                x = ease(seg(self.t, 0, 4.2))
                z = lerp(z0, 1.0, x)
                c = c0 + (self.final_center - c0) * x
                grade = lerp_col(_grade_at(A_END), WHITE, smooth(seg(self.t, 0.5, 4.2)))
                if x >= 1.0:
                    c = pygame.Vector2(self.final_center)
            else:
                z, c, grade = 1.0, pygame.Vector2(self.final_center), WHITE
            self._render_world(c, z, grade)
            screen.blit(self.buf, (0, 0))
            self._draw_air(screen, 0.9 if ph == "awaken" else 0.55)
            if ph == "awaken" and self.flash > 0:
                v = int(54 * self.flash)
                screen.fill((int(v * 0.55), int(v * 0.95), v), special_flags=pygame.BLEND_RGB_ADD)
        if ph != "crawl":
            screen.blit(self.vignette, (0, 0))
        if ph == "awaken":
            self._draw_message(screen)
        self._bars(screen)
        if ph == "tutorial":
            self.tutorial.draw(screen, self.total)
        self._skip_hint(screen)

    # -- vista
    def _draw_vista(self, screen):
        t = self.t
        p = ease(seg(t, 0, VISTA_T))
        self.vista.draw(screen, p, self.stars)
        bright = smooth(seg(t, 0.3, 4.0))
        dusk = lerp_col(WHITE, DORMANT_GRADE, smooth(seg(p, 0.50, 1.0)))
        g = tuple(int(c * bright) for c in dusk)
        screen.fill(g, special_flags=pygame.BLEND_RGB_MULT)
        self._draw_air(screen, bright * (0.5 + 0.5 * p))
        xf = smooth(seg(t, VISTA_T - VISTA_XFADE, VISTA_T))
        if xf > 0:
            z, c = self._awaken_view(0.0)
            self._render_world(c, z, DORMANT_GRADE)
            self.buf.set_alpha(int(255 * xf))
            screen.blit(self.buf, (0, 0))
            self.buf.set_alpha(255)

    def _draw_air(self, screen, k):
        fx = self.fx
        fx.fill((0, 0, 0, 0))
        self.dust.draw(fx, k)
        for x, y, vx, vy, age, life, size in self.kick:
            a = int(150 * (1 - age / life) ** 1.3)
            if a > 3:
                fx.fill((214, 146, 104, a), (int(x), int(y), size, size))
        if self.ring_t is not None and self.phase == "awaken":
            z = self.zoom
            gx, gy = self.ghost.pos.x - self.cam_f[0], self.ghost.pos.y - self.cam_f[1]
            r = int(lerp(14, 300, ease(self.ring_t / 1.8)) * z)
            a = int(200 * (1 - clamp(self.ring_t / 1.8)) ** 1.5)
            if a > 3 and r > 2:
                rect = pygame.Rect(0, 0, r * 2, int(r * 0.9))
                rect.center = (int(gx * z), int((gy - 4) * z))
                pygame.draw.ellipse(fx, (150, 245, 255, a), rect, 3)
        screen.blit(fx, (0, 0))

    # -- world view with sub-pixel camera and zoom
    def _render_world(self, center, zoom, grade):
        vw, vh = W / zoom, H / zoom
        cx = clamp(center.x - vw / 2, 0, MAP_W - vw - 4)
        cy = clamp(center.y - vh / 2, 0, MAP_H - vh - 4)
        ix, iy = int(math.floor(cx)), int(math.floor(cy))
        fx, fy = cx - ix, cy - iy
        iw, ih = int(math.ceil(vw)) + 2, int(math.ceil(vh)) + 2
        view = pygame.Surface((iw, ih))
        view.blit(self.world.ground, (0, 0), pygame.Rect(ix, iy, iw, ih))
        cam = pygame.Vector2(ix, iy)
        for d in sorted(list(self.world.props) + [self.pfade], key=lambda d: d.sort_y):
            d.draw(view, cam)
        if grade != WHITE:
            view.fill(grade, special_flags=pygame.BLEND_RGB_MULT)
        self._draw_rover(view, cam)
        if 0.02 < self.pfade.alpha < 0.98:
            lvl = int(5 * math.sin(math.pi * self.pfade.alpha))
            if lvl >= 1:
                view.blit(sprites.glow(64, lvl), (int(self.player.pos.x - cam.x - 64),
                                                  int(self.player.pos.y - cam.y - 80)),
                          special_flags=pygame.BLEND_RGB_ADD)
        if abs(zoom - 1.0) < 1e-4 and fx == 0 and fy == 0:
            self.buf.blit(view, (0, 0))
        else:
            sw, sh = int(round(iw * zoom)), int(round(ih * zoom))
            self.buf.blit(pygame.transform.smoothscale(view, (sw, sh)),
                          (int(round(-fx * zoom)), int(round(-fy * zoom))))
        self.cam_f, self.zoom = (cx, cy), zoom

    # -- the Ghost Rover (existing sprite frames; mirrors Ghost.draw at full strength)
    def _draw_rover(self, view, cam):
        g = self.ghost
        body, aura, eye, off = self.rv
        add = pygame.BLEND_RGB_ADD
        sx, sy = g.pos.x - cam.x, g.pos.y - cam.y
        t = g.t
        pulse = 0.5 + 0.5 * math.sin(t * 3)
        bob = math.sin(t * 2.2) * 4 * min(1.0, body * 1.6)
        if aura > 0.03:
            lvl = int(round(4 * aura * self.pool))
            if lvl >= 1:
                view.blit(sprites.glow(190, lvl), (int(sx - 190), int(sy - 180)), special_flags=add)
            lvl = int(round((3 + pulse * 2) * aura))
            if lvl >= 1:
                view.blit(sprites.glow(95, lvl), (int(sx - 95), int(sy - 115 + off * 0.5)), special_flags=add)
            for p in g.particles:
                lv = max(1, int(p[4] / p[5] * 10 * aura))
                r = p[6]
                view.blit(sprites.glow(r, lv), (int(p[0] - cam.x - r), int(p[1] - cam.y - r)), special_flags=add)
        # gathering motes: spiral into the body
        cx, cy = sx, sy - 24
        for a0, r0, life, age, size, spin in self.gather:
            k = age / life
            r = r0 * (1 - k) ** 1.6
            a = a0 + spin * k
            lv = int(8 * min(1.0, k * 5) * min(1.0, (1 - k) * 4))
            if lv >= 1:
                view.blit(sprites.glow(size, lv), (int(cx + math.cos(a) * r - size),
                                                   int(cy + math.sin(a) * r * 0.65 - size)), special_flags=add)
        for x, y, vx, vy, life, age, size in self.burst:
            lv = int(9 * (1 - age / life))
            if lv >= 1:
                view.blit(sprites.glow(size, lv), (int(x - cam.x - size), int(y - cam.y - size)), special_flags=add)
        img = g.frames[g.facing_right][0]
        bx = int(sx - img.get_width() / 2)
        by = int(sy - img.get_height() / 2 - 24 + bob + off)
        if body > 0.01:
            flicker = 0.55 if random.random() < 0.04 else 1.0
            if body < 0.9 and random.random() < 0.07:
                flicker *= 0.25
            a = (175 + 30 * math.sin(t * 6)) * flicker * body
            if body < 0.97:        # shimmering ghost-echo while it is still materialising
                img.set_alpha(int(min(255, a * 0.4)))
                view.blit(img, (bx + int(3 * math.sin(t * 17)), by - 1))
            img.set_alpha(int(min(255, a)))
            view.blit(img, (bx, by))
        lvl = int(round(4 * aura))
        if lvl >= 1:
            view.blit(sprites.glow(46, lvl), (int(sx - 46), int(sy - 24 + bob + off - 46)), special_flags=add)
        if eye > 0.02:
            ex = bx + (56 if g.facing_right else 12)
            ey = by + 23
            view.blit(sprites.glow(32, max(1, int(round(9 * eye)))), (ex - 32, ey - 32), special_flags=add)
            v = int(255 * eye)
            view.fill((v, v, v), (ex - 2, ey - 2, 4, 4), special_flags=add)

    # -- overlays
    def _draw_message(self, screen):
        t = self.t - MSG_START
        if t < 0 or t > MSG_IN + MSG_HOLD + MSG_OUT:
            return
        a = smooth(seg(t, 0, MSG_IN)) * (1 - smooth(seg(t, MSG_IN + MSG_HOLD, MSG_IN + MSG_HOLD + MSG_OUT)))
        if self.msg_cache is None:
            f = ui.font(46)
            self.msg_cache = [(f.render(s, True, (225, 245, 250)), f.render(s, True, (0, 0, 0)))
                              for s in OPENING_LINES]
        y = H - BAR_H - 120
        for img, shadow in self.msg_cache:
            for im, dx in ((shadow, 2), (img, 0)):
                im.set_alpha(int(255 * a))
                screen.blit(im, im.get_rect(midtop=(W // 2 + dx, y + dx)))
            y += 46

    def _bars(self, screen):
        h = int(BAR_H * self.bars)
        if h > 0:
            screen.fill((0, 0, 0), (0, 0, W, h))
            screen.fill((0, 0, 0), (0, H - h, W, h))

    def _skip_hint(self, screen):
        a = smooth(seg(self.total, 1.0, 2.0))
        if a <= 0.01:
            return
        img = ui.font(22).render("ESC  Skip", True, DIM)
        img.set_alpha(int(190 * a))
        screen.blit(img, (W - img.get_width() - 16, H - img.get_height() - 12 - int(BAR_H * self.bars * 0.5)))
