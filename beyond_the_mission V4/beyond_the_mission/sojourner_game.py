"""Sojourner minigame - LAST MISSION (Game 6, final challenge).

Night navigation + resource management. Study the whole Martian map, then the
lights go out: guide Sojourner to the station through darkness with a critically
low battery, adapting to dust storms and rockfalls.

Plugs into the existing challenge interface (same as the other minigames):
    SojournerChallenge(eq)  ->  handle_event(e) returns "done" only on victory
                                (EncounterScene then runs the Memory Capsule flow),
                                update(dt), draw(surf), title attribute.
Failure (battery depleted) shows MISSION FAILED + RETRY and never returns "done".

Fairness guarantees (all enforced by code, see generate_map / _try_rockfall):
  * every generated map is validated with Dijkstra: a route exists and its
    cheapest energy cost lies in a sane range;
  * battery = cheapest route cost + a generous reserve, so a player who
    remembers the map and plans well can win;
  * waiting costs NO power, bumping an unseen rock costs NO power;
  * rockfalls only land on pre-marked zones (shown during reconnaissance), at
    least 4 tiles from the rover, after a 3 s warning, and only if a route to
    the station still exists within the remaining battery; they clear by
    themselves;
  * dust storms are announced 3 s ahead, last 9 s and can be waited out.
"""
import heapq
import math
import random

import pygame

import ui
from settings import SCREEN_W, SCREEN_H, CYAN, TEXT, DIM

# --------------------------------------------------------------------- config
COLS, ROWS, T = 22, 13, 30            # map size in tiles, tile size in px
FLAT, ROUGH, UNSTABLE, ROCK = 0, 1, 2, 3
COST = {FLAT: 1, ROUGH: 2, UNSTABLE: 3}
TERRAIN_NAME = {FLAT: "Flat regolith", ROUGH: "Rough sand", UNSTABLE: "Unstable ground"}

RECON_TIME = 25.0
BLACKOUT_TIME = 1.6
MOVE_TIME = 0.11                       # seconds per tile slide
HOLD_DELAY = 0.16                      # hold-to-repeat delay
VIS_NORMAL = 3.6                       # visibility radius (tiles)
VIS_STORM = 1.9
STORM_EXTRA = 1                        # extra battery per move during a storm
WARN_TIME = 3.0
STORM_TIME = 9.0
ROCKFALL_TIME = 12.0
MIN_ROUTE, MAX_ROUTE = 30, 48         # accepted cheapest-route cost range

AMBER = (255, 176, 64)
RED = (255, 80, 70)
GREEN = (110, 255, 170)
ORANGE = (255, 120, 40)

MAP = pygame.Rect(52, 100, COLS * T, ROWS * T)
SIDE = pygame.Rect(724, 100, 200, ROWS * T)
LETTERS = "ABCDEFGHIJKLMNOPQRSTUV"

DIRS = {pygame.K_UP: (0, -1), pygame.K_w: (0, -1), pygame.K_DOWN: (0, 1), pygame.K_s: (0, 1),
        pygame.K_LEFT: (-1, 0), pygame.K_a: (-1, 0), pygame.K_RIGHT: (1, 0), pygame.K_d: (1, 0)}

INTRO = ["Final mission: reach the station before the battery dies.",
         "The surface is dark and dust is rolling in.",
         "Use the map you saw during recon. Good luck, Sojourner."]


# ------------------------------------------------------------ pure game logic
def coord(p):
    return f"{LETTERS[p[0]]}{p[1] + 1}"


def route(grid, start, goal, blocked=()):
    """Cheapest-energy route (Dijkstra, 4-neighbour). Returns (cost, path) or (None, None)."""
    blocked = set(blocked)
    best = {start: 0}
    prev = {}
    heap = [(0, start)]
    while heap:
        c, cur = heapq.heappop(heap)
        if cur == goal:
            path = [cur]
            while cur in prev:
                cur = prev[cur]
                path.append(cur)
            return c, path[::-1]
        if c > best.get(cur, 1e9):
            continue
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = cur[0] + dx, cur[1] + dy
            if not (0 <= nx < COLS and 0 <= ny < ROWS) or (nx, ny) in blocked:
                continue
            t = grid[ny][nx]
            if t == ROCK:
                continue
            nc = c + COST[t]
            if nc < best.get((nx, ny), 1e9):
                best[(nx, ny)] = nc
                prev[(nx, ny)] = cur
                heapq.heappush(heap, (nc, (nx, ny)))
    return None, None


def _blob(grid, rng, kind, cells, keep_free, only=None):
    x, y = rng.randint(1, COLS - 2), rng.randint(1, ROWS - 2)
    for _ in range(cells):
        if (x, y) not in keep_free and (only is None or grid[y][x] == only):
            grid[y][x] = kind
        dx, dy = rng.choice(((1, 0), (-1, 0), (0, 1), (0, -1)))
        x, y = max(1, min(COLS - 2, x + dx)), max(1, min(ROWS - 2, y + dy))


