"""24 METERS ABOVE tests. Scenarios A-F from the spec. pygame is replaced by tests/pygame_stub
(logic + flow + draw-call smoke test; NOT a visual run)."""
import sys
from pathlib import Path
from types import SimpleNamespace as NS
sys.path.insert(0, str(Path(__file__).resolve().parent))
import pygame_stub
pygame = pygame_stub.install()
import ui
import ingenuity_flight as fl
import ingenuity_game as ig
import story_data, puzzle
from ingenuity_helpers import drive, win_minigame, key_event, pilot_target
from game import Game
from interaction import InteractionSystem
from journal import StoryProgress
from discovery import EncounterManager, INSERT_TIME

E = NS(type=pygame.KEYDOWN, key=pygame.K_e)
DT = 1 / 60

# ------------------------------------------------------------- layout fairness
for seed in range(400):
    lay = fl.make_layout(seed)
    assert 7 <= len(lay.gates) <= 10, (seed, len(lay.gates))
    prev = None
    for g in lay.gates:
        assert g["x0"] >= fl.FIRST_GATE_X and g["x1"] <= fl.PAD_X - fl.LAST_GATE_MARGIN + 1       # inside bounds
        p = g["x0"] / fl.PAD_X
        lo, hi = max(g["wl"], 0.0), min(g["wh"], 1.0)
        assert hi - lo >= 0.30 - 1e-9, (seed, g)                                               # window wide enough
        assert fl.altitude_for_speed(fl.V_MIN) <= (lo + hi) / 2 or g["wl"] <= 0.14, (seed, g)  # not below min flyable
        reach = fl.max_reachable_alt(p)
        assert max(g["wl"], 0.0) + 0.05 < reach, ("window above reachable altitude", seed, g, reach)
        if prev:
            gap = g["x0"] - prev["x1"]
            assert gap >= 700, (seed, gap)
            c0 = (max(prev["wl"], 0.2) + min(prev["wh"], 0.9)) / 2
            c1 = (max(g["wl"], 0.2) + min(g["wh"], 0.9)) / 2
            assert abs(c1 - c0) <= 0.45, (seed, c0, c1)
        prev = g
    xs = sorted(d.trigger_x for d in lay.devils)
    for d in lay.devils:                      # devils spawn in free gaps only
        nxt = [g for g in lay.gates if g["x0"] > d.trigger_x]
        prv = [g for g in lay.gates if g["x1"] < d.trigger_x]
        assert prv and nxt and nxt[0]["x0"] - (d.trigger_x + fl.DEVIL_AHEAD) >= 200, (seed, d.trigger_x)
    ph = [g["phase"] for g in lay.gates]
    assert ph == sorted(ph) and set(ph) == {1, 2, 3}
print("layout invariants (400 seeds): PASS")

# ------------------------------------------------------------ Test A (logic) normal completion
def autopilot(seed):
    s = fl.FlightSim(seed)
    n = 0
    while not s.over and n < 60 * 200:
        s.update(DT, fl.altitude_for_speed(s.speed) > pilot_target(s) + 0.004)
        n += 1
    return s, n * DT

res = [autopilot(sd) for sd in range(60)]
assert all(s.state == "won" and s.strikes == 3 and s.dist == fl.PAD_X for s, _ in res)
assert 55 < sum(t for _, t in res) / len(res) < 110, "flight length out of range"
print("A: skilled flights win on every seed (60), avg %.0fs: PASS" % (sum(t for _, t in res) / len(res)))

# phases happen in order and speed rises overall
s = fl.FlightSim(5); seen = []; vmax = []
while not s.over:
    s.update(DT, fl.altitude_for_speed(s.speed) > pilot_target(s) + 0.004)
    for ev in s.drain_events():
        if ev[0] == "phase": seen.append(ev[1])
    vmax.append(s.speed)
