"""Phoenix minigame - BENEATH THE SURFACE.

Minesweeper-inspired excavation puzzle (Puzzle / Strategy / Resource Management).
Dig into Martian soil, recover water ice, avoid buried rocks, and stay inside
your digging-energy budget across three stages.

INTEGRATION (puzzle.py)
-----------------------
    from phoenix import PhoenixChallenge
    CHALLENGES = {
        ...
        "phoenix": PhoenixChallenge,
    }

It follows the same challenge interface as the other minigames:
    handle_event(e) -> "done" ONLY when the player wins and presses CONTINUE
                       (EncounterScene then runs the normal Memory Capsule flow)
    update(dt), draw(surf)
Failure shows GAME OVER + RETRY and never returns "done".

Optional hooks for the capsule reward:
    PhoenixChallenge(eq, on_complete=callback)   # callback(result_dict) on victory
    challenge.get_result()                       # result dict at any time
    phoenix.play(screen)                         # blocking standalone loop -> result dict

Result dict keys: completed, score, rank, ice_collected, rocks_hit,
                  integrity, energy, stages_cleared, stage_log

Run directly for a standalone test (from the game folder):  python phoenix.py

CLUE RULES (the same in every stage)
    Big cyan number   = water-ice cells among the 8 surrounding cells.
    Small orange no.  = rock cells among the 8 surrounding cells.
    Soil colour       = follows the ice number: DRY 0, DAMP 1, MOIST 2, WET 3+.
    Every new game/retry generates randomized stage layouts. Clues are
    recalculated from each generated layout, and a logic solver verifies that
    each layout is solvable within the energy budget without touching a rock.
    Ice and rocks never overlap.
"""

import math
import random

import pygame

import ui
from settings import SCREEN_W, SCREEN_H, CYAN, TEXT, DIM

# --------------------------------------------------------------------- config
POINTS = {"ice": 500, "stage": 500, "all_ice": 300, "rock": -200}
RANKS = [(5000, "S"), (4000, "A"), (3000, "B"), (0, "C")]

MAX_INTEGRITY = 100
DIG_TIME = 0.42            # excavation animation length (seconds)
RESOLVE_DELAY = 0.9        # pause so the last dig can be seen before a panel opens
SOLVER_NODE_LIMIT = 250000

# size    grid width/height          ice    hidden ice cells (deposits)
# rocks   hidden rock cells          target ice needed to clear the stage
# energy  digs available             damage % integrity lost per rock strike
# cell    cell size in pixels
# slack   optimal-play energy margin the verified layout must leave:
#         energy - min_dig_cost must be inside [slack_min, slack_max]
STAGES = [
    dict(name="SURFACE INVESTIGATION", level="EASY", size=5, ice=3, rocks=3,
         target=2, energy=9, damage=34, cell=74, slack=(2, 5)),
    dict(name="COMPACTED SOIL", level="MEDIUM", size=6, ice=4, rocks=7,
         target=3, energy=11, damage=40, cell=64, slack=(2, 4)),
    dict(name="DEEP ICE DEPOSIT", level="HARD", size=7, ice=6, rocks=11,
         target=4, energy=14, damage=50, cell=57, slack=(2, 4)),
]

AMBER = (255, 176, 64)
ORANGE = (255, 140, 60)
RED = (255, 80, 70)
GREEN = (110, 255, 170)
ICE_COL = (130, 245, 255)

PIT = [(104, 66, 46), (96, 78, 86), (74, 94, 122), (50, 114, 152)]   # DRY, DAMP, MOIST, WET
PIT_NAMES = ["DRY", "DAMP", "MOIST", "WET"]

TOP = pygame.Rect(14, 8, 932, 62)
AREA = pygame.Rect(20, 80, 456, 416)
SIDE = pygame.Rect(490, 80, 456, 416)
BAR = pygame.Rect(14, 502, 932, 32)
FINISH_RECT = pygame.Rect(SIDE.x + 18, SIDE.bottom - 52, SIDE.w - 36, 38)


def rank_for(score):
    for need, letter in RANKS:
        if score >= need:
            return letter
    return "C"


# ----------------------------------------------------------- layout + solver
def _nbrs(n, r, c):
    out = []
    for dr in (-1, 0, 1):
        for dc in (-1, 0, 1):
            if dr or dc:
                rr, cc = r + dr, c + dc
                if 0 <= rr < n and 0 <= cc < n:
                    out.append((rr, cc))
    return out


def _make_layout(stage, attempt):
    """Create a randomized candidate layout. kind[r][c]: S soil, I ice, R rock."""
    n = stage["size"]
    # A fresh system-seeded RNG makes each candidate different between runs.
    # The clue arrays below are calculated from this exact randomized layout.
    rng = random.Random()
    cells = [(r, c) for r in range(n) for c in range(n)]

    ice = set()
    groups = 1 if n <= 5 else 2
    for g in range(groups):
        need = stage["ice"] // groups + (1 if g < stage["ice"] % groups else 0)
        free = [p for p in cells if p not in ice]
        grp = {rng.choice(free)}
        while len(grp) < need:
            ring = {q for (r, c) in grp for q in ((r + 1, c), (r - 1, c), (r, c + 1), (r, c - 1))
                    if 0 <= q[0] < n and 0 <= q[1] < n and q not in ice and q not in grp}
            if not ring:
                return None
            grp.add(rng.choice(sorted(ring)))
        ice |= grp

    rest = [p for p in cells if p not in ice]
    rocks = set(rng.sample(rest, stage["rocks"]))
    if ice & rocks:
        return None

    kind = [["S"] * n for _ in range(n)]
    for (r, c) in ice:
        kind[r][c] = "I"
    for (r, c) in rocks:
        kind[r][c] = "R"
    ice_n = [[sum(kind[a][b] == "I" for a, b in _nbrs(n, r, c)) for c in range(n)] for r in range(n)]
    rock_n = [[sum(kind[a][b] == "R" for a, b in _nbrs(n, r, c)) for c in range(n)] for r in range(n)]

    cands = [(r, c) for (r, c) in cells
             if kind[r][c] == "S" and rock_n[r][c] == 0 and len(_nbrs(n, r, c)) >= 5]
    if not cands:
        return None
    start = rng.choice(cands)
    return dict(kind=kind, ice_n=ice_n, rock_n=rock_n, start=start)


class _Abort(Exception):
    pass


