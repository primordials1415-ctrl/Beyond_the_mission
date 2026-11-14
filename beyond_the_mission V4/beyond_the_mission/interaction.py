import pygame


class Interactable:
    """Anything the player can press E on. Needs .pos (ground position)."""

    def __init__(self, name, pos, radius, lines, prompt="Interact", prompt_offset=60):
        self.name = name
        self.pos = pygame.Vector2(pos)
        self.radius = radius
        self.lines = lines              # list of (speaker, text)
        self.prompt = prompt
        self.prompt_offset = prompt_offset
        self.on_end = None              # optional callback when dialogue finishes

    def on_interact(self, player_pos):
        pass


class Conversation(Interactable):
    """Scripted dialogue that is not tied to a world object."""

    def __init__(self, lines, on_end=None):
        super().__init__("conversation", (0, 0), 0, lines)
        self.on_end = on_end


class InteractionSystem:
    def __init__(self):
        self.target = None      # nearby interactable (shows prompt)
        self.active = None      # interactable currently in conversation
        self.index = 0
        self.player_pos = pygame.Vector2()

    @property
    def in_dialogue(self):
        return self.active is not None

    @property
    def current(self):
        return self.active.lines[self.index]

    def update(self, player_pos, interactables):
        self.player_pos = pygame.Vector2(player_pos)
        if self.in_dialogue:
            self.target = None
            return
        best, best_d = None, 1e9
        for it in interactables:
            d = it.pos.distance_to(player_pos)
            if d <= it.radius and d < best_d:
                best, best_d = it, d
        self.target = best

    def handle_event(self, event):
        if event.type != pygame.KEYDOWN:
            return
        if self.in_dialogue:
            if event.key in (pygame.K_e, pygame.K_SPACE):
                self.index += 1
                if self.index >= len(self.active.lines):
                    done, self.active = self.active, None
                    if done.on_end:
                        done.on_end()
        elif self.target and event.key == pygame.K_e:
            self.start(self.target)

    def start(self, interactable):
        self.active = interactable
        self.index = 0
        interactable.on_interact(self.player_pos)

    def start_lines(self, lines, on_end=None):
        self.start(Conversation(lines, on_end))