def _try_map(rng):
    grid = [[FLAT] * COLS for _ in range(ROWS)]
    start = (1, rng.randint(2, ROWS - 3))
    goal = (COLS - 2, rng.randint(2, ROWS - 3))
    keep = {(x, y) for p in (start, goal) for x in range(p[0] - 1, p[0] + 2) for y in range(p[1] - 1, p[1] + 2)}
    # three broken walls force routing decisions; one gap is flat, a second (narrower) one is a risky shortcut
    for wc in (rng.randint(4, 6), rng.randint(9, 11), rng.randint(14, 16)):
        gap = rng.randint(1, ROWS - 3)
        for y in range(ROWS):
            if y not in (gap, gap + 1):
                grid[y][wc] = ROCK
        if rng.random() < 0.7:
            far = [y for y in range(1, ROWS - 1) if abs(y - gap) >= 3]
            if far:
                grid[rng.choice(far)][wc] = UNSTABLE
    for _ in range(rng.randint(6, 9)):
        _blob(grid, rng, ROCK, rng.randint(2, 5), keep)
    for _ in range(rng.randint(6, 8)):
        _blob(grid, rng, ROUGH, rng.randint(4, 9), keep, only=FLAT)
    for _ in range(rng.randint(1, 3)):
        _blob(grid, rng, UNSTABLE, rng.randint(2, 4), keep, only=FLAT)
    for (x, y) in keep:
        if grid[y][x] == ROCK:
            grid[y][x] = FLAT
    return grid, start, goal


def pick_zones(grid, path, start, goal, rng):
    """Rockfall-prone tiles: flat tiles bordering rock. Some lie on the best route
    (so the warning matters), some elsewhere. Shown to the player during recon."""
    def ok(p):
        x, y = p
        if grid[y][x] != FLAT or abs(x - start[0]) + abs(y - start[1]) < 4 or abs(x - goal[0]) + abs(y - goal[1]) < 4:
            return False
        return any(0 <= x + dx < COLS and 0 <= y + dy < ROWS and grid[y + dy][x + dx] == ROCK
                   for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)))
    on_path = [p for p in path[4:-4] if ok(p)]
    rest = [(x, y) for y in range(ROWS) for x in range(COLS) if ok((x, y)) and (x, y) not in on_path]
    zones = rng.sample(on_path, min(3, len(on_path))) + rng.sample(rest, min(5, len(rest)))
    return zones


def generate_map(rng):
    """Validated, solvable mission. Returns dict(grid,start,goal,opt_cost,opt_path,battery,zones)."""
    grid = start = goal = None
    for _ in range(400):
        grid, start, goal = _try_map(rng)
        cost, path = route(grid, start, goal)
        rocks = sum(r.count(ROCK) for r in grid) / (COLS * ROWS)
        if cost is not None and MIN_ROUTE <= cost <= MAX_ROUTE and 0.14 <= rocks <= 0.30:
            break
    else:                                    # fallback: carve a guaranteed corridor
        for x in range(start[0], goal[0] + 1):
            grid[start[1]][x] = FLAT
        for y in range(min(start[1], goal[1]), max(start[1], goal[1]) + 1):
            grid[y][goal[0]] = FLAT
        cost, path = route(grid, start, goal)
    battery = cost + max(10, int(math.ceil(cost * 0.40)))        # reserve for detours / storms
    return dict(grid=grid, start=start, goal=goal, opt_cost=cost, opt_path=path, battery=battery,
                zones=pick_zones(grid, path, start, goal, rng))


# --------------------------------------------------------------------- art
def _mix(c, d, k):
    return tuple(int(c[i] + (d[i] - c[i]) * k) for i in range(3))


def _shade(c, f):
    return tuple(max(0, min(255, int(v * f))) for v in c)


def _rock(surf, cx, cy, rad, rng, tone=(104, 74, 66)):
    n = 9
    pts = [(cx + math.cos(6.283 * i / n) * rad * rng.uniform(0.78, 1.0),
            cy + math.sin(6.283 * i / n) * rad * rng.uniform(0.7, 0.95)) for i in range(n)]
    pygame.draw.polygon(surf, _shade(tone, 0.55), pts)
    pygame.draw.polygon(surf, tone, [(cx + (x - cx) * 0.86 - 1, cy + (y - cy) * 0.86 - 2) for x, y in pts])
    pygame.draw.polygon(surf, _shade(tone, 1.35), [(cx + (x - cx) * 0.45 - 3, cy + (y - cy) * 0.45 - 4) for x, y in pts])
    pygame.draw.polygon(surf, _shade(tone, 0.35), pts, 1)


def _draw_tile(surf, kind, rect, rng, f16):
    base = rng.choice(((112, 48, 32), (118, 52, 34), (106, 46, 30), (122, 56, 36)))
    if kind == ROUGH:
        base = (150, 84, 52)
    elif kind == UNSTABLE:
        base = (80, 32, 24)
    pygame.draw.rect(surf, base, rect)
    for _ in range(5):
        px, py = rect.x + rng.randint(2, T - 3), rect.y + rng.randint(2, T - 3)
        pygame.draw.circle(surf, _shade(base, rng.choice((0.8, 1.2))), (px, py), 1)
    if kind == ROUGH:
        for i in range(3):
            y = rect.y + 7 + i * 8
            pygame.draw.arc(surf, (190, 116, 74), (rect.x + 2, y, T - 4, 8), 0.2, 2.9, 1)
        t = f16.render("2", True, (230, 190, 150))
        surf.blit(t, (rect.right - t.get_width() - 3, rect.bottom - t.get_height() - 1))
    elif kind == UNSTABLE:
        x, y = rect.x + rng.randint(3, 9), rect.y + 2
        pts = [(x, y)]
        while y < rect.bottom - 3:
            x = max(rect.x + 2, min(rect.right - 3, x + rng.randint(-6, 6)))
            y += rng.randint(4, 8)
            pts.append((x, min(y, rect.bottom - 2)))
        pygame.draw.lines(surf, (222, 100, 40), False, pts, 2)
        for i in range(0, T, 6):
            pygame.draw.line(surf, (50, 20, 16), (rect.x + i, rect.bottom - 1), (rect.x + i + 5, rect.y + 1))
        t = f16.render("3", True, (255, 190, 120))
        surf.blit(t, (rect.right - t.get_width() - 3, rect.bottom - t.get_height() - 1))
    elif kind == ROCK:
        _rock(surf, rect.centerx, rect.centery + 1, T * 0.46, rng)
    pygame.draw.rect(surf, _shade(base, 0.72), rect, 1)


