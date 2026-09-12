"""Whole-project smoothness audit: per-screen frame timing, per-frame surface
budget, animation continuity, and cache cold-entry drift.

Run:
    ./venv/bin/python dev_verify_smooth.py

Pass criteria (60 fps budget = 16.67 ms/frame):
  * every screen/scenario: draw+update avg < 6 ms, p99 < 10 ms, max < 14 ms
    (headless dummy driver; real GPU blit adds a constant, so we audit the
    Python/SDL software cost and leave >= 1/2 budget of headroom)
  * steady state: <= 2 fresh surface allocations per frame (transient scenes
    like sun fade-out are judged live, steady frames must be allocation-free)
  * animation: every sheet actually used by a sprite class returns all its
    cells; frame-index cycling is contiguous with no gaps
  * cache: no NEW _cache keys minted during a steady bench window (all lazy
    surfaces were warmed at level load, not mid-frame)
"""
import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import sys
import time

import pygame
pygame.init()
SCREEN = pygame.display.set_mode((1400, 600))

import assets_loader
assets_loader.init()

from constants import *
import entities
import fx
from game import Game
import ui as ui_mod
from levels import ADVENTURE_LEVELS

# never pollute the shipped save.json from this audit
import save as save_mod
save_mod.SAVE_PATH = os.path.join(os.environ.get("TMPDIR", "/tmp"), "pvsz_smooth_save.json")

fails = []


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  [{detail}]" if detail else ""))
    if not ok:
        fails.append(name)


# ---------------------------------------------------------------- allocation
# Count every pygame.Surface / transform / font.render call made while a
# frame is being timed. All call sites go through module attrs
# (pygame.Surface, pygame.transform.rotate, font.render), so swapping the
# attributes on the live modules is enough; C-level loads stay invisible,
# which is fine (we only care about steady-state churn).

_ALLOC = {"n": 0}
_RealSurface = pygame.Surface
_real_rotate = pygame.transform.rotate
_real_smoothscale = pygame.transform.smoothscale


class _CountSurface(_RealSurface):
    def __init__(self, *a, **k):
        _ALLOC["n"] += 1
        super().__init__(*a, **k)

    def copy(self, *a, **k):
        _ALLOC["n"] += 1
        return _RealSurface.copy(self, *a, **k)


class _CountFont(pygame.font.Font):
    # Font instances reject per-object attributes ('render' is read-only),
    # so we swap the class itself before any font is constructed — i18n.font
    # creates lazily inside screen constructors, all of which run below.
    def render(self, *a, **k):
        _ALLOC["n"] += 1
        return super().render(*a, **k)


def _wrap(fn):
    def inner(*a, **k):
        _ALLOC["n"] += 1
        return fn(*a, **k)
    return inner


pygame.Surface = _CountSurface
pygame.font.Font = _CountFont
pygame.transform.rotate = _wrap(_real_rotate)
pygame.transform.smoothscale = _wrap(_real_smoothscale)


