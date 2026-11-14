import math
import random
import pygame
from settings import MAP_W, MAP_H, SCREEN_W, SCREEN_H, BORDER
from interaction import Interactable
import sprites
from story_data import EQUIPMENT


class Prop:
    def __init__(self, sprite, x, y, collider):
        self.sprite = sprite
        self.pos = pygame.Vector2(x, y)      # bottom centre
        self.rect = collider

    @property
    def sort_y(self):
        return self.pos.y

    def draw(self, surf, cam):
        surf.blit(self.sprite, (int(self.pos.x - self.sprite.get_width() / 2 - cam.x),
                                int(self.pos.y - self.sprite.get_height() - cam.y)))


class Beacon(Prop):
    def __init__(self, x, y):
        self.on_img = sprites.draw_beacon(True)
        self.off_img = sprites.draw_beacon(False)
        rect = pygame.Rect(0, 0, 20, 10)
        rect.midbottom = (x, y)
        super().__init__(self.off_img, x, y, rect)

    def draw(self, surf, cam):
        on = (pygame.time.get_ticks() // 600) % 2 == 0
        self.sprite = self.on_img if on else self.off_img
        super().draw(surf, cam)
        if on:
            surf.blit(sprites.glow(40, 5), (int(self.pos.x - 40 - cam.x), int(self.pos.y - 40 - 38 - cam.y)),
                      special_flags=pygame.BLEND_RGB_ADD)


class World:
    def __init__(self):
        rng = random.Random(11)
        self.spawn = (MAP_W // 2, MAP_H // 2)
        self.ghost_start = (1290, 770)   # Ghost Rover starts next to the player
        eq_pos, bc_pos = (860, 560), (1240, 1130)
        self.sites = {e["id"]: e["site"] for e in EQUIPMENT if e["implemented"]}
        avoid = [(*self.spawn, 150), (*self.ghost_start, 110), (*eq_pos, 130), (*bc_pos, 110)]
        avoid += [(sx, sy, 170) for sx, sy in self.sites.values()]

        self.ground = sprites.make_ground(MAP_W, MAP_H, rng, avoid)
        self.props = []
        b = BORDER
        self.walls = [pygame.Rect(-200, -200, MAP_W + 400, 200 + b),
                      pygame.Rect(-200, MAP_H - b, MAP_W + 400, 200 + b),
                      pygame.Rect(-200, -200, 200 + b, MAP_H + 400),
                      pygame.Rect(MAP_W - b, -200, 200 + b, MAP_H + 400)]

        eq_img = sprites.draw_equipment()
        eq_rect = pygame.Rect(0, 0, 66, 26)
        eq_rect.midbottom = (eq_pos[0], eq_pos[1] - 4)
        self.props.append(Prop(eq_img, *eq_pos, eq_rect))
        for eid, (sx, sy) in self.sites.items():     # abandoned equipment wrecks
            rect = pygame.Rect(0, 0, 40, 16)
            rect.midbottom = (sx, sy - 4)
            self.props.append(Prop(sprites.WRECK_ART[eid](), sx, sy, rect))
        beacon = Beacon(*bc_pos)
        self.props.append(beacon)

        placed = []
        tries = 0
        while len(placed) < 70 and tries < 3000:
            tries += 1
            r = rng.choices((5, 7, 9, 12, 16, 22), (5, 5, 4, 3, 2, 1))[0]
            R = r * 2
            x = rng.randint(b + 80, MAP_W - b - 80)
            y = rng.randint(b + 100, MAP_H - b - 40)
            if any(math.hypot(x - ax, y - ay) < ar + R for ax, ay, ar in avoid):
                continue
            if any(math.hypot(x - ax, y - ay) < ar + R + 20 for ax, ay, ar in placed):
                continue
            placed.append((x, y, R))
            rect = pygame.Rect(0, 0, int(R * 1.5), int(R * 0.7))
            rect.midbottom = (x, y - 8)
            self.props.append(Prop(sprites.draw_rock(rng, r), x, y, rect))

        self.colliders = self.walls + [p.rect for p in self.props]
        self.interactables = [
            Interactable("Abandoned Equipment", (eq_pos[0], eq_pos[1] - 10), 95,
                         [("Abandoned Equipment", "[Placeholder] A weathered supply unit, half buried in dust."),
                          ("Abandoned Equipment", "[Placeholder] Its logs are corrupted.")],
                         "Inspect", prompt_offset=80),
            Interactable("Beacon", (bc_pos[0], bc_pos[1] - 6), 75,
                         [("Beacon", "[Placeholder] A faint signal pulses from the beacon.")],
                         "Inspect", prompt_offset=60),
        ]

    def draw_signal(self, surf, cam, site, t):
        """Pulsing cyan signal marker over an equipment site."""
        r = 50 + int((t * 40) % 50) // 5 * 5
        level = max(1, int(7 * (1 - (r - 50) / 50)))
        surf.blit(sprites.glow(r, level), (int(site[0] - cam.x - r), int(site[1] - cam.y - r)),
                  special_flags=pygame.BLEND_RGB_ADD)

    def draw_ground(self, surf, cam):
        surf.blit(self.ground, (0, 0), pygame.Rect(int(cam.x), int(cam.y), SCREEN_W, SCREEN_H))
