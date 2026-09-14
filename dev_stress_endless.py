"""Endless-mode saturation probe: how many zombies/projectiles fit on screen,
and does frame time stay inside the 60fps budget at that saturation?

Two measurements:
  A) real survival run at wave ~70 with a full defense — the steady state a
     dedicated player actually reaches.
  B) synthetic worst case — zombies crammed across the whole lawn and every
     shooter food-boosted (0.09s machine-gun cooldown) so the air saturates.

Reports p50/p95/p99/max update+draw per frame. Not part of the shipped game.
"""
import os, time, random

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
pygame.init()
SCREEN = pygame.display.set_mode((1400, 600))

import save as save_mod
save_mod.SAVE_PATH = os.path.join(os.environ.get("TMPDIR", "/tmp"), "pvsz_stress_save.json")

import assets_loader
assets_loader.init()

from constants import *
from game import Game
import entities

JAR = (SUN_JAR_X + SUN_JAR_W // 2, SUN_JAR_Y + SUN_JAR_W // 2)


def new_survival(waves_queued):
    random.seed(7)
    g = Game(SCREEN)
    g.start_survival("surv_day")
    while len(g.wave.waves) < waves_queued:
        g._generate_survival_waves()
    g.wave.wave_index = g.wave.wave_count - 3
    g.survival_waves = g.wave.wave_index
    return g


def occupied(g, row, col):
    cx, cy = g.grid.get_cell_center(row, col)
    return any(p.alive and p.row == row and abs(p.x - cx) < CELL_W * 0.6
               for p in g.plants)


def full_lawn(g, cols=range(GRID_COLS), plant=PLANT_PEASHOOTER):
    g.sun_value = 999999
    for row in range(GRID_ROWS):
        for col in cols:
            if not occupied(g, row, col):
                g._plant(plant, (row, col))
        g.plant_cooldowns.clear()
    g.sun_value = 999999


def spawn(g, ztype, row, x):
    z = entities.create_zombie(x, g.grid.y + row * CELL_H + 15, row, ztype,
                               getattr(g.wave, "current_speed_mult", 1.0),
                               getattr(g.wave, "current_dmg_mult", 1.0))
    z.grid_y = g.grid.y
    g.zombies.append(z)


def measure(g, frames, label, boost=False, jam=False, wall=False):
    mx_z = mx_p = 0
    up, dr = [], []
    for i in range(frames):
        if boost and i % 20 == 0:
            for p in g.plants:
                if hasattr(p, "food_boost"):
                    p.food_boost = 3.0  # keep every shooter in machine-gun mode
        if wall and i % 30 == 0 and len(g.zombies) < 120:
            # slow-moving (unboosted) wall of bucketheads at the right edge:
            # every boosted gun fires into it -> air fills with peas
            for row in range(GRID_ROWS):
                for k in range(4):
                    if len(g.zombies) >= 120:
                        break
                    x = SCREEN_WIDTH - 60 - k * 24 - (i * 5) % 20
                    spawn(g, ZOMBIE_BUCKETHEAD, row, x)
        if jam and i % 10 == 0 and len(g.zombies) < 250:
            # top zombies back up to saturation as the guns clear them
            types = [ZOMBIE_BASIC, ZOMBIE_CONEHEAD, ZOMBIE_BUCKETHEAD]
            for row in range(GRID_ROWS):
                for k in range(10):
                    if len(g.zombies) >= 250:
                        break
                    x = GRID_X + CELL_W + k * 40 + (i * 7) % 30
                    spawn(g, types[(i + row + k) % 3], row, x)
        for s in list(g.suns):
            if s.alive and not s.collected:
                s.collect(JAR)
        t0 = time.perf_counter(); g.update(1 / 60.0); t1 = time.perf_counter()
        g.draw(); t2 = time.perf_counter()
        up.append((t1 - t0) * 1000); dr.append((t2 - t1) * 1000)
        mx_z = max(mx_z, len(g.zombies)); mx_p = max(mx_p, len(g.projectiles))
    tot = sorted(u + d for u, d in zip(up, dr)); up.sort(); dr.sort()
    n = len(tot)
    print(f"[{label}] zombies<={mx_z}  projectiles<={mx_p}")
    print(f"[{label}] update p50 {up[n//2]:5.2f}  p95 {up[int(n*.95)]:5.2f}  p99 {up[int(n*.99)]:5.2f}  max {up[-1]:5.2f} ms")
    print(f"[{label}] draw   p50 {dr[n//2]:5.2f}  p95 {dr[int(n*.95)]:5.2f}  p99 {dr[int(n*.99)]:5.2f}  max {dr[-1]:5.2f} ms")
    print(f"[{label}] total  p50 {tot[n//2]:5.2f}  p95 {tot[int(n*.95)]:5.2f}  p99 {tot[int(n*.99)]:5.2f}  max {tot[-1]:5.2f} ms   (budget 16.67)\n")
    return tot[int(n * .95)]


print("=== A) real survival @ wave ~68, full pea lawn, endless waves ===")
g = new_survival(70)
g.wave.scaling = True
full_lawn(g)
g.wave.start_wave()
a95 = measure(g, 1500, "A steady")

print("=== B) synthetic saturation: ~250 zombies + machine-gun full lawn ===")
g2 = new_survival(70)
full_lawn(g2)
b95 = measure(g2, 900, "B max", boost=True, jam=True)

print("=== C) projectile saturation: boosted guns, zombie wall at right edge ===")
g3 = new_survival(70)
full_lawn(g3)
c95 = measure(g3, 900, "C bullets", boost=True, wall=True)

print(f"summary: steady p95={a95:.2f}ms  saturation p95={b95:.2f}ms  bullets p95={c95:.2f}ms  (budget 16.67ms)")