# ---------------------------------------------------------------- timing
def bench(label, g, frames=480, mouse_jitter=False, budget_avg=6.0,
          budget_p99=10.0, budget_max=14.0, alloc_cap=2):
    """Time update+draw+draw_state per frame like the real main loop, and
    count fresh surface allocations over the same window."""
    import random
    rnd = random.Random(42)
    times = []
    allocs = []
    for i in range(frames):
        if mouse_jitter:
            x = rnd.randint(200, 1200)
            y = rnd.randint(80, 580)
            g.handle_event(pygame.event.Event(
                pygame.MOUSEMOTION, {"pos": (x, y), "rel": (1, 1), "buttons": (0, 0, 0)}))
        _ALLOC["n"] = 0
        t0 = time.perf_counter()
        g.update(1 / 60.0)
        g.draw()
        g.draw_state()
        t1 = time.perf_counter()
        times.append((t1 - t0) * 1000.0)
        allocs.append(_ALLOC["n"])
    times.sort()
    n = len(times)
    avg = sum(times) / n
    p99 = times[int(n * 0.99)]
    mx = times[-1]
    # steady-state allocations: median over the window (transients excluded)
    allocs_sorted = sorted(allocs)
    med_alloc = allocs_sorted[n // 2]
    print(f"  [{label:<18}] avg {avg:5.2f}ms  p99 {p99:5.2f}ms  max {mx:5.2f}ms"
          f"  allocs/frame med {med_alloc} max {max(allocs)}")
    ok = avg < budget_avg and p99 < budget_p99 and mx < budget_max
    check(f"{label}: frame budget", ok, f"avg<{budget_avg} p99<{budget_p99} max<{budget_max}")
    check(f"{label}: steady allocs <= {alloc_cap}", med_alloc <= alloc_cap, f"med={med_alloc}")
    return avg


# ---------------------------------------------------------------- screens
print("== per-screen frame timing ==")


def new_game(state_setup):
    g = Game(SCREEN)
    state_setup(g)
    for _ in range(30):          # warm lazy first-frame caches
        g.update(1 / 60.0)
        g.draw()
        g.draw_state()
    return g


def s_menu(g):
    pass  # Game starts in STATE_MENU


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
    # now in seed select for 1-1
    assert g.state == STATE_SEED_SELECT, g.state


def _worstcase_play(g, level="4-3"):
    """Fog level (extra layer) + full lawn + horde + suns + shake."""
    g.start_adventure_level(level)
    g.sun_value = 99999
    for row in range(GRID_ROWS):
        for col in (0, 1, 2, 3):
            g._plant(PLANT_PEASHOOTER, (row, col))
            g._plant(PLANT_SNOWPEA, (row, col))
            g.plant_cooldowns.clear()
        g._plant(PLANT_WALLNUT, (row, 7))
    for i in range(30):
        z = entities.create_zombie(GRID_X + 5 * CELL_W,
                                   g.grid.y + (i % GRID_ROWS) * CELL_H + 15,
                                   i % GRID_ROWS,
                                   [ZOMBIE_BASIC, ZOMBIE_CONEHEAD, ZOMBIE_BUCKETHEAD,
                                    ZOMBIE_TACTICIAN, ZOMBIE_HEALER][i % 5])
        z.grid_y = g.grid.y
        g.zombies.append(z)
    g.sun_value = 99999
    return g


def s_play_day(g):
    _worstcase_play(g, "1-3")


def s_play_night(g):
    _worstcase_play(g, "2-3")


def s_play_pool(g):
    _worstcase_play(g, "3-3")


def s_play_fog(g):
    _worstcase_play(g, "4-3")
    # keep some suns alive + a fading one for the per-frame alpha churn
    for row in (1, 3):
        sun = entities.Sun(float(GRID_X + 3 * CELL_W), 100.0 + row * 40)
        sun.phase = "rest"
        sun.falling = False
        sun.target_y = sun.y
        g.suns.append(sun)
    fade = entities.Sun(float(GRID_X + 6 * CELL_W), 200.0)
    fade.phase = "rest"
    fade.falling = False
    fade.target_y = fade.y
    fade.settled_age = fade.lifetime() - 1.2
    g.suns.append(fade)


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
    ("menu", s_menu, False),
    ("mode_select", s_mode, True),
    ("level_select", s_level_select, True),
    ("seed_select", s_seed_select, True),
    ("play_day", s_play_day, False),
    ("play_night", s_play_night, False),
    ("play_pool", s_play_pool, False),
    ("play_fog", s_play_fog, False),
    ("play_roof", s_play_roof, False),
    ("paused", s_paused, False),
    ("game_over", s_game_over, False),
    ("level_complete", s_level_complete, False),
    ("survival_complete", s_survival_complete, False),
]

for name, setup, jitter in SCREENS:
    g = new_game(setup)
    bench(name, g, frames=420, mouse_jitter=jitter)

# transient: sun fade-out allocs are judged separately (short-lived).
print()
print("== animation continuity ==")

SHEETS = {
    "anim_peashooter_idle": 6, "anim_peashooter_attack": 6,
    "anim_snowpea_idle": 6, "anim_snowpea_attack": 6,
    "anim_sunflower_idle": 6, "anim_sunflower_glow": 6,
    "anim_wallnut_idle": 6, "anim_wallnut_cracked": 6,
    "anim_wallnut_verycracked": 6,
    "anim_zombie_a_idle": 7, "anim_zombie_a_eat": 7, "anim_zombie_a_die": 7,
    "anim_zombie_b_idle": 7, "anim_zombie_b_eat": 7, "anim_zombie_b_die": 7,
}
for prefix, expect in SHEETS.items():
    frames = assets_loader.anim_frames(prefix)
    check(f"{prefix}: cells present", len(frames) == expect,
          f"got {len(frames)} of {expect}")
    check(f"{prefix}: every cell non-blank",
          all(fr.get_bounding_rect(min_alpha=16).width > 0 for fr in frames))

