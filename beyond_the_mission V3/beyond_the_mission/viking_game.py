"""Viking 1 & 2 minigame - PHOTO FROM MEMORY (Game 5).

Visual-memory challenge. Study a photograph from a Viking lander, watch the
transmission corrupt and break into fragments, then rebuild the photo from
memory. Three rounds with growing fragment counts and shrinking preview time
(there is NO fail state / time-out - only the preview is timed).

Plugs into the existing challenge interface (same as Insight / Ingenuity):
    VikingChallenge(eq)  ->  handle_event(e) returns "done" only on victory
                             (EncounterScene then runs the Memory Capsule flow),
                             update(dt), draw(surf), title attribute.

Photographs: if the files listed in PHOTO_PATHS exist under assets/ they are
used (any size - they are cover-cropped to PHOTO_W x PHOTO_H, never stretched).
Otherwise a procedural Viking-style Martian photograph is painted, so no
external assets or extra dependencies are required.
"""
import math
import random

import pygame

import assets
import ui
from settings import SCREEN_W, SCREEN_H, CYAN, TEXT, DIM

# --------------------------------------------------------------------- config
# Drop your own photographs at these paths (relative to assets/) to replace the
# procedural ones. Each should show a different scene, hardest one last.
PHOTO_PATHS = ["viking/photo_1.png", "viking/photo_2.png", "viking/photo_3.png"]

PHOTO_W, PHOTO_H = 540, 360     # every photo is shown at exactly this size
# cols/rows MUST divide PHOTO_W / PHOTO_H evenly so tiles are identical in size
# (required for clean swaps and zero distortion) - asserted below.
ROUNDS = [
    dict(name="FAMILIAR GROUND", level="INTRO", cols=3, rows=3, preview=25.0),
    dict(name="DISTANT HORIZON", level="DETAILED", cols=5, rows=4, preview=20.0),
    dict(name="FINAL TRANSMISSION", level="EXTREME", cols=6, rows=5, preview=16.0),
]
for _r in ROUNDS:
    assert PHOTO_W % _r["cols"] == 0 and PHOTO_H % _r["rows"] == 0

GLITCH_CORRUPT = 0.9     # seconds: photo corrupts (slices, colour split)
GLITCH_SCATTER = 1.0     # seconds: fragments fly to their shuffled slots
CLEAR_TIME = 2.8         # success banner before the next photograph
LOW_TIME = 5.0
DRAG_THRESHOLD = 6

AMBER = (255, 176, 64)
RED = (255, 80, 70)
GREEN = (110, 255, 170)
BOARD_BG = (6, 9, 14)

BOARD = pygame.Rect(64, 110, PHOTO_W, PHOTO_H)
SIDE = pygame.Rect(640, 110, 256, PHOTO_H)
RESTART_RECT = pygame.Rect(SIDE.x + 16, SIDE.bottom - 50, SIDE.w - 32, 34)


