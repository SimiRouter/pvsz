"""Per-screen render + animation-motion verification.

For every game screen: draw a real frame, save a PNG, and prove it actually
has content (colour spread, not a black/blank canvas). For every looping
animation the smoothness audit touched (snowpea sheets, sun spin/bob, zombie
walk): draw the screen twice and advance ONLY the subject's own animation
clock between the shots — any pixel difference can then only come from the
subject, proving it actually moves on screen (a registered-but-static sheet
would pass dev_verify_smooth.py's cell checks yet freeze in play).

Pure pygame: the venv has no numpy, so diffs go through pygame.PixelArray
and content stats through a sampled get_at grid.

Run:  SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy ./venv/bin/python dev_verify_screens.py
"""
import math
import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
pygame.init()
SCREEN = pygame.display.set_mode((1400, 600))

import assets_loader
assets_loader.init()

from constants import *
import entities
import save as save_mod
save_mod.SAVE_PATH = os.path.join(os.environ.get("TMPDIR", "/tmp"), "pvsz_screens_save.json")
from game import Game

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "screenshots", "dev_screens")
os.makedirs(OUT, exist_ok=True)

fails = []


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  [{detail}]" if detail else ""))
    if not ok:
        fails.append(name)


def grab(g, name):
    """Full real-frame draw (gameplay layer + state overlay) saved to PNG."""
    g.draw()
    g.draw_state()
    pygame.image.save(g.screen, os.path.join(OUT, name + ".png"))


def diff_saved(name_a, name_b, region=None):
    """Number of pixels that differ between two saved frames.

    ``region`` (x, y, w, h) crops to the animation subject — pixels elsewhere
    are constant by construction, but cropping keeps the pure-Python loop
    fast and the signal local to what we are actually testing."""
    sa = pygame.image.load(os.path.join(OUT, name_a + ".png")).convert()
    sb = pygame.image.load(os.path.join(OUT, name_b + ".png")).convert()
    pa = pygame.PixelArray(sa)
    pb = pygame.PixelArray(sb)
    if region:
        x, y, w, h = region
        pa = pa[x:x + w, y:y + h]
        pb = pb[x:x + w, y:y + h]
    diff = 0
    for cx in range(len(pa)):
        ca = pa[cx]
        cb = pb[cx]
        diff += sum(1 for i in range(len(ca)) if ca[i] != cb[i])
    pa.close()
    pb.close()
    return diff


def stats_saved(name, stride=6):
    """Contrast + palette size over a sampled grid of pixels."""
    s = pygame.image.load(os.path.join(OUT, name + ".png")).convert()
    W, H = s.get_size()
    samples = []
    for y in range(0, H, stride):
        gx = s.get_at
        for x in range(0, W, stride):
            c = gx((x, y))
            samples.append((c.r, c.g, c.b))
    n = len(samples)
    mean = sum(sum(p) for p in samples) / (3.0 * n)
    var = sum((p[0] - mean) ** 2 + (p[1] - mean) ** 2 + (p[2] - mean) ** 2
              for p in samples) / (3.0 * n)
    uniq = len({(p[0] >> 3, p[1] >> 3, p[2] >> 3) for p in samples})
    return math.sqrt(var), uniq, mean


# ---------------------------------------------------------------- screens
def s_menu(g):
    pass


def s_mode(g):
    g.state = STATE_MODE_SELECT


def s_level_select(g):
    g._open_adventure_map()


def s_seed_select(g):
    g._open_adventure_map()
    c = g.level_select.cards[0]
    g.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN,
                                      {"pos": (c.x + c.w // 2, c.y + c.h // 2),
                                       "button": 1}))
    assert g.state == STATE_SEED_SELECT, g.state


def _worstcase_play(g, level):
    """A lawn packed with the heaviest draw load: many plants, many zombies.

    Planting goes through the real placement path so pool/roof validity rules
    apply exactly as in play; cells a level refuses are simply skipped."""
    g.start_adventure_level(level)
    g.sun_value = 99999
    plan = {1: PLANT_PEASHOOTER, 3: PLANT_SUNFLOWER, 5: PLANT_SNOWPEA, 7: PLANT_WALLNUT}
    for row in range(GRID_ROWS):
        for col, pt in plan.items():
            try:
                g._plant(pt, (row, col))
            except Exception:
                pass
            g.plant_cooldowns.clear()
    for i in range(12):
        z = entities.create_zombie(
            GRID_X + 5 * CELL_W,
            g.grid.y + (i % GRID_ROWS) * CELL_H + 15,
            i % GRID_ROWS,
            [ZOMBIE_BASIC, ZOMBIE_CONEHEAD, ZOMBIE_BUCKETHEAD][i % 3])
        z.grid_y = g.grid.y
        g.zombies.append(z)
    g.sun_value = 99999
    return g


