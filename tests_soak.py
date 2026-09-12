"""Soak test: run every game mode headless for thousands of frames with
realistic simulated play (sun collection, planting, pause, fast-forward),
and report exceptions, stuck states, or unbounded growth.

Not part of the shipped game. Run:
    SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy ./venv/bin/python tests_soak.py
"""
import os
import sys
import traceback

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
pygame.init()
SCREEN = pygame.display.set_mode((1400, 600))

# Isolate persistence: victory/defeat flows call save.save(), which would
# otherwise rewrite the player's real save.json with test progress.
import save as save_mod
save_mod.SAVE_PATH = os.path.join(
    os.environ.get("TMPDIR", "/tmp"), "pvsz_soak_save.json")

import assets_loader
assets_loader.init()

from constants import *
from game import Game
import entities

FAILURES = []
JAR = (SUN_JAR_X + SUN_JAR_W // 2, SUN_JAR_Y + SUN_JAR_W // 2)


def check(name, cond, detail=""):
    status = "PASS" if cond else "FAIL"
    print(f"  [{status}] {name}" + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        FAILURES.append(f"{name}: {detail}")


def occupied(g, cell):
    row, col = cell
    cx, cy = g.grid.get_cell_center(row, col)
    return any(p.alive and p.row == row and abs(p.x - cx) < CELL_W * 0.6
               for p in g.plants)


def auto_player(g, i, roster):
    """Collect every sun; plant affordable cards on a spreading pattern."""
    for s in list(g.suns):
        if s.alive and not s.collected:
            s.collect(JAR)
    g.sun_value = max(g.sun_value, 75)
    if i % 40 == 0 and roster:
        pt = roster[(i // 40) % len(roster)]
        n = i // 40
        row, col = n % GRID_ROWS, (n // GRID_ROWS) % GRID_COLS
        if not occupied(g, (row, col)):
            try:
                g._plant(pt, (row, col))
            except Exception:
                traceback.print_exc()
                raise


def run(g, frames, dt=1 / 60.0, events=None):
    for i in range(frames):
        if events:
            events(g, i)
        g.update(dt)
        g.draw()


def roster_of(g):
    return [b.plant_type for b in g.seed_buttons]


def soak_level(lid, label, minutes=4):
    print(f"--- {label} ({lid}), {minutes} sim minutes ---")
    g = Game(SCREEN)
    g.start_adventure_level(lid)
    roster = roster_of(g)
    try:
        run(g, 60 * 60 * minutes, events=lambda gg, i: auto_player(gg, i, roster))
        check(f"{label}: no crash", True)
    except Exception as e:
        traceback.print_exc()
        check(f"{label}: no crash", False, repr(e))
        return g
    check(f"{label}: suns bounded", len(g.suns) <= 61, f"len={len(g.suns)}")
    check(f"{label}: zombies bounded", len(g.zombies) < 200, f"len={len(g.zombies)}")
    check(f"{label}: projectiles bounded", len(g.projectiles) < 400,
          f"len={len(g.projectiles)}")
    ft = getattr(g, "floating_texts", [])
    check(f"{label}: floating texts bounded", len(ft) < 200, f"len={len(ft)}")
    return g


def soak_survival(sid, label, minutes=3):
    print(f"--- survival {label} ({sid}), {minutes} sim minutes ---")
    g = Game(SCREEN)
    g.start_survival(sid)
    roster = roster_of(g)
    try:
        run(g, 60 * 60 * minutes, events=lambda gg, i: auto_player(gg, i, roster))
        check(f"survival {label}: no crash", True)
        check(f"survival {label}: waves advance", g.wave.wave_index >= 2,
              f"wave={g.wave.wave_index}")
    except Exception as e:
        traceback.print_exc()
        check(f"survival {label}: no crash", False, repr(e))


def soak_pause_ffwd():
    print("--- pause / fast-forward / restart ---")
    g = Game(SCREEN)
    g.start_adventure_level("2-1")
    run(g, 600)
    try:
        g.state = STATE_PAUSED
        snap = [round(z.x, 3) for z in g.zombies]
        run(g, 120)
        snap2 = [round(z.x, 3) for z in g.zombies]
        check("pause freezes world", snap == snap2)
        g.state = STATE_PLAYING
        g.speed_mult = 2.0
        run(g, 600)
        g.speed_mult = 1.0
        check("fast-forward ok", g.state == STATE_PLAYING, g.state)
        # restart mid-game
        g.start_adventure_level("2-1")
        run(g, 300)
        check("restart mid-game ok", len(g.zombies) >= 0 and g.state == STATE_PLAYING)
    except Exception as e:
        traceback.print_exc()
        check("pause/ffwd/restart", False, repr(e))


def soak_defeat():
    print("--- defeat flow (lawnmowers then house) ---")
    g = Game(SCREEN)
    g.start_adventure_level("1-1")
    try:
        # dig all mowers by letting zombies through: spawn a rush on row 0
        for k in range(3):
            z = entities.create_zombie(GRID_X + GRID_W - 30,
                                       g.grid.y + 0 * CELL_H + 15, 0,
                                       ZOMBIE_BUCKETHEAD)
            z.grid_y = g.grid.y
            g.zombies.append(z)
        for _ in range(60 * 60 * 3):
            if g.state != STATE_PLAYING:
                break
            g.update(1 / 60.0)
            g.draw()
        check("defeat reached", g.state == STATE_GAME_OVER,
              f"state={g.state}")
        # click through: Enter confirms on defeat screen
        g.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN))
        check("defeat screen exits without crash", True)
    except Exception as e:
        traceback.print_exc()
        check("defeat flow", False, repr(e))


def soak_victory():
    print("--- victory flow (clear 1-1 with no plants) ---")
    g = Game(SCREEN)
    g.start_adventure_level("1-1")
    try:
        # simulate the player killing every zombie as it spawns
        for _ in range(60 * 60 * 6):
            if g.state != STATE_PLAYING:
                break
            for z in list(g.zombies):
                if z.alive and z.hp > 0:
                    z.take_damage(999999)
            g.update(1 / 60.0)
            g.draw()
        check("victory reached", g.state == STATE_LEVEL_COMPLETE,
              f"state={g.state}")
        g.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN))
        check("victory screen exits without crash", True)
    except Exception as e:
        traceback.print_exc()
        check("victory flow", False, repr(e))


def soak_upgrade_and_fx():
    print("--- upgrade replant + heavy FX churn ---")
    g = Game(SCREEN)
    g.start_adventure_level("1-1")
    try:
        g.sun_value = 99999
        for lvl in range(3):
            g._plant(PLANT_PEASHOOTER, (2, 2))
            g.plant_cooldowns.clear()
        plants = [p for p in g.plants if p.alive and p.row == 2]
        check("upgrade to Lv3", any(getattr(p, "level", 1) >= 3 for p in plants),
              f"levels={[getattr(p, 'level', 1) for p in plants]}")
        # cherry bomb + ice churn
        for i in range(600):
            g.sun_value = 99999
            g.plant_cooldowns.clear()
            if i % 60 == 0:
                g._plant(PLANT_CHERRYBOMB, (i % GRID_ROWS, 4))
            g.update(1 / 60.0)
            g.draw()
        check("cherry churn ok", True)
    except Exception as e:
        traceback.print_exc()
        check("upgrade/FX churn", False, repr(e))


def main():
    soak_level("1-3", "day")
    soak_level("2-3", "night")
    soak_level("3-3", "pool")
    soak_level("4-3", "fog")
    soak_level("5-3", "roof")
    soak_level("5-4", "boss")
    soak_survival("surv_day", "Day")
    soak_survival("surv_pool", "Pool")
    soak_pause_ffwd()
    soak_defeat()
    soak_victory()
    soak_upgrade_and_fx()
    print("=" * 60)
    if FAILURES:
        print(f"SOAK FAILURES ({len(FAILURES)}):")
        for f in FAILURES:
            print("  -", f)
        sys.exit(1)
    print("ALL SOAK CHECKS PASSED")


if __name__ == "__main__":
    main()
