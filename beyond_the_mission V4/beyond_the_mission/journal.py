"""Progress tracking and the Ghost Rover archive (no pygame)."""
from story_data import EQUIPMENT, BY_ID


class Archive:
    """Memory Capsules inserted into Ghost Rover's archive."""
    SLOTS = len(EQUIPMENT)

    def __init__(self):
        self.capsules = []   # equipment ids, in insertion order

    def has(self, eq_id):
        return eq_id in self.capsules

    def add(self, eq_id):
        if eq_id in self.capsules:
            return False
        self.capsules.append(eq_id)
        return True

    @property
    def integrity(self):
        return len(self.capsules) / self.SLOTS


class StoryProgress:
    def __init__(self):
        self.archive = Archive()
        self.signal_detected = False

    @property
    def recovered(self):
        return list(self.archive.capsules)

    def is_recovered(self, eq_id):
        return self.archive.has(eq_id)

    def current(self):
        """Next equipment to recover (strict newest-to-oldest order), or None."""
        for eq in EQUIPMENT:
            if not self.archive.has(eq["id"]):
                return eq
        return None

    def is_available(self, eq_id):
        cur = self.current()
        return cur is not None and cur["id"] == eq_id

    def recover(self, eq_id):
        """Insert the capsule. Fails (False) if out of order or already collected."""
        if eq_id not in BY_ID or not self.is_available(eq_id):
            return False
        return self.archive.add(eq_id)

    def to_dict(self):
        return {"capsules": list(self.archive.capsules), "signal": self.signal_detected}

    @classmethod
    def from_dict(cls, d):
        p = cls()
        p.archive.capsules = list(d.get("capsules", []))
        p.signal_detected = bool(d.get("signal", False))
        return p
