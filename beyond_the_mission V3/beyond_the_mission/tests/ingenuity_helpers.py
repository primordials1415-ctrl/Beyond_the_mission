"""Shared helpers: a tracking 'pilot' that plays 24 METERS ABOVE through the challenge's
real event interface (SPACE down/up), used by flow tests."""
from types import SimpleNamespace as NS
import pygame
import ingenuity_flight as fl


def key_event(down, k=None):
    return NS(type=pygame.KEYDOWN if down else pygame.KEYUP, key=k or pygame.K_SPACE)


def pilot_target(sim):
    t = 0.5
    for g in sim.layout.gates:
        if g["x1"] + 40 < sim.dist:
            continue
        if g["x0"] - sim.dist < 1250:
            t = (max(g["wl"], 0.2) + min(g["wh"], 0.9)) / 2
        break
    for h in sim.hazards:
        if h.kind == "devil" and not h.spent and 0 < h.x0 - sim.dist < 900:
            c = (h.lo + h.hi) / 2
            if abs(c - t) < 0.3:
                t = c - 0.32 if c - 0.32 > 0.15 else c + 0.32
    return t


def drive(ch, until, dt=1 / 60, max_s=200, pilot=True, handle=None, update=None):
    """Advance the challenge frame by frame, pressing/releasing SPACE like a player.
    `until(ch)` stops the loop. `handle`/`update` default to the challenge's own methods; pass an
    EncounterScene's to route through the real scene. Returns elapsed seconds."""
    handle, update = handle or ch.handle_event, update or ch.update
    held, t = False, 0.0
    while not until(ch) and t < max_s:
        if pilot and ch.phase == "flying":
            want = fl.altitude_for_speed(ch.sim.speed) > pilot_target(ch.sim) + 0.004
            if want != held:
                handle(key_event(want))
                held = want
        update(dt)
        t += dt
    return t


def win_minigame(ch, handle=None, update=None):
    """From the intro screen to the 'FLIGHT SUCCESSFUL' panel and Continue. Returns handle_event result."""
    handle, update = handle or ch.handle_event, update or ch.update
    handle(NS(type=pygame.KEYDOWN, key=pygame.K_e))        # Start Flight
    assert ch.phase == "flying"
    drive(ch, lambda c: c.phase == "won", handle=handle, update=update)
    assert ch.phase == "won", ch.phase
    update(1.0)
    return handle(NS(type=pygame.KEYDOWN, key=pygame.K_e))  # Continue
