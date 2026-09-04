"""Headless verification of the UX overhaul: drives synthetic events through
Game, screenshots key states, and asserts new interactions work.

    SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy ./venv/bin/python tests_ux.py
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
import i18n

SHOT_DIR = os.path.join(os.path.dirname(__file__), "screenshots", "ux_audit")
os.makedirs(SHOT_DIR, exist_ok=True)


def shot(g, name):
    g.draw()
    g.draw_state()
    pygame.image.save(g.screen, os.path.join(SHOT_DIR, name))


def click(g, x, y):
    g.handle_event(pygame.event.Event(pygame.MOUSEMOTION, {"pos": (x, y), "rel": (0, 0), "buttons": (0, 0, 0)}))
    g.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, {"pos": (x, y), "button": 1}))
    g.handle_event(pygame.event.Event(pygame.MOUSEBUTTONUP, {"pos": (x, y), "button": 1}))


def drag(g, x0, y0, x1, y1):
    g.handle_event(pygame.event.Event(pygame.MOUSEMOTION, {"pos": (x0, y0), "rel": (0, 0), "buttons": (0, 0, 0)}))
    g.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, {"pos": (x0, y0), "button": 1}))
    g.handle_event(pygame.event.Event(pygame.MOUSEMOTION, {"pos": ((x0+x1)//2, (y0+y1)//2), "rel": (10, 10), "buttons": (1, 0, 0)}))
    g.handle_event(pygame.event.Event(pygame.MOUSEMOTION, {"pos": (x1, y1), "rel": (10, 10), "buttons": (1, 0, 0)}))
    g.handle_event(pygame.event.Event(pygame.MOUSEBUTTONUP, {"pos": (x1, y1), "button": 1}))


def test_adventure_flow():
    g = Game(SCREEN)
    i18n.set_lang("zh")
    shot(g, "01_menu.png")

    # start a level
    g.start_adventure_level("1-1")
    assert g.state == STATE_PLAYING
    assert g.speed_mult == 1.0

    # select first card by click, then cancel with right click
    btn = g.seed_buttons[0]
    click(g, btn.x + btn.w // 2, btn.y + btn.h // 2)
    assert btn.selected, "card click should select"
    g.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, {"pos": (700, 300), "button": 3}))
    assert not btn.selected, "right click should cancel selection"

    # drag-plant a peashooter
    g.sun_value = 1000
    btn = g.seed_buttons[0]
    cx, cy = g.grid.get_cell_center(1, 1)
    drag(g, btn.x + btn.w // 2, btn.y + btn.h // 2, cx, cy)
    assert g._cell_plant(1, cx) is not None, "drag should plant a peashooter"
    assert not btn.selected, "selection cleared after planting"

    # hover tooltip on a card
    g.handle_event(pygame.event.Event(pygame.MOUSEMOTION,
                                      {"pos": (g.seed_buttons[1].x + 10, 40), "rel": (0, 0), "buttons": (0, 0, 0)}))
    g.update(0.016)
    assert g.tooltip.visible and "50" in g.tooltip.text, "card tooltip should show cost"

    # simulate and screenshot a live fight
    g.sun_value = 2000
    for col in (2, 3, 4):
        g.plant_cooldowns.clear()
        g._plant(PLANT_PEASHOOTER, (2, col))
    g.wave.start_wave()
    g.wave.spawn_timer = 99  # force immediate spawns
    for _ in range(240):
        g.update(0.016)
        if g.zombies:
            break
    # force some zombies into view for the screenshot
    from entities import create_zombie
    for i, (row, ztype) in enumerate(((1, ZOMBIE_BASIC), (2, ZOMBIE_CONEHEAD),
                                      (3, ZOMBIE_BUCKETHEAD))):
        z = create_zombie(900 + i * 130, g.grid.y + row * CELL_H + 15, row, ztype)
        z.grid_y = g.grid.y
        g.zombies.append(z)
    for _ in range(40):
        g.update(0.016)
    shot(g, "02_playing.png")

    # fast-forward toggle
    g.handle_event(pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_f}))
    assert g.speed_mult == 2.0
    g.handle_event(pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_f}))
    assert g.speed_mult == 1.0

    # sun collection flight: click a sun, wait for jar credit
    from entities import Sun
    sun = Sun(700, 300)
    g.suns.append(sun)
    before = g.sun_value
    click(g, 700, 300)
    assert sun.collected, "sun should be flying to the jar"
    for _ in range(60):
        g.update(0.016)
    assert g.sun_value == before + SUN_VALUE, "sun credit lands after flight"
    assert not g.suns

    # pause screen buttons
    click(g, g.btn_pause.centerx, g.btn_pause.centery)
    assert g.state == STATE_PAUSED
    shot(g, "03_paused.png")
    click(g, g.pause_screen.btn_resume.centerx, g.pause_screen.btn_resume.centery)
    assert g.state == STATE_PLAYING

    # a card drag interrupted by pausing must not fire a phantom plant on resume
    g.sun_value = 1000
    btn = g.seed_buttons[0]
    g.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN,
                                      {"pos": (btn.x + btn.w // 2, btn.y + btn.h // 2), "button": 1}))
    g.handle_event(pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_p}))
    assert g.state == STATE_PAUSED and g._press is None, "pause clears a pending drag"
    g.handle_event(pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_p}))
    assert g.state == STATE_PLAYING
    n_plants = len(g.plants)
    g.handle_event(pygame.event.Event(pygame.MOUSEBUTTONUP,
                                      {"pos": g.grid.get_cell_center(0, 0), "button": 1}))
    assert len(g.plants) == n_plants, "no phantom plant after resume"

    # explosion fx path
    from fx import Explosion
    g.explosions.append(Explosion(800, 300))
    g.add_shake(9)
    g.flash_timer = 0.12
    for _ in range(6):
        g.update(0.016)
    shot(g, "04_explosion.png")


def test_other_envs():
    g = Game(SCREEN)
    g.start_adventure_level("3-3")  # pool
    for _ in range(30):
        g.update(0.016)
    shot(g, "05_pool.png")

    g2 = Game(SCREEN)
    g2.start_adventure_level("5-4")  # roof + boss
    for _ in range(30):
        g2.update(0.016)
    shot(g2, "06_roof_boss.png")

    g3 = Game(SCREEN)
    g3.start_adventure_level("4-3")  # fog
    for _ in range(30):
        g3.update(0.016)
    shot(g3, "07_fog.png")


def test_end_screens():
    g = Game(SCREEN)
    g.start_adventure_level("1-1")
    g.state = STATE_GAME_OVER
    g.wave.wave_index = 3
    shot(g, "08_gameover.png")
    # retry button restarts the same level
    click(g, g.game_over.btn_retry.centerx, g.game_over.btn_retry.centery)
    assert g.state == STATE_PLAYING and g.level_id == "1-1"

    g.state = STATE_LEVEL_COMPLETE
    shot(g, "09_victory.png")
    click(g, g.level_complete.btn_next.centerx, g.level_complete.btn_next.centery)
    assert g.state == STATE_SEED_SELECT and g.pending_level["id"] == "1-2"


def test_new_content():
    # --- balloon zombie: 155 pops the balloon, then it walks ---
    from entities import create_zombie
    g = Game(SCREEN)
    g.start_adventure_level("1-1")
    z = create_zombie(900, g.grid.y + 1 * CELL_H + 15, 1, ZOMBIE_BALLOON)
    z.grid_y = g.grid.y
    g.zombies.append(z)
    assert z.floating and z.balloon_hp == BALLOON_HP
    z.take_damage(155)
    assert not z.floating and z.balloon_hp == 0, "155 dmg pops the balloon"
    assert z.hp == ZOMBIE_INFO[ZOMBIE_BALLOON]["hp"] - 155, "overflow carries"
    g.zombies.clear()

    # balloon floats over plants and never eats them
    cx, cy = g.grid.get_cell_center(1, 3)
    g._plant(PLANT_WALLNUT, (1, 3)); g.plant_cooldowns.clear()
    zb = create_zombie(cx + 120, g.grid.y + 1 * CELL_H + 15, 1, ZOMBIE_BALLOON)
    zb.grid_y = g.grid.y
    g.zombies.append(zb)
    wallnut = g._cell_plant(1, cx)
    hp0 = wallnut.hp
    for _ in range(120):
        g.update(0.016)
    assert wallnut.hp == hp0, "floating balloon never eats plants"

    # --- bungee zombie: sky drop → steal → retreat ---
    g2 = Game(SCREEN)
    g2.start_adventure_level("4-3")
    col = 5
    tx = g2.grid.x + col * CELL_W + (CELL_W - 90) // 2
    row = 2
    g2._plant(PLANT_PEASHOOTER, (row, col)); g2.plant_cooldowns.clear()
    target = g2._cell_plant(row, g2.grid.get_cell_center(row, col)[0])
    zb2 = create_zombie(tx, -250, row, ZOMBIE_BUNGEE)
    zb2.grid_y = g2.grid.y
    g2.zombies.append(zb2)
    for _ in range(int(BUNGEE_DESCEND_S / 0.016) + 60):
        g2.update(0.016)
    assert zb2.stole_plant and not target.alive, "bungee steals the plant"
    assert zb2.bungee_phase in ("climb", "steal")
    g2.zombies.clear()

    # --- plant upgrade: replant same type → level 2, damage doubles ---
    g3 = Game(SCREEN)
    g3.start_adventure_level("1-1")
    g3.sun_value = 9999
    cell = (2, 4)
    g3._plant(PLANT_PEASHOOTER, cell); g3.plant_cooldowns.clear()
    p = g3._cell_plant(2, g3.grid.get_cell_center(2, 4)[0])
    assert p.level == 1 and p.damage == 20
    sun_before = g3.sun_value
    assert g3._plant(PLANT_PEASHOOTER, cell), "upgrade planting allowed"
    assert p.level == 2 and p.damage == 40, "Lv2 doubles damage"
    assert g3.sun_value == sun_before - 100
    g3.plant_cooldowns.clear()
    assert g3._plant(PLANT_PEASHOOTER, cell)
    assert p.level == 3 and p.damage == 60
    g3.plant_cooldowns.clear()
    assert not g3._plant(PLANT_PEASHOOTER, cell), "Lv3 is the cap"
    # sunflower upgrade produces 50-sun drops
    g3._plant(PLANT_SUNFLOWER, (0, 0)); g3.plant_cooldowns.clear()
    g3._plant(PLANT_SUNFLOWER, (0, 0)); g3.plant_cooldowns.clear()
    sf = g3._cell_plant(0, g3.grid.get_cell_center(0, 0)[0])
    assert sf.level == 2 and sf.sun_amount == 50
    g3.plant_cooldowns.clear()
    g3.plants = [q for q in g3.plants if q.plant_type != PLANT_SUNFLOWER]

    # --- plant food: drop → collect → feed peashooter boost ---
    from entities import PlantFood
    g3.plant_food = 0
    pf = PlantFood(700, 300); pf.falling = False
    g3.plant_foods.append(pf)
    click(g3, 700, 300)
    assert g3.plant_food == 1 and not g3.plant_foods
    peashooter = g3._cell_plant(2, g3.grid.get_cell_center(2, 4)[0])
    click(g3, int(peashooter.x + peashooter.w // 2), int(peashooter.y + 30))
    assert g3.plant_food == 0 and peashooter.food_boost > 0, "feeding boosts fire rate"
    g3.plants = []

    # --- survival scaling: wave 30 zombies are faster & bite harder ---
    g4 = Game(SCREEN)
    g4.start_survival("surv_day")
    assert g4.wave.scaling
    sp1, dm1 = g4.wave.scaling_for_wave(1)
    sp30, dm30 = g4.wave.scaling_for_wave(30)
    assert sp1 == 1.0 and dm1 == 1.0
    assert sp30 > 1.5 and dm30 > 2.0, "endless waves scale speed & attack"
    zb3 = create_zombie(0, 0, 0, ZOMBIE_BASIC, sp30, dm30)
    assert zb3.speed > zb3.base_speed and zb3.eat_damage > 30

    # --- screenshot with the new zombies on the lawn ---
    g5 = Game(SCREEN)
    g5.start_adventure_level("4-3")
    g5.sun_value = 5000
    for col in (1, 2, 3):
        g5.plant_cooldowns.clear()
        g5._plant(PLANT_PEASHOOTER, (2, col))
    g5.plant_cooldowns.clear()
    g5._plant(PLANT_PEASHOOTER, (2, 1))  # upgrade → level 2 pips
    g5.plant_foods.append(PlantFood(700, 300))
    balloon = create_zombie(980, g5.grid.y + 1 * CELL_H + 15, 1, ZOMBIE_BALLOON)
    balloon.grid_y = g5.grid.y
    g5.zombies.append(balloon)
    bungee = create_zombie(g5.grid.x + 6 * CELL_W, -120, 3, ZOMBIE_BUNGEE)
    bungee.grid_y = g5.grid.y
    g5.zombies.append(bungee)
    g5.plant_food = 2
    for _ in range(20):
        g5.update(0.016)
    shot(g5, "10_new_content.png")


def main():
    test_adventure_flow()
    test_other_envs()
    test_end_screens()
    test_new_content()
    print("ALL UX CHECKS PASSED — screenshots in", SHOT_DIR)


if __name__ == "__main__":
    main()