def make_rover():
    s = pygame.Surface((26, 26), pygame.SRCALPHA)
    for i in range(3):
        for yy in (2, 19):
            pygame.draw.rect(s, (28, 28, 34), (3 + i * 7, yy, 6, 5), border_radius=2)
    pygame.draw.rect(s, (176, 176, 184), (2, 6, 21, 14), border_radius=3)
    pygame.draw.rect(s, (40, 76, 150), (4, 8, 14, 10))
    for i in range(1, 4):
        pygame.draw.line(s, (90, 130, 200), (4 + i * 3, 8), (4 + i * 3, 17))
    pygame.draw.line(s, (90, 130, 200), (4, 13), (17, 13))
    pygame.draw.circle(s, (255, 232, 130), (22, 13), 2)
    pygame.draw.line(s, (210, 210, 220), (6, 6), (6, 1), 1)
    return {(1, 0): s, (-1, 0): pygame.transform.flip(s, True, False),
            (0, 1): pygame.transform.rotate(s, -90), (0, -1): pygame.transform.rotate(s, 90)}


def draw_station(surf, rect, t):
    cx, cy = rect.center
    pygame.draw.rect(surf, (74, 92, 108), (rect.x + 4, cy - 1, T - 8, 11), border_radius=2)
    pygame.draw.rect(surf, (118, 146, 168), (rect.x + 4, cy - 1, T - 8, 11), 1, border_radius=2)
    pygame.draw.ellipse(surf, (150, 182, 204), (cx - 8, cy - 9, 16, 14))
    pygame.draw.ellipse(surf, (210, 236, 250), (cx - 5, cy - 8, 6, 5))
    pygame.draw.rect(surf, (36, 70, 140), (rect.x + 1, cy + 2, 4, 7))
    pygame.draw.rect(surf, (36, 70, 140), (rect.right - 5, cy + 2, 4, 7))
    pygame.draw.line(surf, (190, 200, 210), (cx + 6, cy - 6), (cx + 6, rect.y + 1), 1)
    on = int(t * 2) % 2 == 0
    pygame.draw.circle(surf, CYAN if on else (20, 70, 80), (cx + 6, rect.y + 2), 2)
    pygame.draw.circle(surf, (150, 255, 190), (cx - 4, cy + 6), 1)


def build_terrain(m, rng):
    surf = pygame.Surface((COLS * T, ROWS * T))
    f16 = ui.font(16)
    for y in range(ROWS):
        for x in range(COLS):
            _draw_tile(surf, m["grid"][y][x], pygame.Rect(x * T, y * T, T, T), rng, f16)
    for (x, y) in m["zones"]:                                 # rockfall-prone zones
        r = pygame.Rect(x * T, y * T, T, T)
        for i in range(0, T, 8):
            pygame.draw.line(surf, AMBER, (r.x + i, r.y + 1), (r.x + min(i + 4, T - 1), r.y + 1))
            pygame.draw.line(surf, AMBER, (r.x + i, r.bottom - 2), (r.x + min(i + 4, T - 1), r.bottom - 2))
            pygame.draw.line(surf, AMBER, (r.x + 1, r.y + i), (r.x + 1, r.y + min(i + 4, T - 1)))
            pygame.draw.line(surf, AMBER, (r.right - 2, r.y + i), (r.right - 2, r.y + min(i + 4, T - 1)))
        pygame.draw.polygon(surf, AMBER, [(r.x + 4, r.y + 14), (r.x + 12, r.y + 14), (r.x + 8, r.y + 5)])
    sx, sy = m["start"]
    r = pygame.Rect(sx * T, sy * T, T, T)
    pygame.draw.circle(surf, (20, 50, 60), r.center, 12)
    pygame.draw.circle(surf, CYAN, r.center, 12, 2)
    t = ui.font(20).render("S", True, CYAN)
    surf.blit(t, t.get_rect(center=r.center))
    return surf


