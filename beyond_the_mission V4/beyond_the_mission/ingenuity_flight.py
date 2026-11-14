"""24 METERS ABOVE - flight simulation (no pygame, frame-independent, unit-testable).

Core idea (one control, HOLD TO DESCEND):
  * Ingenuity flies forward and automatically accelerates.
  * Altitude follows speed (faster = more lift = higher, slower = lower).
  * Hazards form "gates": a safe altitude window with rock / dust on either side.
    The player steers altitude *only* by managing speed, so holding the brake
    descends, releasing climbs, and holding it forever leaves you skimming rocks.

All distances are in screen pixels ("u") at 960x540; altitude is normalised 0..1.
"""
import math
import random

# ------------------------------------------------------------------ tuning
PAD_X = 18500.0            # world x of the landing pad (flight length)
LAND_R0 = 600.0            # landing sequence starts this far before the pad
FIRST_GATE_X = 2200.0
LAST_GATE_MARGIN = 2100.0  # last gate must end this far before the pad

V_START = 150.0
V_MIN = 120.0
V_TOP = 420.0
ACCEL = 60.0               # auto acceleration (u/s^2)
BRAKE_RAMP_UP = 5.0        # brake lever eases in/out -> slowdown is never instant
BRAKE_RAMP_DOWN = 3.0
ALT_MIN, ALT_MAX = 0.08, 0.96
CLIMB_RATE = 0.42          # altitude change per second while climbing / descending
VY_FOLLOW = 7.0            # how quickly vertical speed eases to the input (1/s)

HELI_HALF_W = 26.0         # collision box (u / normalised altitude)
HELI_HALF_H = 0.045

MAX_STRIKES = 3
IMMUNITY = 1.7             # seconds of invulnerability after a hit
HIT_SPEED_KEEP = 0.85      # speed kept after a hit
LANDING_K = 1.7            # landing approach: speed <= K * distance-to-pad
TOUCHDOWN_PAUSE = 0.9      # seconds on the pad before the win panel

DEVIL_AHEAD = 1150.0       # devils spawn this far ahead (off screen)
DEVIL_DRIFT = (90.0, 140.0)
DEVIL_HALF_W = 38.0
DEVIL_HALF_H = 0.08

PHASE_NAMES = {1: "PHASE 1 - TAKEOFF", 2: "PHASE 2 - CRUISING ALTITUDE", 3: "PHASE 3 - FINAL APPROACH"}


def phase_for(progress):
    return 1 if progress < 0.28 else 2 if progress < 0.62 else 3


def speed_cap(progress):
    """Top speed rises continuously through the flight."""
    p = max(0.0, min(1.0, progress))
    return 250.0 + 170.0 * p


def altitude_for_speed(v):
    k = (v - V_MIN) / (V_TOP - V_MIN)
    return ALT_MIN + (ALT_MAX - 0.09) * max(0.0, min(1.0, k))


def max_reachable_alt(progress):
    return altitude_for_speed(speed_cap(progress))


# ------------------------------------------------------------------ layout
class Hazard:
    """Axis-aligned hazard: world x range x altitude band. kind in
    spire | ledge | dust | devil."""
    __slots__ = ("kind", "x0", "x1", "lo", "hi", "spent", "seed", "label")

    def __init__(self, kind, x0, x1, lo, hi, seed=0):
        self.kind, self.x0, self.x1, self.lo, self.hi = kind, x0, x1, lo, hi
        self.spent = False       # once it has hit the helicopter it can never hit again
        self.seed = seed
        self.label = None


class DevilPlan:
    """Unexpected hazard: spawned at run time (not a pre-placed obstacle)."""
    __slots__ = ("trigger_x", "drift", "wander", "phase", "fired")

    def __init__(self, trigger_x, drift, wander, phase):
        self.trigger_x, self.drift, self.wander, self.phase = trigger_x, drift, wander, phase
        self.fired = False


class Layout:
    def __init__(self):
        self.hazards = []   # static: spire / ledge / dust
        self.gates = []     # dicts: x0, x1, wl, wh, phase
        self.devils = []    # DevilPlan


def _window_width(phase):
    return {1: 0.44, 2: 0.38, 3: 0.32}[phase]


GAPS = {1: (1200, 1500), 2: (850, 1100), 3: (700, 880)}   # distance between gates per phase
DEVIL_GAP = (1750, 1900)


def _gap(phase, rng):
    return rng.uniform(*GAPS[phase])


