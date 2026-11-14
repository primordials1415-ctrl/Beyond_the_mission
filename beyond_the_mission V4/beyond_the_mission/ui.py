import math
import pygame
from settings import SCREEN_W, SCREEN_H, CYAN, PANEL, TEXT, DIM

_fonts = {}
SLOTS = 6   # archive slots (one per equipment)


def font(size):
    if size not in _fonts:
        _fonts[size] = pygame.font.Font(None, size)
    return _fonts[size]


def draw_panel(surf, rect, alpha=225):
    rect = pygame.Rect(rect)
    p = pygame.Surface(rect.size, pygame.SRCALPHA)
    p.fill((*PANEL, alpha))
    surf.blit(p, rect.topleft)
    pygame.draw.rect(surf, CYAN, rect, 2)
    pygame.draw.rect(surf, (30, 70, 90), rect.inflate(-8, -8), 1)


def wrap(text, f, max_w):
    lines, cur = [], ""
    for word in text.split():
        test = (cur + " " + word).strip()
        if f.size(test)[0] <= max_w:
            cur = test
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def draw_dialogue(surf, speaker, text):
    rect = pygame.Rect(24, SCREEN_H - 24 - 150, SCREEN_W - 48, 150)
    draw_panel(surf, rect, 235)
    nf = font(32)
    name = nf.render(speaker, True, CYAN)
    tab = pygame.Rect(rect.x + 16, rect.y - 20, name.get_width() + 28, 34)
    draw_panel(surf, tab, 245)
    surf.blit(name, (tab.x + 14, tab.y + 8))
    tf = font(30)
    for i, line in enumerate(wrap(text, tf, rect.w - 40)):
        surf.blit(tf.render(line, True, TEXT), (rect.x + 20, rect.y + 28 + i * 30))
    if (pygame.time.get_ticks() // 500) % 2 == 0:
        hint = font(24).render("[E] Continue", True, CYAN)
        surf.blit(hint, (rect.right - hint.get_width() - 18, rect.bottom - 30))


def draw_prompt(surf, anchor, label):
    t = font(26).render(label, True, TEXT)
    rect = pygame.Rect(0, 0, t.get_width() + 50, 32)
    rect.midbottom = (anchor[0], anchor[1] + int(math.sin(pygame.time.get_ticks() / 250) * 2))
    draw_panel(surf, rect, 230)
    key = pygame.Rect(rect.x + 6, rect.y + 5, 22, 22)
    pygame.draw.rect(surf, CYAN, key, 2)
    k = font(26).render("E", True, CYAN)
    surf.blit(k, k.get_rect(center=key.center))
    surf.blit(t, (rect.x + 38, rect.y + 7))


class Menu:
    def __init__(self, title, items):
        self.title, self.items, self.sel, self.rects = title, items, 0, []
        self.disabled = set()      # actions that are greyed out and cannot be chosen

    def _step(self, d):
        n = len(self.items)
        for _ in range(n):
            self.sel = (self.sel + d) % n
            if self.items[self.sel][1] not in self.disabled:
                return

    def select_first_enabled(self):
        self.sel = 0
        if self.items and self.items[0][1] in self.disabled:
            self._step(1)

    def handle_event(self, e):
        if e.type == pygame.KEYDOWN:
            if e.key in (pygame.K_UP, pygame.K_w):
                self._step(-1)
            elif e.key in (pygame.K_DOWN, pygame.K_s):
                self._step(1)
            elif e.key in (pygame.K_RETURN, pygame.K_SPACE, pygame.K_e):
                return self.items[self.sel][1]
        elif e.type == pygame.MOUSEMOTION:
            for i, r in enumerate(self.rects):
                if r.collidepoint(e.pos) and self.items[i][1] not in self.disabled:
                    self.sel = i
        elif e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
            for i, r in enumerate(self.rects):
                if r.collidepoint(e.pos) and self.items[i][1] not in self.disabled:
                    return self.items[i][1]
        return None

    def draw(self, surf, top):
        title = font(76 if len(self.title) > 8 else 64).render(self.title, True, CYAN)
        surf.blit(title, title.get_rect(midtop=(SCREEN_W // 2, top)))
        self.rects = []
        y = top + 110
        for i, (label, _) in enumerate(self.items):
            r = pygame.Rect(0, 0, 300, 50)
            r.midtop = (SCREEN_W // 2, y)
            self.rects.append(r)
            selected = i == self.sel
            if selected:
                draw_panel(surf, r, 230)
            off = self.items[i][1] in self.disabled
            txt = font(40).render(label, True, (60, 80, 88) if off else (CYAN if selected else DIM))
            surf.blit(txt, txt.get_rect(center=r.center))
            y += 64


# ------------------------------------------------------- story-screen helpers
def center_panel(surf, w, h, alpha=240):
    rect = pygame.Rect(0, 0, w, h)
    rect.center = (SCREEN_W // 2, SCREEN_H // 2)
    draw_panel(surf, rect, alpha)
    return rect


def draw_title(surf, text, y, size=52, color=CYAN):
    t = font(size).render(text, True, color)
    surf.blit(t, t.get_rect(midtop=(SCREEN_W // 2, y)))


def draw_wrapped(surf, text, size, rect, y, color=TEXT, lead=None):
    f = font(size)
    lead = size - 2 if lead is None else lead
    for line in wrap(text, f, rect.w):
        t = f.render(line, True, color)
        surf.blit(t, t.get_rect(midtop=(SCREEN_W // 2, y)))
        y += lead
    return y


class ButtonRow:
    """Centered row of buttons. Keyboard: arrows/A/D to pick, Enter/E/Space to
    confirm. Mouse: hover + click. handle_event returns the chosen index."""

    def __init__(self, labels, y, w=250, h=48, gap=24):
        self.labels, self.sel = labels, 0
        total = len(labels) * w + (len(labels) - 1) * gap
        x = (SCREEN_W - total) // 2
        self.rects = [pygame.Rect(x + i * (w + gap), y, w, h) for i in range(len(labels))]

    def handle_event(self, e):
        n = len(self.labels)
        if e.type == pygame.KEYDOWN:
            if e.key in (pygame.K_LEFT, pygame.K_a, pygame.K_UP, pygame.K_w):
                self.sel = (self.sel - 1) % n
            elif e.key in (pygame.K_RIGHT, pygame.K_d, pygame.K_DOWN, pygame.K_s):
                self.sel = (self.sel + 1) % n
            elif e.key in (pygame.K_RETURN, pygame.K_SPACE, pygame.K_e):
                return self.sel
        elif e.type == pygame.MOUSEMOTION:
            for i, r in enumerate(self.rects):
                if r.collidepoint(e.pos):
                    self.sel = i
        elif e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
            for i, r in enumerate(self.rects):
                if r.collidepoint(e.pos):
                    return i
        return None

    def draw(self, surf):
        for i, (label, r) in enumerate(zip(self.labels, self.rects)):
            sel = i == self.sel
            draw_panel(surf, r, 245 if sel else 200)
            t = font(34).render(label, True, CYAN if sel else DIM)
            surf.blit(t, t.get_rect(center=r.center))


def draw_hud(surf, objective):
    f = font(26)
    t = f.render(objective, True, TEXT)
    rect = pygame.Rect(14, 14, t.get_width() + 24, 34)
    draw_panel(surf, rect, 190)
    surf.blit(t, (rect.x + 12, rect.y + 8))


def draw_toast(surf, text, age):
    t = font(46).render(text, True, CYAN)
    rect = pygame.Rect(0, 0, t.get_width() + 60, 64)
    rect.midtop = (SCREEN_W // 2, 70 - int(max(0, 0.3 - age) * 200))
    draw_panel(surf, rect, 240)
    surf.blit(t, t.get_rect(center=rect.center))


def archive_slot_rect(panel, index):
    w, h, gap = 100, 110, 14
    total = SLOTS * w + (SLOTS - 1) * gap
    return pygame.Rect(panel.x + (panel.w - total) // 2 + index * (w + gap), panel.y + 80, w, h)


def draw_archive(surf, panel, capsule_ids, integrity):
    """Ghost Rover archive: one slot per piece of equipment, in encounter order."""
    from story_data import EQUIPMENT
    draw_panel(surf, panel, 245)
    draw_title(surf, "Ghost Rover Archive", panel.y + 20, 40)
    for i, eq in enumerate(EQUIPMENT):
        r = archive_slot_rect(panel, i)
        filled = eq["id"] in capsule_ids
        pygame.draw.rect(surf, (16, 34, 48) if filled else (12, 18, 26), r, border_radius=8)
        pygame.draw.rect(surf, CYAN if filled else (40, 60, 70), r, 2, border_radius=8)
        if filled:
            cap = pygame.Rect(0, 0, 28, 52)
            cap.center = (r.centerx, r.centery - 10)
            pygame.draw.rect(surf, (24, 40, 60), cap, border_radius=12)
            pygame.draw.rect(surf, CYAN, cap, 2, border_radius=12)
            pygame.draw.rect(surf, (100, 240, 255), cap.inflate(-14, -26), border_radius=4)
            label = font(20).render(eq["name"], True, CYAN)
            if label.get_width() > r.w - 6:      # long names (e.g. Spirit & Opportunity) shrink to fit
                label = font(14).render(eq["name"], True, CYAN)
        else:
            label = font(20).render("???", True, DIM)
        surf.blit(label, label.get_rect(midbottom=(r.centerx, r.bottom - 6)))
    bar = pygame.Rect(panel.x + 60, panel.y + 232, panel.w - 120, 14)
    pygame.draw.rect(surf, (12, 18, 26), bar)
    pygame.draw.rect(surf, CYAN, (bar.x, bar.y, int(bar.w * integrity), bar.h))
    pygame.draw.rect(surf, (40, 60, 70), bar, 1)
    lab = font(22).render("Archive integrity", True, DIM)
    surf.blit(lab, (bar.x, bar.y - 22))