assert seen == [2, 3], seen
assert max(vmax) <= fl.V_TOP + 1e-9 and min(vmax[:-300]) >= fl.V_MIN - 1e-9
free = fl.FlightSim(5); free.hazards = []; free.devil_plans = []          # unobstructed, never braking
marks = {}
while not free.over:
    free.update(DT, False)
    for p in (0.1, 0.45, 0.8):
        if free.progress >= p: marks.setdefault(p, free.speed)
assert marks[0.1] < marks[0.45] < marks[0.8] <= fl.V_TOP and marks[0.8] - marks[0.1] > 100, marks
print("phases 1->2->3 and rising speed, speed bounded: PASS")

# ------------------------------------------------------------ Test D (logic) slowdown
s = fl.FlightSim(1)
for _ in range(60 * 5): s.update(DT, False)
v0 = s.speed; assert v0 > fl.V_START + 50, "auto acceleration"
s.update(DT, True); assert v0 - s.speed < 2, "slowdown is not instantaneous"
speeds = [s.speed]
for _ in range(60): s.update(DT, True); speeds.append(s.speed)
tail = speeds[15:]            # first ~0.25 s the brake lever is still easing in
assert all(a >= b for a, b in zip(tail, tail[1:])) and speeds[-1] < v0 - 40
for _ in range(60 * 6): s.update(DT, True)
assert abs(s.speed - fl.V_MIN) < 1e-6, "floor at V_MIN"
v1 = s.speed
for _ in range(60): s.update(DT, False)
assert s.speed > v1 + 20, "release resumes acceleration"
print("D: hold decelerates gradually, release re-accelerates, limits respected: PASS")

# frame-rate independence (30 / 60 / 144 fps, same input script)
def run(fps):
    s = fl.FlightSim(3); d = 1 / fps
    n = int(12 * fps)
    for i in range(n):
        s.update(d, 4 <= i * d < 6.5)
    return s.dist, s.speed
a, b, c = run(30), run(60), run(144)
assert abs(a[0] - b[0]) / b[0] < 0.01 and abs(c[0] - b[0]) / b[0] < 0.01 and abs(a[1] - b[1]) < 8
print("delta-time consistency across 30/60/144 fps: PASS")

# permanent hold / never hold are not winning strategies
def blind(seed, hold):
    s = fl.FlightSim(seed); n = 0
    while not s.over and n < 60 * 400: s.update(DT, hold); n += 1
    return s.state
w_hold = sum(blind(i, True) == "won" for i in range(30)); w_none = sum(blind(i, False) == "won" for i in range(30))
assert w_hold <= 3 and w_none <= 3, (w_hold, w_none)
print("balance: always-hold wins %d/30, never-hold wins %d/30: PASS" % (w_hold, w_none))

# ------------------------------------------------------------ Test B (logic) strikes
def place(sim, h, alt=None, off=0.5):
    sim.immunity = 0.0
    sim.dist = h.x0 + (h.x1 - h.x0) * off
    sim.alt = alt if alt is not None else (h.lo + h.hi) / 2 if h.lo > -1 and h.hi < 2 else (h.hi - 0.05 if h.lo < 0 else h.lo + 0.05)

s = fl.FlightSim(2)
rocks = [h for h in s.hazards if h.kind in ("spire", "ledge", "dust")]
# one continuous collision (sit inside a long hazard) costs exactly ONE strike
longest = max(rocks, key=lambda h: h.x1 - h.x0)
place(s, longest, off=0.1); s.speed = fl.V_MIN
s.update(DT, False)
for _ in range(60 * 10):
    if s.state != "flying" or s.dist > longest.x1 + 50: break
    s.alt = (longest.hi - 0.03) if longest.lo < 0 else (longest.lo + 0.03)
    s.update(DT, False)
assert s.strikes == 2 and s.hits_taken == 1, (s.strikes, s.hits_taken)
print("B: one continuous collision = one strike: PASS")