def make_layout(seed):
    """Deterministic course. Guarantees (checked by tests): every gate has a safe
    window >= 0.30 wide that is reachable at that point of the flight, consecutive
    windows differ by <= 0.22 altitude with enough distance to fly the change, and
    unexpected hazards only spawn in dedicated long gaps."""
    rng = random.Random(seed)
    lay = Layout()
    x, center, gi, gaps_since_devil = FIRST_GATE_X, 0.25, 0, 0
    limit = PAD_X - LAST_GATE_MARGIN
    while True:
        progress = x / PAD_X
        phase = phase_for(progress)
        width = _window_width(phase)
        cmax = max(0.24, max_reachable_alt(progress) - 0.07)
        cmin = 0.22
        if gi == 0:           # tutorial 1: dust ceiling -> must slow down (window open at the bottom)
            kind_lo, kind_hi = None, "dust"
            wl, wh = 0.0, 0.33
        elif gi == 1:         # tutorial 2: rock spire -> must climb again (window open at the top)
            kind_lo, kind_hi = "spire", None
            wl, wh = 0.38, 1.1
        else:
            step = rng.uniform(-0.22, 0.22)
            center = min(cmax, max(cmin, center + step))
            wl, wh = center - width / 2, center + width / 2
            kinds_lo = {1: ["spire"], 2: ["spire", "dust"], 3: ["spire", "dust"]}[phase]
            kinds_hi = {1: ["ledge", "dust"], 2: ["ledge", "dust"], 3: ["ledge", "dust"]}[phase]
            kind_lo, kind_hi = rng.choice(kinds_lo), rng.choice(kinds_hi)
            if kind_lo == "dust" and kind_hi == "dust" and phase == 2:
                kind_hi = "ledge"            # mix rocks and clouds
            if wl < 0.14:
                kind_lo, wl = None, 0.0
            if wh > 0.92:
                kind_hi, wh = None, 1.1
        if gi < 2:
            center = (0.25, 0.5)[gi]      # where the random walk continues from
        length = rng.uniform(520, 760) if "dust" in (kind_lo, kind_hi) else rng.uniform(320, 420)
        if x + length > limit:
            break
        s = rng.randrange(1 << 30)
        if kind_lo:
            lay.hazards.append(Hazard(kind_lo, x, x + length, -1.0, wl, s))
        if kind_hi:
            lay.hazards.append(Hazard(kind_hi, x, x + length, wh, 2.0, s + 1))
        lay.gates.append(dict(x0=x, x1=x + length, wl=wl, wh=wh, phase=phase))
        gi += 1
        gap = _gap(phase, rng)
        gaps_since_devil += 1
        if phase >= 2 and gaps_since_devil >= 3:      # long ambush gap with an unexpected dust devil
            gap = rng.uniform(*DEVIL_GAP)
            gaps_since_devil = 0
            lay.devils.append(DevilPlan(x + length + 250 + rng.uniform(-60, 120),
                                        rng.uniform(*DEVIL_DRIFT), rng.uniform(0.08, 0.14),
                                        rng.uniform(0, 6.28)))
        x += length + gap
    # an ambush only makes sense if another gate follows it
    last_x = lay.gates[-1]["x0"]
    lay.devils = [d for d in lay.devils if d.trigger_x < last_x]
    return lay


