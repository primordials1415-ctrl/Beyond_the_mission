"""Spirit & Opportunity minigame - TWIN TRAILS (Game 4).

Cooperative grid puzzle in a collapsed Martian cave. The player switches between
Spirit and Opportunity (identical abilities), pushes rocks, holds pressure plates
and opens doors until BOTH rovers stand on the two exit tiles. Three hand-built,
solver-verified stages (no random generation).

Plugs into the existing challenge interface (same as Viking / Insight / Ingenuity):
    TwinTrailsChallenge(eq)  -> handle_event(e) returns "done" ONLY after all three
                                stages are cleared and the player presses CONTINUE
                                (EncounterScene then runs the normal Memory Capsule flow),
                                update(dt), draw(surf), title attribute.
Completion result: `challenge.result` (dict, None until victory) and the optional
`on_complete(result)` callback (fired once, when the player presses CONTINUE).

Register for BOTH robots (see puzzle.py):
    from twin_trails import TwinTrailsChallenge
    CHALLENGES["spirit"] = TwinTrailsChallenge
    CHALLENGES["opportunity"] = TwinTrailsChallenge

Standalone test:  python twin_trails.py
"""
import math
import random

import pygame

try:                                   # project constants when run inside the game
    from settings import SCREEN_W, SCREEN_H
except ImportError:                    # standalone fallback
    SCREEN_W, SCREEN_H = 960, 540

