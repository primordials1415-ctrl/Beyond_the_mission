"""24 METERS ABOVE - Ingenuity minigame screen (pygame view + input).

Plugs into puzzle.CHALLENGES. Interface expected by EncounterScene:
    handle_event(e) -> "done" once the flight succeeded and the player pressed Continue
    update(dt), draw(surf)
All rules live in ingenuity_flight.FlightSim; this file only shows it and feeds it input.
"""
import math
import random
import pygame
from settings import SCREEN_W, SCREEN_H, CYAN, TEXT, DIM
import ui
import ingenuity_flight as fl

LOW_W, LOW_H = SCREEN_W // 2, SCREEN_H // 2      # world is drawn at half size then upscaled (pixel look)
HELI_X = 260                                      # heli screen x (full res)
GROUND_Y = 458                                    # ground line (full res)
ALT_TOP_Y, ALT_BOT_Y = 100, 424                    # screen y for altitude 1.0 / 0.0 (heli centre)
HOLD_KEYS = (pygame.K_SPACE, pygame.K_s, pygame.K_DOWN, pygame.K_LSHIFT, pygame.K_RSHIFT)
BTN = pygame.Rect(SCREEN_W - 270, SCREEN_H - 74, 240, 54)   # on-screen HOLD button
STRIKE_RED = (255, 90, 80)
DAMAGE_TEXT = {"spire": "Rock strike! Fuselage damaged", "ledge": "Cliff strike! Rotor damaged",
               "dust": "Dust in the rotors! Sensors degraded", "devil": "Dust devil! Thrown off course"}


def alt_to_y(a):
    return ALT_BOT_Y - (ALT_BOT_Y - ALT_TOP_Y) * a


def _mix(c1, c2, k):
    return tuple(int(a + (b - a) * k) for a, b in zip(c1, c2))


# ----------------------------------------------------------------- art
def make_sky():
    """Butterscotch Martian sky, dark at the top, dusty at the horizon (low-res)."""
    s = pygame.Surface((LOW_W, LOW_H))
    top, mid, hor = (58, 30, 40), (150, 82, 66), (226, 152, 104)
    for y in range(LOW_H):
        k = y / (LOW_H * 0.86)
        col = _mix(top, mid, k / 0.55) if k < 0.55 else _mix(mid, hor, min(1.0, (k - 0.55) / 0.45))
        pygame.draw.line(s, col, (0, y), (LOW_W, y))
    rng = random.Random(11)
    for _ in range(28):                                  # a few faint stars high up
        v = rng.randint(120, 200)
        s.set_at((rng.randrange(LOW_W), rng.randrange(0, 40)), (v, v - 20, v - 30))
    return s


def make_ridge(seed, base, amp, color, edge, width=LOW_W * 2):
    """Seamless tileable mountain silhouette (low-res), scrolled for parallax."""
    rng = random.Random(seed)
    s = pygame.Surface((width, LOW_H), pygame.SRCALPHA)
    n = 9
    phases = [(rng.uniform(0, 6.28), rng.randint(1, 3) * (1 + i)) for i in range(n)]
    pts = []
    for x in range(0, width + 4, 4):
        y = base
        for i, (ph, f) in enumerate(phases[:4]):
            y += math.sin(2 * math.pi * (x / width) * (f + i) + ph) * amp / (1 + i * 0.9)
        pts.append((x, y))
    poly = [(0, LOW_H)] + pts + [(width, LOW_H)]
    pygame.draw.polygon(s, color, poly)
    pygame.draw.lines(s, edge, False, pts, 1)
    return s


def make_ground_strip():
    """Seamless rocky ground band at the bottom of the low-res frame."""
    w, h = LOW_W * 2, LOW_H - GROUND_Y // 2
    s = pygame.Surface((w, h))
    rng = random.Random(21)
    s.fill((142, 70, 46))
    pygame.draw.rect(s, (176, 96, 58), (0, 0, w, 2))
    pygame.draw.rect(s, (96, 44, 32), (0, 2, w, 1))
    for _ in range(260):
        x, y = rng.randrange(w), rng.randrange(3, h)
        col = rng.choice(((120, 58, 40), (166, 90, 54), (104, 48, 36), (186, 108, 66)))
        pygame.draw.rect(s, col, (x, y, rng.choice((1, 2, 3)), rng.choice((1, 1, 2))))
    return s