def _deduce(n, lay, revealed):
    """Constraint enumeration over the frontier. Returns {cell: bitmask} where the
    mask lists every type (1 soil, 2 ice, 4 rock) that cell can take in some
    assignment consistent with ALL visible clues. None if too expensive."""
    kind, ice_n, rock_n = lay["kind"], lay["ice_n"], lay["rock_n"]
    cons, frontier = [], set()
    for (r, c) in revealed:
        if kind[r][c] != "S":
            continue
        unk, known_ice = [], 0
        for (a, b) in _nbrs(n, r, c):
            if (a, b) in revealed:
                known_ice += kind[a][b] == "I"
            else:
                unk.append((a, b))
        if unk:
            cons.append((unk, ice_n[r][c] - known_ice, rock_n[r][c]))
            frontier.update(unk)
    cells = sorted(frontier)
    idx = {p: i for i, p in enumerate(cells)}
    F = len(cells)
    state = [[ni, nr, len(u), 0, 0] for (u, ni, nr) in cons]   # need_ice, need_rock, remaining, ice, rock
    cons_of = [[] for _ in range(F)]
    for ci, (u, _, _) in enumerate(cons):
        for p in u:
            cons_of[idx[p]].append(ci)

    seen = [0] * F
    vals = [0] * F
    nodes = [0]

    def rec(i):
        if i == F:
            for j in range(F):
                seen[j] |= 1 << vals[j]
            return
        nodes[0] += 1
        if nodes[0] > SOLVER_NODE_LIMIT:
            raise _Abort
        for v in (0, 1, 2):
            for ci in cons_of[i]:
                s = state[ci]
                s[2] -= 1
                if v == 1:
                    s[3] += 1
                elif v == 2:
                    s[4] += 1
            ok = True
            for ci in cons_of[i]:
                s = state[ci]
                if s[3] > s[0] or s[4] > s[1] or s[3] + s[2] < s[0] or s[4] + s[2] < s[1]:
                    ok = False
                    break
            if ok:
                vals[i] = v
                rec(i + 1)
            for ci in cons_of[i]:
                s = state[ci]
                s[2] += 1
                if v == 1:
                    s[3] -= 1
                elif v == 2:
                    s[4] -= 1

    try:
        rec(0)
    except _Abort:
        return None
    return {p: seen[i] for p, i in idx.items()}


def _solve_cost(lay, stage):
    """Play the stage using ONLY logically certain moves (never a rock).
    Returns the number of digs needed to reach the ice target, or None if the
    layout cannot be solved without guessing."""
    n, kind = stage["size"], lay["kind"]
    revealed = {lay["start"]}
    found = cost = 0
    while found < stage["target"]:
        info = _deduce(n, lay, revealed)
        if not info:
            return None
        safe = [(p, m) for p, m in info.items() if m and not (m & 4)]
        if not safe:
            return None

        def rank(item):
            p, m = item
            unknown_around = sum(q not in revealed for q in _nbrs(n, *p))
            if m == 2:
                return (0, 0)            # certain ice
            if m == 3:
                return (1, -unknown_around)   # soil-or-ice, never rock
            return (2, -unknown_around)       # certain soil: pure information

        p, _ = min(safe, key=rank)
        revealed.add(p)
        cost += 1
        if kind[p[0]][p[1]] == "R":
            return None                  # cannot happen: guards solver soundness
        if kind[p[0]][p[1]] == "I":
            found += 1
    return cost


_LAYOUTS = {}


def build_layout(stage_i):
    """Build and cache a randomized layout that passes the solvability check."""
    if stage_i in _LAYOUTS:
        return _LAYOUTS[stage_i]
    st = STAGES[stage_i]
    lo, hi = st["slack"]
    for attempt in range(2000):
        lay = _make_layout(st, attempt)
        if not lay:
            continue
        cost = _solve_cost(lay, st)
        if cost is not None and lo <= st["energy"] - cost <= hi:
            lay["min_cost"] = cost
            lay["attempt"] = attempt
            _LAYOUTS[stage_i] = lay
            return lay
    raise RuntimeError("Phoenix: could not build a solvable layout for stage %d" % (stage_i + 1))


# ------------------------------------------------------------------ drawing
def _shade(col, f):
    return tuple(max(0, min(255, int(v * f))) for v in col)


def _txt(surf, s, size, color, pos, anchor="topleft", alpha=255):
    t = ui.font(size).render(s, True, color)
    if alpha < 255:
        t.set_alpha(alpha)
    r = t.get_rect(**{anchor: pos})
    surf.blit(t, r)
    return r


_BG = None


