"""Headless regression tests for the PvZ Python project.

Run from the project root:
    SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy ./venv/bin/python tests_smoke.py
"""
import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
import pygame
pygame.init()
SCREEN = pygame.display.set_mode((1400, 600))
import assets_loader
assets_loader.init()
from constants import *
from game import Game
from levels import ADVENTURE_LEVELS, SURVIVAL_MODES, POOL_WATER_ROWS
from main import _viewport, _to_logical
from ui import LevelSelectScreen, SeedSelectScreen

# Redirect the save file into TMPDIR so the adventure-completion test below
# never pollutes the real save.json shipped with the project.
import save as save_mod
save_mod.SAVE_PATH = os.path.join(os.environ.get("TMPDIR", "/tmp"), "pvsz_smoke_save.json")


def test_viewports():
    for size in ((640, 360), (800, 600), (1024, 768), (1400, 600),
                 (1920, 1080), (2560, 1440), (700, 1200)):
        view = _viewport(size)
        assert pygame.Rect((0, 0), size).contains(view)
        x, y = _to_logical(view.center, view)
        assert abs(x - 700) <= 1 and abs(y - 300) <= 1


def test_ui_bounds():
    bounds = pygame.Rect(0, 0, SCREEN_WIDTH, SCREEN_HEIGHT)
    ls = LevelSelectScreen()
    ls.set_items(ADVENTURE_LEVELS, "Adventure", {"1-1"})
    rects = [pygame.Rect(c.x, c.y, c.w, c.h) for c in ls.cards]
    assert all(bounds.contains(r) for r in rects)
    assert all(not a.colliderect(b) for i, a in enumerate(rects) for b in rects[i + 1:])
    ss = SeedSelectScreen()
    ss.set_level(next(x for x in ADVENTURE_LEVELS if x["id"] == "3-2"))
    rects = list(ss._card_rects().values())
    assert all(bounds.contains(r) for r in rects)


def build_defense(g):
    g.sun_value = 99999
    if g.bg_type == BG_POOL:
        for row in POOL_WATER_ROWS:
            for col in range(GRID_COLS):
                g._plant(PLANT_LILYPAD, (row, col)); g.plant_cooldowns.clear()
    for row in range(GRID_ROWS):
        for col, plant in ((1, PLANT_PEASHOOTER), (2, PLANT_PEASHOOTER),
                           (3, PLANT_PEASHOOTER), (7, PLANT_WALLNUT)):
            g._plant(plant, (row, col)); g.plant_cooldowns.clear()


def test_adventure():
    import random
    for level in ADVENTURE_LEVELS:
        random.seed(123)
        g = Game(SCREEN); g.start_adventure_level(level["id"]); build_defense(g)
        for _ in range(60000):
            g.update(.016)
            if g.state in (STATE_LEVEL_COMPLETE, STATE_GAME_OVER):
                break
        assert g.state == STATE_LEVEL_COMPLETE, (level["id"], g.state)


def test_survival_reset_and_space():
    g = Game(SCREEN)
    for _ in range(3):
        g.start_survival("surv_day")
        assert g.wave.wave_index == 1 and g.wave.wave_count == 50
    g.wave.wave_index = 1; g.wave.wave_count = 3
    g.wave.waves = [(1, [ZOMBIE_BASIC], 0)] * 3
    g.wave.wave_active = False; g.wave.between_waves = True; g.wave.wave_cleared = True
    g.handle_event(pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_SPACE}))
    assert g.wave.wave_index == 2 and g.wave.wave_active
    for mode in SURVIVAL_MODES:
        g.start_survival(mode["id"])
        expected = 6 if mode["bg"] == BG_POOL else 5
        assert len(g.seed_buttons) == expected