def draw_heli(frame, damaged=0):
    """Ingenuity, side view, in the project's pixel style (white body, solar panel, rotors)."""
    s = pygame.Surface((40, 34), pygame.SRCALPHA)
    OUT = (28, 30, 44)
    pygame.draw.line(s, (90, 100, 120), (20, 22), (20, 6), 1)                      # mast
    for x, y in ((12, 31), (28, 31)):                                               # legs
        pygame.draw.line(s, OUT, (20, 24), (x, y), 1)
        pygame.draw.line(s, (170, 178, 192), (x - 2, 31), (x + 2, 31), 1)
    pygame.draw.rect(s, OUT, (14, 22, 13, 8))                                       # fuselage
    pygame.draw.rect(s, (236, 234, 226), (15, 23, 11, 6))
    pygame.draw.rect(s, (172, 150, 96), (15, 27, 11, 2))                            # gold foil
    pygame.draw.rect(s, (48, 62, 96), (18, 25, 3, 2))                               # camera eye
    pygame.draw.rect(s, OUT, (11, 2, 19, 6))                                        # solar panel
    pygame.draw.rect(s, (26, 52, 100), (12, 3, 17, 4))
    pygame.draw.line(s, (92, 140, 200), (13, 4), (27, 4), 1)
    spin = frame % 3                                                                # counter-rotating blades
    for y, ln in ((12, (17, 15, 18)[spin]), (16, (15, 18, 16)[spin])):
        pygame.draw.line(s, (214, 218, 226), (20 - ln, y), (20 + ln, y), 1)
        pygame.draw.line(s, (150, 156, 170), (20 - ln, y + 1), (20 + ln, y + 1), 1)
    if damaged:
        pygame.draw.rect(s, (60, 40, 34), (22, 24, 3, 3))                          # scorch mark
    # Keep the helicopter facing the direction of travel while the world scrolls
    # opposite to the simulated forward movement. The scene reads left-to-right,
    # so the nose points to the right. The rotor animation stays aligned frame-by-frame.
    return pygame.transform.flip(s, True, False)