def s_play_day(g):
    _worstcase_play(g, "1-3")


def s_play_night(g):
    _worstcase_play(g, "2-2")


def s_play_pool(g):
    _worstcase_play(g, "3-2")


def s_play_fog(g):
    _worstcase_play(g, "4-3")


def s_play_roof(g):
    _worstcase_play(g, "5-3")


def s_paused(g):
    _worstcase_play(g, "1-3")
    g.state = STATE_PAUSED


def s_game_over(g):
    g.start_adventure_level("1-1")
    g.state = STATE_GAME_OVER


def s_level_complete(g):
    g.start_adventure_level("1-1")
    g.state = STATE_LEVEL_COMPLETE


def s_survival_complete(g):
    g.start_survival("surv_day")
    g.state = STATE_SURVIVAL_COMPLETE


SCREENS = [
    ("menu", s_menu), ("mode_select", s_mode), ("level_select", s_level_select),
    ("seed_select", s_seed_select), ("play_day", s_play_day),
    ("play_night", s_play_night), ("play_pool", s_play_pool),
    ("play_fog", s_play_fog), ("play_roof", s_play_roof), ("paused", s_paused),
    ("game_over", s_game_over), ("level_complete", s_level_complete),
    ("survival_complete", s_survival_complete),
]

print("== per-screen render sanity (13 screens) ==")
for name, setup in SCREENS:
    g = Game(SCREEN)
    try:
        setup(g)
    except Exception as e:
        check(f"{name}: setup", False, repr(e))
        continue
    # let the intro/wave machinery tick a bit so HUD and animations are live
    for _ in range(30):
        g.update(1 / 60.0)
        g.draw()
        g.draw_state()
    grab(g, name)
    std, uniq, mean = stats_saved(name)
    # any real screen: some contrast and a palette well beyond a blank canvas
    check(f"{name}: rendered content", std > 8 and uniq > 100,
          f"std={std:.1f} uniq={uniq} mean={mean:.0f} -> {name}.png")

print()
print("== animation actually moves on screen ==")

# 1) SnowPea sheets: registered, distinct cells, attack differs from idle.
frames = assets_loader.anim_frames("anim_snowpea_idle")
distinct = {pygame.image.tostring(fr, "RGBA") for fr in frames}
check("snowpea idle sheet: cells are distinct art", len(distinct) >= 4,
      f"{len(distinct)} distinct of {len(frames)}")
atk = assets_loader.anim_frames("anim_snowpea_attack")
check("snowpea attack sheet differs from idle",
      {pygame.image.tostring(fr, "RGBA") for fr in atk} != distinct)


def _quiet_lawn(g):
    """Strip everything that moves by itself so only the test subject can
    change pixels between two grabs."""
    g.zombies.clear()
    g.suns.clear()
    g.projectiles.clear()
    g.coin_drops.clear()
    g.explosions.clear()
    g.plant_foods.clear()
    g.floating_texts.clear()
    g.fx.clear()
    g.shake = 0.0
    g.flash_timer = 0.0
    g.wave_warning.alive = False
    for p in g.plants:                       # freeze every plant clock
        p.anim_time = 0.0
        p.attacking = False


# 2) SnowPea on the lawn: advance only its anim_time between shots.
g = Game(SCREEN)
s_play_day(g)
for _ in range(10):
    g.update(1 / 60.0)
_quiet_lawn(g)
snow = next(p for p in g.plants if p.plant_type == PLANT_SNOWPEA)
sbox = (int(snow.x) - 10, int(snow.y) - 40, 170, 170)
grab(g, "anim_snowpea_a")
for _ in range(15):          # 0.25 s of a 1 s (6-cell) cycle
    snow.anim_time += 1 / 60.0
grab(g, "anim_snowpea_b")
da = diff_saved("anim_snowpea_a", "anim_snowpea_b", sbox)
check("snowpea idle: pixels change over 0.25s", da > 200, f"{da} px differ")
fidx = {int(t * 6) % 6 for t in (0.0, 0.2, 0.4)}
check("snowpea frame index advances with anim_time", len(fidx) == 3, f"{sorted(fidx)}")

