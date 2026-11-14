"""Procedural placeholder art (pixel style: drawn small, then upscaled)."""
import math
import random
import pygame
from settings import BORDER

OUT = (28, 30, 44)
WHITE = (234, 238, 242)
SHADE = (172, 180, 194)
GREY = (108, 116, 130)
ORANGE = (236, 122, 42)
VISOR = (26, 52, 88)
VISOR_HI = (120, 214, 246)


def upscale(s, k=2):
    return pygame.transform.scale(s, (s.get_width() * k, s.get_height() * k))


def _box(s, fill, x, y, w, h):
    pygame.draw.rect(s, OUT, (x - 1, y - 1, w + 2, h + 2))
    pygame.draw.rect(s, fill, (x, y, w, h))


# ---------------------------------------------------------------- astronaut
def draw_astronaut(facing, anim, frame):
    s = pygame.Surface((16, 21), pygame.SRCALPHA)
    swing = (0, 1, 0, -1)[frame % 4] if anim == "walk" else 0
    bob = 1 if (anim == "idle" and frame % 2) else 0
    if facing in ("down", "up"):
        for x, d in ((5, swing), (8, -swing)):
            h = 4 + d
            _box(s, WHITE, x, 15, 3, h)
            pygame.draw.rect(s, GREY, (x, 15 + h - 2, 3, 2))
        if facing == "down":
            _box(s, WHITE, 4, 9 + bob, 8, 7)
            pygame.draw.rect(s, ORANGE, (6, 11 + bob, 2, 2))
            pygame.draw.rect(s, VISOR_HI, (9, 11 + bob, 1, 1))
        else:
            _box(s, GREY, 4, 9 + bob, 8, 7)
            pygame.draw.rect(s, SHADE, (5, 10 + bob, 6, 2))
            pygame.draw.rect(s, ORANGE, (7, 13 + bob, 2, 1))
        for x, d in ((2, -swing), (12, swing)):
            _box(s, WHITE, x, 10 + bob + d, 2, 4)
            pygame.draw.rect(s, GREY, (x, 13 + bob + d, 2, 1))
        _box(s, WHITE, 3, 1 + bob, 10, 8)
        if facing == "down":
            pygame.draw.rect(s, VISOR, (5, 3 + bob, 6, 4))
            pygame.draw.rect(s, VISOR_HI, (6, 4 + bob, 2, 1))
        else:
            pygame.draw.rect(s, SHADE, (5, 3 + bob, 6, 3))
    else:
        right = facing == "right"
        for x, d, col in ((6, swing, WHITE), (7, -swing, SHADE)):
            h = 4 + d
            _box(s, col, x, 15, 3, h)
            pygame.draw.rect(s, GREY, (x, 15 + h - 2, 3, 2))
        _box(s, GREY, 2 if right else 11, 9 + bob, 3, 6)
        _box(s, WHITE, 5, 9 + bob, 6, 7)
        _box(s, SHADE, 6, 10 + bob + swing, 3, 4)
        _box(s, WHITE, 4, 1 + bob, 8, 8)
        vx = 8 if right else 4
        pygame.draw.rect(s, VISOR, (vx, 3 + bob, 4, 4))
        pygame.draw.rect(s, VISOR_HI, (vx + 1, 4 + bob, 2, 1))
    return upscale(s)