# ---------------------------------------------------------------------- game
class SojournerChallenge:
    title = "LAST MISSION"

    def __init__(self, eq=None, seed=None):
        self.eq = eq
        self.seed = seed
        self.attempt = 0
        self._light_cache = {}
        self.rover_imgs = make_rover()
        r = random.Random(5)
        self.stars = [(r.randint(0, SCREEN_W), r.randint(0, SCREEN_H), r.randint(60, 200)) for _ in range(70)]
        self.dust = [(r.random(), r.random(), r.uniform(0.6, 1.6), r.randint(10, 34)) for _ in range(80)]
        self.reset()

    # ------------------------------------------------------------ state reset
    def reset(self):
        """Full reset (construction): back to the briefing with a fresh map."""
        self.attempt = 0
        self._new_mission()
        self.phase = "intro"
        self.t = 0.0
        self.intro_chars = 0
        self.buttons = ui.ButtonRow(["Begin Mission"], 446, w=300)
        self.end_buttons = None
        wrapped = []
        f = ui.font(28)
        for para in INTRO:
            wrapped += ui.wrap(para, f, 700) + [""]
        self.intro_lines = wrapped[:-1]
        self.intro_total = sum(len(l) for l in self.intro_lines)

    def _new_mission(self):
        """Generate a fresh solvable map and clear EVERY piece of mission state."""
        seed = None if self.seed is None else self.seed + self.attempt
        self.rng = random.Random(seed)
        self.map = generate_map(self.rng)
        self.grid, self.start, self.goal = self.map["grid"], self.map["start"], self.map["goal"]
        self.zones = list(self.map["zones"])
        self.battery_max = self.map["battery"]
        self.battery = self.battery_max
        self.terrain = build_terrain(self.map, random.Random(self.rng.random()))
        self.rock_sprite = self._make_block_sprite()
        self.rover = self.start
        self.rpos = [float(self.start[0]), float(self.start[1])]
        self.facing = (1, 0)
        self.moving = None                 # dict(frm, to, t)
        self.held = []
        self.hold_t = 0.0
        self.steps = 0
        self.visited = {self.start}
        self.explored = set()
        self.mem = pygame.Surface(MAP.size, pygame.SRCALPHA)
        self.mem.fill((0, 0, 0, 250))
        self.station_found = False
        self.vis_r = VIS_NORMAL
        self.dark_k = 0.0
        self.mission_t = 0.0
        self.ev = None                     # dict(kind, stage, t, tile)
        self.blocked = {}                  # tile -> seconds left
        self.storm_k = 0.0
        self.storms = self.rockfalls = 0
        self.next_event_t = self.rng.uniform(11, 15)
        self.banner = None                 # [text, colour, age]
        self.floaters = []
        self.bump_t = 0.0
        self.result_t = 0.0
        self.won = False

    def _make_block_sprite(self):
        s = pygame.Surface((T, T), pygame.SRCALPHA)
        r = random.Random(3)
        pygame.draw.rect(s, (96, 44, 30), (0, 0, T, T))
        _rock(s, 10, 17, 8, r, (130, 96, 84))
        _rock(s, 20, 12, 7, r, (112, 80, 70))
        _rock(s, 19, 22, 6, r, (146, 108, 92))
        pygame.draw.rect(s, AMBER, (0, 0, T, T), 2)
        return s

    def _set_phase(self, p):
        self.phase, self.t = p, 0.0

    # ----------------------------------------------------------- flow control
    def _start_recon(self):
        self._set_phase("recon")
        self.time_left = RECON_TIME

    def _start_blackout(self):
        self._set_phase("blackout")
        self._explore()

    def _win(self):
        self.won = True
        self.end_buttons = ui.ButtonRow(["Continue"], 452, w=280)
        self._set_phase("win")

    def _fail(self):
        self.end_buttons = ui.ButtonRow(["Retry"], 420, w=280)
        self._set_phase("fail")

    def _retry(self):
        """Retry = brand-new terrain/hazards, full battery, back at the start."""
        self.attempt += 1
        self._new_mission()
        self._start_recon()

    # ------------------------------------------------------------------ input
    def handle_event(self, e):
        if self.phase == "intro":
            if self.intro_chars < self.intro_total:
                if e.type in (pygame.KEYDOWN, pygame.MOUSEBUTTONDOWN):
                    self.intro_chars = self.intro_total      # skip the typewriter
            elif self.buttons.handle_event(e) == 0:
                self._start_recon()
        elif self.phase == "recon":
            if self.t > 1.5 and ((e.type == pygame.KEYDOWN and e.key in (pygame.K_SPACE, pygame.K_RETURN,
                                                                         pygame.K_KP_ENTER)) or
                                 (e.type == pygame.MOUSEBUTTONDOWN and e.button == 1)):
                self._start_blackout()                     # ready early
        elif self.phase == "night":
            if e.type == pygame.KEYDOWN and e.key in DIRS:
                d = DIRS[e.key]
                if d in self.held:
                    self.held.remove(d)
                self.held.append(d)
                self.hold_t = 0.0
                self._try_move(d)
            elif e.type == pygame.KEYUP and e.key in DIRS:
                d = DIRS[e.key]
                if d in self.held:
                    self.held.remove(d)
        elif self.phase == "fail":
            if self.t >= 0.9 and self.end_buttons.handle_event(e) == 0:
                self._retry()
        elif self.phase == "win":
            if self.t >= 0.9 and self.end_buttons.handle_event(e) == 0:
                return "done"                              # -> existing Memory Capsule flow
        return None

    # --------------------------------------------------------------- movement
    def _step_cost(self, tile):
        return COST[self.grid[tile[1]][tile[0]]] + (STORM_EXTRA if self._storm_active() else 0)

    def _say(self, text, colour=TEXT):
        self.banner = [text, colour, 0.0]

    def _try_move(self, d):
        if self.phase != "night" or self.moving:
            return
        nx, ny = self.rover[0] + d[0], self.rover[1] + d[1]
        self.facing = d
        if not (0 <= nx < COLS and 0 <= ny < ROWS):
            return
        if self.grid[ny][nx] == ROCK:
            self._reveal((nx, ny))
            self._say("Rock - path blocked (no power used)", AMBER)
            return
        if (nx, ny) in self.blocked:
            self._say("Rockfall debris - wait or take another route", AMBER)
            return
        cost = self._step_cost((nx, ny))
        if cost > self.battery:
            self._say("Not enough power for that terrain", RED)
            self._check_stuck()
            return
        self.battery -= cost
        self.steps += 1
        self.moving = dict(frm=self.rover, to=(nx, ny), t=0.0)
        self.floaters.append([f"-{cost}", AMBER if cost == 1 else (RED if cost > 2 else ORANGE),
                              self.rover[0], self.rover[1], 0.0])

    def _reveal(self, tile):
        if tile not in self.explored:
            self.explored.add(tile)
            self.mem.fill((0, 0, 0, 172), pygame.Rect(tile[0] * T, tile[1] * T, T, T))
            if tile == self.goal:
                self.station_found = True
                self._say("Station located!", GREEN)

    def _explore(self):
        cx, cy = self.rpos[0] + 0.5, self.rpos[1] + 0.5
        r = self.vis_r * 0.92
        for y in range(max(0, int(cy - r)), min(ROWS, int(cy + r) + 2)):
            for x in range(max(0, int(cx - r)), min(COLS, int(cx + r) + 2)):
                if math.hypot(x + 0.5 - cx, y + 0.5 - cy) <= r:
                    self._reveal((x, y))

    def _check_stuck(self):
        """Fail when power is gone, or no neighbouring tile is affordable."""
        if self.battery <= 0:
            self._fail()
            return
        x, y = self.rover
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = x + dx, y + dy
            if 0 <= nx < COLS and 0 <= ny < ROWS and self.grid[ny][nx] != ROCK \
                    and COST[self.grid[ny][nx]] <= self.battery:
                return
        self._fail()

    # ------------------------------------------------------------------ events
    def _storm_active(self):
        return bool(self.ev and self.ev["kind"] == "storm" and self.ev["stage"] == "active")

    def _plan_event(self):
        order = []
        if self.storms < 2:
            order.append("storm")
        if self.rockfalls < 3:
            order.append("rockfall")
        self.rng.shuffle(order)
        for kind in order:
            if kind == "storm":
                self.ev = dict(kind="storm", stage="warn", t=0.0, tile=None)
                self.storms += 1
                self._say("WARNING: dust storm approaching - visibility will drop", AMBER)
                return
            tile = self._pick_rockfall()
            if tile:
                self.ev = dict(kind="rockfall", stage="warn", t=0.0, tile=tile)
                self.rockfalls += 1
                self._say(f"WARNING: rockfall expected at {coord(tile)}", AMBER)
                return
        self.next_event_t = self.mission_t + 6.0

    def _route_ok(self, blocked):
        c, _ = route(self.grid, self.rover, self.goal, blocked)
        return c is not None and c <= self.battery - 2

    def _pick_rockfall(self):
        cands = [z for z in self.zones if z not in self.blocked and z != self.goal
                 and abs(z[0] - self.rover[0]) + abs(z[1] - self.rover[1]) >= 4]
        _, path = route(self.grid, self.rover, self.goal, self.blocked)
        on_path = set(path or [])
        cands.sort(key=lambda z: (z not in on_path, self.rng.random()))
        for z in cands:
            if self._route_ok(set(self.blocked) | {z}):
                return z
        return None

    def _update_events(self, dt):
        self.mission_t += dt
        for tile in list(self.blocked):
            self.blocked[tile] -= dt
            if self.blocked[tile] <= 0:
                del self.blocked[tile]
                self._say("Path cleared", GREEN)
        ev = self.ev
        if ev is None:
            if self.mission_t >= self.next_event_t and self.steps >= 2:
                self._plan_event()
        else:
            ev["t"] += dt
            if ev["stage"] == "warn" and ev["t"] >= WARN_TIME:
                ev["stage"], ev["t"] = "active", 0.0
                if ev["kind"] == "storm":
                    self._say("DUST STORM - visibility reduced, +1 power per move. Waiting is free.", RED)
                else:
                    z = ev["tile"]
                    moving_in = self.moving and self.moving["to"] == z
                    if z == self.rover or moving_in or not self._route_ok(set(self.blocked) | {z}):
                        self._say("Rockfall missed the route", GREEN)
                        self.ev = None
                        self.next_event_t = self.mission_t + self.rng.uniform(14, 20)
                        return
                    self.blocked[z] = ROCKFALL_TIME
                    self._reveal(z)
                    self._say(f"ROCKFALL at {coord(z)} - tile blocked for {int(ROCKFALL_TIME)} s", RED)
            elif ev["stage"] == "active":
                end = STORM_TIME if ev["kind"] == "storm" else 1.0
                if ev["t"] >= end:
                    if ev["kind"] == "storm":
                        self._say("Storm passing - visibility recovering", GREEN)
                    self.ev = None
                    self.next_event_t = self.mission_t + self.rng.uniform(15, 22)
        target = 1.0 if self._storm_active() else (0.25 if ev and ev["kind"] == "storm" else 0.0)
        rate = 1.4 if target > self.storm_k else 0.7
        self.storm_k += max(-rate * dt, min(rate * dt, target - self.storm_k))
        goal_r = VIS_NORMAL + (VIS_STORM - VIS_NORMAL) * min(1.0, self.storm_k)
        self.vis_r += max(-3 * dt, min(3 * dt, goal_r - self.vis_r))

    # ----------------------------------------------------------------- update
    def update(self, dt):
        dt = max(0.0, min(dt, 0.1))
        self.t += dt
        if self.phase == "intro":
            self.intro_chars = min(self.intro_total, self.intro_chars + dt * 55)
        elif self.phase == "recon":
            self.time_left = max(0.0, self.time_left - dt)
            if self.time_left <= 0:
                self._start_blackout()
        elif self.phase == "blackout":
            self.dark_k = min(1.0, self.t / BLACKOUT_TIME)
            if self.t >= BLACKOUT_TIME:
                self.dark_k = 1.0
                self._set_phase("night")
        elif self.phase == "night":
            self._update_night(dt)
        elif self.phase in ("win", "fail"):
            self.result_t = self.t
        if self.banner:
            self.banner[2] += dt
            if self.banner[2] > 3.2:
                self.banner = None
        for f in self.floaters:
            f[4] += dt
        self.floaters = [f for f in self.floaters if f[4] < 0.9]

    def _update_night(self, dt):
        self._update_events(dt)
        if self.moving:
            m = self.moving
            m["t"] += dt
            k = min(1.0, m["t"] / MOVE_TIME)
            self.rpos = [m["frm"][0] + (m["to"][0] - m["frm"][0]) * k, m["frm"][1] + (m["to"][1] - m["frm"][1]) * k]
            self.facing = (m["to"][0] - m["frm"][0], m["to"][1] - m["frm"][1])
            if k >= 1.0:
                self.rover = m["to"]
                self.rpos = [float(self.rover[0]), float(self.rover[1])]
                self.visited.add(self.rover)
                self.moving = None
                if self.rover == self.goal:
                    self._explore()
                    self._win()
                    return
                self._check_stuck()
                if self.phase != "night":
                    return
        self._explore()
        if self.held and not self.moving:
            self.hold_t += dt
            if self.hold_t >= HOLD_DELAY:
                self._try_move(self.held[-1])
        elif not self.held:
            self.hold_t = 0.0

    # ---------------------------------------------------------------- drawing
    def draw(self, surf):
        for x, y, b in self.stars:
            surf.set_at((x, y), (b, b, b))
        if self.phase == "intro":
            self._draw_intro(surf)
        elif self.phase in ("recon", "blackout", "night", "win", "fail"):
            self._draw_station(surf)
            if self.phase == "win":
                self._draw_win(surf)
            elif self.phase == "fail":
                self._draw_fail(surf)

    def _draw_intro(self, surf):
        r = ui.center_panel(surf, 800, 500)
        ui.draw_title(surf, "SOJOURNER  -  LAST MISSION", r.y + 18, 56)
        ui.draw_title(surf, "Final Challenge   |   Difficulty: EXTREME", r.y + 68, 26, AMBER)
        left = int(self.intro_chars)
        y = r.y + 112
        f = ui.font(28)
        for line in self.intro_lines:
            if left <= 0:
                break
            txt = line[:left]
            left -= len(line)
            if txt:
                t = f.render(txt, True, TEXT if line != "Good luck, Sojourner." else CYAN)
                surf.blit(t, t.get_rect(midtop=(SCREEN_W // 2, y)))
            y += 26 if line else 14
        if self.intro_chars >= self.intro_total:
            self.buttons.draw(surf)
        elif (pygame.time.get_ticks() // 500) % 2 == 0:
            ui.draw_title(surf, "press any key to skip", r.bottom - 34, 22, DIM)

    def _light(self, rpx):
        key = max(8, int(rpx) // 4 * 4)
        if key not in self._light_cache:
            s = pygame.Surface((key * 2, key * 2), pygame.SRCALPHA)
            s.fill((0, 0, 0, 250))
            for r in range(key, 0, -2):
                u = max(0.0, (r / key - 0.34) / 0.66)
                pygame.draw.circle(s, (0, 0, 0, int(250 * u ** 1.4)), (key, key), r)
            self._light_cache[key] = s
        return self._light_cache[key], key

    def _tile_px(self, x, y):
        return int(x * T), int(y * T)

    def _draw_station(self, surf):
        ui.draw_panel(surf, pygame.Rect(24, 18, 912, 504), 245)
        night = self.phase in ("blackout", "night", "win", "fail")
        surf.blit(ui.font(34).render("SOJOURNER  -  LAST MISSION", True, CYAN), (52, 30))
        sub = {"recon": "ROUTE RECONNAISSANCE", "blackout": "NIGHT FALLS", "night": "NIGHT MISSION",
               "win": "MISSION COMPLETE", "fail": "MISSION FAILED"}[self.phase]
        surf.blit(ui.font(24).render(sub, True, AMBER if self.phase != "fail" else RED), (52, 64))
        for i in range(COLS):
            t = ui.font(18).render(LETTERS[i], True, DIM)
            surf.blit(t, t.get_rect(center=(MAP.x + i * T + T // 2, MAP.y - 10)))
        for j in range(ROWS):
            t = ui.font(18).render(str(j + 1), True, DIM)
            surf.blit(t, t.get_rect(center=(MAP.x - 14, MAP.y + j * T + T // 2)))

        view = pygame.Surface(MAP.size)
        view.blit(self.terrain, (0, 0))
        gx, gy = self._tile_px(*self.goal)
        draw_station(view, pygame.Rect(gx, gy, T, T), pygame.time.get_ticks() / 1000)
        for tile in self.blocked:
            view.blit(self.rock_sprite, self._tile_px(*tile))

        if night:
            dark = self.mem.copy()
            rpx = self.vis_r * T
            light, key = self._light(rpx)
            cx, cy = int((self.rpos[0] + 0.5) * T), int((self.rpos[1] + 0.5) * T)
            dark.blit(light, (cx - key, cy - key), special_flags=pygame.BLEND_RGBA_MIN)
            if self.dark_k < 1.0:
                dark.set_alpha(int(255 * self.dark_k))
            view.blit(dark, (0, 0))
            self._draw_marks(view)
            rimg = self.rover_imgs[self.facing if self.facing in self.rover_imgs else (1, 0)]
            pygame.draw.circle(view, (255, 220, 120), (cx, cy), 16, 1)
            view.blit(rimg, (cx - 13, cy - 13))
            if self.storm_k > 0.02:
                self._draw_dust(view)
        else:
            self._draw_recon_marks(view)
        surf.blit(view, MAP.topleft)
        low = self.battery <= self.battery_max * 0.25 and night and self.phase == "night"
        pygame.draw.rect(surf, RED if low and int(self.t * 3) % 2 == 0 else CYAN, MAP.inflate(4, 4), 2)

        for f in self.floaters:
            txt = ui.font(26).render(f[0], True, f[1])
            surf.blit(txt, (MAP.x + int((f[2] + 0.4) * T), MAP.y + int((f[3] - 0.2) * T - f[4] * 26)))
        if self.banner and self.phase == "night":
            self._draw_banner(surf)
        if self.phase == "blackout":
            ui.draw_title(surf, "LIGHTS OUT", MAP.centery - 30, 64, RED)
        self._draw_side(surf)
        hint = ("Move with arrows/WASD. Save power and watch the dust."
                if night else "Study the map, then press SPACE when ready.")
        ui.draw_title(surf, hint, 497, 22, DIM)

    def _draw_recon_marks(self, view):
        gx, gy = self._tile_px(*self.goal)
        pulse = 0.5 + 0.5 * math.sin(pygame.time.get_ticks() / 250)
        pygame.draw.rect(view, (int(60 + 120 * pulse), 255, int(190 + 60 * pulse)), (gx - 1, gy - 1, T + 2, T + 2), 2)
        lab = ui.font(18).render("STATION", True, GREEN)
        view.blit(lab, lab.get_rect(midbottom=(gx + T // 2, gy - 1 if gy > 20 else gy + T + 18)))
        sx, sy = self._tile_px(*self.start)
        lab = ui.font(18).render("START", True, CYAN)
        view.blit(lab, lab.get_rect(midbottom=(sx + T // 2, sy - 1 if sy > 20 else sy + T + 18)))
        rimg = self.rover_imgs[(1, 0)]
        view.blit(rimg, (sx + 2, sy + 2))

    def _draw_marks(self, view):
        for (x, y) in self.visited:                          # trail
            if (x, y) != self.rover:
                pygame.draw.circle(view, (80, 200, 220), (x * T + T // 2, y * T + T // 2), 2)
        if self.station_found:
            gx, gy = self._tile_px(*self.goal)
            pygame.draw.rect(view, GREEN, (gx - 1, gy - 1, T + 2, T + 2), 1)
        pulse = 0.5 + 0.5 * math.sin(pygame.time.get_ticks() / 120)
        ev = self.ev
        if ev and ev["kind"] == "rockfall" and ev["stage"] == "warn":      # always-visible warning
            x, y = self._tile_px(*ev["tile"])
            pygame.draw.rect(view, (255, int(120 + 100 * pulse), 40), (x, y, T, T), 3)
            t = ui.font(26).render("!", True, AMBER)
            view.blit(t, t.get_rect(center=(x + T // 2, y + T // 2)))
        for tile in self.blocked:
            x, y = self._tile_px(*tile)
            view.blit(self.rock_sprite, (x, y))
            pygame.draw.rect(view, (255, int(120 + 100 * pulse), 40), (x, y, T, T), 2)

    def _draw_dust(self, view):
        k = min(1.0, self.storm_k)
        tint = pygame.Surface(MAP.size, pygame.SRCALPHA)
        tint.fill((170, 78, 34, int(64 * k)))
        view.blit(tint, (0, 0))
        tm = pygame.time.get_ticks() / 1000
        for fx, fy, sp, ln in self.dust:
            x = int(((fx + tm * 0.18 * sp) % 1.0) * MAP.w)
            y = int(fy * MAP.h + math.sin(tm * sp + fx * 9) * 6)
            pygame.draw.line(view, (226, 142, 84), (x, y), (x + ln, y + 2), 1)

    def _draw_banner(self, surf):
        text, col, age = self.banner
        t = ui.font(28).render(text, True, col)
        r = pygame.Rect(0, 0, t.get_width() + 40, 40)
        r.midtop = (MAP.centerx, MAP.y + 8 - int(max(0, 0.25 - age) * 160))
        ui.draw_panel(surf, r, 235)
        surf.blit(t, t.get_rect(center=r.center))

    # ---- sidebar
    def _draw_side(self, surf):
        ui.draw_panel(surf, SIDE, 215)
        x0, w = SIDE.x + 14, SIDE.w - 28

        def lab(txt, y, col=DIM, size=20):
            f = ui.font(size)
            while size > 14 and f.size(txt)[0] > w:
                size -= 1
                f = ui.font(size)
            surf.blit(f.render(txt, True, col), (x0, y))

        if self.phase in ("recon",):
            lab("MEMORIZE THE MAP", SIDE.y + 10, AMBER, 24)
            low = self.time_left <= 8
            c = RED if low and int(self.t * 4) % 2 == 0 else TEXT
            n = ui.font(84).render(str(int(math.ceil(self.time_left))), True, c)
            surf.blit(n, n.get_rect(midtop=(SIDE.centerx, SIDE.y + 32)))
            bar = pygame.Rect(x0, SIDE.y + 112, w, 8)
            pygame.draw.rect(surf, (12, 18, 26), bar)
            pygame.draw.rect(surf, RED if low else AMBER, (bar.x, bar.y, int(bar.w * self.time_left / RECON_TIME), bar.h))
            pygame.draw.rect(surf, (40, 60, 70), bar, 1)
            lab("Battery", SIDE.y + 132)
            lab(f"{self.battery_max} units", SIDE.y + 150, GREEN, 30)
            lab(f"Best route costs ~{self.map['opt_cost']}", SIDE.y + 180, TEXT, 20)
            y = SIDE.y + 208
            for name, col, extra in (("Flat  -1", (118, 52, 34), ""), ("Rough sand  -2", (150, 84, 52), ""),
                                     ("Unstable  -3", (80, 32, 24), ""), ("Rock  blocked", (104, 74, 66), ""),
                                     ("Rockfall zone", AMBER, "z")):
                sw = pygame.Rect(x0, y + 2, 16, 16)
                pygame.draw.rect(surf, col, sw, 0 if not extra else 2)
                if not extra:
                    pygame.draw.rect(surf, (200, 200, 210), sw, 1)
                lab("   " + name, y, TEXT, 20)
                y += 24
            lab("Press SPACE when ready", SIDE.bottom - 28, DIM, 18)
            return
        # battery
        frac = max(0.0, self.battery / self.battery_max)
        col = GREEN if frac > 0.5 else (AMBER if frac > 0.25 else RED)
        flash = frac <= 0.25 and int(pygame.time.get_ticks() / 300) % 2 == 0
        lab("BATTERY", SIDE.y + 10, DIM, 22)
        if frac <= 0.25:
            lab("LOW POWER", SIDE.y + 30, RED, 16)
        n = ui.font(64).render(str(self.battery), True, RED if flash else col)
        surf.blit(n, n.get_rect(midtop=(SIDE.centerx, SIDE.y + 48)))
        bar = pygame.Rect(x0, SIDE.y + 90, w, 20)
        pygame.draw.rect(surf, (12, 18, 26), bar)
        pygame.draw.rect(surf, col, (bar.x, bar.y, int(bar.w * frac), bar.h))
        for k in range(1, 4):
            pygame.draw.line(surf, (12, 18, 26), (bar.x + bar.w * k // 4, bar.y), (bar.x + bar.w * k // 4, bar.bottom))
        pygame.draw.rect(surf, CYAN, bar, 1)
        lab(f"of {self.battery_max} units", SIDE.y + 114, DIM, 18)
        # status block
        under = self.grid[self.rover[1]][self.rover[0]]
        tcol = {FLAT: TEXT, ROUGH: AMBER, UNSTABLE: RED}[under]
        extra = f" +{STORM_EXTRA}" if self._storm_active() else ""
        lab("POSITION", SIDE.y + 146)
        lab(coord(self.rover), SIDE.y + 162, TEXT, 28)
        lab("TERRAIN", SIDE.y + 192)
        lab(TERRAIN_NAME[under], SIDE.y + 208, tcol, 22)
        lab(f"Step cost: {COST[under]}{extra}", SIDE.y + 228, DIM, 18)
        vis = "REDUCED" if self.vis_r < VIS_NORMAL - 0.3 else "Normal"
        lab("VISIBILITY", SIDE.y + 252)
        lab(f"{vis}  ({self.vis_r:.1f})", SIDE.y + 268, RED if vis == "REDUCED" else TEXT, 22)
        lab("HAZARD", SIDE.y + 298)
        ev = self.ev
        if ev and ev["kind"] == "storm":
            left = (WARN_TIME - ev["t"]) if ev["stage"] == "warn" else (STORM_TIME - ev["t"])
            lab(("Storm in " if ev["stage"] == "warn" else "DUST STORM ") + f"{max(0, left):.0f}s",
                SIDE.y + 314, AMBER if ev["stage"] == "warn" else RED, 22)
        elif ev and ev["kind"] == "rockfall" and ev["stage"] == "warn":
            lab(f"Rockfall {coord(ev['tile'])}", SIDE.y + 314, AMBER, 22)
        elif self.blocked:
            lab(f"Debris {coord(next(iter(self.blocked)))}", SIDE.y + 314, RED, 22)
        else:
            lab("None", SIDE.y + 314, GREEN, 22)
        lab("STATION", SIDE.y + 342)
        lab("LOCATED" if self.station_found else "Unknown", SIDE.y + 358, GREEN if self.station_found else DIM, 22)

    # ---- end screens
    def _draw_win(self, surf):
        dim = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
        dim.fill((0, 0, 0, 150))
        surf.blit(dim, (0, 0))
        r = ui.center_panel(surf, 800, 480)
        ui.draw_title(surf, "MISSION COMPLETE", r.y + 16, 66, GREEN)
        ui.draw_title(surf, "The instruments have been delivered.", r.y + 82, 32, TEXT)
        body = r.inflate(-90, 0)
        y = ui.draw_wrapped(surf, "Through darkness, dust and falling rock, Sojourner carried its last "
                                  "cargo home. From Ingenuity's sky to the Viking landers' first photographs, "
                                  "every machine left something behind - and you brought it all together.",
                            26, body, r.y + 126)
        y = ui.draw_wrapped(surf, "The six-mission challenge is complete. The archive remembers.", 28, body, y + 8, CYAN)
        left = self.battery / self.battery_max
        rank = "S" if left >= 0.30 else ("A" if left >= 0.20 else ("B" if left >= 0.10 else "C"))
        rc = {"S": CYAN, "A": GREEN, "B": AMBER, "C": ORANGE}[rank]
        ui.draw_title(surf, f"Battery left {self.battery}/{self.battery_max}    Steps {self.steps}    "
                            f"Best route {self.map['opt_cost']}", y + 18, 26, TEXT)
        ui.draw_title(surf, f"RANK  {rank}", y + 52, 56, rc)
        self.end_buttons.draw(surf)

    def _draw_fail(self, surf):
        dim = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
        dim.fill((0, 0, 0, min(170, int(self.t * 300))))
        surf.blit(dim, (0, 0))
        if self.t < 0.5:
            return
        r = ui.center_panel(surf, 700, 340)
        ui.draw_title(surf, "MISSION FAILED", r.y + 24, 68, RED)
        body = r.inflate(-80, 0)
        ui.draw_wrapped(surf, "Sojourner's power is gone. The instruments never reached the station.",
                        30, body, r.y + 108)
        ui.draw_title(surf, f"Steps taken: {self.steps}     Station located: {'yes' if self.station_found else 'no'}",
                      r.y + 190, 26, DIM)
        ui.draw_title(surf, "Retry builds a new terrain with new hazards.", r.y + 222, 24, DIM)
        self.end_buttons.draw(surf)


# ----------------------------------------------------- standalone test runner
if __name__ == "__main__":
    pygame.init()
    screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
    pygame.display.set_caption("Sojourner - Last Mission (standalone)")
    clock = pygame.time.Clock()
    game = SojournerChallenge()
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
