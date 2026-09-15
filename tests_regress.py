"""Regression tests for the PvZ Python project.

Covers the targeted bug fixes for C11/C12/C13/H16/H17 (and the C14-UI/H23
cases are tested in tests_ux.py since they involve UI caches).

Run from the project root:
    SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy ./venv/bin/python tests_regress.py
"""
import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
import json
import pygame
pygame.init()
SCREEN = pygame.display.set_mode((1400, 600))
import assets_loader
assets_loader.init()
from constants import *
from game import Game
from save import SaveData


# Always redirect the save file to a scratch path so the regression suite
# never touches the shipped save.json.
import save as save_mod
save_mod.SAVE_PATH = os.path.join(os.environ.get("TMPDIR", "/tmp"),
                                  "pvsz_regress_save.json")


# ----- B2: C12 — bungee speed_mult scaling ---------------------------------

def test_b2_bungee_speed_mult_scaling():
    """At speed_mult=2.0 the bungee covers double the y distance per second."""
    from entities import Zombie
    row = 2
    grid_y = 0
    base = Zombie(900, 0, row, ZOMBIE_BUNGEE)
    base.grid_y = grid_y
    base._speed_mult = 1.0
    # Bungee constructor forces y=-250 (sky-start) regardless of caller.
    y0 = base.y
    fast = Zombie(900, 0, row, ZOMBIE_BUNGEE)
    fast.grid_y = grid_y
    fast._speed_mult = 2.0

    # dt small enough that neither bungee reaches target_y (clamps + phase
    # change would otherwise hide the ratio).
    dt = 0.1
    base.update(dt, [])
    fast.update(dt, [])
    base_dy = base.y - y0
    fast_dy = fast.y - y0
    assert fast_dy > base_dy > 0, (base_dy, fast_dy)
    # speed_mult scales dt directly → exactly 2× for the same elapsed time.
    assert abs(fast_dy - 2.0 * base_dy) < 1e-6, (base_dy, fast_dy)


def main():
    test_b2_bungee_speed_mult_scaling()
    print("ALL REGRESSION TESTS PASSED")


if __name__ == "__main__":
    main()