# ------------------------------------------------------------ pure game logic
def make_shuffle(n, rng):
    """slots[i] = piece shown in slot i (piece p belongs in slot p).
    Any permutation is solvable with swaps. Never returns the solved layout and
    keeps accidental fixed points low so the start is genuinely scrambled."""
    max_fixed = max(0, n // 5)
    for _ in range(300):
        slots = list(range(n))
        rng.shuffle(slots)
        fixed = sum(1 for i, p in enumerate(slots) if i == p)
        if fixed <= max_fixed and slots != list(range(n)):
            return slots
    return [(i + max(1, n // 2)) % n for i in range(n)]   # fallback: zero fixed points


def aligned_count(slots):
    return sum(1 for i, p in enumerate(slots) if i == p)


def is_solved(slots):
    return slots == list(range(len(slots)))


def slot_at(pos, cols, rows):
    """Slot index under screen position `pos` (None if outside the board)."""
    if not BOARD.collidepoint(pos):
        return None
    tw, th = PHOTO_W // cols, PHOTO_H // rows
    c = min(cols - 1, (pos[0] - BOARD.x) // tw)
    r = min(rows - 1, (pos[1] - BOARD.y) // th)
    return int(r * cols + c)


def fmt_time(s):
    s = int(s)
    return f"{s // 60}:{s % 60:02d}"


# ----------------------------------------------- procedural Martian photographs
def _mix(c1, c2, k):
    return tuple(int(c1[i] + (c2[i] - c1[i]) * k) for i in range(3))


def _shade(c, f):
    return tuple(max(0, min(255, int(v * f))) for v in c)


def _grad(surf, y0, y1, c0, c1, w):
    for y in range(y0, y1):
        k = (y - y0) / max(1, y1 - y0 - 1)
        pygame.draw.line(surf, _mix(c0, c1, k), (0, y), (w, y))


def _ridge(w, base, amp, rng):
    p = [rng.uniform(0, 6.28) for _ in range(3)]
    f = [rng.uniform(0.8, 1.6), rng.uniform(2.2, 3.6), rng.uniform(5, 8)]
    pts = []
    for x in range(0, w + 8, 6):
        u = x / w
        y = base - amp * (0.5 * math.sin(6.28 * f[0] * u + p[0]) + 0.3 * math.sin(6.28 * f[1] * u + p[1])
                          + 0.2 * math.sin(6.28 * f[2] * u + p[2])) + rng.uniform(-1.5, 1.5)
        pts.append((x, y))
    return pts


def _noise(w, h, lo, hi, rng):
    s = pygame.Surface((w, h))
    for y in range(h):
        for x in range(w):
            v = rng.randint(lo, hi)
            s.set_at((x, y), (v, v, v))
    return s


def _scale_pts(pts, cx, cy, s, dx, dy):
    return [(cx + (x - cx) * s + dx, cy + (y - cy) * s + dy) for x, y in pts]


def _rock_pts(cx, cy, r, rng):
    n = rng.randint(7, 10)
    ry = r * rng.uniform(0.5, 0.78)
    return [(cx + math.cos(6.283 * i / n) * r * rng.uniform(0.8, 1.12),
             cy + math.sin(6.283 * i / n) * ry * rng.uniform(0.8, 1.12)) for i in range(n)], ry


def _draw_rock(surf, pts, cx, cy, r, ry, tone, rng, pits=0):
    pygame.draw.polygon(surf, _shade(tone, 0.55), pts)
    pygame.draw.polygon(surf, tone, _scale_pts(pts, cx, cy, 0.88, -0.08 * r, -0.14 * ry))
    pygame.draw.polygon(surf, _shade(tone, 1.28), _scale_pts(pts, cx, cy, 0.5, -0.28 * r, -0.4 * ry))
    pygame.draw.polygon(surf, _shade(tone, 0.35), pts, 1)
    for _ in range(pits):
        px, py = cx + rng.uniform(-0.6, 0.6) * r, cy + rng.uniform(-0.4, 0.4) * ry
        pygame.draw.ellipse(surf, _shade(tone, 0.4), (px, py, rng.uniform(4, 10), rng.uniform(3, 6)))


def make_photo(spec, w, h):
    """Paint one Viking-style Martian surface photograph (butterscotch sky,
    rust soil, rocks, haze, grain). Deterministic for a given spec seed."""
    rng = random.Random(spec["seed"])
    surf = pygame.Surface((w, h))
    hz = int(h * spec["horizon"])
    _grad(surf, 0, hz + 1, spec["sky_top"], spec["sky_hz"], w)

    def overlay():
        return pygame.Surface((w, h), pygame.SRCALPHA)

    if spec.get("sun"):                                        # sun glow in the sky
        ov = overlay()
        sx, sy = int(spec["sun"][0] * w), int(spec["sun"][1] * h)
        for r in range(110, 0, -5):
            pygame.draw.circle(ov, (255, 224, 176, 7 + (110 - r) // 9), (sx, sy), r)
        pygame.draw.circle(ov, (255, 246, 220, 200), (sx, sy), 9)
        surf.blit(ov, (0, 0))
    ov = overlay()                                             # thin cloud streaks
    for _ in range(spec.get("clouds", 6)):
        cx, cy = rng.randint(0, w), rng.randint(6, max(8, hz - 30))
        pygame.draw.ellipse(ov, (255, 225, 195, 38), (cx - 90, cy, rng.randint(90, 220), rng.randint(5, 11)))
    surf.blit(ov, (0, 0))

    if spec.get("crater"):                                     # distant crater rim
        cx = int(spec["crater"] * w)
        pygame.draw.ellipse(surf, (176, 120, 96), (cx - 110, hz - 20, 220, 40))
        pygame.draw.ellipse(surf, (132, 84, 68), (cx - 90, hz - 14, 180, 30))
        pygame.draw.arc(surf, (214, 156, 118), (cx - 110, hz - 20, 220, 40), 0.2, 2.9, 2)

    for off, amp, col in spec["hills"]:                        # far -> near ridges
        pts = _ridge(w, hz - off, amp, rng)
        pygame.draw.polygon(surf, col, pts + [(w, hz + 6), (0, hz + 6)])

    _grad(surf, hz, h, spec["ground_far"], spec["ground_near"], w)
    tex = pygame.transform.smoothscale(_noise(w // 5, (h - hz) // 5 + 1, 165, 255, rng), (w, h - hz))
    surf.blit(tex, (0, hz), special_flags=pygame.BLEND_RGB_MULT)

    gy = lambda f: hz + 8 + f * (h - hz - 14)                  # perspective: f 0 far .. 1 near
    ov = overlay()
    if spec.get("dunes"):                                      # low dune ripples
        for k in range(7):
            y = gy(0.06 + 0.14 * k + rng.uniform(-0.02, 0.02))
            x = rng.randint(-120, w - 160)
            ww, hh = rng.randint(260, 420), int(10 + 16 * k / 2)
            pygame.draw.ellipse(ov, (80, 40, 26, 46), (x, y, ww, hh))
            pygame.draw.arc(ov, (240, 180, 130, 90), (x, y, ww, hh), 0.15, 3.0, 2)
    for _ in range(spec.get("streaks", 0)):                    # wind streaks
        y = gy(rng.random())
        x = rng.randint(0, w - 40)
        pygame.draw.line(ov, (255, 205, 160, 44), (x, y), (x + rng.randint(40, 170), y + rng.randint(-2, 2)), 2)
        pygame.draw.line(ov, (70, 34, 22, 40), (x, y + 3), (x + rng.randint(30, 120), y + 3), 1)
    surf.blit(ov, (0, 0))

    if spec.get("trench"):                                     # sampler-arm trench
        x0, y0 = int(w * 0.10), int(h * 0.80)
        for i in range(4):
            ox, oy = x0 + i * 16, y0 + i * 3
            pygame.draw.polygon(surf, (74, 40, 28), [(ox, oy), (ox + 130, oy - 12), (ox + 140, oy + 6), (ox + 8, oy + 22)])
            pygame.draw.line(surf, (216, 156, 116), (ox, oy), (ox + 130, oy - 12), 2)
            pygame.draw.line(surf, (40, 20, 14), (ox + 8, oy + 22), (ox + 140, oy + 6), 2)

    rocks = []                                                 # perspective-scaled scatter
    for _ in range(spec["rocks"]):
        f = rng.random() ** 0.8
        y = gy(f)
        r = rng.uniform(7, 24) * (0.3 + 1.15 * f)
        rocks.append((y, rng.randint(8, w - 8), r, rng.choice(spec["tones"])))
    rocks.sort()
    ov = overlay()
    for y, x, r, _t in rocks:                                  # shadows first
        pygame.draw.ellipse(ov, (46, 20, 12, 105), (x - r * 0.3, y - r * 0.1, r * 2.0, r * 0.75))
    big = spec.get("bigrock")
    if big:
        bx, by, br = int(big[0] * w), int(big[1] * h), big[2]
        pygame.draw.ellipse(ov, (46, 20, 12, 120), (bx - br * 0.3, by - br * 0.05, br * 2.2, br * 0.95))
    surf.blit(ov, (0, 0))
    for y, x, r, tone in rocks:
        pts, ry = _rock_pts(x, y, r, rng)
        _draw_rock(surf, pts, x, y, r, ry, tone, rng)
    if big:                                                    # "Big Joe"-style boulder
        pts, ry = _rock_pts(bx, by, br, rng)
        _draw_rock(surf, pts, bx, by, br, ry, spec["tones"][0], rng, pits=9)

    if spec.get("lander"):                                     # footpad + strut in foreground
        cx, cy = int(w * 0.84), int(h * 0.88)
        pygame.draw.ellipse(surf, (150, 88, 60), (cx - 96, cy - 16, 192, 46))
        pygame.draw.line(surf, (70, 70, 78), (cx - 4, cy - 4), (cx - 58, cy - 190), 11)
        pygame.draw.line(surf, (150, 150, 158), (cx - 8, cy - 4), (cx - 62, cy - 190), 3)
        pygame.draw.line(surf, (60, 60, 68), (cx + 8, cy - 4), (cx + 52, cy - 120), 6)
        pygame.draw.ellipse(surf, (88, 88, 96), (cx - 70, cy - 20, 140, 40))
        pygame.draw.ellipse(surf, (172, 172, 178), (cx - 62, cy - 18, 124, 32))
        pygame.draw.ellipse(surf, (122, 122, 130), (cx - 40, cy - 12, 80, 20))
    if spec.get("chart"):                                      # colour calibration chart
        px, py = int(w * 0.60), int(h * 0.56)
        pygame.draw.line(surf, (50, 50, 56), (px + 27, py + 36), (px + 27, py + 62), 4)
        pygame.draw.rect(surf, (28, 28, 34), (px, py, 54, 36))
        for i, col in enumerate([(220, 60, 50), (60, 190, 90), (60, 100, 220),
                                 (240, 210, 70), (235, 235, 235), (110, 110, 118)]):
            pygame.draw.rect(surf, col, (px + 4 + (i % 3) * 16, py + 4 + (i // 3) * 15, 14, 13))

    ov = overlay()                                             # dust haze at the horizon
    for i in range(46):
        pygame.draw.line(ov, (*spec["sky_hz"], int(110 * (1 - i / 46) ** 1.5)), (0, hz - 6 + i), (w, hz - 6 + i))
    surf.blit(ov, (0, 0))

    ov = overlay()                                             # vignette + scanlines
    for i in range(40):
        pygame.draw.rect(ov, (0, 0, 0, int(120 * (1 - i / 40) ** 2)), pygame.Rect(i, i, w - 2 * i, h - 2 * i), 1)
    for y in range(0, h, 3):
        pygame.draw.line(ov, (0, 0, 0, 24), (0, y), (w, y))
    surf.blit(ov, (0, 0))
    grain = pygame.transform.smoothscale(_noise(w // 3, h // 3, 0, 26, rng), (w, h))
    surf.blit(grain, (0, 0), special_flags=pygame.BLEND_RGB_ADD)

    f = ui.font(20)                                            # camera data stamp
    t = f.render(spec["caption"], True, (240, 230, 210))
    pygame.draw.rect(surf, (12, 8, 8), (8, h - 30, t.get_width() + 14, 22))
    surf.blit(t, (15, h - 27))
    return surf


PHOTO_SPECS = [
    dict(seed=11, horizon=0.44, sky_top=(150, 118, 108), sky_hz=(232, 176, 134),
         ground_far=(204, 134, 90), ground_near=(152, 90, 56), sun=(0.18, 0.16), clouds=5,
         hills=[(10, 10, (178, 120, 98)), (3, 7, (192, 128, 94))], rocks=16, streaks=10,
         tones=[(150, 88, 60), (186, 112, 76), (112, 66, 50)],
         caption="VL-1  SOL 001  CHRYSE PLANITIA"),
    dict(seed=29, horizon=0.36, sky_top=(138, 106, 112), sky_hz=(226, 166, 130),
         ground_far=(190, 122, 82), ground_near=(140, 82, 54), sun=(0.82, 0.15), clouds=8,
         crater=0.68, dunes=True, streaks=6,
         hills=[(34, 30, (150, 104, 98)), (22, 26, (164, 112, 96)), (12, 20, (178, 118, 92)),
                (4, 12, (192, 128, 92))],
         rocks=36, tones=[(150, 88, 60), (196, 126, 86), (104, 62, 48)],
         caption="VL-2  SOL 030  UTOPIA PLANITIA"),
    dict(seed=47, horizon=0.30, sky_top=(118, 92, 100), sky_hz=(214, 152, 116),
         ground_far=(178, 110, 72), ground_near=(120, 68, 44), clouds=10, crater=0.24,
         streaks=14, trench=True, lander=True, chart=True, bigrock=(0.36, 0.66, 66), dunes=True,
         hills=[(20, 22, (140, 98, 92)), (10, 16, (158, 106, 90)), (3, 9, (176, 114, 88))],
         rocks=54, tones=[(120, 70, 52), (176, 108, 74), (96, 58, 46), (208, 138, 98)],
         caption="VL-1  SOL 2245  FINAL TRANSMISSION"),
]


def fit_cover(img, w, h):
    """Scale to cover w x h then center-crop (aspect ratio preserved)."""
    iw, ih = img.get_size()
    if (iw, ih) == (w, h):
        return img.convert()
    s = max(w / iw, h / ih)
    sw, sh = max(w, math.ceil(iw * s)), max(h, math.ceil(ih * s))
    scaled = pygame.transform.smoothscale(img.convert(), (sw, sh))
    out = pygame.Surface((w, h))
    out.blit(scaled, (0, 0), pygame.Rect((sw - w) // 2, (sh - h) // 2, w, h))
    return out


# ---------------------------------------------------------------------- game
class VikingChallenge:
    title = "PHOTO FROM MEMORY"

    def __init__(self, eq=None, seed=None):
        self.eq = eq
        self.seed = seed
        self.photos = {}            # round index -> photo surface (built once, reused on retry)
        self.reset()

    # ------------------------------------------------------------ state reset
    def reset(self):
        """Full reset (construction and Restart): all rounds, all puzzle state."""
        self.rng = random.Random(self.seed)
        self.phase = "intro"        # intro|preview|glitch|rebuild|clear|victory
        self.t = 0.0
        self.round_i = 0
        self.results = []           # per completed round: dict(moves, time)
        self.slots, self.pos, self.tiles = [], [], []
        self.cols = self.rows = self.n = self.tw = self.th = 0
        self.photo = self.tint_r = self.tint_c = None
        self.time_left = 0.0
        self.moves = 0
        self.round_t = 0.0
        self._clear_interaction()
        self.restart_armed = 0.0
        self.mouse = (0, 0)
        self.buttons = ui.ButtonRow(["START"], 428)
        self.end_buttons = None

    def _clear_interaction(self):
        self.sel = None
        self.drag = None            # dict(slot, grab, active, deselect)
        self.hover = None
        self.flash = {}

    def _set_phase(self, p):
        self.phase, self.t = p, 0.0

    # ------------------------------------------------------------ round setup
    def _get_photo(self, i):
        if i not in self.photos:
            spec = PHOTO_SPECS[i]
            img = assets.load_image(PHOTO_PATHS[i], lambda: make_photo(spec, PHOTO_W, PHOTO_H))
            self.photos[i] = fit_cover(img, PHOTO_W, PHOTO_H)
        return self.photos[i]

    def _slot_xy(self, i):
        return BOARD.x + (i % self.cols) * self.tw, BOARD.y + (i // self.cols) * self.th

    def _begin_round(self, i):
        spec = ROUNDS[i]
        self.round_i = i
        self.cols, self.rows = spec["cols"], spec["rows"]
        self.n = self.cols * self.rows
        self.tw, self.th = PHOTO_W // self.cols, PHOTO_H // self.rows
        self.photo = self._get_photo(i)
        self.tiles = [self.photo.subsurface(pygame.Rect((p % self.cols) * self.tw, (p // self.cols) * self.th,
                                                        self.tw, self.th)) for p in range(self.n)]
        self.tint_r = self.photo.copy()
        self.tint_r.fill((255, 70, 70), special_flags=pygame.BLEND_RGB_MULT)
        self.tint_c = self.photo.copy()
        self.tint_c.fill((60, 255, 255), special_flags=pygame.BLEND_RGB_MULT)
        self.slots = make_shuffle(self.n, self.rng)
        self.pos = [list(self._slot_xy(p)) for p in range(self.n)]   # pieces start at home
        self._clear_interaction()
        self.moves = 0
        self.round_t = 0.0
        self.time_left = spec["preview"]
        self._set_phase("preview")

    def _begin_glitch(self):
        self._set_phase("glitch")

    def _begin_rebuild(self):
        for i, p in enumerate(self.slots):
            self.pos[p] = list(self._slot_xy(i))
        self.round_t = 0.0
        self._set_phase("rebuild")

    def _clear_round(self):
        self.results.append(dict(moves=self.moves, time=self.round_t))
        self._clear_interaction()
        self._set_phase("clear")

    def _next_round(self):
        if self.round_i + 1 < len(ROUNDS):
            self._begin_round(self.round_i + 1)
        else:
            self.end_buttons = ui.ButtonRow(["Replay", "Continue"], 438, w=220)
            self.end_buttons.sel = 1
            self._set_phase("victory")

    # ------------------------------------------------------------------ moves
    def _swap(self, a, b):
        if a == b:
            return
        self.slots[a], self.slots[b] = self.slots[b], self.slots[a]
        self.moves += 1
        self.flash[self.slots[a]] = 0.35
        self.flash[self.slots[b]] = 0.35
        if is_solved(self.slots):
            self._clear_round()

    def _dragging_piece(self, p):
        d = self.drag
        return bool(d and d["active"] and self.slots[d["slot"]] == p)

    # ------------------------------------------------------------------ input
    def handle_event(self, e):
        if self.phase == "intro":
            if self.buttons.handle_event(e) == 0:
                self._begin_round(0)
        elif self.phase == "preview":
            if self.t > 0.8 and ((e.type == pygame.KEYDOWN and e.key in (pygame.K_SPACE, pygame.K_RETURN,
                                                                         pygame.K_KP_ENTER, pygame.K_e)) or
                                 (e.type == pygame.MOUSEBUTTONDOWN and e.button == 1 and BOARD.collidepoint(e.pos))):
                self._begin_glitch()                       # player is ready: skip the rest of the preview
        elif self.phase == "rebuild":
            self._board_input(e)
        elif self.phase == "clear":
            if self.t > 0.6 and ((e.type == pygame.KEYDOWN and e.key in (pygame.K_SPACE, pygame.K_RETURN,
                                                                         pygame.K_KP_ENTER, pygame.K_e)) or
                                 (e.type == pygame.MOUSEBUTTONDOWN and e.button == 1)):
                self._next_round()
        elif self.phase == "victory":
            c = self.end_buttons.handle_event(e)
            if c == 1:
                return "done"                              # -> existing Memory Capsule flow
            if c == 0:
                self.reset()                               # replay = full reset
        return None

    def _board_input(self, e):
        if e.type == pygame.MOUSEMOTION:
            self.mouse = e.pos
            self.hover = slot_at(e.pos, self.cols, self.rows)
            d = self.drag
            if d and not d["active"]:
                sx, sy = d["start"]
                if abs(e.pos[0] - sx) > DRAG_THRESHOLD or abs(e.pos[1] - sy) > DRAG_THRESHOLD:
                    d["active"] = True
                    self.sel = None
        elif e.type == pygame.MOUSEBUTTONDOWN:
            self.mouse = e.pos
            if e.button == 3:                              # right click cancels
                self.sel, self.drag = None, None
                return
            if e.button != 1:
                return
            if RESTART_RECT.collidepoint(e.pos):
                if self.restart_armed > 0:
                    self.reset()
                else:
                    self.restart_armed = 2.0               # click again to confirm
                return
            s = slot_at(e.pos, self.cols, self.rows)
            if s is None:
                self.sel = None
                return
            if self.sel is not None and self.sel != s:     # click-click swap
                a, self.sel = self.sel, None
                self._swap(a, s)
                return
            x, y = self._slot_xy(s)
            self.drag = dict(slot=s, start=e.pos, grab=(e.pos[0] - x, e.pos[1] - y),
                             active=False, deselect=(self.sel == s))
        elif e.type == pygame.MOUSEBUTTONUP and e.button == 1 and self.drag:
            d, self.drag = self.drag, None
            if d["active"]:
                t = slot_at(e.pos, self.cols, self.rows)
                if t is not None and t != d["slot"]:
                    self._swap(d["slot"], t)
            else:
                self.sel = None if d["deselect"] else d["slot"]

    # ----------------------------------------------------------------- update
    def update(self, dt):
        dt = max(0.0, min(dt, 0.1))
        self.t += dt
        if self.phase == "preview":
            self.time_left = max(0.0, self.time_left - dt)
            if self.time_left <= 0.0:
                self._begin_glitch()
        elif self.phase == "glitch":
            if self.t >= GLITCH_CORRUPT + GLITCH_SCATTER:
                self._begin_rebuild()
        elif self.phase in ("rebuild", "clear"):
            if self.phase == "rebuild":
                self.round_t += dt
                self.restart_armed = max(0.0, self.restart_armed - dt)
            self._animate(dt)
            if self.phase == "clear" and self.t >= CLEAR_TIME:
                self._next_round()

    def _animate(self, dt):
        k = min(1.0, dt * 16)
        for i, p in enumerate(self.slots):
            if self._dragging_piece(p):
                gx, gy = self.drag["grab"]
                self.pos[p] = [self.mouse[0] - gx, self.mouse[1] - gy]
                continue
            tx, ty = self._slot_xy(i)
            q = self.pos[p]
            q[0] += (tx - q[0]) * k
            q[1] += (ty - q[1]) * k
            if abs(tx - q[0]) < 0.5 and abs(ty - q[1]) < 0.5:
                q[0], q[1] = tx, ty
        for p in list(self.flash):
            self.flash[p] -= dt
            if self.flash[p] <= 0:
                del self.flash[p]

    # ---------------------------------------------------------------- drawing
    def draw(self, surf):
        if self.phase == "intro":
            self._draw_intro(surf)
        elif self.phase == "victory":
            self._draw_victory(surf)
        else:
            self._draw_station(surf)

    def _draw_intro(self, surf):
        r = ui.center_panel(surf, 780, 470)
        ui.draw_title(surf, "PHOTO FROM MEMORY", r.y + 16, 58)
        ui.draw_title(surf, "Viking 1 & 2  -  Mars Surface Imaging", r.y + 72, 28, DIM)
        body = r.inflate(-110, 0)
        y = ui.draw_wrapped(surf, "Study each photograph from the Viking landers. The transmission will then "
                                  "corrupt and break into fragments. Rebuild the photograph from memory.",
                            28, body, r.y + 108)
        ui.draw_title(surf, "Click two fragments to swap them, or drag one onto another", y + 10, 26, AMBER)
        y += 52
        for i, rd in enumerate(ROUNDS):
            line = f"{i + 1}.  {rd['name']}  -  {rd['cols'] * rd['rows']} fragments  -  {int(rd['preview'])} s preview"
            ui.draw_title(surf, line, y + i * 30, 28, TEXT)
        ui.draw_title(surf, "No time limit while rebuilding", y + 100, 24, DIM)
        self.buttons.draw(surf)

    def _draw_header(self, surf):
        ui.draw_panel(surf, pygame.Rect(40, 26, 880, 488), 245)
        rd = ROUNDS[self.round_i]
        surf.blit(ui.font(32).render(f"ROUND {self.round_i + 1}/3  -  {rd['name']}", True, CYAN), (64, 40))
        surf.blit(ui.font(22).render(f"Difficulty: {rd['level']}   |   {self.n} fragments ({self.cols}x{self.rows})",
                                     True, DIM), (64, 70))
        for i in range(3):
            c = pygame.Rect(64 + i * 30, 92, 22, 10)
            if i < len(self.results):
                pygame.draw.rect(surf, CYAN, c)
            else:
                pygame.draw.rect(surf, AMBER if i == self.round_i else DIM, c, 2)
        f = ui.font(24).render("VIKING 1 & 2", True, DIM)
        surf.blit(f, f.get_rect(topright=(896, 42)))

    def _draw_frame(self, surf, col=CYAN):
        pygame.draw.rect(surf, col, BOARD.inflate(8, 8), 1)
        for (x, y, dx, dy) in ((BOARD.x - 4, BOARD.y - 4, 1, 1), (BOARD.right + 4, BOARD.y - 4, -1, 1),
                               (BOARD.x - 4, BOARD.bottom + 4, 1, -1), (BOARD.right + 4, BOARD.bottom + 4, -1, -1)):
            pygame.draw.line(surf, col, (x, y), (x + 16 * dx, y), 3)
            pygame.draw.line(surf, col, (x, y), (x, y + 16 * dy), 3)

    def _draw_station(self, surf):
        self._draw_header(surf)
        if self.phase == "preview":
            surf.blit(self.photo, BOARD.topleft)
            self._draw_frame(surf)
            bar = pygame.Rect(BOARD.x, BOARD.bottom + 12, BOARD.w, 8)
            frac = self.time_left / ROUNDS[self.round_i]["preview"]
            pygame.draw.rect(surf, BOARD_BG, bar)
            pygame.draw.rect(surf, RED if self.time_left <= LOW_TIME else AMBER, (bar.x, bar.y, int(bar.w * frac), bar.h))
            pygame.draw.rect(surf, (40, 60, 70), bar, 1)
            ui.draw_title(surf, "Memorize the photo, then press SPACE", BOARD.bottom + 28, 22, DIM)
        elif self.phase == "glitch":
            self._draw_glitch(surf)
            self._draw_frame(surf, RED if int(self.t * 10) % 2 == 0 else CYAN)
        elif self.phase == "rebuild":
            self._draw_board(surf)
            self._draw_frame(surf)
            ui.draw_title(surf, "Swap or drag pieces. Right-click cancels.",
                          BOARD.bottom + 18, 22, DIM)
        elif self.phase == "clear":
            self._draw_clear(surf)
        self._draw_side(surf)

    # ---- sidebar
    def _draw_side(self, surf):
        ui.draw_panel(surf, SIDE, 215)
        cx = SIDE.centerx

        def label(txt, y, col=DIM, size=22):
            t = ui.font(size).render(txt, True, col)
            surf.blit(t, t.get_rect(midtop=(cx, y)))

        if self.phase == "preview":
            label("MEMORIZE", SIDE.y + 16, AMBER, 34)
            low = self.time_left <= LOW_TIME
            col = RED if low and int(self.t * 4) % 2 == 0 else (TEXT if not low else (255, 150, 120))
            label(f"{int(math.ceil(self.time_left))}", SIDE.y + 66, col, 120)
            label("SECONDS", SIDE.y + 142)
            label(f"{self.n} pieces", SIDE.y + 196, TEXT, 28)
            label("The photo is about", SIDE.y + 236)
            label("to scramble.", SIDE.y + 258)
        elif self.phase == "glitch":
            on = int(self.t * 12) % 2 == 0
            label("SIGNAL LOST", SIDE.y + 20, RED if on else (255, 150, 120), 34)
            label("Rebuilding photo", SIDE.y + 72)
            label("from memory...", SIDE.y + 96)
        else:
            label("MATCHED", SIDE.y + 16)
            done = self.n if self.phase == "clear" else aligned_count(self.slots)
            label(f"{done}/{self.n}", SIDE.y + 42, GREEN if done == self.n else CYAN, 66)
            bar = pygame.Rect(SIDE.x + 20, SIDE.y + 108, SIDE.w - 40, 12)
            pygame.draw.rect(surf, BOARD_BG, bar)
            pygame.draw.rect(surf, CYAN, (bar.x, bar.y, int(bar.w * done / self.n), bar.h))
            pygame.draw.rect(surf, (40, 60, 70), bar, 1)
            label("MOVES", SIDE.y + 138)
            label(f"{self.moves}", SIDE.y + 158, TEXT, 44)
            label("TIME", SIDE.y + 204)
            label(fmt_time(self.round_t), SIDE.y + 224, TEXT, 44)
            if self.phase == "rebuild":
                label("No timer", SIDE.y + 276, DIM, 22)
                armed = self.restart_armed > 0
                ui.draw_panel(surf, RESTART_RECT, 245 if armed else 200)
                t = ui.font(26).render("Click again to restart" if armed else "Restart", True, AMBER if armed else DIM)
                surf.blit(t, t.get_rect(center=RESTART_RECT.center))

    # ---- glitch transition
    def _draw_glitch(self, surf):
        t = self.t
        clip = surf.get_clip()
        pygame.draw.rect(surf, BOARD_BG, BOARD)
        surf.set_clip(BOARD)
        if t < GLITCH_CORRUPT:
            k = t / GLITCH_CORRUPT
            rng = random.Random(int(t * 14) + self.round_i * 100)
            bands = 12
            bh = PHOTO_H // bands
            for b in range(bands):
                y0 = b * bh
                h = bh if b < bands - 1 else PHOTO_H - y0
                off = int(rng.uniform(-38, 38) * k) if rng.random() < 0.18 + 0.22 * k else 0
                surf.blit(self.photo, (BOARD.x + off, BOARD.y + y0), pygame.Rect(0, y0, PHOTO_W, h))
            s = int(1 + 3 * k)
            for img, dx in ((self.tint_r, s), (self.tint_c, -s)):
                img.set_alpha(int(28 + 46 * k))
                surf.blit(img, (BOARD.x + dx, BOARD.y))
            if k > 0.55:
                for c in range(1, self.cols):
                    pygame.draw.line(surf, (8, 12, 18), (BOARD.x + c * self.tw, BOARD.y), (BOARD.x + c * self.tw, BOARD.bottom), 1)
                for r in range(1, self.rows):
                    pygame.draw.line(surf, (8, 12, 18), (BOARD.x, BOARD.y + r * self.th), (BOARD.right, BOARD.y + r * self.th), 1)
        else:
            k = (t - GLITCH_CORRUPT) / GLITCH_SCATTER
            e = min(1.0, k * k * (2.2 - 1.2 * min(1.0, k)))
            for p in range(self.n):
                hx, hy = self._slot_xy(p)
                slot = self.slots.index(p)
                tx, ty = self._slot_xy(slot)
                jr = random.Random(p * 977 + int(t * 20))
                jx, jy = jr.uniform(-10, 10) * (1 - e), jr.uniform(-10, 10) * (1 - e)
                x, y = hx + (tx - hx) * e + jx, hy + (ty - hy) * e + jy
                surf.blit(self.tiles[p], (int(x), int(y)))
                pygame.draw.rect(surf, (8, 12, 18), pygame.Rect(int(x), int(y), self.tw, self.th), 1)
        srng = random.Random(int(t * 18) + 7)
        for _ in range(12):
            c = srng.randint(120, 255)
            pygame.draw.rect(surf, (c, c, c), (BOARD.x + srng.randint(0, PHOTO_W), BOARD.y + srng.randint(0, PHOTO_H),
                                               srng.randint(2, 18), srng.randint(1, 2)))
        for _ in range(2):
            pygame.draw.rect(surf, CYAN, (BOARD.x, BOARD.y + srng.randint(0, PHOTO_H), PHOTO_W, srng.randint(1, 2)))
        surf.set_clip(clip)
        if int(t * 8) % 2 == 0:
            ui.draw_title(surf, "TRANSMISSION CORRUPTED", BOARD.y + 12, 30, RED)

    # ---- reconstruction board
    def _draw_board(self, surf):
        pygame.draw.rect(surf, BOARD_BG, BOARD)
        for i in range(self.n):
            x, y = self._slot_xy(i)
            pygame.draw.rect(surf, (24, 36, 48), pygame.Rect(x, y, self.tw, self.th), 1)
        d = self.drag
        if d and d["active"]:                              # empty slot left behind by the lifted piece
            x, y = self._slot_xy(d["slot"])
            pygame.draw.rect(surf, (14, 22, 32), pygame.Rect(x, y, self.tw, self.th))
            pygame.draw.rect(surf, (40, 100, 120), pygame.Rect(x, y, self.tw, self.th), 1)
        where = [0] * self.n
        for i, p in enumerate(self.slots):
            where[p] = i

        def order(p):
            tx, ty = self._slot_xy(where[p])
            moving = abs(self.pos[p][0] - tx) + abs(self.pos[p][1] - ty) > 1
            return (self._dragging_piece(p), moving)
        for p in sorted(range(self.n), key=order):
            x, y = self.pos[p]
            slot = where[p]
            if self._dragging_piece(p):
                sh = pygame.Surface((self.tw, self.th), pygame.SRCALPHA)
                sh.fill((0, 0, 0, 130))
                surf.blit(sh, (int(x) + 6, int(y) + 8))
                state = "drag"
            elif self.sel == slot:
                state = "sel"
            elif self.hover == slot and not (d and d["active"]):
                state = "hover"
            else:
                state = None
            self._draw_piece(surf, p, x, y, state)
        if d and d["active"]:                              # drop target highlight
            tgt = slot_at(self.mouse, self.cols, self.rows)
            if tgt is not None and tgt != d["slot"]:
                x, y = self._slot_xy(tgt)
                pygame.draw.rect(surf, AMBER, pygame.Rect(x, y, self.tw, self.th), 3)

    def _draw_piece(self, surf, p, x, y, state):
        r = pygame.Rect(int(x), int(y), self.tw, self.th)
        surf.blit(self.tiles[p], r.topleft)
        ov = pygame.Surface((self.tw, self.th), pygame.SRCALPHA)
        if state == "hover":
            ov.fill((255, 255, 255, 28))
        elif state == "sel":
            ov.fill((80, 235, 255, int(40 + 30 * math.sin(pygame.time.get_ticks() / 150))))
        f = self.flash.get(p, 0)
        if f > 0:
            ov.fill((255, 190, 80, int(130 * f / 0.35)))
        surf.blit(ov, r.topleft)
        pygame.draw.rect(surf, (8, 12, 18), r, 1)
        if state == "sel":
            pygame.draw.rect(surf, CYAN, r, 3)
        elif state == "drag":
            pygame.draw.rect(surf, CYAN, r, 2)
        elif state == "hover":
            pygame.draw.rect(surf, TEXT, r, 2)

    # ---- success / victory
    def _draw_clear(self, surf):
        surf.blit(self.photo, BOARD.topleft)               # the recovered photograph, intact
        self._draw_frame(surf, GREEN)
        sweep = int((self.t / 0.7) * PHOTO_H) if self.t < 0.7 else None
        if sweep is not None:
            pygame.draw.line(surf, (200, 255, 230), (BOARD.x, BOARD.y + sweep), (BOARD.right, BOARD.y + sweep), 3)
        ui.draw_toast(surf, "PHOTOGRAPH RECOVERED", self.t)
        last = self.round_i == len(ROUNDS) - 1
        if self.t > 0.6 and (pygame.time.get_ticks() // 500) % 2 == 0:
            ui.draw_title(surf, "[SPACE] " + ("Finish" if last else "Next photograph"), BOARD.bottom - 36, 26, TEXT)
        ui.draw_title(surf, f"{self.moves} moves   |   {fmt_time(self.results[-1]['time'])}", BOARD.bottom + 18, 26, GREEN)

    def _draw_victory(self, surf):
        r = ui.center_panel(surf, 820, 470)
        ui.draw_title(surf, "MISSION COMPLETE", r.y + 14, 60, GREEN)
        ui.draw_title(surf, "All Viking photographs reconstructed from memory", r.y + 72, 28, DIM)
        tw, th = 236, 157
        gap = 22
        x0 = r.x + (r.w - (3 * tw + 2 * gap)) // 2
        for i in range(3):
            x = x0 + i * (tw + gap)
            thumb = pygame.transform.smoothscale(self._get_photo(i), (tw, th))
            surf.blit(thumb, (x, r.y + 112))
            pygame.draw.rect(surf, CYAN, (x, r.y + 112, tw, th), 2)
            res = self.results[i] if i < len(self.results) else dict(moves=0, time=0)
            t = ui.font(26).render(ROUNDS[i]["name"], True, CYAN)
            surf.blit(t, t.get_rect(midtop=(x + tw // 2, r.y + 112 + th + 8)))
            t = ui.font(24).render(f"{res['moves']} moves  |  {fmt_time(res['time'])}", True, TEXT)
            surf.blit(t, t.get_rect(midtop=(x + tw // 2, r.y + 112 + th + 32)))
        total_m = sum(x["moves"] for x in self.results)
        total_t = sum(x["time"] for x in self.results)
        ui.draw_title(surf, f"TOTAL   {total_m} moves   |   {fmt_time(total_t)}", r.y + 340, 34, AMBER)
        self.end_buttons.draw(surf)


# ----------------------------------------------------- standalone test runner
if __name__ == "__main__":
    pygame.init()
    screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
    pygame.display.set_caption("Photo from Memory (standalone)")
    clock = pygame.time.Clock()
    game = VikingChallenge()
    running = True
    while running:
        dt = clock.tick(60) / 1000
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT or (ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE):
                running = False
            elif game.handle_event(ev) == "done":
                print("VICTORY -> Memory Capsule would be granted here.")
                game.reset()
        game.update(dt)
        screen.fill((0, 0, 0))
        game.draw(screen)
        pygame.display.flip()
    pygame.quit()