# -------------------------------------------------------------- ghost rover
def draw_ghost_rover(frame):
    """Translucent spectral rover, facing right."""
    s = pygame.Surface((34, 22), pygame.SRCALPHA)
    body = (120, 230, 255, 150)
    deep = (40, 140, 200, 175)
    lite = (215, 255, 255, 230)
    edge = (170, 250, 255, 235)
    pygame.draw.polygon(s, (100, 220, 255, 80),
                        [(7, 6), (2, 8), (4, 10), (0, 12), (4, 14), (1, 16), (7, 16)])
    for i, x in enumerate((6, 13, 20)):
        for y in (1, 18):
            pygame.draw.rect(s, deep, (x, y, 6, 3))
            pygame.draw.rect(s, edge, (x, y, 6, 3), 1)
            pygame.draw.rect(s, lite, (x + 1 + ((i + frame) % 2) * 3, y + 1, 1, 1))
    pygame.draw.rect(s, body, (6, 4, 20, 14))
    pygame.draw.rect(s, edge, (6, 4, 20, 14), 1)
    pygame.draw.rect(s, deep, (9, 6, 9, 10))
    for x in (12, 15):
        pygame.draw.line(s, (90, 200, 235, 170), (x, 6), (x, 15))
    pygame.draw.line(s, (90, 200, 235, 170), (9, 11), (17, 11))
    pygame.draw.rect(s, edge, (9, 6, 9, 10), 1)
    pygame.draw.rect(s, lite, (20, 9, 2, 4))
    pygame.draw.rect(s, body, (24, 7, 7, 8))
    pygame.draw.rect(s, edge, (24, 7, 7, 8), 1)
    pygame.draw.rect(s, lite, (27, 9, 2, 2))   # hollow glowing eyes
    pygame.draw.rect(s, lite, (27, 12, 2, 2))
    pygame.draw.line(s, edge, (6, 11), (3, 6))
    pygame.draw.rect(s, lite, (2, 5, 2, 2))
    return upscale(s)


