import sys
sys.path.insert(0, "..")
from story_data import EQUIPMENT, objective, rover_lines
from journal import StoryProgress

ids = [e["id"] for e in EQUIPMENT]
assert ids == ["ingenuity","insight","phoenix","spirit","opportunity","sojourner","viking"], ids
p = StoryProgress()
assert p.current()["id"] == "ingenuity"
assert not p.recover("insight"), "skip ahead must fail"
assert not p.recover("viking")
assert p.is_available("ingenuity") and not p.is_available("insight")
assert objective(p) == "Explore Mars."
p.signal_detected = True
assert objective(p) == "Follow the signal."
assert p.recover("ingenuity")
assert not p.recover("ingenuity"), "duplicate capsule must fail"
assert p.recovered == ["ingenuity"]
assert p.current()["id"] == "insight" and p.is_available("insight") and not p.is_available("ingenuity")
assert "More lost memories are waiting" in objective(p) and "InSight" in objective(p)
assert "InSight" in rover_lines(p)[0][1]
assert abs(p.archive.integrity - 1/7) < 1e-9
q = StoryProgress.from_dict(p.to_dict()); assert q.recovered == ["ingenuity"] and q.signal_detected
assert p.recover("insight") and p.current()["id"] == "phoenix"
print("journal/story_data logic: PASS")
