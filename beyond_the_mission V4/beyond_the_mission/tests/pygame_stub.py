"""Minimal pygame stand-in for headless logic/flow tests (pygame itself is not needed).
Rect and Surface behave enough for ui.py / ingenuity_game.py; everything drawn is a no-op.
Event/key constants are unique MagicMock attributes (compared by identity)."""
import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


class FakeRect:
    def __init__(self, *a):
        if len(a) == 1:
            a = tuple(a[0]) if not isinstance(a[0], FakeRect) else (a[0].x, a[0].y, a[0].w, a[0].h)
        elif len(a) == 2:
            a = (*a[0], *a[1])
        self.x, self.y, self.w, self.h = a

    right = property(lambda s: s.x + s.w)
    bottom = property(lambda s: s.y + s.h)
    centerx = property(lambda s: s.x + s.w // 2)
    centery = property(lambda s: s.y + s.h // 2)
    size = property(lambda s: (s.w, s.h))
    topleft = property(lambda s: (s.x, s.y))
    center = property(lambda s: (s.centerx, s.centery))

    def __setattr__(self, k, v):
        if k == "center":
            object.__setattr__(self, "x", v[0] - self.w // 2)
            object.__setattr__(self, "y", v[1] - self.h // 2)
        elif k == "midtop":
            object.__setattr__(self, "x", v[0] - self.w // 2)
            object.__setattr__(self, "y", v[1])
        elif k == "midbottom":
            object.__setattr__(self, "x", v[0] - self.w // 2)
            object.__setattr__(self, "y", v[1] - self.h)
        else:
            object.__setattr__(self, k, v)

    def get_rect(self, **kw):
        return self

    def inflate(self, dx, dy):
        return FakeRect(self.x - dx // 2, self.y - dy // 2, self.w + dx, self.h + dy)

    def collidepoint(self, *p):
        px, py = p[0] if len(p) == 1 else p
        return self.x <= px < self.x + self.w and self.y <= py < self.y + self.h


class FakeSurface:
    def __init__(self, size=(1, 1), *a, **k):
        self.size = tuple(size)

    def get_width(self): return self.size[0]
    def get_height(self): return self.size[1]
    def get_rect(self, **kw): return FakeRect(0, 0, *self.size)
    def blit(self, *a, **k): pass
    def fill(self, *a, **k): pass
    def set_at(self, *a, **k): pass
    def set_alpha(self, *a, **k): pass
    def convert_alpha(self): return self


class FakeFont:
    def size(self, text): return (len(text) * 8, 20)
    def render(self, text, aa, color): return FakeSurface((len(text) * 8, 20))


def install():
    m = MagicMock()
    m.Rect = FakeRect
    m.Surface = FakeSurface
    m.font.Font = lambda name, size: FakeFont()
    m.transform.scale = lambda s, size: FakeSurface(size)
    m.time.get_ticks = lambda: 0
    sys.modules["pygame"] = m
    return m