# ------------------------------------------------------------------ props
def draw_rock(rng, r):
    w, h = r * 2 + 8, int(r * 1.7) + 8
    s = pygame.Surface((w, h), pygame.SRCALPHA)
    cx, cy = w / 2, h - 5 - r * 0.75
    pygame.draw.ellipse(s, (30, 10, 8, 90),
                        (int(cx - r * 1.05), int(h - 4 - r * 0.45), int(r * 2.1), int(r * 0.5 + 3)))
    n = 9
    pts = []
    for i in range(n):
        a = i * 2 * math.pi / n + rng.uniform(-0.15, 0.15)
        j = rng.uniform(0.78, 1.08)
        pts.append((cx + math.cos(a) * r * j, cy + math.sin(a) * r * 0.75 * j))
    base = rng.choice(((122, 64, 46), (140, 76, 52), (106, 58, 46)))
    pygame.draw.polygon(s, base, pts)
    pygame.draw.polygon(s, (58, 26, 22), pts, 1)
    hi = tuple(min(255, c + 30) for c in base)
    pts2 = [(cx - r * 0.12 + (x - cx) * 0.6, cy - r * 0.18 + (y - cy) * 0.55) for x, y in pts]
    pygame.draw.polygon(s, hi, pts2)
    for _ in range(r // 2 + 2):
        px = int(cx + rng.uniform(-r * 0.6, r * 0.6))
        py = int(cy + rng.uniform(-r * 0.4, r * 0.4))
        if 0 <= px < w and 0 <= py < h:
            s.set_at((px, py), (70, 30, 26))
    return upscale(s)


def draw_equipment():
    """Abandoned supply unit with a broken solar panel and bent dish."""
    s = pygame.Surface((40, 30), pygame.SRCALPHA)
    pygame.draw.ellipse(s, (30, 10, 8, 90), (2, 22, 34, 7))
    pygame.draw.polygon(s, OUT, [(19, 1), (39, 5), (37, 17), (17, 13)])
    pygame.draw.polygon(s, (36, 62, 108), [(20, 3), (37, 6), (35, 15), (19, 12)])
    for p in ((25, 4, 24, 13), (31, 5, 30, 14)):
        pygame.draw.line(s, (80, 120, 170), (p[0], p[1]), (p[2], p[3]))
    pygame.draw.line(s, (14, 22, 40), (27, 5), (31, 12))      # crack
    _box(s, (96, 104, 116), 4, 13, 26, 13)
    for i in range(0, 26, 4):                                  # hazard stripe
        pygame.draw.rect(s, ORANGE if (i // 4) % 2 == 0 else OUT, (4 + i, 13, 4, 3))
    pygame.draw.rect(s, (150, 90, 60), (8, 19, 5, 3))          # rust
    pygame.draw.rect(s, (150, 90, 60), (22, 21, 4, 4))
    pygame.draw.rect(s, (70, 76, 88), (14, 18, 8, 6), 1)       # hatch
    pygame.draw.rect(s, GREY, (10, 8, 1, 6))
    pygame.draw.ellipse(s, SHADE, (5, 4, 9, 5))
    pygame.draw.ellipse(s, OUT, (5, 4, 9, 5), 1)
    return upscale(s)


def draw_beacon(on):
    s = pygame.Surface((12, 24), pygame.SRCALPHA)
    pygame.draw.ellipse(s, (30, 10, 8, 90), (0, 20, 12, 4))
    _box(s, GREY, 2, 18, 8, 4)
    _box(s, (70, 76, 90), 5, 6, 2, 13)
    _box(s, SHADE, 3, 1, 6, 6)
    pygame.draw.rect(s, (90, 255, 255) if on else (20, 70, 80), (4, 2, 4, 3))
    return upscale(s)


# ------------------------------------------------------------ ground & fx
def make_ground(w, h, rng, avoid):
    pal = [(150, 70, 45), (158, 76, 47), (142, 64, 42), (168, 86, 50), (134, 60, 40)]
    cw, ch = w // 64 + 2, h // 64 + 2
    coarse = pygame.Surface((cw, ch), 0, 32)
    for y in range(ch):
        for x in range(cw):
            coarse.set_at((x, y), rng.choice(pal))
    ground = pygame.transform.smoothscale(coarse, (w, h))

    gw, gh = w // 6, h // 6                      # chunky pixel grain
    grain = pygame.Surface((gw, gh), pygame.SRCALPHA)
    for y in range(gh):
        for x in range(gw):
            v = rng.random()
            if v < 0.25:
                grain.set_at((x, y), (40, 14, 10, rng.randint(10, 34)))
            elif v > 0.85:
                grain.set_at((x, y), (230, 150, 90, rng.randint(8, 24)))
    ground.blit(pygame.transform.scale(grain, (w, h)), (0, 0))

    for _ in range(45):                          # dust patches
        rx, ry = rng.randint(80, 260), rng.randint(40, 120)
        t = pygame.Surface((rx * 2, ry * 2), pygame.SRCALPHA)
        col = (225, 140, 80, 16) if rng.random() < 0.5 else (60, 24, 18, 20)
        pygame.draw.ellipse(t, col, (0, 0, rx * 2, ry * 2))
        ground.blit(t, (rng.randint(0, w) - rx, rng.randint(0, h) - ry))

    for _ in range(700):                         # pebbles
        x, y = rng.randint(0, w), rng.randint(0, h)
        col = rng.choice(((96, 44, 32), (186, 108, 66), (120, 62, 44)))
        pygame.draw.rect(ground, col, (x, y, rng.choice((2, 3, 4)), rng.choice((2, 3))))

    placed = 0
    while placed < 18:                           # craters (decorative)
        x = rng.randint(BORDER + 100, w - BORDER - 100)
        y = rng.randint(BORDER + 80, h - BORDER - 80)
        rx = rng.randint(26, 70)
        ry = int(rx * 0.6)
        if any(math.hypot(x - ax, y - ay) < ar + rx for ax, ay, ar in avoid):
            continue
        t = pygame.Surface((rx * 2 + 12, ry * 2 + 12), pygame.SRCALPHA)
        c = (t.get_width() // 2, t.get_height() // 2)
        pygame.draw.ellipse(t, (176, 100, 62), (c[0] - rx, c[1] - ry, rx * 2, ry * 2))
        pygame.draw.ellipse(t, (96, 42, 32), (c[0] - rx + 5, c[1] - ry + 4, rx * 2 - 10, ry * 2 - 8))
        pygame.draw.ellipse(t, (126, 60, 40), (c[0] - rx + 9, c[1] - ry + 8, rx * 2 - 16, ry * 2 - 14))
        pygame.draw.ellipse(t, (70, 30, 24), (c[0] - rx, c[1] - ry, rx * 2, ry * 2), 2)
        ground.blit(t, (x - c[0], y - c[1]))
        placed += 1

    edge = pygame.Surface((w, h), pygame.SRCALPHA)   # dark rocky map edge
    for i in range(BORDER + 40):
        a = int(220 * (1 - i / (BORDER + 40)) ** 1.4)
        col = (28, 10, 8, a)
        pygame.draw.line(edge, col, (0, i), (w, i))
        pygame.draw.line(edge, col, (0, h - 1 - i), (w, h - 1 - i))
        pygame.draw.line(edge, col, (i, 0), (i, h))
        pygame.draw.line(edge, col, (w - 1 - i, 0), (w - 1 - i, h))
    ground.blit(edge, (0, 0))
    return ground


_glow_cache = {}


def glow(radius, level, color=(70, 225, 255)):
    """Additive-blend light sprite. Blit with BLEND_RGB_ADD."""
    key = (radius, level, color)
    if key not in _glow_cache:
        s = pygame.Surface((radius * 2, radius * 2))
        s.fill((0, 0, 0))
        step = 1 if radius < 12 else 2
        for i in range(radius, 0, -step):
            k = ((1 - i / radius) ** 1.6) * (level / 10)
            pygame.draw.circle(s, tuple(int(c * k) for c in color), (radius, radius), i)
        _glow_cache[key] = s
    return _glow_cache[key]


def make_vignette(w, h):
    sw, sh = 64, 36
    s = pygame.Surface((sw, sh), pygame.SRCALPHA)
    for y in range(sh):
        for x in range(sw):
            dx = (x / (sw - 1) - 0.5) * 2
            dy = (y / (sh - 1) - 0.5) * 2
            d = math.hypot(dx, dy * 0.9) / 1.2
            a = max(0.0, min(1.0, (d - 0.45) / 0.6))
            s.set_at((x, y), (18, 4, 8, int(a * a * 190)))
    return pygame.transform.smoothscale(s, (w, h))


# ------------------------------------------------- Ingenuity set (placeholder)
def draw_ingenuity_wreck():
    """Abandoned Ingenuity helicopter, seen from above: drooping rotor, dusty."""
    s = pygame.Surface((36, 26), pygame.SRCALPHA)
    pygame.draw.ellipse(s, (30, 10, 8, 90), (4, 18, 28, 7))
    for x, y in ((9, 15), (25, 15), (9, 8), (25, 8)):          # legs
        pygame.draw.line(s, OUT, (18, 13), (x, y))
    pygame.draw.line(s, SHADE, (3, 11), (33, 9), 2)            # rotor blade
    pygame.draw.line(s, GREY, (5, 14), (28, 16), 2)            # lower blade
    pygame.draw.line(s, OUT, (3, 11), (33, 9), 1)
    _box(s, (232, 232, 226), 14, 12, 8, 7)                      # body
    _box(s, (26, 48, 90), 12, 6, 12, 6)                         # solar panel
    pygame.draw.line(s, (80, 120, 170), (18, 6), (18, 11))
    pygame.draw.rect(s, (150, 90, 60), (22, 14, 4, 3))          # rust / dust
    pygame.draw.rect(s, (214, 140, 96, 140), (10, 17, 14, 3))
    return upscale(s)


def draw_ghost_ingenuity(frame):
    """Translucent violet-white spectral helicopter (distinct from Ghost Rover)."""
    s = pygame.Surface((36, 26), pygame.SRCALPHA)
    body = (205, 175, 255, 150)
    deep = (130, 90, 210, 170)
    lite = (245, 235, 255, 235)
    edge = (225, 205, 255, 230)
    pygame.draw.polygon(s, (190, 150, 255, 70), [(14, 19), (11, 25), (16, 22), (18, 25), (21, 22), (25, 25), (22, 19)])
    ends = ((2, 11, 34, 9), (6, 5, 30, 15))[frame % 2]         # spinning rotor
    pygame.draw.line(s, (220, 200, 255, 110), (ends[0], ends[1]), (ends[2], ends[3]), 3)
    pygame.draw.line(s, edge, (ends[0], ends[1]), (ends[2], ends[3]), 1)
    pygame.draw.rect(s, body, (14, 10, 8, 8))
    pygame.draw.rect(s, edge, (14, 10, 8, 8), 1)
    pygame.draw.rect(s, deep, (12, 5, 12, 5))
    pygame.draw.rect(s, edge, (12, 5, 12, 5), 1)
    pygame.draw.rect(s, lite, (16, 12, 1, 2))                  # hollow eyes
    pygame.draw.rect(s, lite, (19, 12, 1, 2))
    for x in (9, 27):
        pygame.draw.line(s, edge, (18, 17), (x, 20))
    return upscale(s)


GHOST_ROBOT_ART = {"ingenuity": draw_ghost_ingenuity}


def draw_capsule():
    """Memory Capsule (reward / archive art)."""
    s = pygame.Surface((20, 34), pygame.SRCALPHA)
    pygame.draw.rect(s, OUT, (1, 1, 18, 32), border_radius=8)
    pygame.draw.rect(s, (30, 52, 78), (2, 2, 16, 30), border_radius=7)
    pygame.draw.rect(s, (90, 235, 255), (5, 6, 10, 16), border_radius=4)
    pygame.draw.rect(s, (200, 255, 255), (7, 8, 3, 10), border_radius=1)
    pygame.draw.rect(s, ORANGE, (3, 24, 14, 3))
    pygame.draw.rect(s, (90, 235, 255), (2, 2, 16, 30), 1, border_radius=7)
    return pygame.transform.scale(s, (80, 136))


# ------------------------------------------- remaining equipment (placeholders)
# One shape function per equipment; drawn solid for the wreck and translucent
# for its Ghost Robot. Each returns the eye rects used by the ghost version.
def _pal_solid():
    return dict(body=(222, 222, 216), deep=(40, 64, 112), lite=(245, 245, 240), edge=OUT,
                accent=ORANGE)


def _pal_ghost(t):
    r, g, b = t
    dim = lambda k: (int(r * k), int(g * k), int(b * k))
    up = lambda n: (min(255, r + n), min(255, g + n), min(255, b + n))
    return dict(body=(*t, 150), deep=(*dim(0.5), 175), lite=(*up(70), 235), edge=(*up(35), 235),
                accent=(*up(70), 235))


def _shape_insight(s, p, f):
    for cx in (7, 29):
        pygame.draw.circle(s, p["deep"], (cx, 13), 7)
        pygame.draw.circle(s, p["edge"], (cx, 13), 7, 1)
        pygame.draw.line(s, p["edge"], (cx - 6, 13), (cx + 6, 13))
        pygame.draw.line(s, p["edge"], (cx, 7), (cx, 19))
    pygame.draw.rect(s, p["body"], (13, 8, 10, 10))
    pygame.draw.rect(s, p["edge"], (13, 8, 10, 10), 1)
    pygame.draw.circle(s, p["accent"], (18, 14), 2)
    return [(15, 9), (19, 9)]


def _shape_phoenix(s, p, f):
    pygame.draw.polygon(s, p["deep"], [(14, 12), (2, 4), (2, 21)])
    pygame.draw.polygon(s, p["deep"], [(22, 12), (34, 4), (34, 21)])
    pygame.draw.polygon(s, p["edge"], [(14, 12), (2, 4), (2, 21)], 1)
    pygame.draw.polygon(s, p["edge"], [(22, 12), (34, 4), (34, 21)], 1)
    pygame.draw.rect(s, p["body"], (14, 7, 8, 10))
    pygame.draw.rect(s, p["edge"], (14, 7, 8, 10), 1)
    pygame.draw.line(s, p["accent"], (18, 17), (18, 24), 2)      # robotic arm
    return [(15, 9), (19, 9)]


def _shape_mer(s, p, f, stuck=False):
    for i, x in enumerate((6, 15, 24)):
        for y in (2, 20):
            if stuck and i == 2 and y == 20:
                continue                                          # buried wheel
            pygame.draw.rect(s, p["deep"], (x, y, 6, 4))
            pygame.draw.rect(s, p["edge"], (x, y, 6, 4), 1)
    pygame.draw.rect(s, p["body"], (7, 6, 20, 14))
    pygame.draw.rect(s, p["edge"], (7, 6, 20, 14), 1)
    pygame.draw.rect(s, p["deep"], (10, 8, 10, 10))
    pygame.draw.line(s, p["edge"], (15, 8), (15, 17))
    pygame.draw.rect(s, p["lite"], (22, 9, 2, 6))
    pygame.draw.rect(s, p["body"], (26, 8, 6, 8))
    pygame.draw.rect(s, p["edge"], (26, 8, 6, 8), 1)
    return [(28, 9), (28, 12)]


def _shape_spirit(s, p, f):
    return _shape_mer(s, p, f, stuck=True)


def _shape_sojourner(s, p, f):
    for x in (10, 16, 22):
        for y in (5, 17):
            pygame.draw.rect(s, p["deep"], (x, y, 4, 4))
            pygame.draw.rect(s, p["edge"], (x, y, 4, 4), 1)
    pygame.draw.rect(s, p["body"], (9, 8, 18, 10))
    pygame.draw.rect(s, p["edge"], (9, 8, 18, 10), 1)
    pygame.draw.rect(s, p["deep"], (11, 9, 9, 8))
    pygame.draw.line(s, p["accent"], (12, 8), (9, 2))
    return [(22, 10), (22, 13)]


def _shape_viking(s, p, f):
    for cx in (10, 26):
        for dx, dy in ((-7, 8), (7, 8), (0, -8)):
            pygame.draw.line(s, p["edge"], (cx, 13), (cx + dx, 13 + dy))
        pygame.draw.circle(s, p["body"], (cx, 13), 6)
        pygame.draw.circle(s, p["edge"], (cx, 13), 6, 1)
        pygame.draw.circle(s, p["accent"], (cx, 13), 2)
    return [(8, 9), (11, 9), (24, 9), (27, 9)]


SHAPES = {"insight": _shape_insight, "phoenix": _shape_phoenix, "spirit": _shape_spirit,
          "opportunity": _shape_mer, "sojourner": _shape_sojourner, "viking": _shape_viking}


def make_wreck(shape):
    s = pygame.Surface((36, 26), pygame.SRCALPHA)
    pygame.draw.ellipse(s, (30, 10, 8, 90), (3, 19, 30, 7))
    shape(s, _pal_solid(), 0)
    pygame.draw.rect(s, (214, 140, 96, 120), (8, 19, 20, 3))     # dust
    return upscale(s)


def make_ghost(shape, tint, frame):
    s = pygame.Surface((36, 26), pygame.SRCALPHA)
    p = _pal_ghost(tint)
    off = (frame % 2) * 2 - 1
    pygame.draw.polygon(s, (*tint, 70), [(13, 21), (11 + off, 25), (16, 23), (18 - off, 25), (21, 23), (25 + off, 25), (23, 21)])
    eyes = shape(s, p, frame)
    for x, y in eyes:
        pygame.draw.rect(s, p["lite"], (x, y, 2, 2))
    return upscale(s)


WRECK_ART = {"ingenuity": draw_ingenuity_wreck}
from story_data import BY_ID as _BY_ID
for _id, _shape in SHAPES.items():
    WRECK_ART[_id] = lambda _s=_shape: make_wreck(_s)
    GHOST_ROBOT_ART[_id] = lambda frame, _s=_shape, _t=_BY_ID[_id]["tint"]: make_ghost(_s, _t, frame)