def test_mouse_seed_guard_and_preview():
    g = Game(SCREEN); g.start_adventure_level("1-1"); btn = g.seed_buttons[0]
    g.sun_value = 0; g._select_seed_button(btn); assert not btn.selected
    g.sun_value = 999; g.plant_cooldowns[btn.plant_type] = 3
    g._select_seed_button(btn); assert not btn.selected
    g.plant_cooldowns.clear(); g._select_seed_button(btn); assert btn.selected
    g.handle_event(pygame.event.Event(pygame.MOUSEMOTION, {"pos": g.grid.get_cell_center(2, 2), "rel": (0,0), "buttons": (0,0,0)}))
    assert g.grid.hover_cell == (2, 2)
    g.draw()  # placement preview path

    # Cob Cannon follows a deliberate arm-then-target interaction and must not
    # crash or steal a click intended for a selected seed card.
    g.sun_value = 9999
    g.plant_cooldowns.clear()
    assert g._plant(PLANT_COBCANNON, (0, 0))
    cob = g._first_cob_cannon()
    btn.selected = True
    target = g.grid.get_cell_center(1, 1)
    g.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN,
                                      {"pos": target, "button": 1}))
    assert g._cell_plant(1, target[0]).plant_type == PLANT_PEASHOOTER
    btn.selected = False
    g.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN,
                                      {"pos": (cob.x + 20, cob.y + 20), "button": 1}))
    g.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN,
                                      {"pos": target, "button": 1}))
    assert len(g.projectiles) == 1 and not g._cob_armed


def test_zombie_animation_frames():
    # The shipped zombie strips contain seven cells (the old six-cell slice
    # made the walking sprite jump/disappear between frames).
    for prefix in ("anim_zombie_a_idle", "anim_zombie_b_idle"):
        frames = assets_loader.anim_frames(prefix)
        assert len(frames) == 7
        assert all(frame.get_bounding_rect(min_alpha=16).width > 0 for frame in frames)


def test_sun_lifecycle():
    # Full 阳光 life cycle in one compact assertion block (see
    # dev_verify_sun.py for the expanded behavioral audit).
    from entities import Sun
    s = Sun(400, -40); s.drop_from_sky(400.0)
    assert s.phase == "fall" and s.falling
    while s.phase == "fall":
        s.update(1/60)
    assert s.phase == "bounce" and not s.falling  # grabbable mid-bounce
    while s.phase == "bounce":
        s.update(1/60)
    assert s.phase == "rest"
    assert s.squash > 0.0           # final impact squashes too (settle thud)
    for _ in range(20):
        s.update(1/60)              # ~0.33s later the squash has decayed away
    assert s.squash == 0.0
    # hover freeze: motion suspends while the game reports the sun hovered,
    # spin keeps turning; resumes the moment hover leaves (阳光停在光标下).
    # Track the *visual* center — the resting bob is draw-only, so physics y
    # would sit still even without the freeze.
    v0 = s._visual_center()
    for _ in range(30):
        s.update(1/60, hovered=True)
    assert s._visual_center() == v0 and s.angle > 0
    s.update(1/60, hovered=False)
    assert s._visual_center() != v0
    # circular hit test matches the drawn bob position, not raw physics
    cx, cy = s._visual_center()
    assert s.contains(cx, cy)
    d = SUN_COLLECT_RADIUS
    assert not s.contains(cx + d - 1, cy + d - 1)   # square corner excluded
    # collect: credits only on arrival, flight unaffected by hover
    s.collect((70, 40))
    px = s.x
    for _ in range(5):
        s.update(1/60, hovered=True)
    assert s.x != px and not s.arrived  # hover does not stall the flight
    while s.alive and not s.arrived:
        s.update(1/60)
    assert s.arrived
    # expiry: blink phase near end of life, restores alpha when collected
    e = Sun(500, 300); e.phase = "rest"; e.falling = False
    e.settled_age = e.lifetime() - Sun.EXPIRE_WARN_S + 0.05
    for _ in range(12):
        e.update(1/60)              # blink can sample high right at entry
    assert e.phase == "fading" and e.alpha < 255
    e.collect((70, 40))
    assert e.alpha == 255


def main():
    test_viewports(); test_ui_bounds(); test_survival_reset_and_space()
    test_mouse_seed_guard_and_preview(); test_zombie_animation_frames()
    test_sun_lifecycle(); test_adventure()
    print("ALL SMOKE TESTS PASSED")


if __name__ == "__main__":
    main()