def draw_spire(h_px, w_px, seed, tint=0):
    """Rock butte rising from the ground (low-res surface w_px x h_px). The flat, jagged top
    deliberately matches the hazard's rectangular hitbox, so what you see is what hurts."""
    rng = random.Random(seed)
    s = pygame.Surface((w_px, h_px + 6), pygame.SRCALPHA)
    n = 6
    left, right = [], []
    for i in range(n + 1):
        y = h_px - h_px * i / n
        half = (w_px / 2 - 2) * (1 - 0.10 * (i / n)) + rng.uniform(-1.5, 1.5)
        left.append((w_px / 2 - half, y))
        right.append((w_px / 2 + half, y))
    top_edge = [(left[-1][0] + (right[-1][0] - left[-1][0]) * k / 8, rng.uniform(0, 3)) for k in range(9)]
    pts = left + top_edge + right[::-1]
    base = rng.choice(((122, 64, 46), (136, 72, 50), (108, 58, 44)))
    pygame.draw.polygon(s, base, pts)
    pygame.draw.polygon(s, tuple(max(0, c - 28) for c in base),
                        [(w_px * 0.72, 3)] + right[::-1] + [(w_px * 0.72, h_px)])      # shaded right face
    pygame.draw.polygon(s, (176, 100, 62), top_edge + [(top_edge[-1][0], 5), (top_edge[0][0], 5)])   # lit top rim
    pygame.draw.polygon(s, (58, 26, 22), pts, 1)
    for _ in range(max(3, h_px // 8)):
        x, y = rng.randint(4, w_px - 5), rng.randint(8, h_px)
        s.set_at((x, y), (70, 30, 26))
    return s


def draw_ledge(h_px, w_px, seed):
    """Overhanging cliff hanging from the top of the screen."""
    rng = random.Random(seed)
    s = pygame.Surface((w_px, h_px + 6), pygame.SRCALPHA)
    pts = [(0, 0), (w_px, 0)]
    n = 7
    for i in range(n + 1):
        x = w_px - w_px * i / n
        depth = h_px - rng.uniform(0, 8) - (6 if i in (0, n) else 0)
        pts.append((x, depth))
    base = rng.choice(((112, 58, 44), (126, 66, 48)))
    pygame.draw.polygon(s, base, pts)
    pygame.draw.polygon(s, tuple(max(0, c - 26) for c in base), [(0, 0), (w_px, 0), (w_px, 6), (0, 6)])
    pygame.draw.polygon(s, (58, 26, 22), pts, 1)
    for _ in range(max(3, h_px // 10)):
        s.set_at((rng.randint(3, w_px - 4), rng.randint(2, max(3, h_px - 3))), (70, 30, 26))
    return s


class IngenuityChallenge:
    title = "24 METERS ABOVE"

    INTRO_TEXT = ("Ingenuity is flying across the Martian terrain and it keeps accelerating. "
                  "Hold to descend, release to climb. Reach Wright Brothers Field "
                  "before you lose all three strikes.")

    def __init__(self, eq, seed=None):
        self.eq = eq
        self.seed = seed
        self.phase = "intro"          # intro | flying | lost | won | done
        self.t = 0.0
        self.sim = None
        self.input_held = False       # combined keyboard / mouse / touch hold
        self._keys, self._mouse, self._fingers = set(), False, set()
        self.buttons = ui.ButtonRow(["Start Flight"], 420, w=280)
        self.attempts = 0
        self._build_art()
        self.banner = None            # [text, age]
        self.damage_msg = None        # [text, age]
        self.shake = 0.0
        self.particles = []
        self.scroll = 0.0
        self.frame_t = 0.0

    # ----------------------------------------------------------- setup
    def _build_art(self):
        self.sky = make_sky()
        self.layers = [(make_ridge(3, 150, 16, (126, 70, 70), (150, 92, 84)), 0.05),
                       (make_ridge(7, 176, 22, (110, 56, 56), (136, 78, 70)), 0.12),
                       (make_ridge(9, 198, 14, (96, 46, 44), (124, 68, 58)), 0.26)]
        self.ground = make_ground_strip()
        self.heli_frames = [draw_heli(i) for i in range(3)]
        self.heli_hurt = [draw_heli(i, 1) for i in range(3)]
        self.low = pygame.Surface((LOW_W, LOW_H))
        self.cloud = pygame.Surface((LOW_W, LOW_H), pygame.SRCALPHA)
        self.dust_motes = [(random.Random(i).random(), random.Random(i + 99).random(),
                            random.Random(i + 7).uniform(0.4, 1.4)) for i in range(40)]
        self._sprite_cache = {}

    def start_flight(self):
        """(Re)initialise every piece of per-flight state. Used for first start and for Retry."""
        self.sim = fl.FlightSim(self.seed if self.seed is not None else None)
        self.attempts += 1
        self._keys.clear()
        self._fingers.clear()
        self._mouse = False
        self.input_held = False
        self.banner = [fl.PHASE_NAMES[1], 0.0]
        self.damage_msg = None
        self.shake = 0.0
        self.particles = []
        self.scroll = 0.0
        self.t = 0.0
        self.phase = "flying"

    # ----------------------------------------------------------- input
    def _recalc_hold(self):
        self.input_held = bool(self._keys or self._mouse or self._fingers) and self.phase == "flying"

    def _release_all(self):
        self._keys.clear()
        self._fingers.clear()
        self._mouse = False
        self.input_held = False

    def handle_event(self, e):
        if self.phase == "done":
            return None
        if self.phase == "intro":
            if self.buttons.handle_event(e) == 0:
                self.start_flight()
            return None
        if self.phase == "flying":
            self._flight_input(e)
            return None
        if self.phase == "lost":
            if self.t >= 0.5 and self.buttons.handle_event(e) == 0:      # Retry
                self.start_flight()
            return None
        if self.phase == "won":
            if self.t >= 0.6 and self.buttons.handle_event(e) == 0:      # Continue -> capsule reward
                self.phase = "done"
                return "done"
        return None

    def _flight_input(self, e):
        if e.type == pygame.KEYDOWN and e.key in HOLD_KEYS:
            self._keys.add(e.key)
        elif e.type == pygame.KEYUP and e.key in HOLD_KEYS:
            self._keys.discard(e.key)
        elif e.type == pygame.MOUSEBUTTONDOWN and getattr(e, "button", 1) == 1 and BTN.collidepoint(e.pos):
            self._mouse = True
        elif e.type == pygame.MOUSEBUTTONUP and getattr(e, "button", 1) == 1:
            self._mouse = False
        elif e.type == getattr(pygame, "FINGERDOWN", -1):
            if BTN.collidepoint(e.x * SCREEN_W, e.y * SCREEN_H):
                self._fingers.add(e.finger_id)
        elif e.type == getattr(pygame, "FINGERUP", -1):
            self._fingers.discard(e.finger_id)
        self._recalc_hold()

    # ----------------------------------------------------------- update
    def update(self, dt):
        if self.phase in ("done",):
            return
        self.t += dt
        self.frame_t += dt
        if self.banner:
            self.banner[1] += dt
            if self.banner[1] > 2.6:
                self.banner = None
        if self.damage_msg:
            self.damage_msg[1] += dt
            if self.damage_msg[1] > 2.0:
                self.damage_msg = None
        self.shake = max(0.0, self.shake - dt * 2.5)
        if self.sim is None or self.phase not in ("flying",):
            if self.phase == "intro":
                self.scroll += 120 * dt         # idle scenery drift behind the intro panel
            self._update_particles(dt)
            return
        self.sim.update(dt, self.input_held)
        self.scroll = self.sim.dist
        for ev in self.sim.drain_events():
            self._on_event(ev)
        self._update_particles(dt)
        self._emit_dust(dt)

    def _on_event(self, ev):
        kind = ev[0]
        if kind == "hit":
            self.shake = 0.55
            self.damage_msg = [DAMAGE_TEXT.get(ev[1].kind, "Collision!"), 0.0]
            for _ in range(22):
                a = random.uniform(0, 6.28)
                sp = random.uniform(60, 220)
                self.particles.append([HELI_X, alt_to_y(self.sim.alt), math.cos(a) * sp, math.sin(a) * sp,
                                       random.uniform(0.4, 0.9), random.choice(((255, 200, 120), (236, 234, 226), (160, 90, 60)))])
        elif kind == "phase":
            self.banner = [fl.PHASE_NAMES[ev[1]], 0.0]
        elif kind == "lost":
            self._release_all()
            self.phase, self.t = "lost", 0.0
            self.buttons = ui.ButtonRow(["Retry"], 400, w=280)
        elif kind == "won":
            self._release_all()
            self.phase, self.t = "won", 0.0
            self.buttons = ui.ButtonRow(["Continue"], 400, w=280)

    def _emit_dust(self, dt):
        if self.sim.state == "landing" or self.sim.touchdown_t > 0:
            if self.sim.alt < 0.25 and random.random() < 0.9:
                self.particles.append([HELI_X + random.uniform(-30, 30), GROUND_Y - 6, random.uniform(-90, 90),
                                       random.uniform(-25, -4), random.uniform(0.5, 1.1), (214, 150, 104)])

    def _update_particles(self, dt):
        for p in self.particles:
            p[0] += p[2] * dt
            p[1] += p[3] * dt
            p[3] += 140 * dt * (0 if p[5] == (214, 150, 104) else 1)
            p[4] -= dt
        self.particles = [p for p in self.particles if p[4] > 0]

    # ------------------------------------------------------------ draw
    def _wx(self, world_x):
        return HELI_X + (world_x - (self.sim.dist if self.sim else self.scroll))

    def draw(self, surf):
        sim = self.sim
        dist = sim.dist if sim else self.scroll
        low = self.low
        low.blit(self.sky, (0, 0))
        for layer, k in self.layers:                                  # parallax mountains
            ox = int(dist * k / 2) % layer.get_width()
            low.blit(layer, (-ox, 0))
            low.blit(layer, (layer.get_width() - ox, 0))
        gy = GROUND_Y // 2
        gx = int(dist * 0.5) % self.ground.get_width()
        low.blit(self.ground, (-gx, gy))
        low.blit(self.ground, (self.ground.get_width() - gx, gy))
        if sim:
            self._draw_pad(low, sim)
            for h in sim.hazards:
                if h.kind in ("spire", "ledge"):
                    self._draw_rock(low, h)
            self._draw_heli(low, sim)
        else:
            self._blit_heli_idle(low)
        # upscale world
        ox = oy = 0
        if self.shake > 0:
            ox, oy = random.randint(-3, 3) * self.shake, random.randint(-3, 3) * self.shake
        frame = pygame.transform.scale(low, (SCREEN_W, SCREEN_H))
        surf.blit(frame, (int(ox), int(oy)))
        if sim:
            self._draw_clouds(surf, sim)
            self._draw_warnings(surf, sim)
        self._draw_particles(surf)
        if self.phase == "intro":
            self._draw_intro(surf)
            return
        self._draw_hud(surf, sim)
        if self.phase == "lost":
            self._draw_end(surf, "FLIGHT LOST", "Ingenuity sustained too much damage during its flight.", STRIKE_RED)
        elif self.phase == "won":
            self._draw_end(surf, "FLIGHT SUCCESSFUL", "Ingenuity has completed its flight across the Martian terrain.", CYAN)

    # --- world pieces
    def _sprite(self, key, make):
        if key not in self._sprite_cache:
            self._sprite_cache[key] = make()
        return self._sprite_cache[key]

    def _draw_rock(self, low, h):
        sx0 = self._wx(h.x0) / 2
        w = int((h.x1 - h.x0) / 2)
        if sx0 > LOW_W + 4 or sx0 + w < -4:
            return
        if h.kind == "spire":
            top = int(alt_to_y(h.hi) / 2)
            hp = max(8, GROUND_Y // 2 + 2 - top)
            spr = self._sprite(("s", h.seed, hp, w), lambda: draw_spire(hp, w, h.seed))
            low.blit(spr, (int(sx0), top))
        else:
            bottom = int(alt_to_y(h.lo) / 2)
            hp = max(8, bottom + 4)
            spr = self._sprite(("l", h.seed, hp, w), lambda: draw_ledge(hp, w, h.seed))
            low.blit(spr, (int(sx0), -4))

    def _draw_pad(self, low, sim):
        px = self._wx(fl.PAD_X) / 2
        if px < -80 or px > LOW_W + 200:
            return
        gy = GROUND_Y // 2
        pygame.draw.rect(low, (70, 52, 56), (int(px) - 60, gy - 2, 120, 4))
        pygame.draw.rect(low, (206, 196, 170), (int(px) - 60, gy - 2, 120, 1))
        pygame.draw.rect(low, (236, 234, 226), (int(px) - 3, gy - 1, 6, 1))
        on = int(self.frame_t * 3) % 2
        for dx in (-58, -29, 0, 29, 56):                       # runway lights
            col = (255, 220, 120) if on else (150, 110, 60)
            pygame.draw.rect(low, col, (int(px) + dx, gy - 4, 2, 2))
        pygame.draw.line(low, (150, 156, 170), (int(px) + 70, gy - 2), (int(px) + 70, gy - 26), 1)   # flag
        pygame.draw.polygon(low, (236, 122, 42), [(int(px) + 70, gy - 26), (int(px) + 82, gy - 22), (int(px) + 70, gy - 18)])

    def _heli_pos(self, sim):
        return HELI_X // 2, int(alt_to_y(sim.alt) / 2)

    def _draw_heli(self, low, sim):
        if sim.immunity > 0 and int(sim.immunity * 14) % 2 == 0 and sim.state != "lost":
            return                                              # blink while immune
        frames = self.heli_hurt if sim.strikes < fl.MAX_STRIKES else self.heli_frames
        spr = frames[int(self.frame_t * 24) % 3]
        # shadow on the ground scales with height
        cx, cy = self._heli_pos(sim)
        k = max(0.25, 1 - sim.alt)
        pygame.draw.ellipse(low, (74, 32, 26), (cx - int(18 * k), GROUND_Y // 2 + 2, int(36 * k), 3))
        low.blit(spr, (cx - 20, cy - 17))

    def _blit_heli_idle(self, low):
        spr = self.heli_frames[int(self.frame_t * 24) % 3]
        low.blit(spr, (HELI_X // 2 - 20, int(alt_to_y(0.4) / 2 + math.sin(self.frame_t * 2) * 3) - 17))

    # --- full-res overlays
    def _draw_clouds(self, surf, sim):
        ov = self.cloud
        ov.fill((0, 0, 0, 0))
        t = self.frame_t
        for h in sim.hazards:
            sx0, sx1 = self._wx(h.x0), self._wx(h.x1)
            if sx0 > SCREEN_W + 40 or sx1 < -40:
                continue
            if h.kind == "dust":
                ytop = 0 if h.hi > 1.5 else alt_to_y(h.hi)
                ybot = GROUND_Y if h.lo < 0 else alt_to_y(h.lo)
                self._dust_band(ov, sx0 / 2, sx1 / 2, ytop / 2, ybot / 2, h.seed, t)
            elif h.kind == "devil":
                self._dust_devil(ov, (sx0 + sx1) / 4, (alt_to_y(h.lo) + alt_to_y(h.hi)) / 4, h, t)
        surf.blit(pygame.transform.scale(ov, (SCREEN_W, SCREEN_H)), (0, 0))
        for h in sim.hazards:                                  # dashed outline = clear dust-cloud marker
            if h.kind != "dust":
                continue
            sx0, sx1 = self._wx(h.x0), self._wx(h.x1)
            if sx0 > SCREEN_W or sx1 < 0:
                continue
            ytop = 0 if h.hi > 1.5 else alt_to_y(h.hi)
            ybot = GROUND_Y if h.lo < 0 else alt_to_y(h.lo)
            edge_y = ytop if h.lo < 0 else ybot          # the edge that faces the safe window
            x = max(0, int(sx0))
            while x < min(SCREEN_W, sx1):
                pygame.draw.line(surf, (255, 190, 110), (x, int(edge_y)), (min(x + 12, int(sx1)), int(edge_y)), 2)
                x += 22
            tag = ui.font(22).render("DUST", True, (255, 214, 150))
            surf.blit(tag, (max(6, int(sx0) + 8), int(edge_y) + (6 if h.lo >= 0 else -20)))

    def _dust_band(self, ov, x0, x1, y0, y1, seed, t):
        rng = random.Random(seed)
        w, hgt = max(10, x1 - x0), max(10, y1 - y0)
        pygame.draw.rect(ov, (196, 120, 78, 70), (int(x0), int(y0), int(w), int(hgt)))
        n = int(w / 14) + 4
        for i in range(n):
            px = x0 + rng.uniform(0, w) + math.sin(t * 0.8 + i) * 2
            py = y0 + rng.uniform(0, hgt)
            r = rng.randint(10, 22)
            pygame.draw.circle(ov, (214, 140, 94, 70), (int(px), int(py)), r)
            pygame.draw.circle(ov, (232, 168, 116, 55), (int(px - 3), int(py - 3)), max(4, r - 6))
        pygame.draw.rect(ov, (232, 168, 116, 150), (int(x0), int(y0), int(w), int(hgt)), 1)

    def _dust_devil(self, ov, cx, cy, h, t):
        half_h = (alt_to_y(h.lo) - alt_to_y(h.hi)) / 4
        for i in range(9):
            k = i / 8
            yy = cy - half_h * 1.6 + k * half_h * 3.2
            ww = 6 + 20 * k
            off = math.sin(t * 6 + i * 0.9) * 4
            pygame.draw.ellipse(ov, (210, 130, 84, 150), (int(cx - ww + off), int(yy - 3), int(ww * 2), 7))
            pygame.draw.ellipse(ov, (240, 190, 140, 110), (int(cx - ww * 0.6 + off), int(yy - 2), int(ww * 1.2), 4))

    def _draw_warnings(self, surf, sim):
        for ahead, c in sim.devil_warnings():
            sx = HELI_X + ahead
            if sx < SCREEN_W + 20:
                continue                        # on screen already: the devil itself is the cue
            y = int(alt_to_y(c))
            blink = int(self.frame_t * 6) % 2
            col = STRIKE_RED if blink else (255, 190, 110)
            pts = [(SCREEN_W - 14, y), (SCREEN_W - 44, y - 17), (SCREEN_W - 44, y + 17)]
            pygame.draw.polygon(surf, (20, 10, 12), pts)
            pygame.draw.polygon(surf, col, pts, 3)
            m = ui.font(30).render("!", True, col)
            surf.blit(m, m.get_rect(center=(SCREEN_W - 33, y + 1)))
            pygame.draw.line(surf, col, (SCREEN_W - 44, y), (SCREEN_W - 120, y), 1)

    def _draw_particles(self, surf):
        for x, y, vx, vy, life, col in self.particles:
            r = 3 if col != (214, 150, 104) else 5
            pygame.draw.circle(surf, col, (int(x), int(y)), r)

    # --- HUD
    def _draw_hud(self, surf, sim):
        # top-left: name + progress
        panel = pygame.Rect(14, 10, 400, 54)
        ui.draw_panel(surf, panel, 205)
        surf.blit(ui.font(26).render("INGENUITY", True, CYAN), (panel.x + 12, panel.y + 6))
        pct = int((sim.progress if sim else 0) * 100)
        surf.blit(ui.font(22).render(f"FLIGHT {pct}%", True, TEXT), (panel.right - 100, panel.y + 8))
        bar = pygame.Rect(panel.x + 12, panel.y + 34, panel.w - 24, 10)
        pygame.draw.rect(surf, (12, 18, 26), bar)
        if sim:
            pygame.draw.rect(surf, CYAN, (bar.x, bar.y, int(bar.w * sim.progress), bar.h))
            for ph in (0.28, 0.62):
                pygame.draw.line(surf, (30, 70, 90), (bar.x + int(bar.w * ph), bar.y - 2), (bar.x + int(bar.w * ph), bar.bottom + 2), 2)
            pygame.draw.circle(surf, (236, 122, 42), (bar.x + int(bar.w * sim.progress), bar.centery), 6)
        pygame.draw.rect(surf, (40, 60, 70), bar, 1)
        # top-right: strikes
        spanel = pygame.Rect(SCREEN_W - 230, 10, 216, 54)
        ui.draw_panel(surf, spanel, 205)
        surf.blit(ui.font(22).render("STRIKES", True, DIM), (spanel.x + 12, spanel.y + 17))
        left = sim.strikes if sim else fl.MAX_STRIKES
        for i in range(fl.MAX_STRIKES):
            c = (spanel.right - 118 + i * 36 + 14, spanel.centery)
            alive = i < left
            pygame.draw.circle(surf, (28, 30, 44), c, 14)
            if alive:                                       # intact: helicopter glyph (rotor + body)
                pygame.draw.circle(surf, CYAN, c, 12)
                pygame.draw.line(surf, (12, 18, 26), (c[0] - 8, c[1] - 5), (c[0] + 8, c[1] - 5), 2)
                pygame.draw.line(surf, (12, 18, 26), (c[0], c[1] - 5), (c[0], c[1] - 2), 2)
                pygame.draw.rect(surf, (12, 18, 26), (c[0] - 5, c[1] - 2, 10, 7), border_radius=2)
            else:                                           # spent strike: red cross
                pygame.draw.circle(surf, (70, 40, 44), c, 12, 2)
                pygame.draw.line(surf, STRIKE_RED, (c[0] - 5, c[1] - 5), (c[0] + 5, c[1] + 5), 3)
                pygame.draw.line(surf, STRIKE_RED, (c[0] - 5, c[1] + 5), (c[0] + 5, c[1] - 5), 3)
        # bottom-left: speed + altitude gauge
        if sim:
            self._draw_gauge(surf, sim)
        # hold button
        self._draw_button(surf)
        # banners
        if self.banner:
            txt, age = self.banner
            a = min(1.0, age / 0.3, (2.6 - age) / 0.4)
            t = ui.font(46).render(txt, True, CYAN)
            r = pygame.Rect(0, 0, t.get_width() + 50, 58)
            r.midtop = (SCREEN_W // 2, 78)
            ui.draw_panel(surf, r, int(235 * max(0, a)))
            t.set_alpha(int(255 * max(0, a)))
            surf.blit(t, t.get_rect(center=r.center))
            if txt.startswith("PHASE 1") and sim and sim.time < 7 and self.phase == "flying":
                hint = "Hold to descend. Release to climb."
                h = ui.font(24).render(hint, True, TEXT)
                hr = pygame.Rect(0, 0, h.get_width() + 28, 32)
                hr.midtop = (SCREEN_W // 2, SCREEN_H - 140)
                ui.draw_panel(surf, hr, 215)
                surf.blit(h, h.get_rect(center=hr.center))
        if self.damage_msg:
            txt, age = self.damage_msg
            t = ui.font(30).render(txt, True, STRIKE_RED)
            r = pygame.Rect(0, 0, t.get_width() + 34, 40)
            r.midtop = (SCREEN_W // 2, 118)
            ui.draw_panel(surf, r, 235)
            surf.blit(t, t.get_rect(center=r.center))

    def _draw_gauge(self, surf, sim):
        panel = pygame.Rect(14, SCREEN_H - 76, 350, 62)
        ui.draw_panel(surf, panel, 205)
        surf.blit(ui.font(22).render("SPEED", True, DIM), (panel.x + 12, panel.y + 8))
        bar = pygame.Rect(panel.x + 82, panel.y + 9, 150, 14)
        pygame.draw.rect(surf, (12, 18, 26), bar)
        col = (255, 160, 90) if sim.speed_fraction > 0.8 else CYAN
        pygame.draw.rect(surf, col, (bar.x, bar.y, int(bar.w * sim.speed_fraction), bar.h))
        cap = (fl.speed_cap(sim.progress) - fl.V_MIN) / (fl.V_TOP - fl.V_MIN)
        pygame.draw.line(surf, (236, 234, 226), (bar.x + int(bar.w * cap), bar.y - 3), (bar.x + int(bar.w * cap), bar.bottom + 3), 2)
        pygame.draw.rect(surf, (40, 60, 70), bar, 1)
        surf.blit(ui.font(22).render(f"{int(sim.speed / 10):>2} m/s", True, TEXT), (bar.right + 10, panel.y + 8))
        surf.blit(ui.font(22).render("ALT", True, DIM), (panel.x + 12, panel.y + 34))
        meters = int(round(sim.alt * 24))
        surf.blit(ui.font(22).render(f"{meters:>2} m", True, TEXT), (panel.x + 82, panel.y + 34))
        state = "DESCENDING" if sim.brake > 0.5 else "CLIMBING" if sim.state == "flying" else "LANDING"
        surf.blit(ui.font(22).render(state, True, CYAN if sim.brake > 0.5 else DIM), (bar.x + 70, panel.y + 34))

    def _draw_button(self, surf):
        if self.phase != "flying":
            return
        held = self.input_held
        ui.draw_panel(surf, BTN, 250 if held else 205)
        if held:
            pygame.draw.rect(surf, (20, 60, 80), BTN.inflate(-8, -8))
        t = ui.font(28).render("HOLD TO DESCEND", True, CYAN if held else TEXT)
        surf.blit(t, t.get_rect(center=BTN.center))

    # --- screens
    def _draw_intro(self, surf):
        dim = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
        dim.fill((0, 0, 0, 120))
        surf.blit(dim, (0, 0))
        r = ui.center_panel(surf, 700, 400)
        ui.draw_title(surf, "24 METERS ABOVE", r.y + 22, 62)
        ui.draw_title(surf, "Ingenuity Mars Helicopter", r.y + 78, 30, DIM)
        y = ui.draw_wrapped(surf, self.INTRO_TEXT, 30, r.inflate(-70, 0), r.y + 118)
        y = ui.draw_wrapped(surf, "HOLD SPACE / S / DOWN, touch or click the button to descend. "
                                  "Release to climb. Avoid rock and dust.", 28, r.inflate(-70, 0), y + 10, CYAN)
        ui.draw_wrapped(surf, "Three strikes and the flight is lost.", 26, r.inflate(-70, 0), y + 8, DIM)
        self.buttons.draw(surf)

    def _draw_end(self, surf, title, msg, color):
        dim = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
        dim.fill((0, 0, 0, 150))
        surf.blit(dim, (0, 0))
        r = ui.center_panel(surf, 680, 300)
        ui.draw_title(surf, title, r.y + 30, 64, color)
        ui.draw_wrapped(surf, msg, 32, r.inflate(-70, 0), r.y + 118)
        if self.phase == "won":
            ui.draw_wrapped(surf, f"Strikes remaining: {self.sim.strikes} / {fl.MAX_STRIKES}", 26,
                            r.inflate(-70, 0), r.y + 190, DIM)
        self.buttons.draw(surf)


# ----------------------------------------------------- standalone test runner
if __name__ == "__main__":
    pygame.init()
    screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
    pygame.display.set_caption("24 Meters Above (standalone)")
    clock = pygame.time.Clock()
    game = IngenuityChallenge({"id": "ingenuity"})
    running = True
    while running:
        dt = clock.tick(60) / 1000
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT or (ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE):
                running = False
            elif game.handle_event(ev) == "done":
                print("VICTORY -> Memory Capsule would be granted here.")
                running = False
        game.update(dt)
        screen.fill((0, 0, 0))
        game.draw(screen)
        pygame.display.flip()
    pygame.quit()