def _background():
    """Procedural Martian terrain, drawn once."""
    global _BG
    if _BG is not None:
        return _BG
    bg = pygame.Surface((SCREEN_W, SCREEN_H))
    for y in range(SCREEN_H):
        k = y / SCREEN_H
        pygame.draw.line(bg, (int(96 + 44 * k), int(50 + 30 * k), int(36 + 20 * k)), (0, y), (SCREEN_W, y))
    rng = random.Random(4242)
    layer = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
    for _ in range(90):                      # soft dust blotches
        w, h = rng.randint(60, 240), rng.randint(20, 90)
        col = rng.choice([(70, 34, 24, 46), (170, 100, 64, 38), (200, 130, 84, 26)])
        pygame.draw.ellipse(layer, col, (rng.randint(-40, SCREEN_W), rng.randint(-20, SCREEN_H), w, h))
    for _ in range(26):                      # craters
        x, y, r = rng.randint(0, SCREEN_W), rng.randint(0, SCREEN_H), rng.randint(10, 38)
        pygame.draw.ellipse(layer, (60, 28, 20, 70), (x - r, y - r // 2, r * 2, r))
        pygame.draw.ellipse(layer, (190, 120, 80, 60), (x - r, y - r // 2, r * 2, r), 2)
    for _ in range(120):                     # wind ripples
        x, y, w = rng.randint(0, SCREEN_W), rng.randint(0, SCREEN_H), rng.randint(20, 90)
        pygame.draw.line(layer, (210, 140, 96, 34), (x, y), (x + w, y + rng.randint(-3, 3)), 2)
    for _ in range(160):                     # pebbles
        x, y = rng.randint(0, SCREEN_W), rng.randint(0, SCREEN_H)
        r = rng.randint(1, 4)
        pygame.draw.circle(layer, (50, 30, 26, 120), (x + 1, y + 1), r)
        pygame.draw.circle(layer, (150, 104, 80, 150), (x, y), r)
    bg.blit(layer, (0, 0))
    vig = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
    for i in range(44):
        pygame.draw.rect(vig, (8, 4, 4, int(110 * (1 - i / 44) ** 2)),
                         pygame.Rect(0, 0, SCREEN_W, SCREEN_H).inflate(-2 * i, -2 * i), 2)
    bg.blit(vig, (0, 0))
    _BG = bg
    return bg


def _draw_hidden_tile(surf, rect, var=0, specks=(), hover=False, flag=False):
    base = (158 + var * 5, 96 + var * 3, 66 + var * 2)
    r = rect.inflate(-4, -4)
    pygame.draw.rect(surf, _shade(base, 0.6), r.move(0, 2), border_radius=9)
    pygame.draw.rect(surf, base, r, border_radius=9)
    hl = pygame.Surface((r.w - 8, max(4, r.h // 3)), pygame.SRCALPHA)
    pygame.draw.rect(hl, (255, 232, 200, 40), hl.get_rect(), border_radius=7)
    surf.blit(hl, (r.x + 4, r.y + 4))
    pygame.draw.rect(surf, _shade(base, 0.78), r, 2, border_radius=9)
    for fx, fy, rad, sh in specks:
        pygame.draw.circle(surf, _shade(base, sh), (r.x + int(fx * r.w), r.y + int(fy * r.h)), rad)
    if hover:
        ov = pygame.Surface(r.size, pygame.SRCALPHA)
        pygame.draw.rect(ov, (255, 255, 255, 40), ov.get_rect(), border_radius=9)
        surf.blit(ov, r.topleft)
    if flag:
        cx, top, bot = r.centerx, r.y + r.h * 0.18, r.bottom - r.h * 0.18
        pygame.draw.line(surf, (235, 235, 235), (cx - 4, top), (cx - 4, bot), 3)
        pygame.draw.polygon(surf, (255, 200, 60), [(cx - 4, top), (cx - 4 + r.w * 0.3, top + r.h * 0.14),
                                                    (cx - 4, top + r.h * 0.28)])
        pygame.draw.ellipse(surf, (90, 50, 36), (cx - 12, bot - 3, 16, 7))


def _draw_pit(surf, rect, ice_n, rock_n, survey=False):
    """Excavated soil with its two clues."""
    col = PIT[min(ice_n, 3)]
    r = rect.inflate(-4, -4)
    pygame.draw.rect(surf, _shade(col, 0.5), r, border_radius=9)
    inner = r.inflate(-6, -6)
    pygame.draw.rect(surf, col, inner, border_radius=7)
    pygame.draw.line(surf, _shade(col, 0.62), (inner.x + 4, inner.y + 2), (inner.right - 5, inner.y + 2), 3)
    pygame.draw.rect(surf, _shade(col, 1.3), inner, 1, border_radius=7)
    nc = ICE_COL if ice_n else (205, 180, 165)
    big = ui.font(int(rect.h * 0.62)).render(str(ice_n), True, nc)
    sh = ui.font(int(rect.h * 0.62)).render(str(ice_n), True, _shade(col, 0.4))
    cx, cy = inner.centerx - rect.h * 0.04, inner.centery - rect.h * 0.02
    surf.blit(sh, sh.get_rect(center=(cx + 2, cy + 2)))
    surf.blit(big, big.get_rect(center=(cx, cy)))
    rc = ORANGE if rock_n else (150, 120, 100)
    small = ui.font(max(16, int(rect.h * 0.3))).render(str(rock_n), True, rc)
    sr = small.get_rect(bottomright=(inner.right - 4, inner.bottom - 2))
    surf.blit(small, sr)
    k = max(5, int(rect.h * 0.1))
    tx, ty = sr.x - k - 3, sr.bottom - 5
    pygame.draw.polygon(surf, rc, [(tx, ty), (tx + k * 0.55, ty - k), (tx + k * 1.1, ty)], 2)
    if survey:
        _txt(surf, "SURVEY" if rect.h >= 56 else "S", 15, CYAN, (inner.x + 4, inner.y + 3))


def _draw_crystal(surf, cx, cy, s):
    def poly(pts, col, w=0):
        pygame.draw.polygon(surf, col, [(cx + px * s, cy + py * s) for px, py in pts], w)
    poly([(-0.98, 0.7), (-0.66, -0.12), (-0.3, 0.7)], (105, 195, 232))
    poly([(0.3, 0.7), (0.66, -0.05), (0.98, 0.7)], (105, 195, 232))
    poly([(-0.44, 0.82), (-0.52, -0.05), (0, -0.98), (0.52, -0.05), (0.44, 0.82)], (168, 240, 255))
    poly([(0, -0.98), (0.52, -0.05), (0.44, 0.82), (0.1, 0.82)], (112, 205, 242))
    poly([(0, -0.98), (-0.2, -0.1), (-0.06, 0.74), (-0.44, 0.82), (-0.52, -0.05)], (228, 252, 255))
    poly([(-0.44, 0.82), (-0.52, -0.05), (0, -0.98), (0.52, -0.05), (0.44, 0.82)], (40, 110, 150), 2)


def _draw_rock(surf, cx, cy, s):
    def poly(pts, col, w=0):
        pygame.draw.polygon(surf, col, [(cx + px * s, cy + py * s) for px, py in pts], w)
    poly([(-0.9, 0.55), (-0.72, -0.3), (-0.2, -0.82), (0.46, -0.66), (0.92, 0.0), (0.78, 0.62), (0.1, 0.84)],
         (116, 110, 116))
    poly([(-0.2, -0.82), (0.46, -0.66), (0.92, 0.0), (0.1, 0.1)], (150, 144, 150))
    poly([(-0.9, 0.55), (-0.72, -0.3), (-0.2, -0.82), (0.1, 0.1)], (132, 126, 132))
    poly([(0.1, 0.84), (0.78, 0.62), (0.92, 0.0), (0.1, 0.1)], (84, 78, 86))
    poly([(-0.9, 0.55), (-0.72, -0.3), (-0.2, -0.82), (0.46, -0.66), (0.92, 0.0), (0.78, 0.62), (0.1, 0.84)],
         (46, 40, 48), 2)
    pygame.draw.line(surf, (230, 70, 60), (cx - 0.1 * s, cy - 0.2 * s), (cx + 0.25 * s, cy + 0.25 * s), 2)
    pygame.draw.line(surf, (230, 70, 60), (cx + 0.25 * s, cy + 0.25 * s), (cx + 0.05 * s, cy + 0.55 * s), 2)


def _draw_ice_cell(surf, rect, t):
    r = rect.inflate(-4, -4)
    pygame.draw.rect(surf, (26, 56, 86), r, border_radius=9)
    pygame.draw.rect(surf, (52, 104, 150), r.inflate(-6, -6), border_radius=7)
    glow = pygame.Surface(r.size, pygame.SRCALPHA)
    pulse = 70 + int(40 * math.sin(t * 4))
    pygame.draw.circle(glow, (150, 240, 255, pulse), (r.w // 2, r.h // 2), int(r.w * 0.42))
    surf.blit(glow, r.topleft)
    _draw_crystal(surf, r.centerx, r.centery + 1, r.w * 0.34)
    for i, (dx, dy) in enumerate(((-0.3, -0.3), (0.32, -0.12), (-0.1, 0.34))):
        a = max(0.0, math.sin(t * 5 + i * 2.1))
        k = 1 + int(3 * a * r.w / 64)
        x, y = r.centerx + dx * r.w, r.centery + dy * r.h
        if a > 0.2:
            pygame.draw.line(surf, (255, 255, 255), (x - k, y), (x + k, y), 1)
            pygame.draw.line(surf, (255, 255, 255), (x, y - k), (x, y + k), 1)
    pygame.draw.rect(surf, (140, 230, 255), r, 2, border_radius=9)


def _draw_rock_cell(surf, rect):
    r = rect.inflate(-4, -4)
    pygame.draw.rect(surf, (34, 24, 26), r, border_radius=9)
    pygame.draw.rect(surf, (68, 48, 50), r.inflate(-6, -6), border_radius=7)
    _draw_rock(surf, r.centerx, r.centery + 1, r.w * 0.34)
    pygame.draw.rect(surf, (220, 80, 70), r, 2, border_radius=9)


# --------------------------------------------------------------------- game
class PhoenixChallenge:
    title = "Beneath the Surface"

    def __init__(self, eq=None, on_complete=None):
        self.eq = eq
        self.on_complete = on_complete
        self.bg = _background()
        self.reset(show_briefing=True)

    # ------------------------------------------------------------ state reset
    def reset(self, show_briefing=True):
        """Full reset of the minigame; generate fresh layouts for a new run/retry."""
        # Layouts are cached while a run is in progress so each stage stays
        # consistent. Clear the cache here so a retry/new game gets new layouts.
        _LAYOUTS.clear()
        self.t = 0.0
        self.score = 0
        self.shown_score = 0.0
        self.ice_total = 0
        self.rocks_total = 0
        self.stages_cleared = 0
        self.stage_log = []
        self.won = False
        self.fail_stage = None
        self.fail_reason = ""
        self.particles, self.floaters = [], []
        self.shake = 0.0
        self.flash_int = 0.0
        self.pending = None
        self.page = 0
        self.in_help = False
        self.help_return = None
        self.buttons = None
        self.end_buttons = None
        self.msg, self.msg_col = "", TEXT
        self._begin_stage(0)
        if show_briefing:
            self.phase = "briefing"
            self._brief_buttons()

    def _begin_stage(self, i):
        """Load a stage and reset ALL stage-specific resources."""
        st = STAGES[i]
        lay = build_layout(i)
        n = st["size"]
        self.stage_i, self.st = i, st
        self.n = n
        self.kind, self.ice_n, self.rock_n = lay["kind"], lay["ice_n"], lay["rock_n"]
        self.total_ice, self.total_rocks = st["ice"], st["rocks"]
        self.revealed = [[False] * n for _ in range(n)]
        self.flags = [[False] * n for _ in range(n)]
        self.anim = [[None] * n for _ in range(n)]
        self.start = lay["start"]
        self.revealed[self.start[0]][self.start[1]] = True
        self.integrity = MAX_INTEGRITY
        self.energy = st["energy"]
        self.disp_int = float(MAX_INTEGRITY)
        self.ice_found = 0
        self.rocks_stage = 0
        self.stage_points = 0
        self.cleared = False
        self.bonus = False
        self.bonus_done = False
        self.all_ice_awarded = False
        self.cell = st["cell"]
        w = n * self.cell
        self.gx, self.gy = AREA.centerx - w // 2, AREA.centery - w // 2
        self.cursor = (n // 2, n // 2)
        self.last_dig = None
        self.pending = None
        rng = random.Random(1000 + i)
        self.vars = [[rng.randint(-2, 2) for _ in range(n)] for _ in range(n)]
        self.specks = [[[(rng.random() * 0.8 + 0.1, rng.random() * 0.8 + 0.1, rng.randint(1, 3),
                          rng.choice((0.8, 0.9, 1.12))) for _ in range(5)] for _ in range(n)]
                       for _ in range(n)]
        self._say("Survey site scanned. Use its clues to find safe cells.", CYAN)
        self.phase = "intro"
        self.buttons = ui.ButtonRow(["BEGIN EXCAVATION"], 392, w=330)

    def _say(self, text, col=TEXT):
        self.msg, self.msg_col = text, col

    # -------------------------------------------------------------- geometry
    def _cell_rect(self, r, c, off=(0, 0)):
        return pygame.Rect(self.gx + c * self.cell + off[0], self.gy + r * self.cell + off[1], self.cell, self.cell)

    def _cell_at(self, pos):
        x, y = pos[0] - self.gx, pos[1] - self.gy
        if 0 <= x < self.n * self.cell and 0 <= y < self.n * self.cell:
            return y // self.cell, x // self.cell
        return None

    # ----------------------------------------------------------- core action
    def _add_points(self, pts, pos, label=None):
        before = self.score
        self.score = max(0, self.score + pts)          # score never goes below zero
        real = self.score - before
        self.stage_points += real
        col = GREEN if pts > 0 else RED
        self.floaters.append([label or ("%+d" % pts), pos[0], pos[1], 1.4, col, 34 if pts > 0 else 30])

    def dig(self, r, c):
        """Excavate one cell. Returns True if an excavation happened."""
        if self.phase != "playing":
            return False
        if self.revealed[r][c] or self.flags[r][c] or self.energy <= 0:
            return False                                # no duplicates, no negative energy
        self.energy = max(0, self.energy - 1)
        self.revealed[r][c] = True
        self.anim[r][c] = self.t
        self.last_dig = (r, c, self.t)
        rect = self._cell_rect(r, c)
        pos = rect.center
        k = self.kind[r][c]
        if k == "I":
            self.ice_found += 1
            self.ice_total += 1
            self._add_points(POINTS["ice"], pos)
            self._spark(pos, (150, 240, 255), 26)
            self._say("WATER ICE recovered!  +%d" % POINTS["ice"], ICE_COL)
        elif k == "R":
            self.rocks_stage += 1
            self.rocks_total += 1
            self.integrity = max(0, self.integrity - self.st["damage"])
            self._add_points(POINTS["rock"], pos)
            self.shake, self.flash_int = 0.22, 0.35
            self._spark(pos, (255, 150, 70), 16)
            self._dust(pos, (110, 104, 110), 10)
            self._say("ROCK STRIKE!  Arm integrity -%d%%" % self.st["damage"], RED)
        else:
            self._dust(pos, PIT[min(self.ice_n[r][c], 3)], 16)
            self._say("Soil sample: %d ice, %d rock nearby." % (self.ice_n[r][c], self.rock_n[r][c]), TEXT)
        self._check_state(pos)
        return True

    def toggle_flag(self, r, c):
        if self.phase == "playing" and not self.revealed[r][c]:
            self.flags[r][c] = not self.flags[r][c]

    def _check_state(self, pos):
        if not self.cleared:
            if self.ice_found >= self.st["target"]:
                self.cleared = True
                self.stages_cleared += 1
                self._add_points(POINTS["stage"], (pos[0], pos[1] - 26), "+%d STAGE" % POINTS["stage"])
                self._say("ICE TARGET REACHED - stage secured!", GREEN)
                self._check_all_ice(pos)
                self._resolve("cleared", RESOLVE_DELAY)
            elif self.integrity <= 0:
                self._fail("Equipment integrity reached zero - the robotic arm is destroyed.")
            elif self.energy <= 0:
                self._fail("Digging energy ran out before the ice target was reached.")
        else:                                           # bonus digging: can never cause a failure
            self._check_all_ice(pos)
            if self.all_ice_awarded or self.integrity <= 0 or self.energy <= 0:
                self.bonus_done = True
                self._resolve("cleared", RESOLVE_DELAY)

    def _check_all_ice(self, pos):
        if not self.all_ice_awarded and self.ice_found >= self.total_ice:
            self.all_ice_awarded = True
            self._add_points(POINTS["all_ice"], (pos[0], pos[1] - 54), "+%d ALL ICE" % POINTS["all_ice"])
            self._say("ALL ICE DISCOVERED!  +%d bonus" % POINTS["all_ice"], AMBER)

    def _fail(self, reason):
        self.fail_stage = self.stage_i
        self.fail_reason = reason
        self._resolve("gameover", RESOLVE_DELAY + 0.3)

    def _resolve(self, nxt, delay):
        self.phase = "resolving"
        self.pending = [nxt, delay]

    def _enter_cleared(self):
        can_bonus = (self.ice_found < self.total_ice and self.energy > 0
                     and self.integrity > 0 and not self.bonus_done)
        last = self.stage_i == len(STAGES) - 1
        labels = (["BONUS DIG"] if can_bonus else []) + ["FINISH MISSION" if last else "NEXT STAGE"]
        self.can_bonus = can_bonus
        self.buttons = ui.ButtonRow(labels, 372, w=250)
        self.phase = "cleared"

    def _enter_gameover(self):
        self.end_buttons = ui.ButtonRow(["RETRY"], 392, w=260)
        self.phase = "gameover"

    def _leave_stage(self):
        self.stage_log.append(dict(stage=self.stage_i + 1, name=self.st["name"], ice=self.ice_found,
                                   rocks=self.rocks_stage, integrity=self.integrity, energy=self.energy,
                                   points=self.stage_points, all_ice=self.all_ice_awarded))
        if self.stage_i < len(STAGES) - 1:
            self._begin_stage(self.stage_i + 1)
        else:
            self.won = True
            self.end_buttons = ui.ButtonRow(["CONTINUE"], 462, w=260)
            self.phase = "victory"

    def get_result(self):
        return dict(completed=self.won, score=self.score, rank=rank_for(self.score),
                    ice_collected=self.ice_total, rocks_hit=self.rocks_total,
                    integrity=self.integrity, energy=self.energy,
                    stages_cleared=self.stages_cleared, stage_log=list(self.stage_log))

    # ---------------------------------------------------------------- effects
    def _dust(self, pos, col, n):
        for _ in range(n):
            a = random.uniform(0, math.tau)
            sp = random.uniform(30, 150)
            self.particles.append([pos[0], pos[1], math.cos(a) * sp, math.sin(a) * sp - 40,
                                   random.uniform(0.35, 0.8), 0.8, _shade(col, random.uniform(0.9, 1.5)),
                                   random.randint(2, 5)])

    def _spark(self, pos, col, n):
        for _ in range(n):
            a = random.uniform(0, math.tau)
            sp = random.uniform(80, 260)
            self.particles.append([pos[0], pos[1], math.cos(a) * sp, math.sin(a) * sp - 60,
                                   random.uniform(0.4, 0.9), 0.9, col, random.randint(2, 4)])

    # ------------------------------------------------------------------ input
    def _brief_buttons(self):
        resume = "RESUME" if self.in_help else "START"
        self.buttons = ui.ButtonRow(["NEXT"] if self.page == 0 else ["BACK", resume], 478, w=230)

    def _open_help(self):
        self.help_return = self.phase
        self.in_help, self.page = True, 0
        self.phase = "briefing"
        self._brief_buttons()

    def handle_event(self, e):
        ph = self.phase
        if ph == "briefing":
            i = self.buttons.handle_event(e)
            if i is not None:
                if self.page == 0:
                    self.page = 1
                elif i == 0:
                    self.page = 0
                elif self.in_help:
                    self.in_help, self.phase = False, self.help_return
                    if self.phase == "intro":
                        self.buttons = ui.ButtonRow(["BEGIN EXCAVATION"], 392, w=330)
                else:
                    self.phase = "intro"
                    self.buttons = ui.ButtonRow(["BEGIN EXCAVATION"], 392, w=330)
                if self.phase == "briefing":
                    self._brief_buttons()
        elif ph == "intro":
            if e.type == pygame.KEYDOWN and e.key == pygame.K_h:
                self._open_help()
            elif self.buttons.handle_event(e) == 0:
                self.phase = "playing"
                self._say("Dig a safe cell next to the survey site.", CYAN)
        elif ph == "playing":
            self._handle_play(e)
        elif ph == "cleared":
            i = self.buttons.handle_event(e)
            if i is not None:
                if self.can_bonus and i == 0:
                    self.bonus = True
                    self.phase = "playing"
                    self._say("BONUS DIG: find the remaining ice (no failure possible).", AMBER)
                else:
                    self._leave_stage()
        elif ph == "gameover":
            if self.end_buttons.handle_event(e) == 0:
                self.reset(show_briefing=False)          # RETRY: full reset, back to stage 1
        elif ph == "victory":
            if self.end_buttons.handle_event(e) == 0:
                if self.on_complete:
                    self.on_complete(self.get_result())
                return "done"                            # -> existing Memory Capsule flow
        return None

    def _handle_play(self, e):
        if e.type == pygame.MOUSEMOTION:
            hit = self._cell_at(e.pos)
            if hit:
                self.cursor = hit
        elif e.type == pygame.MOUSEBUTTONDOWN:
            if self.bonus and e.button == 1 and FINISH_RECT.collidepoint(e.pos):
                self._finish_bonus()
                return
            hit = self._cell_at(e.pos)
            if hit:
                self.cursor = hit
                if e.button == 1:
                    self.dig(*hit)
                elif e.button == 3:
                    self.toggle_flag(*hit)
        elif e.type == pygame.KEYDOWN:
            r, c = self.cursor
            if e.key in (pygame.K_LEFT, pygame.K_a):
                c -= 1
            elif e.key in (pygame.K_RIGHT, pygame.K_d):
                c += 1
            elif e.key in (pygame.K_UP, pygame.K_w):
                r -= 1
            elif e.key in (pygame.K_DOWN, pygame.K_s):
                r += 1
            elif e.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE, pygame.K_e):
                self.dig(*self.cursor)
            elif e.key == pygame.K_f:
                self.toggle_flag(*self.cursor)
            elif e.key == pygame.K_h:
                self._open_help()
            elif e.key == pygame.K_n and self.bonus:
                self._finish_bonus()
            self.cursor = (max(0, min(self.n - 1, r)), max(0, min(self.n - 1, c)))

    def _finish_bonus(self):
        self.bonus_done = True
        self._enter_cleared()

    # ----------------------------------------------------------------- update
    def update(self, dt):
        dt = min(dt, 0.05)
        self.t += dt
        self.shake = max(0.0, self.shake - dt)
        self.flash_int = max(0.0, self.flash_int - dt)
        self.disp_int += (self.integrity - self.disp_int) * min(1.0, dt * 8)
        self.shown_score += (self.score - self.shown_score) * min(1.0, dt * 7)
        if abs(self.shown_score - self.score) < 1:
            self.shown_score = float(self.score)
        for p in self.particles:
            p[0] += p[2] * dt
            p[1] += p[3] * dt
            p[3] += 380 * dt
            p[4] -= dt
        self.particles = [p for p in self.particles if p[4] > 0]
        for f in self.floaters:
            f[2] -= 38 * dt
            f[3] -= dt
        self.floaters = [f for f in self.floaters if f[3] > 0]
        if self.phase == "resolving" and self.pending:
            self.pending[1] -= dt
            if self.pending[1] <= 0:
                nxt, self.pending = self.pending[0], None
                if nxt == "cleared":
                    self._enter_cleared()
                else:
                    self._enter_gameover()

    # ------------------------------------------------------------------- draw
    def draw(self, surf):
        surf.blit(self.bg, (0, 0))
        if self.phase == "briefing":
            self._dim(surf, 120)
            self._draw_briefing(surf)
            return
        self._draw_top(surf)
        self._draw_grid(surf)
        self._draw_side(surf)
        self._draw_bar(surf)
        self._draw_effects(surf)
        if self.phase in ("intro", "cleared", "gameover", "victory"):
            self._dim(surf, 150)
            getattr(self, "_draw_" + self.phase)(surf)

    @staticmethod
    def _dim(surf, a):
        d = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
        d.fill((6, 8, 14, a))
        surf.blit(d, (0, 0))

    # --- scene
    def _draw_top(self, surf):
        ui.draw_panel(surf, TOP, 215)
        _txt(surf, "PHOENIX", 40, CYAN, (30, 12))
        _txt(surf, "BENEATH THE SURFACE", 22, DIM, (32, 44))
        for i in range(len(STAGES)):
            rc = pygame.Rect(300 + i * 34, 22, 26, 26)
            done = i < self.stage_i or (i == self.stage_i and self.cleared)
            pygame.draw.rect(surf, (30, 70, 50) if done else (16, 26, 36), rc, border_radius=5)
            pygame.draw.rect(surf, GREEN if done else (CYAN if i == self.stage_i else DIM), rc, 2, border_radius=5)
            _txt(surf, str(i + 1), 24, GREEN if done else TEXT, rc.center, "center")
        _txt(surf, "STAGE %d / %d" % (self.stage_i + 1, len(STAGES)), 30, TEXT, (420, 14))
        _txt(surf, "%s  -  %s" % (self.st["name"], self.st["level"]), 22, AMBER, (420, 42))
        _txt(surf, "SCORE", 20, DIM, (TOP.right - 18, 12), "topright")
        _txt(surf, "{:,}".format(int(round(self.shown_score))), 40, AMBER, (TOP.right - 18, 26), "topright")

    def _draw_grid(self, surf):
        off = (0, 0)
        if self.shake > 0:
            m = 7 * self.shake / 0.35
            off = (random.uniform(-m, m), random.uniform(-m, m))
        n, cs = self.n, self.cell
        board = pygame.Rect(self.gx, self.gy, n * cs, n * cs).inflate(14, 14)
        ui.draw_panel(surf, board.move(*off), 150)
        for i in range(n):                                       # coordinate labels
            _txt(surf, chr(65 + i), 16, DIM, (self.gx + i * cs + cs // 2 + off[0], board.y + 1), "midtop")
            _txt(surf, str(i + 1), 16, DIM, (board.x + 2 + off[0], self.gy + i * cs + cs // 2 + off[1]), "midleft")
        hovering = self.phase == "playing"
        for r in range(n):
            for c in range(n):
                rect = self._cell_rect(r, c, off)
                a = self.anim[r][c]
                if not self.revealed[r][c]:
                    _draw_hidden_tile(surf, rect, self.vars[r][c], self.specks[r][c],
                                      hover=hovering and self.cursor == (r, c), flag=self.flags[r][c])
                    continue
                k = self.kind[r][c]
                if k == "I":
                    _draw_ice_cell(surf, rect, self.t)
                elif k == "R":
                    _draw_rock_cell(surf, rect)
                else:
                    _draw_pit(surf, rect, self.ice_n[r][c], self.rock_n[r][c], (r, c) == self.start)
                if a is not None and self.t - a < DIG_TIME:       # dust cover shrinking away
                    p = (self.t - a) / DIG_TIME
                    tile = pygame.Surface(rect.size, pygame.SRCALPHA)
                    _draw_hidden_tile(tile, tile.get_rect(), self.vars[r][c], self.specks[r][c])
                    s = max(2, int(cs * (1 - p * 0.55)))
                    tile = pygame.transform.smoothscale(tile, (s, s))
                    tile.set_alpha(int(255 * (1 - p)))
                    surf.blit(tile, tile.get_rect(center=rect.center))
                    if k == "I":
                        ring = pygame.Surface(rect.size, pygame.SRCALPHA)
                        pygame.draw.circle(ring, (170, 245, 255, int(200 * (1 - p))), (cs // 2, cs // 2),
                                           int(cs * (0.2 + 0.5 * p)), 3)
                        surf.blit(ring, rect.topleft)
                    elif k == "R":
                        fl = pygame.Surface(rect.size, pygame.SRCALPHA)
                        fl.fill((255, 60, 50, int(150 * (1 - p))))
                        surf.blit(fl, rect.topleft)
        if hovering and not self.revealed[self.cursor[0]][self.cursor[1]]:
            self._draw_cursor(surf, self._cell_rect(*self.cursor, off))
        if self.last_dig and self.t - self.last_dig[2] < DIG_TIME + 0.05:
            self._draw_arm(surf, self._cell_rect(self.last_dig[0], self.last_dig[1], off), self.t - self.last_dig[2])

    def _draw_cursor(self, surf, rect):
        k, L = 4 + int(2 * math.sin(self.t * 6)), max(10, rect.w // 4)
        r = rect.inflate(-2 + k // 2, -2 + k // 2)
        for (x, y, dx, dy) in ((r.left, r.top, 1, 1), (r.right, r.top, -1, 1),
                               (r.left, r.bottom, 1, -1), (r.right, r.bottom, -1, -1)):
            pygame.draw.line(surf, CYAN, (x, y), (x + dx * L, y), 3)
            pygame.draw.line(surf, CYAN, (x, y), (x, y + dy * L), 3)

    def _draw_arm(self, surf, rect, age):
        """Phoenix's robotic arm drilling into the cell."""
        p = min(1.0, age / DIG_TIME)
        cx = rect.centerx
        tip = rect.centery - 18 + 12 * math.sin(p * math.pi * 7) ** 2 - 14 * (1 - p)
        low = self.integrity <= self.st["damage"]
        col = (190, 200, 210)
        base = (cx, AREA.y - 2)
        elbow = (cx + 26, (base[1] + tip) / 2 - 8)
        pygame.draw.line(surf, _shade(col, 0.5), base, elbow, 9)
        pygame.draw.line(surf, _shade(col, 0.5), elbow, (cx, tip), 9)
        pygame.draw.line(surf, col, base, elbow, 5)
        pygame.draw.line(surf, col, elbow, (cx, tip), 5)
        for pt in (base, elbow):
            pygame.draw.circle(surf, (70, 80, 92), pt, 7)
            pygame.draw.circle(surf, (210, 220, 230), pt, 4)
        pygame.draw.polygon(surf, (255, 190, 80), [(cx - 8, tip), (cx + 8, tip), (cx, tip + 18)])
        pygame.draw.polygon(surf, (120, 90, 50), [(cx - 8, tip), (cx + 8, tip), (cx, tip + 18)], 2)
        if low and int(age * 30) % 2 == 0:
            pygame.draw.line(surf, (255, 240, 120), (cx + 8, tip + 4), (cx + 18, tip - 2), 2)

    def _draw_effects(self, surf):
        for x, y, _, _, life, mx, col, sz in self.particles:
            a = max(0, min(255, int(255 * life / mx)))
            dot = pygame.Surface((sz * 2, sz * 2), pygame.SRCALPHA)
            pygame.draw.circle(dot, (*col, a), (sz, sz), sz)
            surf.blit(dot, (x - sz, y - sz))
        for text, x, y, life, col, size in self.floaters:
            t = ui.font(size).render(text, True, col)
            sh = ui.font(size).render(text, True, (20, 12, 12))
            t.set_alpha(int(255 * min(1.0, life / 0.6)))
            sh.set_alpha(t.get_alpha())
            surf.blit(sh, sh.get_rect(center=(x + 2, y + 2)))
            surf.blit(t, t.get_rect(center=(x, y)))

    # --- side panel
    def _draw_side(self, surf):
        ui.draw_panel(surf, SIDE, 215)
        sx, W = SIDE.x + 18, SIDE.w - 36
        y = SIDE.y + 12
        # active objective first and most prominent
        _txt(surf, "OBJECTIVE", 22, AMBER, (sx, y))
        _txt(surf, "Recover %d ice" % self.st["target"], 30, GREEN if self.cleared else ICE_COL,
             (sx + W, y + 2), "topright")
        _txt(surf, "avoid rocks and stay powered", 18, DIM, (sx, y + 28))
        # water ice
        _txt(surf, "WATER ICE", 24, DIM, (sx, y + 54))
        _txt(surf, "%d / %d" % (min(self.ice_found, self.st["target"]), self.st["target"]), 38,
             GREEN if self.cleared else ICE_COL, (sx + W, y + 50), "topright")
        for k in range(self.st["target"]):
            cx = sx + 16 + k * 36
            if k < self.ice_found:
                _draw_crystal(surf, cx, y + 98, 13)
            else:
                pygame.draw.polygon(surf, (70, 100, 120), [(cx, y + 85), (cx + 8, y + 97), (cx + 6, y + 110),
                                                           (cx - 6, y + 110), (cx - 8, y + 97)], 2)
        if self.ice_found > self.st["target"]:
            _txt(surf, "+%d bonus" % (self.ice_found - self.st["target"]), 22, AMBER,
                 (sx + 20 + self.st["target"] * 36, y + 96))
        _txt(surf, "Survey: %d ice deposits, %d rocks buried" % (self.total_ice, self.total_rocks), 18, DIM,
             (sx, y + 122))
        # integrity
        y += 100
        _txt(surf, "ROBOTIC ARM INTEGRITY", 24, DIM, (sx, y))
        pct = int(round(self.integrity))
        ic = GREEN if pct > 60 else (AMBER if pct > 30 else RED)
        _txt(surf, "%d%%" % pct, 30, ic, (sx + W, y - 3), "topright")
        bar = pygame.Rect(sx, y + 28, W, 22)
        pygame.draw.rect(surf, (14, 20, 28), bar, border_radius=5)
        fill = bar.copy()
        fill.w = int(W * max(0.0, self.disp_int) / MAX_INTEGRITY)
        if fill.w > 0:
            pygame.draw.rect(surf, ic, fill, border_radius=5)
        if self.flash_int > 0 and int(self.t * 20) % 2 == 0:
            pygame.draw.rect(surf, (255, 255, 255), bar, 3, border_radius=5)
        else:
            pygame.draw.rect(surf, (60, 90, 100), bar, 2, border_radius=5)
        _txt(surf, "Each rock strike: -%d%% integrity" % self.st["damage"], 20, DIM, (sx, y + 54))
        # energy
        y += 84
        _txt(surf, "DIGGING ENERGY", 24, DIM, (sx, y))
        _txt(surf, "%d / %d" % (self.energy, self.st["energy"]), 30, AMBER if self.energy > 3 else RED,
             (sx + W, y - 3), "topright")
        mx = self.st["energy"]
        gap = 3
        seg = (W - gap * (mx - 1)) / mx
        for i in range(mx):
            rc = pygame.Rect(int(sx + i * (seg + gap)), y + 28, max(2, int(seg)), 22)
            on = i < self.energy
            pygame.draw.rect(surf, AMBER if on else (26, 30, 36), rc, border_radius=3)
            pygame.draw.rect(surf, (255, 220, 140) if on else (60, 64, 70), rc, 1, border_radius=3)
        _txt(surf, "1 energy per dig - no recharge", 20, DIM, (sx, y + 54))
        # soil key
        y += 84
        _txt(surf, "SOIL KEY  (colour = ice nearby)", 22, DIM, (sx, y))
        for i in range(4):
            rc = pygame.Rect(sx + i * 108, y + 22, 40, 40)
            _draw_pit(surf, rc, i, 0)
            _txt(surf, PIT_NAMES[i], 19, TEXT, (rc.right + 2, rc.centery - 8))
        _txt(surf, "Big number = ICE in 8 surrounding cells", 20, ICE_COL, (sx, y + 68))
        _txt(surf, "Small orange = ROCKS in 8 surrounding cells", 20, ORANGE, (sx, y + 88))
        if self.bonus and self.phase == "playing":
            ui.draw_panel(surf, FINISH_RECT, 245)
            _txt(surf, "FINISH STAGE  [N]", 26, AMBER, FINISH_RECT.center, "center")

    def _draw_bar(self, surf):
        ui.draw_panel(surf, BAR, 215)
        _txt(surf, self.msg, 24, self.msg_col, (28, BAR.centery), "midleft")
        _txt(surf, "CLICK/ENTER dig    RIGHT-CLICK/F flag    H help", 20, DIM, (BAR.right - 16, BAR.centery), "midright")

    # --- overlay panels
    def _draw_intro(self, surf):
        st = self.st
        r = ui.center_panel(surf, 660, 390)
        ui.draw_title(surf, "STAGE %d - %s" % (self.stage_i + 1, st["name"]), r.y + 18, 46)
        ui.draw_title(surf, "DIFFICULTY: %s" % st["level"], r.y + 64, 28, AMBER)
        rows = [("Excavation grid", "%d x %d" % (st["size"], st["size"])),
                ("Ice target to clear stage", "%d water ice" % st["target"]),
                ("Hidden in this region", "%d ice deposits, %d rocks" % (st["ice"], st["rocks"])),
                ("Digging energy", "%d digs (no recharge)" % st["energy"]),
                ("Arm integrity", "100%%  (rock strike -%d%%)" % st["damage"])]
        y = r.y + 108
        for a, b in rows:
            _txt(surf, a, 28, DIM, (r.x + 60, y))
            _txt(surf, b, 28, TEXT, (r.right - 60, y), "topright")
            y += 38
        ui.draw_title(surf, "A free survey scan marks your starting cell.", y + 6, 24, CYAN)
        self.buttons.draw(surf)
        ui.draw_title(surf, "Press H for the instructions", r.bottom - 30, 22, DIM)

    def _draw_cleared(self, surf):
        r = ui.center_panel(surf, 620, 340)
        ui.draw_title(surf, "STAGE %d COMPLETE" % (self.stage_i + 1), r.y + 18, 56, GREEN)
        y = r.y + 88
        for a, b, col in ((("Water ice recovered"), "%d / %d" % (self.ice_found, self.total_ice), ICE_COL),
                          ("Rocks struck", str(self.rocks_stage), ORANGE if self.rocks_stage else TEXT),
                          ("Stage points", "{:,}".format(self.stage_points), AMBER),
                          ("Energy left", "%d / %d" % (self.energy, self.st["energy"]), TEXT)):
            _txt(surf, a, 28, DIM, (r.x + 70, y))
            _txt(surf, b, 28, col, (r.right - 70, y), "topright")
            y += 36
        if self.all_ice_awarded:
            ui.draw_title(surf, "ALL ICE DISCOVERED  +%d" % POINTS["all_ice"], y + 4, 28, AMBER)
        elif self.can_bonus:
            ui.draw_title(surf, "Bonus dig: find ALL the ice for +%d (no failure risk)" % POINTS["all_ice"],
                          y + 4, 24, DIM)
        self.buttons.draw(surf)

    def _draw_gameover(self, surf):
        r = ui.center_panel(surf, 700, 400)
        ui.draw_title(surf, "GAME OVER", r.y + 18, 76, RED)
        fs = STAGES[self.fail_stage]
        ui.draw_title(surf, "Failed: Stage %d - %s" % (self.fail_stage + 1, fs["name"]), r.y + 100, 30, TEXT)
        ui.draw_wrapped(surf, self.fail_reason, 26, r.inflate(-80, 0), r.y + 140, DIM)
        ui.draw_title(surf, "Score: {:,}".format(self.score), r.y + 206, 46, AMBER)
        ui.draw_title(surf, "Ice this stage: %d / %d      Energy left: %d      Integrity: %d%%"
                      % (self.ice_found, fs["target"], self.energy, self.integrity), r.y + 262, 24, DIM)
        self.end_buttons.draw(surf)

    def _draw_victory(self, surf):
        r = ui.center_panel(surf, 720, 470)
        ui.draw_title(surf, "MISSION COMPLETE", r.y + 14, 60, GREEN)
        ui.draw_title(surf, "All three excavation sites cleared", r.y + 70, 26, DIM)
        rank = rank_for(self.score)
        rc = {"S": AMBER, "A": GREEN, "B": ICE_COL, "C": TEXT}[rank]
        ui.draw_title(surf, "RANK  %s" % rank, r.y + 100, 78, rc)
        ui.draw_title(surf, "Final score: {:,}".format(self.score), r.y + 180, 42, AMBER)
        rows = [("Total ice collected", str(self.ice_total), ICE_COL),
                ("Rocks encountered", str(self.rocks_total), ORANGE if self.rocks_total else TEXT),
                ("Arm integrity remaining", "%d%%" % self.integrity, TEXT),
                ("Digging energy remaining", "%d / %d" % (self.energy, self.st["energy"]), TEXT)]
        y = r.y + 240
        for a, b, col in rows:
            _txt(surf, a, 28, DIM, (r.x + 110, y))
            _txt(surf, b, 28, col, (r.right - 110, y), "topright")
            y += 36
        ui.draw_title(surf, "Integrity / energy shown for the final stage", y + 2, 20, DIM)
        self.end_buttons.draw(surf)

    # --- instructions
    def _draw_briefing(self, surf):
        r = ui.center_panel(surf, 900, 500)
        if self.page == 0:
            self._brief_page_1(surf, r)
        else:
            self._brief_page_2(surf, r)
        _txt(surf, "PAGE %d / 2" % (self.page + 1), 20, DIM, (r.right - 22, r.y + 14), "topright")
        self.buttons.draw(surf)

    def _brief_page_1(self, surf, r):
        ui.draw_title(surf, "PHOENIX - BENEATH THE SURFACE", r.y + 14, 50)
        ui.draw_title(surf, "North Polar Region", r.y + 58, 24, DIM)
        ui.draw_wrapped(surf, "Objective: recover WATER ICE and avoid dug rocks. Use the clues, but keep digging safe.",
                        26, r.inflate(-120, 0), r.y + 90, AMBER)
        x, y = r.x + 40, r.y + 150
        _txt(surf, "HIDDEN CELLS", 24, AMBER, (x, y))
        cs = 52
        items = [("SOIL", "Safe clue tile", "soil"),
                 ("ICE", "Target for the stage", "ice"),
                 ("ROCK", "Danger - damages the arm", "rock")]
        for i, (nm, desc, kind) in enumerate(items):
            rc = pygame.Rect(x, y + 30 + i * 56, cs, cs)
            if kind == "soil":
                _draw_pit(surf, rc, 1, 1)
            elif kind == "ice":
                _draw_ice_cell(surf, rc, self.t)
            else:
                _draw_rock_cell(surf, rc)
            _txt(surf, nm, 28, TEXT, (x + cs + 14, rc.y + 2))
            _txt(surf, desc, 20, DIM, (x + cs + 14, rc.y + 28))
        x2 = r.x + 520
        _txt(surf, "READ THE CLUES", 24, AMBER, (x2, y))
        samp = pygame.Rect(x2, y + 32, 92, 92)
        _draw_pit(surf, samp, 2, 1)
        _txt(surf, "Big cyan number = ice nearby", 22, ICE_COL, (x2 + 106, y + 38))
        _txt(surf, "Small orange number = rocks nearby", 22, ORANGE, (x2 + 106, y + 70))
        _txt(surf, "Soil gets wetter as the ice count rises", 22, DIM, (x2, y + 112))
        for i in range(4):
            rc = pygame.Rect(x2 + i * 84, y + 140, 44, 44)
            _draw_pit(surf, rc, i, 0)
            _txt(surf, PIT_NAMES[i], 18, TEXT, (rc.centerx, rc.bottom + 4), "midtop")
        ui.draw_wrapped(surf, "Right-click or press F to flag a risky tile. Flags cannot be dug.",
                        22, r.inflate(-110, 0), r.bottom - 78, CYAN)

    def _brief_page_2(self, surf, r):
        ui.draw_title(surf, "RESOURCES & TIPS", r.y + 14, 46)
        x, y = r.x + 40, r.y + 64
        _txt(surf, "ARM INTEGRITY", 22, GREEN, (x, y))
        _txt(surf, "Each rock hit hurts the arm. Zero integrity ends the run.", 21, TEXT, (x + 200, y))
        _txt(surf, "DIGGING ENERGY", 22, AMBER, (x, y + 30))
        _txt(surf, "Every dig costs 1. Run out and the mission fails.", 21, TEXT, (x + 200, y + 30))
        _txt(surf, "CHOOSE SMARTLY", 22, ICE_COL, (x, y + 68))
        _txt(surf, "Clear the stage target and you may keep digging for bonus ice.", 21, TEXT, (x + 200, y + 68))
        y2 = y + 120
        _txt(surf, "STAGE GOAL", 24, AMBER, (x, y2))
        for i, st in enumerate(STAGES):
            _txt(surf, "%d. %s" % (i + 1, st["name"]), 20, TEXT, (x + 20, y2 + 28 + i * 24))
            _txt(surf, "target %d ice" % st["target"], 20, DIM, (x + 260, y2 + 28 + i * 24))
        _txt(surf, "SCORING", 24, AMBER, (x + 470, y2))
        for i, (a, b) in enumerate([("ice", "+500"), ("stage", "+500"), ("all ice", "+300"), ("rock", "-200")]):
            cx = x + 470
            cy = y2 + 30 + i * 24
            _txt(surf, a, 20, TEXT, (cx, cy))
            _txt(surf, b, 20, RED if b.startswith("-") else GREEN, (cx + 140, cy), "topright")
        ui.draw_wrapped(surf, "The main objective is always the same: recover enough ice, then keep the arm and power alive.",
                        22, r.inflate(-110, 0), y2 + 122, CYAN)


# ------------------------------------------------------- standalone runners
def play(screen, clock=None, on_complete=None):
    """Blocking loop for easy integration/testing. Returns the result dict on
    victory, or None if the window is closed / ESC is pressed."""
    clock = clock or pygame.time.Clock()
    game = PhoenixChallenge(on_complete=on_complete)
    while True:
        dt = clock.tick(60) / 1000
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT or (ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE):
                return None
            if game.handle_event(ev) == "done":
                return game.get_result()
        game.update(dt)
        game.draw(screen)
        pygame.display.flip()


if __name__ == "__main__":
    pygame.init()
    pygame.display.set_caption("Phoenix - Beneath the Surface (standalone)")
    scr = pygame.display.set_mode((SCREEN_W, SCREEN_H))
    res = play(scr)
    if res:
        print("VICTORY -> Memory Capsule would be granted here.", res)
    pygame.quit()