# --------------------------------------------------------------- simulation
class FlightSim:
    """States: flying -> landing -> won   |   flying -> lost."""

    def __init__(self, seed=None):
        self.seed = random.randrange(1 << 30) if seed is None else seed
        self.rng = random.Random(self.seed ^ 0x5EED)       # runtime randomness (devil altitude)
        self.layout = make_layout(self.seed)
        self.hazards = list(self.layout.hazards)
        self.devil_plans = self.layout.devils
        self.state = "flying"
        self.dist = 0.0
        self.speed = V_START
        self.alt = altitude_for_speed(V_START)
        self.brake = 0.0
        self.vy = 0.0
        self.strikes = MAX_STRIKES
        self.immunity = 0.0
        self.time = 0.0
        self.phase = 1
        self.events = []          # drained by the UI: ("hit", hazard) ("phase", n) ("landing",) ("won",) ("lost",)
        self.last_hit_kind = None
        self.hits_taken = 0
        self.landing_r0 = None
        self.landing_alt0 = None
        self.touchdown_t = 0.0

    # ------------------------------------------------------------ queries
    @property
    def progress(self):
        return max(0.0, min(1.0, self.dist / PAD_X))

    @property
    def over(self):
        return self.state in ("won", "lost")

    @property
    def speed_fraction(self):
        return max(0.0, min(1.0, (self.speed - V_MIN) / (V_TOP - V_MIN)))

    def drain_events(self):
        ev, self.events = self.events, []
        return ev

    def hazard_rect(self, h):
        return h.x0, h.x1, h.lo, h.hi

    # ------------------------------------------------------------- update
    def update(self, dt, hold):
        """Advance by dt seconds. `hold` is the slow-down input (ignored once over)."""
        if self.over or dt <= 0:
            return
        dt = min(dt, 0.05)       # never let a long frame tunnel through obstacles
        self.time += dt
        self.immunity = max(0.0, self.immunity - dt)
        if self.state == "flying":
            self._fly(dt, hold)
        elif self.state == "landing":
            self._land(dt)

    def _fly(self, dt, hold):
        # --- brake lever (gradual in / out) and speed
        target = 1.0 if hold else 0.0
        rate = BRAKE_RAMP_UP if hold else BRAKE_RAMP_DOWN
        self.brake += max(-rate * dt, min(rate * dt, target - self.brake))
        # speed is independent of the input: always accelerates toward the cap
        self.speed += ACCEL * dt
        self.speed = max(V_MIN, min(speed_cap(self.progress), self.speed))
        # --- input only steers altitude: hold = descend, release = climb
        self.vy += ((-1.0 if hold else 1.0) * CLIMB_RATE - self.vy) * min(1.0, VY_FOLLOW * dt)
        self.alt += self.vy * dt
        self.alt = max(ALT_MIN, min(ALT_MAX, self.alt))
        self.dist += self.speed * dt
        # --- phase change
        ph = phase_for(self.progress)
        if ph != self.phase:
            self.phase = ph
            self.events.append(("phase", ph))
        # --- unexpected hazards + collisions
        self._spawn_devils()
        self._move_devils(dt)
        self._collide()
        if self.state == "flying" and self.dist >= PAD_X - LAND_R0:
            self.state = "landing"
            self.landing_r0 = PAD_X - self.dist
            self.landing_alt0 = self.alt
            self.events.append(("landing",))

    def _spawn_devils(self):
        for plan in self.devil_plans:
            if plan.fired or self.dist < plan.trigger_x:
                continue
            plan.fired = True
            # centre is never on top of the helicopter: >= 0.14 away, inside the flyable range
            lo, hi = 0.22, 0.85
            for _ in range(20):
                c = self.rng.uniform(lo, hi)
                if abs(c - self.alt) >= 0.14:
                    break
            else:
                c = lo if self.alt > 0.5 else hi
            x = self.dist + DEVIL_AHEAD
            d = Hazard("devil", x - DEVIL_HALF_W, x + DEVIL_HALF_W, c - DEVIL_HALF_H, c + DEVIL_HALF_H,
                       self.rng.randrange(1 << 30))
            d.label = (c, plan.drift, plan.wander, plan.phase, self.time)   # base centre, drift, wander, phase, t0
            self.hazards.append(d)

    def _move_devils(self, dt):
        for h in self.hazards:
            if h.kind != "devil":
                continue
            c0, drift, wander, ph, t0 = h.label
            h.x0 -= drift * dt
            h.x1 -= drift * dt
            c = c0 + wander * math.sin(1.6 * (self.time - t0) + ph)
            h.lo, h.hi = c - DEVIL_HALF_H, c + DEVIL_HALF_H
        # drop devils that are far behind
        self.hazards = [h for h in self.hazards if not (h.kind == "devil" and h.x1 < self.dist - 400)]

    def devil_warnings(self):
        """Devils not yet on screen (for the warning marker): list of (x_ahead, altitude centre)."""
        return [(h.x0 - self.dist, (h.lo + h.hi) / 2) for h in self.hazards
                if h.kind == "devil" and not h.spent and h.x0 - self.dist > 0]

    # --------------------------------------------------------- collisions
    def _collide(self):
        if self.immunity > 0:
            return
        hx0, hx1 = self.dist - HELI_HALF_W, self.dist + HELI_HALF_W
        ha0, ha1 = self.alt - HELI_HALF_H, self.alt + HELI_HALF_H
        for h in self.hazards:
            if h.spent:
                continue
            if h.kind == "devil":
                mx, ma = 8.0, 0.012
            elif h.kind == "dust":
                mx, ma = 22.0, 0.02       # clouds are soft: forgiving edges
            else:
                mx, ma = 10.0, 0.015
            if hx1 > h.x0 + mx and hx0 < h.x1 - mx and ha1 > h.lo + ma and ha0 < h.hi - ma:
                self._hit(h)
                return

    def _hit(self, h):
        h.spent = True                      # one hazard can only ever cost one strike
        self.strikes -= 1
        self.hits_taken += 1
        self.last_hit_kind = h.kind
        self.immunity = IMMUNITY
        self.speed = max(V_MIN, self.speed * HIT_SPEED_KEEP)
        self.events.append(("hit", h))
        if self.strikes <= 0:
            self.state = "lost"
            self.brake = 0.0
            self.events.append(("lost",))

    # ------------------------------------------------------------ landing
    def _land(self, dt):
        r = PAD_X - self.dist
        self.speed = min(self.speed, max(LANDING_K * r, 14.0))
        step = self.speed * dt
        if r - step <= 1.0:
            self.dist = PAD_X
            self.speed = 0.0
            self.alt = 0.0
            self.touchdown_t += dt
            if self.touchdown_t >= TOUCHDOWN_PAUSE:
                self.state = "won"
                self.events.append(("won",))
            return
        self.dist += step
        r = PAD_X - self.dist
        self.alt = self.landing_alt0 * max(0.0, min(1.0, r / self.landing_r0))
        self.brake = 0.0

    # ----------------------------------------------------------- test aid
    def teleport(self, dist):
        """Test/debug helper: jump forward without triggering collisions on the way."""
        self.dist = dist