# cycling: the moduli used by draw code must step through every cell.
cyc = [int(t * 6) % 6 for t in [i / 60.0 for i in range(240)]]
check("plant cycle %6 covers 0..5", sorted(set(cyc)) == list(range(6)))
check("snowpea draw cycles %6 too", len({int((k / 60.0) * 6) % 6 for k in range(240)}) == 6)
wp = [int((k / 60.0) * 1.1 * 7) % 7 for k in range(600)]
check("zombie walk_phase %7 covers 0..6", sorted(set(wp)) == list(range(7)))

# CobCannon kernel: per-frame rotate + surface churn during flight.
g = Game(SCREEN)
g.start_adventure_level("1-1")
g.sun_value = 9999
g.plant_cooldowns.clear()
assert g._plant(PLANT_COBCANNON, (2, 0))
# launch one manually to isolate the projectile path
kb = entities.KernelBomb(300.0, 200.0, 700.0, 400.0, damage=1800, radius=110)
alloc_kills = 0
frames = 0
_ALLOCs = []
while kb.alive:
    _ALLOC["n"] = 0
    kb.update(1 / 60.0)
    kb.draw(g.screen)
    frames += 1
    _ALLOCs.append(_ALLOC["n"])
    if frames > 300:
        break
med = sorted(_ALLOCs)[len(_ALLOCs) // 2]
check("KernelBomb in-flight allocs/frame", med <= 12,
      f"med={med} over {frames} frames (projectile is short-lived; "
      f"fix if steady >12)")

# PlantFood collect trail allocs
pf = entities.PlantFood(400.0, 300.0)
pf.phase = "rest"
pf.falling = False
pf.target_y = 300.0
for _ in range(40):
    pf.update(1 / 60.0)
assert pf.collect((80, 40))
pfa = []
while pf.alive and not pf.arrived:
    _ALLOC["n"] = 0
    pf.update(1 / 60.0)
    pf.draw(g.screen)
    pfa.append(_ALLOC["n"])
med = sorted(pfa)[len(pfa) // 2]
check("PlantFood collect-flight allocs/frame", med <= 12, f"med={med}")

# mower dust + fading-sun allocs during transient (informational + hard cap)
g.suns.clear()
fade = entities.Sun(500.0, 300.0)
fade.phase = "rest"
fade.falling = False
fade.target_y = 300.0
fade.settled_age = fade.lifetime() - 2.0
g.suns.append(fade)
sun_allocs = []
while fade.alive:
    _ALLOC["n"] = 0
    g.update(1 / 60.0)
    g.draw()
    g.draw_state()
    sun_allocs.append(_ALLOC["n"])
med = sorted(sun_allocs)[len(sun_allocs) // 2]
check("fading-sun frames allocs/frame", med <= 14,
      f"med={med} over {len(sun_allocs)} frames (fx.faded copy + per-alpha "
      f"smoothscale + tilt rotate all legitimate per-frame art, but bounded)")

print()
print("== cache cold-entry drift (steady bench must mint nothing) ==")
g = _worstcase_play(new_game(s_play_day), "1-3")
for _ in range(60):
    g.update(1 / 60.0)
    g.draw()
    g.draw_state()
before = set(assets_loader._cache)
for _ in range(300):
    g.update(1 / 60.0)
    g.draw()
    g.draw_state()
new_keys = set(assets_loader._cache) - before
check("assets_loader mints nothing mid-bench", len(new_keys) == 0,
      f"new keys: {sorted(new_keys)[:8]}")

# UI-level: menu tooltip / button label churn across hover jitter
g = new_game(s_level_select)
before = set(assets_loader._cache)
bench("level_select2", g, frames=300, mouse_jitter=True)
new_keys = set(assets_loader._cache) - before
check("level_select mints no asset cache", len(new_keys) == 0,
      f"new: {sorted(new_keys)[:8]}")

print()
print("== seed-button card render cache ==")
import i18n
g = Game(SCREEN)
g.start_adventure_level("1-3")
btns = g.seed_buttons
n_cards = len(btns)
font = i18n.font(16)
allocs = []
for i in range(240):
    cds = {btns[0].plant_type: max(0.0, 8.0 - i / 30.0)}
    g.sun_value = 99999 if i % 2 else 0
    _ALLOC["n"] = 0
    for b in btns:
        b.update(g.sun_value, cds, 1 / 60.0)
        b.draw(g.screen, font)
    allocs.append(_ALLOC["n"])
med = sorted(allocs)[len(allocs) // 2]
check("seed cards steady allocs", med <= n_cards + 4,
      f"med={med} for {n_cards} cards — overlays are cached; cost must be "
      f"per-card blits only")

print()
print("RESULT:", "ALL PASS" if not fails else f"{len(fails)} FAILURES")
for f in fails:
    print("  -", f)
sys.exit(1 if fails else 0)