s = fl.FlightSim(2)
picks = [rocks[0], rocks[3], rocks[6]]
for i, h in enumerate(picks):
    place(s, h, off=0.5); s.update(DT, False)
    assert s.strikes == 3 - (i + 1) or s.state == "lost", (i, s.strikes)
    assert s.immunity > 0 or s.state == "lost"
    evs = s.drain_events(); assert any(e[0] == "hit" for e in evs)
assert s.state == "lost" and s.strikes == 0 and any(e[0] == "lost" for e in evs)
d0, sp0 = s.dist, s.speed
for _ in range(120): s.update(DT, True)
assert s.dist == d0 and s.speed == sp0 and s.state == "lost", "no progress / input after game over"
# immunity: back-to-back hits inside the recovery window are ignored
s = fl.FlightSim(2); place(s, rocks[0]); s.update(DT, False)
st = s.strikes; place(s, rocks[3]); s.immunity = 1.0; s.update(DT, False)
assert s.strikes == st
print("B: three separate hits end the flight; immunity respected; input dead after loss: PASS")

# strike taken on a hazard can never be re-taken from the same hazard after immunity ends
s = fl.FlightSim(2); h = longest; place(s, h, off=0.1); s.update(DT, False); st = s.strikes
s.immunity = 0; place(s, h, off=0.12); s.update(DT, False); assert s.strikes == st
print("B: spent hazards cannot re-hit: PASS")

# unexpected hazards: never spawn on the helicopter, warning visible before arrival, bounded in the playfield
s = fl.FlightSim(7); spawned = 0; warned = False
while not s.over:
    before = [h for h in s.hazards if h.kind == "devil"]
    s.update(DT, fl.altitude_for_speed(s.speed) > pilot_target(s) + 0.004)
    for h in s.hazards:
        if h.kind == "devil" and h not in before:
            spawned += 1
            assert h.x0 - s.dist >= fl.DEVIL_AHEAD - 80 - fl.DEVIL_HALF_W, "spawned too close"
            assert 0.1 <= (h.lo + h.hi) / 2 <= 0.95
    warned |= bool(s.devil_warnings())
assert spawned == len(fl.make_layout(7).devils) >= 1 and warned
print("C: unexpected hazards spawn ahead, off screen, with warning: PASS")

# -------------------------------------------------------------- challenge UI/flow
eq = story_data.BY_ID["ingenuity"]
assert isinstance(puzzle.make_challenge(eq), ig.IngenuityChallenge)
assert type(puzzle.make_challenge(story_data.BY_ID["insight"])).__name__ == "PlaceholderChallenge"   # others untouched
ch = puzzle.make_challenge(eq)
assert ch.phase == "intro" and ch.sim is None and ch.title == "24 METERS ABOVE"
ch.update(0.5); ch.draw(pygame.Surface((960, 540)))        # intro screen draws (no sim yet)
assert ch.handle_event(NS(type=pygame.KEYDOWN, key=pygame.K_e)) is None and ch.phase == "flying"
assert ch.sim.strikes == 3 and ch.sim.dist == 0

# Test D (input): keyboard / mouse / touch all hold, release stops
def held(): return ch.input_held
ch.handle_event(key_event(True)); assert held(); ch.handle_event(key_event(False)); assert not held()
for k in (pygame.K_s, pygame.K_DOWN):
    ch.handle_event(key_event(True, k)); assert held(); ch.handle_event(key_event(False, k)); assert not held()
ch.handle_event(NS(type=pygame.MOUSEBUTTONDOWN, button=1, pos=(10, 10))); assert not held(), "click outside button"
x, y = ig.BTN.center
ch.handle_event(NS(type=pygame.MOUSEBUTTONDOWN, button=1, pos=(x, y))); assert held()
ch.handle_event(NS(type=pygame.MOUSEBUTTONUP, button=1, pos=(0, 0))); assert not held()
ch.handle_event(NS(type=pygame.FINGERDOWN, finger_id=7, x=x / 960, y=y / 540)); assert held()
ch.handle_event(NS(type=pygame.FINGERDOWN, finger_id=8, x=0.05, y=0.05)); assert held()
ch.handle_event(NS(type=pygame.FINGERUP, finger_id=7, x=0, y=0)); assert not held()
ch.handle_event(key_event(True)); ch.update(DT); v_a = ch.sim.speed
for _ in range(90): ch.update(DT)
assert ch.sim.speed < v_a, "holding via the challenge slows Ingenuity"
ch.handle_event(key_event(False))
v_b = ch.sim.speed
for _ in range(60): ch.update(DT)
assert ch.sim.speed > v_b
print("D: keyboard (SPACE/S/DOWN), mouse button and touch all hold/release correctly: PASS")