# ======================================================================== LOGIC
# (pure rules, no pygame: this is what the solver verified)
DIRS = {"up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0)}
ROVERS = ("spirit", "opportunity")

# Legend: # wall  % rubble (wall)  . floor  S/O rover starts  r rock  E exit
#         a-d pressure plates   A-D doors (a door is open while EVERY plate with
#         the same letter is pressed by a rover or a rock; a door never closes
#         on a rover/rock standing in it).
LEVELS = [
    dict(name="THE COLLAPSE", level="EASY", opt=28, par=36, hint="Hold a plate so your partner can pass.",
         rows=[
             "############",
             "#S...#....E#",
             "#.a..A.....#",
             "#....#.r.b.#",
             "#....B.....#",
             "#O...#....E#",
             "############"]),
    dict(name="BLOCKED PASSAGE", level="MEDIUM", opt=34, par=44, hint="Doors need BOTH plates pressed. Rocks count.",
         rows=[
             "#############",
             "#.....#.....#",
             "#.a...A..r.b#",
             "#.....#.r...#",
             "#..r..##.####",
             "#.....#....E#",
             "#....a#.....#",
             "#S.O..B....E#",
             "#############"]),
    dict(name="THE ESCAPE", level="HARD", opt=46, par=60, hint="Every mechanism is linked. Plan the whole route.",
         rows=[
             "################",
             "#.....#.....####",
             "#.a...A.r...####",
             "#..r..#.....#.E#",
             "#...a.#...r.C.d#",
             "#....c#...c.#.E#",
             "#.....B.b...D..#",
             "#S.O..#.....####",
             "################"]),
]


class Board:
    """Static layout + pure rules. A state is (spirit_pos, opp_pos, frozenset(rocks))."""

    def __init__(self, spec):
        rows = spec["rows"]
        self.h, self.w = len(rows), len(rows[0])
        self.walls, self.rubble, self.exits = set(), set(), []
        self.plates, self.doors = {}, {}
        rocks, s, o = set(), None, None
        for y, row in enumerate(rows):
            assert len(row) == self.w, f"ragged row {y}"
            for x, ch in enumerate(row):
                p = (x, y)
                if ch == "#":
                    self.walls.add(p)
                elif ch == "%":
                    self.walls.add(p)
                    self.rubble.add(p)
                elif ch == "S":
                    s = p
                elif ch == "O":
                    o = p
                elif ch == "r":
                    rocks.add(p)
                elif ch == "E":
                    self.exits.append(p)
                elif ch in "abcd":
                    self.plates[p] = ch
                elif ch in "ABCD":
                    self.doors[p] = ch.lower()
        assert s and o and len(self.exits) == 2
        self.start = (s, o, frozenset(rocks))
        self.letters = {}
        for p, l in self.plates.items():
            self.letters.setdefault(l, []).append(p)
        for l in set(self.doors.values()):
            assert l in self.letters, f"door {l} has no plate"

    # ---- queries
    def pressed(self, st, p):
        return p in st[2] or p == st[0] or p == st[1]

    def letter_active(self, st, l):
        return all(self.pressed(st, p) for p in self.letters.get(l, ()))

    def door_open(self, st, p):
        """Open while its plates are held, and never closed on something standing in it."""
        return self.letter_active(st, self.doors[p]) or p in st[2] or p == st[0] or p == st[1]

    def blocked(self, st, p):
        x, y = p
        if not (0 <= x < self.w and 0 <= y < self.h) or p in self.walls:
            return True
        return p in self.doors and not self.door_open(st, p)

    def solved(self, st):
        return st[0] in self.exits and st[1] in self.exits

    # ---- rules
    def step(self, st, who, d):
        """Returns (new_state, info) or None if the move is illegal.
        info = dict(frm, to, rock=(frm, to) or None)."""
        i = ROVERS.index(who)
        pos, other = st[i], st[1 - i]
        dx, dy = DIRS[d]
        to = (pos[0] + dx, pos[1] + dy)
        if self.blocked(st, to) or to == other:
            return None
        rocks, push = st[2], None
        if to in rocks:
            dest = (to[0] + dx, to[1] + dy)
            if self.blocked(st, dest) or dest in rocks or dest == other or dest in self.exits:
                return None
            rocks = (rocks - {to}) | {dest}
            push = (to, dest)
        new = [st[0], st[1], rocks]
        new[i] = to
        return (new[0], new[1], new[2]), dict(frm=pos, to=to, rock=push)


# ========================================================================= VIEW
CYAN, TEXT, DIM, PANEL = (80, 235, 255), (225, 240, 245), (120, 150, 160), (10, 16, 26)
GOLD, GREEN, RED = (255, 205, 90), (110, 235, 150), (255, 110, 90)
ROVER_COL = {"spirit": (255, 150, 60), "opportunity": (70, 185, 255)}
ROVER_NAME = {"spirit": "SPIRIT", "opportunity": "OPPORTUNITY"}
PLATE_COL = {"a": (255, 190, 70), "b": (80, 210, 255), "c": (235, 115, 235), "d": (120, 235, 140)}
LEVEL_COL = {"EASY": GREEN, "MEDIUM": GOLD, "HARD": RED}

TOP_H, BOT_H = 64, 52
MOVE_T = 0.11            # seconds per rover step
REPEAT_DELAY = 0.28      # hold a key this long before auto-repeat starts
WIPE_T = 0.45            # stage transition (rock doors) duration
CLEAR_DELAY = 0.45       # pause after the second rover reaches the exit

PTS_STAGE, PTS_CLEAN, PTS_PAR = 1000, 500, 300
RANKS = ((4500, "S", GOLD), (3500, "A", GREEN), (2500, "B", CYAN), (0, "C", DIM))

_fonts, _glows = {}, {}


def _font(size):
    if size not in _fonts:
        _fonts[size] = pygame.font.Font(None, size)
    return _fonts[size]


def _rect(x, y, w, h):
    return pygame.Rect(int(x), int(y), max(1, int(w)), max(1, int(h)))


def _mix(c1, c2, k):
    k = max(0.0, min(1.0, k))
    return tuple(int(c1[i] + (c2[i] - c1[i]) * k) for i in range(3))


def _shade(c, f):
    return tuple(max(0, min(255, int(v * f))) for v in c)


def _ease(k):
    k = max(0.0, min(1.0, k))
    return k * k * (3 - 2 * k)


def rank_for(score):
    for lim, letter, col in RANKS:
        if score >= lim:
            return letter, col
    return "C", DIM


def _text(surf, txt, size, color, pos, anchor="topleft"):
    img = _font(size).render(str(txt), True, color)
    r = img.get_rect()
    setattr(r, anchor, pos)
    surf.blit(img, r)
    return r


def _panel(surf, rect, alpha=225, border=CYAN):
    rect = pygame.Rect(rect)
    p = pygame.Surface(rect.size, pygame.SRCALPHA)
    p.fill((*PANEL, alpha))
    surf.blit(p, rect.topleft)
    pygame.draw.rect(surf, border, rect, 2)
    pygame.draw.rect(surf, (30, 70, 90), rect.inflate(-8, -8), 1)


def _glow(radius, color):
    key = (radius, color)
    if key not in _glows:
        s = pygame.Surface((radius * 2, radius * 2), pygame.SRCALPHA)
        for i in range(radius, 0, -3):
            pygame.draw.circle(s, (*color, int(70 * (1 - i / radius) ** 1.5) + 4), (radius, radius), i)
        _glows[key] = s
    return _glows[key]


def _rock_shape():
    rng = random.Random(11)
    return [(math.cos(6.283 * i / 9) * rng.uniform(0.78, 1.08), math.sin(6.283 * i / 9) * rng.uniform(0.74, 1.0))
            for i in range(9)]


ROCK_PTS = _rock_shape()


class _Button:
    def __init__(self, label, rect):
        self.label, self.rect = label, pygame.Rect(rect)

    def draw(self, surf, hot=False, size=24, color=None):
        _panel(surf, self.rect, 245 if hot else 200, CYAN if hot else (40, 100, 120))
        _text(surf, self.label, size, color or (CYAN if hot else DIM), self.rect.center, "center")


class TwinTrailsChallenge:
    title = "TWIN TRAILS"

    def __init__(self, eq=None, on_complete=None):
        self.eq = eq
        self.on_complete = on_complete
        self.boards = [Board(spec) for spec in LEVELS]
        self.bg = self._make_bg()
        by = SCREEN_H - BOT_H + 9
        self.btn_stage = _Button("RESTART STAGE  [R]", (SCREEN_W - 16 - 190 * 2 - 10, by, 190, 34))
        self.btn_game = _Button("RESTART GAME", (SCREEN_W - 16 - 190, by, 190, 34))
        self.btn_next = _Button("CONTINUE", (SCREEN_W // 2 - 130, 0, 260, 46))
        self.btn_again = _Button("PLAY AGAIN", (0, 0, 230, 46))
        self.btn_done = _Button("CONTINUE", (0, 0, 230, 46))
        self.mouse = (-1, -1)
        self.reset_game()

    # ================================================================ state
    def reset_game(self):
        """Full reset: all stages, scoring, statistics."""
        self.stage_i = 0
        self.score = 0
        self.total_moves = 0
        self.restarts = [0] * len(LEVELS)
        self.stats = [None] * len(LEVELS)
        self.result = None
        self._fired = False
        self.confirm_t = 0.0
        self.vsel = 1
        self.t = 0.0
        self.wipe = dict(kind="open", t=0.0, cb=None)
        self._load_stage(0)
        self.phase = "intro"

    def _load_stage(self, i):
        """(Re)build one stage from scratch: used for first load, stage restart and next stage."""
        self.stage_i = i
        self.board = self.boards[i]
        b = self.board
        self.st = b.start
        self.moves = 0
        self.active = 0
        self.face = {"spirit": "right", "opportunity": "right"}
        self.held, self.queued = {}, None
        self.ranim = {0: None, 1: None}      # rover index -> [src_cell, t]
        self.rockanim = {}                   # rock dest cell -> [src_cell, t]
        self.bump = None                     # [rover index, dir, t]
        self.particles, self.rings = [], []
        self.clear_t = 0.0
        self.switch_t = 1.0
        self.plate_glow = {p: (1.0 if b.pressed(self.st, p) else 0.0) for p in b.plates}
        self.door_amt = {p: (1.0 if b.door_open(self.st, p) else 0.0) for p in b.doors}
        self.door_axis = {p: ("v" if (p[0], p[1] - 1) in b.walls and (p[0], p[1] + 1) in b.walls else "h")
                          for p in b.doors}
        self.T = min(52, (SCREEN_W - 40) // b.w, (SCREEN_H - TOP_H - BOT_H - 16) // b.h)
        self.ox = (SCREEN_W - b.w * self.T) // 2
        self.oy = TOP_H + (SCREEN_H - TOP_H - BOT_H - b.h * self.T) // 2
        self.static = self._make_static()

    def close(self):
        """Drop transient state (input, animations). Safe to call more than once."""
        self.held, self.queued = {}, None
        self.ranim, self.rockanim = {0: None, 1: None}, {}
        self.particles, self.rings = [], []
        self.bump = self.wipe = None

    @property
    def busy(self):
        return any(a is not None for a in self.ranim.values()) or bool(self.rockanim)

    def _make_result(self):
        letter, _ = rank_for(self.score)
        return dict(completed=True, score=self.score, rank=letter, total_moves=self.total_moves,
                    restarts=sum(self.restarts), stages=[dict(s) for s in self.stats])

    # =============================================================== events
    def handle_event(self, e):
        if e.type == pygame.MOUSEMOTION:
            self.mouse = e.pos
            return None
        if self.wipe:                       # ignore input while the cave doors move
            return None
        if e.type == pygame.KEYUP:
            for d, keys in KEYMAP.items():
                if e.key in keys:
                    self.held.pop(d, None)
            return None
        if e.type == pygame.KEYDOWN:
            return self._key(e)
        if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
            return self._click(e.pos)
        return None

    def _confirm_key(self, e):
        return e.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE, pygame.K_e)

    def _key(self, e):
        if self.phase == "intro":
            if self._confirm_key(e):
                self.phase = "play"
            return None
        if self.phase == "clear":
            if self._confirm_key(e):
                self._after_clear()
            return None
        if self.phase == "victory":
            if e.key in (pygame.K_LEFT, pygame.K_a, pygame.K_RIGHT, pygame.K_d):
                self.vsel ^= 1
            elif self._confirm_key(e):
                return self._victory_choice(self.vsel)
            return None
        # ---- play
        for d, keys in KEYMAP.items():
            if e.key in keys:
                self.held[d] = 0.0
                self.queued = d
                return None
        if e.key in (pygame.K_TAB, pygame.K_SPACE):
            self._switch()
        elif e.key == pygame.K_r:
            if e.mod & pygame.KMOD_SHIFT:
                self._ask_restart_game()
            else:
                self._restart_stage()
        return None

    def _click(self, pos):
        if self.phase == "intro":
            self.phase = "play"
        elif self.phase == "clear":
            if self.btn_next.rect.collidepoint(pos):
                self._after_clear()
        elif self.phase == "victory":
            if self.btn_again.rect.collidepoint(pos):
                return self._victory_choice(0)
            if self.btn_done.rect.collidepoint(pos):
                return self._victory_choice(1)
        else:
            if self.btn_stage.rect.collidepoint(pos):
                self._restart_stage()
            elif self.btn_game.rect.collidepoint(pos):
                self._ask_restart_game()
            else:                                       # click a rover to select it
                for i, p in enumerate(self.st[:2]):
                    if self._cell_rect(p).collidepoint(pos):
                        if i != self.active:
                            self._switch()
        return None

    def _victory_choice(self, c):
        if c == 0:
            self._start_transition(self.reset_game_after_wipe)
            return None
        if not self._fired:
            self._fired = True
            if self.on_complete:
                self.on_complete(self.result)
        return "done"

    def reset_game_after_wipe(self):
        self.reset_game()                  # reset_game installs its own opening wipe

    # ============================================================== actions
    def _switch(self):
        self.active ^= 1
        self.switch_t = 0.0

    def _restart_stage(self):
        if self.phase != "play":
            return
        i = self.stage_i
        self.restarts[i] += 1
        self._start_transition(lambda: self._load_stage(i))

    def _ask_restart_game(self):
        if self.confirm_t > 0:             # second press within the window = confirmed
            self.confirm_t = 0.0
            self._start_transition(self.reset_game_after_wipe)
        else:
            self.confirm_t = 2.5

    def _start_transition(self, cb):
        self.held, self.queued = {}, None
        self.wipe = dict(kind="close", t=0.0, cb=cb)

    def _pressed_plates(self, st):
        return {p for p in self.board.plates if self.board.pressed(st, p)}

    def _try_move(self, d):
        b, who = self.board, ROVERS[self.active]
        self.face[who] = d
        r = b.step(self.st, who, d)
        if not r:
            self.bump = [self.active, d, 0.0]      # blocked: little nudge, no move counted
            return
        new, info = r
        before = self._pressed_plates(self.st)
        self.st = new
        self.moves += 1
        self.total_moves += 1
        self.ranim[self.active] = [info["frm"], 0.0]
        if info["rock"]:
            src, dest = info["rock"]
            self.rockanim[dest] = [src, 0.0]
            self._dust(src, d)
        for p in self._pressed_plates(new) - before:
            self.rings.append([p, 0.0, PLATE_COL[b.plates[p]]])

    def _dust(self, cell, d):
        cx, cy = self._cell_center(cell)
        dx, dy = DIRS[d]
        for _ in range(7):
            sp = random.uniform(20, 70)
            self.particles.append([cx - dx * self.T * 0.3, cy - dy * self.T * 0.3,
                                   -dx * sp + random.uniform(-30, 30), -dy * sp + random.uniform(-30, 30),
                                   0.0, random.uniform(0.3, 0.5), random.choice(((180, 130, 95), (150, 105, 80)))])

    def _stage_clear(self):
        i, spec = self.stage_i, LEVELS[self.stage_i]
        clean = self.restarts[i] == 0
        fast = self.moves <= spec["par"]
        pts = PTS_STAGE + (PTS_CLEAN if clean else 0) + (PTS_PAR if fast else 0)
        self.score += pts
        self.stats[i] = dict(name=spec["name"], moves=self.moves, par=spec["par"], restarts=self.restarts[i],
                             clean=clean, fast=fast, points=pts)
        self.phase, self.t = "clear", 0.0
        self.held, self.queued = {}, None

    def _after_clear(self):
        if self.stage_i + 1 < len(LEVELS):
            nxt = self.stage_i + 1

            def go():
                self._load_stage(nxt)
                self.phase, self.t = "intro", 0.0
            self._start_transition(go)
        else:
            def fin():
                self.result = self._make_result()
                self.phase, self.t, self.vsel = "victory", 0.0, 1
            self._start_transition(fin)

    # ================================================================ update
    def update(self, dt):
        self.t += dt
        self.confirm_t = max(0.0, self.confirm_t - dt)
        self.switch_t += dt
        self._update_wipe(dt)
        self._update_anims(dt)
        if self.phase != "play" or self.wipe:
            return
        for d in self.held:
            self.held[d] += dt
        if not self.busy:
            d, self.queued = self.queued, None
            if d is None:
                rep = [k for k, v in self.held.items() if v >= REPEAT_DELAY]
                d = rep[-1] if rep else None
            if d:
                self._try_move(d)
        if not self.busy and self.board.solved(self.st):
            self.clear_t += dt
            if self.clear_t >= CLEAR_DELAY:
                self._stage_clear()
        else:
            self.clear_t = 0.0

    def _update_wipe(self, dt):
        w = self.wipe
        if not w:
            return
        w["t"] += dt
        if w["t"] >= WIPE_T:
            if w["kind"] == "close":
                cb = w["cb"]
                self.wipe = dict(kind="open", t=0.0, cb=None)
                if cb:
                    cb()
            else:
                self.wipe = None

    def _update_anims(self, dt):
        for i, a in self.ranim.items():
            if a:
                a[1] += dt
                if a[1] >= MOVE_T:
                    self.ranim[i] = None
        for k in [k for k, a in self.rockanim.items() if a[1] + dt >= MOVE_T]:
            del self.rockanim[k]
        for a in self.rockanim.values():
            a[1] += dt
        if self.bump:
            self.bump[2] += dt
            if self.bump[2] > 0.16:
                self.bump = None
        b = self.board
        for p in b.plates:
            tgt = 1.0 if b.pressed(self.st, p) else 0.0
            g = self.plate_glow[p]
            self.plate_glow[p] = min(tgt, g + dt * 7) if tgt > g else max(tgt, g - dt * 7)
        for p in b.doors:
            tgt = 1.0 if b.door_open(self.st, p) else 0.0
            g = self.door_amt[p]
            self.door_amt[p] = min(tgt, g + dt * 4.5) if tgt > g else max(tgt, g - dt * 4.5)
        for r in self.rings:
            r[1] += dt
        self.rings = [r for r in self.rings if r[1] < 0.45]
        for p in self.particles:
            p[0] += p[2] * dt
            p[1] += p[3] * dt
            p[4] += dt
        self.particles = [p for p in self.particles if p[4] < p[5]]

    # ============================================================== geometry
    def _cell_rect(self, c):
        return _rect(self.ox + c[0] * self.T, self.oy + c[1] * self.T, self.T, self.T)

    def _cell_center(self, c):
        return self.ox + (c[0] + 0.5) * self.T, self.oy + (c[1] + 0.5) * self.T

    def _rover_center(self, i):
        dst = self.st[i]
        a = self.ranim[i]
        x, y = self._cell_center(dst)
        if a:
            sx, sy = self._cell_center(a[0])
            k = 1 - _ease(a[1] / MOVE_T)
            x, y = x + (sx - x) * k, y + (sy - y) * k
        if self.bump and self.bump[0] == i:
            dx, dy = DIRS[self.bump[1]]
            o = math.sin(math.pi * min(1.0, self.bump[2] / 0.16)) * self.T * 0.1
            x, y = x + dx * o, y + dy * o
        return x, y

    # ================================================================= drawing
    def _make_bg(self):
        s = pygame.Surface((SCREEN_W, SCREEN_H))
        for y in range(SCREEN_H):
            k = y / SCREEN_H
            pygame.draw.line(s, _mix((34, 18, 20), (20, 10, 14), k), (0, y), (SCREEN_W, y))
        rng = random.Random(21)
        for _ in range(120):                                   # rocky mottling
            x, y, r = rng.randrange(SCREEN_W), rng.randrange(SCREEN_H), rng.randint(14, 60)
            pygame.draw.circle(s, _shade((48, 27, 26), rng.uniform(0.7, 1.25)), (x, y), r)
        for x in range(-20, SCREEN_W + 40, 38):                # stalactites / stalagmites
            h, w = rng.randint(14, 60), rng.randint(12, 24)
            pygame.draw.polygon(s, (18, 9, 12), [(x - w, 0), (x + w, 0), (x, h)])
            h = rng.randint(10, 44)
            pygame.draw.polygon(s, (18, 9, 12), [(x - w, SCREEN_H), (x + w, SCREEN_H), (x + 6, SCREEN_H - h)])
        v = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)   # vignette
        for i in range(40):
            pygame.draw.rect(v, (0, 0, 0, int(150 * (1 - i / 40) ** 2)),
                             (i * 6, i * 4, SCREEN_W - i * 12, SCREEN_H - i * 8), 8)
        s.blit(v, (0, 0))
        return s

    def _make_static(self):
        b, T = self.board, self.T
        s = pygame.Surface((b.w * T, b.h * T))
        s.fill((20, 10, 12))
        rng = random.Random(100 + self.stage_i)
        for y in range(b.h):
            for x in range(b.w):
                r = _rect(x * T, y * T, T, T)
                if (x, y) in b.walls:
                    base = _shade((70, 42, 38), rng.uniform(0.8, 1.15))
                    pygame.draw.rect(s, base, r)
                    for _ in range(3):
                        cx, cy = r.x + rng.uniform(0.2, 0.8) * T, r.y + rng.uniform(0.2, 0.8) * T
                        rad = rng.uniform(0.18, 0.32) * T
                        pts = [(cx + math.cos(a * 0.9) * rad * rng.uniform(0.7, 1.1),
                                cy + math.sin(a * 0.9) * rad * rng.uniform(0.7, 1.1)) for a in range(7)]
                        pygame.draw.polygon(s, _shade(base, rng.uniform(0.7, 1.3)), pts)
                    if (x, y) in b.rubble:                      # cave-in debris pile
                        for _ in range(6):
                            cx, cy = r.x + rng.uniform(0.2, 0.8) * T, r.y + rng.uniform(0.25, 0.85) * T
                            rad = rng.uniform(0.09, 0.17) * T
                            pygame.draw.circle(s, (92, 40 + rng.randint(0, 30), 38), (int(cx), int(cy)), int(rad))
                            pygame.draw.circle(s, (140, 90, 70), (int(cx - rad * 0.3), int(cy - rad * 0.3)),
                                               max(1, int(rad * 0.4)))
                else:
                    base = _shade((132, 78, 54), rng.uniform(0.92, 1.08))
                    pygame.draw.rect(s, base, r)
                    pygame.draw.rect(s, _shade(base, 0.82), r, 1)
                    for _ in range(3):
                        pygame.draw.circle(s, _shade(base, rng.uniform(0.75, 1.2)),
                                           (r.x + rng.randint(4, T - 4), r.y + rng.randint(4, T - 4)),
                                           rng.randint(1, 3))
        for y in range(b.h):                                      # lit rim where wall meets floor
            for x in range(b.w):
                if (x, y) not in b.walls:
                    continue
                for dx, dy in DIRS.values():
                    n = (x + dx, y + dy)
                    if 0 <= n[0] < b.w and 0 <= n[1] < b.h and n[0:2] not in b.walls:
                        px, py = x * T, y * T
                        if dx:
                            xx = px + (T - 3 if dx > 0 else 0)
                            pygame.draw.rect(s, (28, 14, 16), (xx, py, 3, T))
                        else:
                            yy = py + (T - 3 if dy > 0 else 0)
                            pygame.draw.rect(s, (28, 14, 16), (px, yy, T, 3))
        return s

    def draw(self, surf):
        surf.blit(self.bg, (0, 0))
        b, T = self.board, self.T
        surf.blit(self.static, (self.ox, self.oy))
        pulse = 0.5 + 0.5 * math.sin(self.t * 3)
        for p in b.exits:
            self._draw_exit(surf, p, pulse)
        for p, l in b.plates.items():
            self._draw_plate(surf, p, PLATE_COL[l], l)
        for r in self.rings:
            cx, cy = self._cell_center(r[0])
            k = r[1] / 0.45
            col = _mix(r[2], (132, 78, 54), k)
            pygame.draw.circle(surf, col, (int(cx), int(cy)), int(T * (0.3 + 0.5 * k)), 3)
        for p, l in b.doors.items():
            self._draw_door(surf, p, PLATE_COL[l])
        self._draw_rocks(surf)
        self._draw_rovers(surf)
        for p in self.particles:
            k = 1 - p[4] / p[5]
            pygame.draw.circle(surf, p[6], (int(p[0]), int(p[1])), max(1, int(4 * k)))
        self._draw_hud(surf)
        if self.phase == "intro":
            self._draw_intro(surf)
        elif self.phase == "clear":
            self._draw_clear(surf)
        elif self.phase == "victory":
            self._draw_victory(surf)
        self._draw_wipe(surf)

    # ---- board objects
    def _draw_exit(self, surf, p, pulse):
        r, T = self._cell_rect(p), self.T
        occupied = p in self.st[:2]
        col = GREEN if occupied else _mix((60, 190, 160), (120, 255, 220), pulse)
        pygame.draw.rect(surf, (14, 40, 36), r.inflate(-4, -4), border_radius=6)
        if occupied:
            surf.blit(_glow(int(T * 0.9), GREEN), (r.centerx - int(T * 0.9), r.centery - int(T * 0.9)))
        pygame.draw.rect(surf, col, r.inflate(-6, -6), 3, border_radius=6)
        cx, cy = r.center
        for off in (-0.14, 0.06):                                   # chevrons
            y = cy + int(off * T)
            pygame.draw.lines(surf, col, False, [(cx - T * 0.18, y + T * 0.08), (cx, y - T * 0.06),
                                                 (cx + T * 0.18, y + T * 0.08)], 3)
        _text(surf, "EXIT", max(12, int(T * 0.26)), col, (cx, r.bottom - 8), "midbottom")

    def _draw_plate(self, surf, p, col, letter):
        r, T = self._cell_rect(p), self.T
        g = self.plate_glow[p]
        pygame.draw.rect(surf, (40, 24, 24), r.inflate(-8, -8), border_radius=5)
        inner = r.inflate(-14, -14)
        pygame.draw.rect(surf, _mix(_shade(col, 0.3), col, g), inner, border_radius=4)
        pygame.draw.rect(surf, col, inner, 2, border_radius=4)
        if g > 0.05:
            surf.blit(_glow(int(T * 0.7), col), (r.centerx - int(T * 0.7), r.centery - int(T * 0.7)))
        _text(surf, letter.upper(), max(14, int(T * 0.34)), _mix(col, (30, 20, 20), g * 0.8), r.center, "center")

    def _draw_door(self, surf, p, col):
        b, T = self.board, self.T
        r = self._cell_rect(p)
        amt = self.door_amt[p]
        pygame.draw.rect(surf, (36, 22, 24), r)
        half = (T / 2) * (1 - amt)
        metal, dark = (112, 118, 130), (62, 66, 78)
        if self.door_axis[p] == "v":
            panels = [_rect(r.x, r.y, T, half), _rect(r.x, r.bottom - half, T, half)]
            seams = [(r.x, r.y + half - 2, T, 3), (r.x, r.bottom - half - 1, T, 3)]
        else:
            panels = [_rect(r.x, r.y, half, T), _rect(r.right - half, r.y, half, T)]
            seams = [(r.x + half - 2, r.y, 3, T), (r.right - half - 1, r.y, 3, T)]
        if amt < 0.98:
            for pr in panels:
                pygame.draw.rect(surf, metal, pr)
                pygame.draw.rect(surf, dark, pr, 2)
            for sm in seams:
                pygame.draw.rect(surf, col, _rect(*sm))
            letter = b.doors[p]
            need = b.letters[letter]
            on = sum(1 for q in need if b.pressed(self.st, q))
            if amt < 0.5:                                          # lock lamps: one per required plate
                n = len(need)
                for k in range(n):
                    lx = r.centerx + (k - (n - 1) / 2) * T * 0.22
                    pygame.draw.circle(surf, (20, 14, 16), (int(lx), r.centery), max(3, int(T * 0.1)))
                    pygame.draw.circle(surf, col if k < on else (70, 50, 50), (int(lx), r.centery),
                                       max(2, int(T * 0.075)))
        pygame.draw.rect(surf, col, r, 2)

    def _draw_rocks(self, surf):
        T = self.T
        for p in self.st[2]:
            cx, cy = self._cell_center(p)
            a = self.rockanim.get(p)
            if a:
                sx, sy = self._cell_center(a[0])
                k = 1 - _ease(a[1] / MOVE_T)
                cx, cy = cx + (sx - cx) * k, cy + (sy - cy) * k
            rad = T * 0.4
            pygame.draw.ellipse(surf, (28, 14, 14), _rect(cx - rad, cy + rad * 0.45, rad * 2, rad * 0.8))
            pts = [(cx + x * rad, cy + y * rad) for x, y in ROCK_PTS]
            pygame.draw.polygon(surf, (150, 108, 86), pts)
            pygame.draw.polygon(surf, (196, 150, 120),
                                [(cx - rad * 0.15 + x * rad * 0.55, cy - rad * 0.2 + y * rad * 0.5) for x, y in ROCK_PTS])
            pygame.draw.polygon(surf, (60, 36, 32), pts, 2)

    def _draw_rovers(self, surf):
        order = sorted((0, 1), key=lambda i: self._rover_center(i)[1])
        for i in order:
            cx, cy = self._rover_center(i)
            self._draw_rover(surf, ROVERS[i], cx, cy, i == self.active)

    def _draw_rover(self, surf, who, cx, cy, active):
        T, col, face = self.T, ROVER_COL[who], self.face[who]
        horiz = face in ("left", "right")
        sign = 1 if face in ("right", "down") else -1
        L, Wd = T * 0.78, T * 0.58
        if active:
            surf.blit(_glow(int(T * 0.85), col), (int(cx - T * 0.85), int(cy - T * 0.85)))

        def box(lx, ly, lw, lh):                      # (along, across) local box -> screen rect
            if horiz:
                return _rect(cx + lx - lw / 2, cy + ly - lh / 2, lw, lh)
            return _rect(cx + ly - lh / 2, cy + lx - lw / 2, lh, lw)

        pygame.draw.ellipse(surf, (30, 16, 16), _rect(cx - L * 0.5, cy + Wd * 0.2, L, Wd * 0.5))
        for k in (-1, 0, 1):                          # six wheels
            for side in (-1, 1):
                pygame.draw.rect(surf, (32, 32, 38), box(k * L * 0.3, side * Wd * 0.46, L * 0.2, Wd * 0.2),
                                 border_radius=3)
        pygame.draw.rect(surf, (214, 217, 224), box(0, 0, L * 0.8, Wd * 0.72), border_radius=5)
        pygame.draw.rect(surf, _shade(col, 0.55), box(-sign * L * 0.04, 0, L * 0.5, Wd * 0.5), border_radius=3)
        pygame.draw.rect(surf, col, box(-sign * L * 0.04, 0, L * 0.46, Wd * 0.44), border_radius=3)
        pygame.draw.rect(surf, (110, 114, 124), box(0, 0, L * 0.8, Wd * 0.72), 2, border_radius=5)
        mx = sign * L * 0.3                                           # mast + camera head
        pygame.draw.rect(surf, (90, 94, 104), box(mx, 0, L * 0.1, Wd * 0.16))
        hx, hy = (cx + mx + sign * L * 0.06, cy) if horiz else (cx, cy + mx + sign * L * 0.06)
        pygame.draw.circle(surf, (235, 238, 245), (int(hx), int(hy)), max(3, int(T * 0.09)))
        pygame.draw.circle(surf, (40, 60, 80), (int(hx), int(hy)), max(1, int(T * 0.045)))
        _text(surf, ROVER_NAME[who][0], max(12, int(T * 0.3)), (30, 22, 22), (cx - sign * L * 0.04 if horiz else cx,
              cy if horiz else cy - sign * L * 0.04), "center")
        if active:
            bob = math.sin(self.t * 6) * 3
            ty = cy - T * 0.58 - bob
            pygame.draw.polygon(surf, col, [(cx - 7, ty - 9), (cx + 7, ty - 9), (cx, ty)])
            pygame.draw.polygon(surf, (255, 255, 255), [(cx - 7, ty - 9), (cx + 7, ty - 9), (cx, ty)], 1)
            c = self._cell_rect(self.st[ROVERS.index(who)]).inflate(-2, -2)   # corner brackets
            ln = int(T * 0.22)
            for sx, sy in ((c.left, c.top), (c.right, c.top), (c.left, c.bottom), (c.right, c.bottom)):
                dx = 1 if sx == c.left else -1
                dy = 1 if sy == c.top else -1
                pygame.draw.line(surf, col, (sx, sy), (sx + dx * ln, sy), 3)
                pygame.draw.line(surf, col, (sx, sy), (sx, sy + dy * ln), 3)
            if self.switch_t < 0.3:
                k = self.switch_t / 0.3
                pygame.draw.circle(surf, _mix(col, (40, 24, 24), k), (int(cx), int(cy)), int(T * (0.4 + 0.5 * k)), 3)

    # ---- HUD
    def _draw_hud(self, surf):
        spec = LEVELS[self.stage_i]
        _panel(surf, (0, 0, SCREEN_W, TOP_H), 235)
        lc = LEVEL_COL[spec["level"]]
        _text(surf, f"STAGE {self.stage_i + 1} / {len(LEVELS)}  -  {spec['level']}", 20, lc, (16, 8))
        _text(surf, spec["name"], 34, CYAN, (16, 28))
        for i in range(len(LEVELS)):                                       # progress pips
            done = self.stats[i] is not None
            c = (SCREEN_W // 2 - 20 + i * 20, 12)
            pygame.draw.circle(surf, GREEN if done else (CYAN if i == self.stage_i else (50, 70, 80)), c, 6,
                               0 if (done or i == self.stage_i) else 2)
        for i, who in enumerate(ROVERS):                                   # rover chips
            col = ROVER_COL[who]
            r = pygame.Rect(SCREEN_W // 2 - 215 + i * 220, 26, 210, 32)
            act = i == self.active
            _panel(surf, r, 245 if act else 170, col if act else (50, 60, 70))
            pygame.draw.circle(surf, col, (r.x + 18, r.centery), 8)
            _text(surf, ROVER_NAME[who], 24, TEXT if act else DIM, (r.x + 34, r.centery), "midleft")
            if self.st[i] in self.board.exits:
                _text(surf, "AT EXIT", 18, GREEN, (r.right - 8, r.centery), "midright")
            elif act:
                _text(surf, "ACTIVE", 18, col, (r.right - 8, r.centery), "midright")
        over = self.moves > spec["par"]
        _text(surf, f"MOVES {self.moves} / {spec['par']}", 28, RED if over else TEXT, (SCREEN_W - 16, 8), "topright")
        _text(surf, f"SCORE {self.score:,}", 28, GOLD, (SCREEN_W - 16, 34), "topright")
        y0 = SCREEN_H - BOT_H
        _panel(surf, (0, y0, SCREEN_W, BOT_H), 235)
        _text(surf, "WASD / ARROWS: move     TAB / SPACE: switch rover     R: restart stage", 20, TEXT, (16, y0 + 9))
        _text(surf, spec["hint"], 20, DIM, (16, y0 + 29))
        if self.phase == "play":
            self.btn_stage.draw(surf, self.btn_stage.rect.collidepoint(self.mouse), 22)
            hot = self.btn_game.rect.collidepoint(self.mouse) or self.confirm_t > 0
            self.btn_game.label = "CLICK AGAIN TO CONFIRM" if self.confirm_t > 0 else "RESTART GAME"
            self.btn_game.draw(surf, hot, 22, RED if self.confirm_t > 0 else None)

    # ---- overlays
    def _dim(self, surf, a=150):
        d = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
        d.fill((0, 0, 0, a))
        surf.blit(d, (0, 0))

    def _draw_intro(self, surf):
        spec = LEVELS[self.stage_i]
        self._dim(surf, 130)
        r = pygame.Rect(0, 0, 620, 280)
        r.center = (SCREEN_W // 2, SCREEN_H // 2)
        _panel(surf, r, 242)
        cx = r.centerx
        _text(surf, f"STAGE {self.stage_i + 1} OF {len(LEVELS)}", 26, DIM, (cx, r.y + 22), "midtop")
        _text(surf, spec["name"], 58, CYAN, (cx, r.y + 50), "midtop")
        _text(surf, f"DIFFICULTY: {spec['level']}", 26, LEVEL_COL[spec["level"]], (cx, r.y + 108), "midtop")
        lines = [spec["hint"], f"Recommended: {spec['par']} moves. Both rovers must reach an exit."]
        if self.stage_i == 0:
            lines.insert(0, "Move with WASD / arrows. Switch rover with TAB or SPACE.")
        y = r.y + 142
        for ln in lines:
            _text(surf, ln, 24, TEXT, (cx, y), "midtop")
            y += 26
        if self.eq:
            _text(surf, f"Recovering the memories of {self.eq.get('name', '')}", 20, DIM, (cx, r.bottom - 56), "midtop")
        if int(self.t * 2) % 2 == 0:
            _text(surf, "PRESS ENTER OR SPACE TO BEGIN", 26, CYAN, (cx, r.bottom - 34), "midtop")

    def _draw_clear(self, surf):
        s = self.stats[self.stage_i]
        self._dim(surf, 130)
        r = pygame.Rect(0, 0, 560, 330)
        r.center = (SCREEN_W // 2, SCREEN_H // 2)
        _panel(surf, r, 244)
        cx = r.centerx
        _text(surf, "STAGE CLEARED", 56, GREEN, (cx, r.y + 22), "midtop")
        _text(surf, s["name"], 28, CYAN, (cx, r.y + 78), "midtop")
        rows = [(f"Stage complete", PTS_STAGE, True),
                (f"No restarts", PTS_CLEAN, s["clean"]),
                (f"Moves {s['moves']} / {s['par']} recommended", PTS_PAR, s["fast"])]
        y = r.y + 116
        for label, pts, got in rows:
            _text(surf, label, 26, TEXT if got else (90, 100, 108), (r.x + 50, y))
            _text(surf, f"+{pts:,}" if got else "-", 26, GOLD if got else (90, 100, 108), (r.right - 50, y), "topright")
            y += 34
        pygame.draw.line(surf, (40, 100, 120), (r.x + 40, y + 2), (r.right - 40, y + 2), 1)
        _text(surf, "STAGE SCORE", 28, TEXT, (r.x + 50, y + 12))
        _text(surf, f"{s['points']:,}", 30, GOLD, (r.right - 50, y + 10), "topright")
        self.btn_next.rect.y = r.bottom - 66
        self.btn_next.label = "CONTINUE" if self.stage_i + 1 < len(LEVELS) else "FINISH"
        self.btn_next.draw(surf, True, 30)

    def _draw_victory(self, surf):
        self._dim(surf, 175)
        r = pygame.Rect(0, 0, 720, 420)
        r.center = (SCREEN_W // 2, SCREEN_H // 2)
        _panel(surf, r, 246)
        cx = r.centerx
        res = self.result
        _text(surf, "MISSION COMPLETED", 60, GREEN, (cx, r.y + 16), "midtop")
        _text(surf, "Spirit and Opportunity escaped the cave together.", 24, TEXT, (cx, r.y + 74), "midtop")
        y = r.y + 108
        for i, s in enumerate(res["stages"]):
            _text(surf, f"{i + 1}. {s['name']}", 24, CYAN, (r.x + 40, y))
            _text(surf, f"{s['moves']} / {s['par']} moves   {s['restarts']} restarts", 22, DIM, (cx + 40, y + 2))
            _text(surf, f"+{s['points']:,}", 24, GOLD, (r.right - 40, y), "topright")
            y += 30
        pygame.draw.line(surf, (40, 100, 120), (r.x + 30, y + 4), (r.right - 30, y + 4), 1)
        _text(surf, f"TOTAL MOVES  {res['total_moves']}", 28, TEXT, (r.x + 40, y + 20))
        _text(surf, f"FINAL SCORE  {res['score']:,}", 34, GOLD, (r.x + 40, y + 52))
        letter, col = rank_for(res["score"])
        _text(surf, "RANK", 22, DIM, (r.right - 110, y + 14), "midtop")
        _text(surf, letter, 96, col, (r.right - 110, y + 32), "midtop")
        by = r.bottom - 64
        self.btn_again.rect.topleft = (cx - 240, by)
        self.btn_done.rect.topleft = (cx + 10, by)
        self.btn_again.draw(surf, self.vsel == 0 or self.btn_again.rect.collidepoint(self.mouse), 28)
        self.btn_done.draw(surf, self.vsel == 1 or self.btn_done.rect.collidepoint(self.mouse), 28)

    def _draw_wipe(self, surf):
        w = self.wipe
        if not w:
            return
        p = _ease(w["t"] / WIPE_T)
        cover = p if w["kind"] == "close" else 1 - p
        half = int(SCREEN_W / 2 * cover)
        if half <= 0:
            return
        for x0, x1 in ((0, half), (SCREEN_W - half, SCREEN_W)):
            pygame.draw.rect(surf, (26, 14, 16), (x0, 0, x1 - x0, SCREEN_H))
            for y in range(0, SCREEN_H, 28):
                pygame.draw.line(surf, (40, 22, 24), (x0, y), (x1, y), 2)
        pygame.draw.rect(surf, (120, 70, 55), (half - 4, 0, 4, SCREEN_H))
        pygame.draw.rect(surf, (120, 70, 55), (SCREEN_W - half, 0, 4, SCREEN_H))


KEYMAP = {
    "up": (pygame.K_w, pygame.K_UP), "down": (pygame.K_s, pygame.K_DOWN),
    "left": (pygame.K_a, pygame.K_LEFT), "right": (pygame.K_d, pygame.K_RIGHT),
}


def run_standalone():
    """Play Twin Trails on its own window (dev/testing)."""
    pygame.init()
    pygame.display.set_caption("Twin Trails")
    screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
    clock = pygame.time.Clock()
    game = TwinTrailsChallenge(on_complete=lambda res: print("Twin Trails result:", res))
    running = True
    while running:
        dt = min(clock.tick(60) / 1000, 0.05)
        for e in pygame.event.get():
            if e.type == pygame.QUIT or (e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE):
                running = False
            elif game.handle_event(e) == "done":
                running = False
        game.update(dt)
        game.draw(screen)
        pygame.display.flip()
    game.close()
    pygame.quit()


if __name__ == "__main__":
    run_standalone()
