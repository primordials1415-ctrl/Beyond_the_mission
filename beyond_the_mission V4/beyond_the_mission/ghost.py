import math
import random
import pygame
from settings import GHOST_SPEED
from assets import load_image
from interaction import Interactable
import sprites

LINES = [
    ("Ghost Rover", "[Placeholder] ...signal detected. Explorer?"),
    ("Ghost Rover", "[Placeholder] I do not remember how I ended up here."),
    ("Ghost Rover", "[Placeholder] Stay close. I will follow you."),
]


class Ghost(Interactable):
    NOTICE = 300   # starts following when the player gets this close
    STOP = 85      # keeps this distance from the player

    def __init__(self, x, y):
        super().__init__("Ghost Rover", (x, y), 95, LINES, "Talk", prompt_offset=95)
        self.vel = pygame.Vector2()
        self.following = False
        self.moving = False
        self.facing_right = False
        self.t = 0.0
        self.acc = 0.0
        self.particles = []   # [x, y, vx, vy, life, max_life, size]
        base = [load_image(f"ghost/rover_{i}.png", lambda i=i: sprites.draw_ghost_rover(i))
                for i in range(2)]
        self.frames = {True: base, False: [pygame.transform.flip(f, True, False) for f in base]}

    @property
    def sort_y(self):
        return self.pos.y

    def on_interact(self, player_pos):
        self.facing_right = player_pos.x > self.pos.x

    def update(self, dt, player_pos, frozen):
        self.t += dt
        to = pygame.Vector2(player_pos) - self.pos
        dist = to.length()
        if not self.following and dist < self.NOTICE:
            self.following = True
        target = pygame.Vector2()
        if self.following and not frozen and dist > self.STOP:
            d = to / dist
            target = d * GHOST_SPEED * (1.7 if dist > 320 else 1.0)
            if abs(d.x) > 0.25:
                self.facing_right = d.x > 0
        elif self.following and abs(to.x) > 20:
            self.facing_right = to.x > 0
        self.vel += (target - self.vel) * min(1.0, 5 * dt)
        self.pos += self.vel * dt
        self.moving = self.vel.length() > 10

        self.acc += dt * (34 if self.moving else 16)
        while self.acc >= 1:
            self.acc -= 1
            life = random.uniform(0.9, 1.8)
            self.particles.append([
                self.pos.x + random.uniform(-28, 28), self.pos.y - 24 + random.uniform(-14, 14),
                random.uniform(-10, 10) - self.vel.x * 0.15, -random.uniform(14, 38),
                life, life, random.choice((3, 3, 4, 5))])
        for p in self.particles:
            p[0] += p[2] * dt
            p[1] += p[3] * dt
            p[4] -= dt
        self.particles = [p for p in self.particles if p[4] > 0]

    def draw(self, surf, cam):
        add = pygame.BLEND_RGB_ADD
        sx, sy = self.pos.x - cam.x, self.pos.y - cam.y
        pulse = 0.5 + 0.5 * math.sin(self.t * 3)
        surf.blit(sprites.glow(95, int(3 + pulse * 2)), (int(sx - 95), int(sy - 115)), special_flags=add)
        for p in self.particles:
            lvl = max(1, int(p[4] / p[5] * 10))
            r = p[6]
            surf.blit(sprites.glow(r, lvl), (int(p[0] - cam.x - r), int(p[1] - cam.y - r)), special_flags=add)
        bob = math.sin(self.t * (5 if self.moving else 2.2)) * (2 if self.moving else 4)
        img = self.frames[self.facing_right][int(self.t * 9) % 2 if self.moving else 0]
        flicker = 0.55 if random.random() < 0.04 else 1.0
        img.set_alpha(int((175 + 30 * math.sin(self.t * 6)) * flicker))
        bx, by = int(sx - img.get_width() / 2), int(sy - img.get_height() / 2 - 24 + bob)
        surf.blit(img, (bx, by))
        surf.blit(sprites.glow(46, 4), (int(sx - 46), int(sy - 24 + bob - 46)), special_flags=add)


class GhostRobot(Interactable):
    """Ghost Robot of one piece of equipment (hovering echo near its wreck).
    Art: assets/ghost/<id>_0.png, <id>_1.png or sprites.GHOST_ROBOT_ART[id]."""
    TINT = (190, 140, 255)

    def __init__(self, eq, x, y):
        super().__init__(eq["ghost_name"], (x, y), 95, [], "Talk", prompt_offset=105)
        self.eq = eq
        self.TINT = eq.get("tint", self.TINT)
        self.t = 0.0
        self.acc = 0.0
        self.particles = []
        art = sprites.GHOST_ROBOT_ART[eq["id"]]
        self.frames = [load_image(f"ghost/{eq['id']}_{i}.png", lambda i=i: art(i)) for i in range(2)]

    @property
    def sort_y(self):
        return self.pos.y

    def update(self, dt, player_pos=None):
        self.t += dt
        self.acc += dt * 18
        while self.acc >= 1:
            self.acc -= 1
            life = random.uniform(0.9, 1.7)
            self.particles.append([self.pos.x + random.uniform(-30, 30), self.pos.y - 40 + random.uniform(-16, 16),
                                   random.uniform(-8, 8), -random.uniform(12, 32), life, life, random.choice((3, 3, 4))])
        for p in self.particles:
            p[0] += p[2] * dt
            p[1] += p[3] * dt
            p[4] -= dt
        self.particles = [p for p in self.particles if p[4] > 0]

    def draw(self, surf, cam):
        add = pygame.BLEND_RGB_ADD
        sx, sy = self.pos.x - cam.x, self.pos.y - cam.y
        bob = math.sin(self.t * 2.4) * 5
        surf.blit(sprites.glow(80, int(3 + (0.5 + 0.5 * math.sin(self.t * 3)) * 2), self.TINT),
                  (int(sx - 80), int(sy - 100)), special_flags=add)
        for p in self.particles:
            r = p[6]
            surf.blit(sprites.glow(r, max(1, int(p[4] / p[5] * 10)), self.TINT),
                      (int(p[0] - cam.x - r), int(p[1] - cam.y - r)), special_flags=add)
        img = self.frames[int(self.t * 14) % 2]
        flicker = 0.55 if random.random() < 0.04 else 1.0
        img.set_alpha(int((180 + 30 * math.sin(self.t * 5)) * flicker))
        surf.blit(img, (int(sx - img.get_width() / 2), int(sy - img.get_height() / 2 - 40 + bob)))
        surf.blit(sprites.glow(40, 4, self.TINT), (int(sx - 40), int(sy - 40 + bob - 40)), special_flags=add)