# Test B/C (flow): lose three strikes -> failure screen -> retry
ch = puzzle.make_challenge(eq); ch.handle_event(E)
rocks = [h for h in ch.sim.hazards if h.kind in ("spire", "ledge", "dust")]
for h in (rocks[0], rocks[3], rocks[6]):
    ch.sim.immunity = 0; ch.sim.dist = h.x0 + 100; ch.sim.alt = (h.hi - 0.05) if h.lo < 0 else h.lo + 0.05
    ch.update(DT)
assert ch.phase == "lost" and ch.sim.strikes == 0 and not ch.input_held
ch.draw(pygame.Surface((960, 540)))                                  # failure screen draws
assert ch.handle_event(key_event(True)) is None and not ch.input_held       # held input ignored after game over
ch.update(1.0)
dist_lost = ch.sim.dist; ch.update(1.0); assert ch.sim.dist == dist_lost
old_sim = ch.sim
assert ch.handle_event(E) is None and ch.phase == "flying"           # Retry
assert ch.sim is not old_sim and ch.sim.strikes == 3 and ch.sim.dist == 0 and ch.sim.speed == fl.V_START
assert ch.sim.immunity == 0 and ch.sim.state == "flying" and not ch.input_held and ch.attempts == 2
assert all(not h.spent for h in ch.sim.hazards) and not any(h.kind == "devil" for h in ch.sim.hazards)
print("B/C: three hits -> FLIGHT LOST screen -> Retry resets strikes, speed, progress, hazards: PASS")

# retry never completes the challenge
done_flags = []
ch2 = puzzle.make_challenge(eq); ch2.handle_event(E)
for h in [h for h in ch2.sim.hazards if h.kind in ("spire", "ledge", "dust")][:3]:
    ch2.sim.immunity = 0; ch2.sim.dist = h.x0 + 100; ch2.sim.alt = (h.hi - 0.05) if h.lo < 0 else h.lo + 0.05; ch2.update(DT)
ch2.update(1.0)
for _ in range(5): done_flags.append(ch2.handle_event(E)); ch2.update(1.0); ch2.sim.strikes = 0; ch2.phase = "lost"; ch2.t = 1
assert done_flags == [None] * 5
print("C: failure/retry never returns 'done': PASS")

# draw smoke test across a whole flight (all hazard kinds, landing, win)
ch = puzzle.make_challenge(eq); ch.handle_event(E)
kinds, frames = set(), 0
def watch(c):
    global frames
    frames += 1
    if frames % 10 == 0:
        c.draw(pygame.Surface((960, 540)))
    kinds.update(h.kind for h in c.sim.hazards if -200 < h.x0 - c.sim.dist < 900)
    return c.phase == "won"
drive(ch, watch)
assert {"spire", "ledge", "dust", "devil"} <= kinds, kinds
ch.draw(pygame.Surface((960, 540)))
assert ch.phase == "won" and ch.sim.strikes == 3
print("draw smoke test over a full flight (%s): PASS" % ",".join(sorted(kinds)))

# Test A (UI): win through events, Continue -> "done" exactly once
ch = puzzle.make_challenge(eq)
assert win_minigame(ch) == "done" and ch.phase == "done"
assert ch.handle_event(E) is None and ch.handle_event(key_event(True)) is None