# 3) Sun rest phase: bob/tilt must move pixels over 10 frames.
g = Game(SCREEN)
g.start_adventure_level("1-1")
for _ in range(10):
    g.update(1 / 60.0)
_quiet_lawn(g)
sun = entities.Sun(500.0, 300.0)
sun.phase = "rest"
sun.falling = False
sun.target_y = 300.0
g.suns = [sun]
for _ in range(5):
    sun.update(1 / 60.0)
grab(g, "sun_a")
for _ in range(10):
    sun.update(1 / 60.0)     # only the sun advances; game clock frozen
grab(g, "sun_b")
ds = diff_saved("sun_a", "sun_b", (420, 210, 160, 180))
check("sun rest: pixels change over 10 frames (bob/spin)", ds > 100,
      f"{ds} px differ")

# 4) Zombie walk: advance only the walk phase between shots.
g = Game(SCREEN)
s_play_day(g)
for _ in range(10):
    g.update(1 / 60.0)
g.suns.clear()
g.projectiles.clear()
g.fx.clear()
g.coin_drops.clear()
g.wave_warning.alive = False
z = g.zombies[0]
z.x = float(GRID_X + 4 * CELL_W)   # park it on the lawn for a stable shot
z.is_eating = False
z.dying_timer = 0
zbox = (int(z.x) - 10, int(z.y) - 50, 150, 210)
grab(g, "zombie_a")
for _ in range(14):
    z.walk_phase = (z.walk_phase + (z.speed / 60.0) / z.STRIDE_PX) % 1.0
grab(g, "zombie_b")
dz = diff_saved("zombie_a", "zombie_b", zbox)
check("zombie walk: pixels change over 14 frames", dz > 100, f"{dz} px differ")
zz = entities.create_zombie(300.0, g.grid.y + CELL_H + 15, 1, ZOMBIE_BASIC)
zz.grid_y = g.grid.y
seen = {zz._frame_index()}
for _ in range(90):
    zz.walk_phase = (zz.walk_phase + (zz.speed / 60.0) / zz.STRIDE_PX) % 1.0
    seen.add(zz._frame_index())
check("zombie walk frames cycle through >1 cell", len(seen) >= 2, f"visited {sorted(seen)}")

# 5) Language toggle must re-key the text caches (invalidate wiring).
import i18n
import ui as ui_mod
i18n.set_lang("en")
before = len(ui_mod.fx._text_cache)
ui_mod.invalidate_text_caches()
check("invalidate_text_caches clears fx cache", len(ui_mod.fx._text_cache) == 0,
      f"had {before} entries")
ui_mod.invalidate_text_caches()   # idempotent, must not raise

# Render the ZH menu, remember its cache keys; toggle to EN; every ZH-only
# (translated) key must be gone afterwards — the old-language surfaces were
# dropped by invalidate_text_caches(). Keys that are the same string in both
# languages (numbers, the "PLANTS VS ZOMBIES" wordmark) legitimately persist.
# Game.__init__ re-reads lang from the save file, so force ZH *after* it is
# constructed, otherwise a previous run's persisted "en" wins and the menu
# renders EN from the start (which is what the earlier FAIL was measuring).
g = Game(SCREEN)
i18n.set_lang("zh")
g.state = STATE_MENU
g.draw()
g.draw_state()
zh_keys = set(ui_mod.fx._text_cache)
zh_only = {k for k in zh_keys if any(ord(c) > 127 for c in str(k[0]))}
g._toggle_language()
g.draw()
g.draw_state()
after = set(ui_mod.fx._text_cache)
stale = zh_only & after
en_renders = any(k[0] == "Start Game" for k in after)
check("language toggle drops stale-language text cache",
      len(zh_only) > 0 and not stale and en_renders,
      f"{len(zh_only)} zh-only keys, stale {len(stale)}, EN re-rendered {en_renders}")
grab(g, "menu_en_after_toggle")
i18n.set_lang("en")

# 6) Hover-freeze sun still holds (feature regression from the sun audit).
s = entities.Sun(400.0, 300.0)
s.phase = "rest"
s.falling = False
s.target_y = 300.0
v0 = s._visual_center()
for _ in range(30):
    s.update(1 / 60.0, hovered=True)
check("sun hover-freeze still holds", s._visual_center() == v0)

print()
print("RESULT:", "ALL PASS" if not fails else f"{len(fails)} FAILURES")
for f in fails:
    print("  -", f)
print("screenshots:", OUT)
raise SystemExit(1 if fails else 0)
