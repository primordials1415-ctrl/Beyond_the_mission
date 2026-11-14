"""Story and equipment data (no pygame). Order of EQUIPMENT = encounter order,
newest mission to oldest. To add art/dialogue for an entry, set its fields and
implemented=True (art functions live in sprites.py)."""


def _eq(id, name, location, mission, ghost, personality, challenge, site, tint, intro, thanks,
        cutscene_text=None):
    return dict(
        id=id, name=name, location=location, mission=mission, ghost_name=ghost,
        personality=personality, challenge=challenge, implemented=True, site=site, tint=tint,
        intro_lines=[(ghost, t) if sp == "G" else ("Ghost Rover", t) for sp, t in intro],
        thanks_lines=[(ghost, thanks)],
        capsule_title=f"{name} Memory Capsule",
        capsule_blurb=f"This capsule holds fragments of {name}'s mission memories.",
        cutscene_title="Memory Reconstruction",
        cutscene_text=cutscene_text or
        f"{name}'s memories are being reconstructed. Its complete story will be revealed here.",
        recovery_lines=None)   # filled in below


EQUIPMENT = [
    _eq("ingenuity", "Ingenuity", "Jezero Crater, Mars",
        "Demonstrate powered, controlled flight on another planet", "Ghost Ingenuity",
        "Cheerful and curious; gets excited about the sky", "(future) flight-themed challenge",
        (1780, 450), (190, 140, 255),
        [("G", "Bzzt... hello? Is someone there?"),
         ("R", "We heard your signal. Who are you?"),
         ("G", "I'm... Ingenuity. I think. My memories are broken into little pieces."),
         ("G", "I remember spinning blades. A lot of sky. Then static."),
         ("R", "My archive is damaged too. Recovering your memories might help repair it."),
         ("G", "Will you help me find them, explorer?")],
        "Thank you, explorer. I remember the sky now."),
    _eq("insight", "InSight", "Elysium Planitia, Mars",
        "Study the internal structure of Mars", "Ghost InSight",
        "Quiet and patient; a good listener", "(future) listening / seismic challenge",
        (2100, 900), (150, 190, 255),
        [("G", "...Shh. Do you hear that? The ground is humming."),
         ("R", "Hello? Are you InSight?"),
         ("G", "I think so. I used to listen to Mars. Its rumbles, its tiny shakes."),
         ("G", "But my listening memories are scattered. Will you help me find them?")],
        "Thank you. I can hear Mars again."),
    _eq("phoenix", "Phoenix", "Martian North Polar Region",
        "Investigate the Martian soil and search for water ice", "Ghost Phoenix",
        "Calm and careful; notices small details", "(future) digging / soil challenge",
        (1900, 1350), (255, 165, 120),
        [("G", "Careful... please don't step on the frost. It's very delicate."),
         ("R", "We're friends. Are you Phoenix?"),
         ("G", "I was. I dug into cold soil near the top of the world. I remember a scoop... and something icy."),
         ("G", "The rest is fuzzy. Could you help me remember?")],
        "Thank you. The ice is clear in my mind now."),
    _eq("spirit", "Spirit", "Gusev Crater, Mars",
        "Investigate Martian rocks and evidence of ancient water", "Ghost Spirit",
        "Determined and stubborn", "(future) rock-analysis challenge",
        (1300, 1400), (150, 255, 170),
        [("G", "Stop right there! ...Oh. Sorry. Old habit."),
         ("G", "I'm Spirit. I never gave up, even when I got stuck. But my memories did."),
         ("R", "Our archives are both damaged. Maybe we can fix them together."),
         ("G", "Hmph. Fine. Let's find my missing pieces.")],
        "Hmph... thanks. I remembered something important."),
    _eq("opportunity", "Opportunity", "Meridiani Planum, Mars",
        "Investigate rocks and minerals for evidence of past water", "Ghost Opportunity",
        "Optimistic and tireless", "(future) mineral challenge",
        (500, 1250), (255, 220, 120),
        [("G", "Hello, hello! What a beautiful day for exploring!"),
         ("R", "You sound cheerful. Are you Opportunity?"),
         ("G", "That's me! I kept going and going. But now my memories are in little pieces."),
         ("G", "Want to help? We'll make it fun, I promise!")],
        "You did it! I knew we could."),
    _eq("sojourner", "Sojourner", "Ares Vallis, Mars",
        "Test rover technology and study Martian rocks and soil", "Ghost Sojourner",
        "Small but brave", "(future) driving / navigation challenge",
        (400, 500), (255, 160, 220),
        [("G", "Um... hi. I'm small. Is that okay?"),
         ("R", "Small is perfectly fine. Are you Sojourner?"),
         ("G", "I was the first little rover to roll on Mars! ...I think. My memories are fuzzy."),
         ("G", "I'll be brave if you'll help me look for them.")],
        "Thank you. Even small explorers matter."),
    _eq("viking", "Viking 1 and 2", "Chryse Planitia and Utopia Planitia, Mars",
        "Study Martian soil and investigate the possibility of life", "Ghost Viking",
        "Wise and thoughtful, like an elder", "(future) life-detection challenge",
        (800, 250), (225, 235, 240),
        [("G", "Ah. Visitors. It has been a long, long time."),
         ("R", "Are you the Viking landers?"),
         ("G", "We were two. Now I am an echo of both. We asked a big question about Mars."),
         ("G", "I have forgotten the answers. Will you help me remember, young explorer?")],
        "Thank you, young explorer. The question lives on.",
        cutscene_text="The Viking landers' memories are being reconstructed. Their complete story will be revealed here."),
]
BY_ID = {e["id"]: e for e in EQUIPMENT}

# Ingenuity keeps its hand-written recovery dialogue; the rest are generated.
for _i, _e in enumerate(EQUIPMENT):
    if _i == 0:
        _e["recovery_lines"] = [
            ("Ghost Rover", "Memory fragment received... Archive integrity improving."),
            ("Ghost Rover", "More lost memories are out there. I can sense another signal. Let's keep exploring!")]
    elif _i < len(EQUIPMENT) - 1:
        _e["recovery_lines"] = [
            ("Ghost Rover", "Memory fragment received... Archive integrity improving."),
            ("Ghost Rover", f"I'm detecting another signal. I think it's {EQUIPMENT[_i + 1]['name']}.")]
    else:
        _e["recovery_lines"] = [
            ("Ghost Rover", "Memory fragment received... Archive integrity restored."),
            ("Ghost Rover", "That was the last one. A mission doesn't become meaningless just because it ends.")]

INTRO_LINES = [
    ("Ghost Rover", "Explorer, wait. I'm picking up a faint signal."),
    ("Ghost Rover", "It isn't in my archive. My database is... damaged. I can't tell what it is."),
    ("Ghost Rover", "The signal is to the northeast. Let's follow it."),
]


def objective(progress):
    cur = progress.current()
    if cur is None:
        return "All lost memories recovered!"
    if progress.recovered:
        return f"More lost memories are waiting to be discovered. Next: {cur['name']}."
    if not progress.signal_detected:
        return "Explore Mars."
    return "Follow the signal."


def rover_lines(progress):
    """What Ghost Rover says when the player talks to it (E)."""
    if not progress.signal_detected or not progress.recovered:
        return [("Ghost Rover", "The signal is to the northeast. Let's follow it.")]
    cur = progress.current()
    if cur is None:
        return [("Ghost Rover", "My archive is complete. Thank you, explorer.")]
    return [("Ghost Rover", f"Another memory is out there. I think it belongs to {cur['name']}.")]