# ---------------------------------------------------- Tests E/F: reward + story integration
def new_game():
    g = Game.__new__(Game)
    g.progress = StoryProgress(); g.scene = None; g.toast = None; g.state = "play"
    g.interaction = InteractionSystem(); g.encounters = EncounterManager(g.progress, g.start_encounter)
    return g

g = new_game()
robot = g.encounters.robots["ingenuity"]
g.start_story()
for _ in range(3): g.interaction.handle_event(E)
g.interaction.target = robot; g.interaction.handle_event(E)
for _ in range(len(robot.lines)): g.interaction.handle_event(E)
s = g.scene; assert g.state == "scene" and s.phase == "choice"
s.handle_event(E); assert s.phase == "minigame" and isinstance(s.challenge, ig.IngenuityChallenge)
assert s.challenge.phase == "intro"
s.handle_event(E); assert s.phase == "minigame" and s.challenge.phase == "flying"      # starts the flight, no skip
assert g.progress.recovered == []
# fail first
ch = s.challenge
rocks = [h for h in ch.sim.hazards if h.kind in ("spire", "ledge", "dust")]
for h in rocks[:3]:
    ch.sim.immunity = 0; ch.sim.dist = h.x0 + 100; ch.sim.alt = (h.hi - 0.05) if h.lo < 0 else h.lo + 0.05
    s.update(DT)
assert ch.phase == "lost" and s.phase == "minigame" and g.progress.recovered == []
s.update(1.0); s.handle_event(E); assert ch.phase == "flying" and s.phase == "minigame"   # retry stays in minigame
assert g.progress.recovered == [] and not g.progress.is_recovered("ingenuity")
print("E: failure + retry award nothing: PASS")
# now win
drive(ch, lambda c: c.phase == "won")
# the scene routes update()/events; emulate its own loop for the final hop
assert s.phase == "minigame" and g.progress.recovered == []
ch.update(1.0)
s.handle_event(E); assert s.phase == "capsule", s.phase                                  # Continue -> existing reward sequence
assert g.progress.recovered == []                                                         # not collected until inserted
s.handle_event(E); assert s.phase == "insert" and g.progress.recovered == ["ingenuity"]  # Memory Capsule #01 into the archive
s.update(INSERT_TIME + 0.1); s.handle_event(E); assert s.phase == "cutscene"
s.handle_event(E)
assert g.scene is None and g.state == "play" and g.toast[0] == "Memory Successfully Recovered!"
for _ in range(2): g.interaction.handle_event(E)
assert g.progress.current()["id"] == "insight" and g.progress.archive.integrity == 1 / 7
assert list(g.encounters.robots) == ["ingenuity", "insight"]
assert type(puzzle.make_challenge(story_data.BY_ID["insight"])).__name__ == "PlaceholderChallenge"
print("A/F: win -> Continue -> capsule -> archive -> cutscene -> InSight unlocked, InSight still placeholder: PASS")

# E: replay cannot duplicate: scene never reopens, recover() refuses a second capsule
g.start_encounter(story_data.BY_ID["ingenuity"]); assert g.scene is None
assert not g.progress.recover("ingenuity") and g.progress.recovered == ["ingenuity"]
g.interaction.target = g.encounters.robots["ingenuity"]; g.interaction.handle_event(E)
for _ in range(len(g.interaction.active.lines)): g.interaction.handle_event(E)
assert g.scene is None and g.progress.recovered == ["ingenuity"]
# state survives continuing (save round trip)
assert StoryProgress.from_dict(g.progress.to_dict()).recovered == ["ingenuity"]
print("E: capsule awarded exactly once, collected state preserved: PASS")

# "Not Yet" still works and leaves no half-state
g2 = new_game(); g2.start_encounter(story_data.BY_ID["ingenuity"])
g2.scene.handle_event(NS(type=pygame.KEYDOWN, key=pygame.K_d)); g2.scene.handle_event(E)
assert g2.scene is None and g2.progress.recovered == []
print("F: 'Not Yet' cancel unchanged: PASS")
