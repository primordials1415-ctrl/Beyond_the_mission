import pygame
from settings import PLAYER_SPEED
from assets import load_image
import sprites

FACINGS = ("down", "up", "left", "right")


class Player:
    FOOT_W, FOOT_H = 18, 10

    def __init__(self, x, y):
        self.pos = pygame.Vector2(x, y)      # feet (bottom centre)
        self.facing = "down"
        self.anim = "idle"
        self.t = 0.0
        self.frame = 0
        self.frames = {}
        for f in FACINGS:
            self.frames[("idle", f)] = [
                load_image(f"player/idle_{f}_{i}.png",
                           lambda f=f, i=i: sprites.draw_astronaut(f, "idle", i))
                for i in range(2)]
            self.frames[("walk", f)] = [
                load_image(f"player/walk_{f}_{i}.png",
                           lambda f=f, i=i: sprites.draw_astronaut(f, "walk", i))
                for i in range(4)]

    @property
    def sort_y(self):
        return self.pos.y

    @property
    def rect(self):
        r = pygame.Rect(0, 0, self.FOOT_W, self.FOOT_H)
        r.midbottom = (round(self.pos.x), round(self.pos.y))
        return r

    def update(self, dt, move, colliders):
        moving = move.length_squared() > 0
        anim = "walk" if moving else "idle"
        if anim != self.anim:
            self.anim, self.t, self.frame = anim, 0.0, 0
        if moving:
            move = move.normalize()          # 8-direction, equal diagonal speed
            if abs(move.x) >= abs(move.y):
                self.facing = "right" if move.x > 0 else "left"
            else:
                self.facing = "down" if move.y > 0 else "up"
            self._step(move.x * PLAYER_SPEED * dt, 0, colliders)
            self._step(0, move.y * PLAYER_SPEED * dt, colliders)
        self.t += dt
        frames = self.frames[(self.anim, self.facing)]
        period = 0.11 if moving else 0.6
        self.frame = int(self.t / period) % len(frames)

    def _step(self, dx, dy, colliders):
        self.pos.x += dx
        self.pos.y += dy
        r = self.rect
        for c in colliders:
            if r.colliderect(c):
                if dx > 0:
                    self.pos.x = c.left - self.FOOT_W / 2
                elif dx < 0:
                    self.pos.x = c.right + self.FOOT_W / 2
                if dy > 0:
                    self.pos.y = c.top
                elif dy < 0:
                    self.pos.y = c.bottom + self.FOOT_H
                r = self.rect

    def draw(self, surf, cam):
        img = self.frames[(self.anim, self.facing)][self.frame]
        sx, sy = self.pos.x - cam.x, self.pos.y - cam.y
        shadow = pygame.Surface((30, 12), pygame.SRCALPHA)
        pygame.draw.ellipse(shadow, (20, 6, 4, 90), (0, 0, 30, 12))
        surf.blit(shadow, (int(sx - 15), int(sy - 8)))
        surf.blit(img, (int(sx - img.get_width() / 2), int(sy - img.get_height() + 4)))
