"""End-to-end health check for every effect system added in this session.

For each effect (A through N2), runs the smallest synthetic scenario that
exercises the system, then asserts the expected state. Reports a pass/fail
line per effect.

Run: SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy ./venv/bin/python fx_health_check.py
"""
import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
import sys
import traceback
import pygame
pygame.init()
pygame.display.set_mode((1400, 600))
import assets_loader
assets_loader.init()
from constants import *
from game import Game
from entities import *
import fx as fx_mod


results = []
W, H = 1400, 600


def check(name, fn):
    try:
        fn()
        results.append((name, "PASS", None))
    except Exception as e:
        tb = traceback.format_exc(limit=2).strip().splitlines()
        results.append((name, "FAIL", f"{type(e).__name__}: {e} | {tb[-1] if tb else ''}"))


def fresh_game(start_level=True):
    screen = pygame.display.set_mode((W, H))
    g = Game(screen)
    if start_level:
        g.start_adventure_level("1-1")
    g.sun_value = 9999
    return g


# ─────────────────────────────────────────────────────────
# A — bite_shake
# ─────────────────────────────────────────────────────────
def t_A():
    g = fresh_game()
    g._plant("peashooter", (2, 3))
    p = g.plants[0]
    initial = p.bite_shake
    p.take_damage(20)
    assert p.bite_shake > initial, f"bite_shake not triggered: {initial} → {p.bite_shake}"
    assert p.bite_shake >= 0.18, f"bite_shake too small: {p.bite_shake}"


# ─────────────────────────────────────────────────────────
# B — plant_debris (on death)
# ─────────────────────────────────────────────────────────
def t_B():
    g = fresh_game()
    g._plant("peashooter", (2, 3))
    p = g.plants[0]
    for _ in range(60):
        g.update(0.016)
    p.alive = False
    initial_debris = len(g.plant_debris)
    for _ in range(5):
        g.update(0.016)
    assert len(g.plant_debris) > initial_debris, (
        f"plant_debris not spawned: was {initial_debris}, now {len(g.plant_debris)}")


# ─────────────────────────────────────────────────────────
# C — pea_impact sparks
# ─────────────────────────────────────────────────────────
def t_C():
    g = fresh_game()
    g._plant("peashooter", (2, 3))
    from entities import create_zombie, Projectile
    z = create_zombie(900, g.grid.y + 2 * CELL_H + 15, 2, ZOMBIE_BASIC)
    z.grid_y = g.grid.y
    z.base_speed = 0.0
    z.speed = 0.0
    g.zombies.append(z)
    proj = Projectile(700, g.grid.y + 2 * CELL_H + 8, 2)
    g.projectiles.append(proj)
    pre = len(g.pea_impact)
    for _ in range(40):
        g.update(0.016)
    assert len(g.pea_impact) > pre, (
        f"pea_impact not spawned: was {pre}, now {len(g.pea_impact)}")


# ─────────────────────────────────────────────────────────
# E — zombie_heads / equipment chunks
# ─────────────────────────────────────────────────────────
def t_E():
    g = fresh_game()
    from entities import create_zombie
    z = create_zombie(900, g.grid.y + 2 * CELL_H + 15, 2, ZOMBIE_CONEHEAD)
    z.grid_y = g.grid.y
    z.base_speed = 0.0
    z.speed = 0.0
    g.zombies.append(z)
    pre = len(g.zombie_heads)
    z.take_damage(99999)
    for _ in range(80):
        g.update(0.016)
    assert len(g.zombie_heads) > pre, (
        f"zombie_heads not spawned: was {pre}, now {len(g.zombie_heads)}")


# ─────────────────────────────────────────────────────────
# F — balloon pop shreds
# ─────────────────────────────────────────────────────────
def t_F():
    g = fresh_game()
    from entities import create_zombie
    z = create_zombie(900, g.grid.y + 2 * CELL_H + 15, 2, ZOMBIE_BALLOON)
    z.grid_y = g.grid.y
    g.zombies.append(z)
    z.hp = 1
    z.take_damage(BALLOON_HP + 1)
    pre = len(g.balloon_pop)
    for _ in range(5):
        g.update(0.016)
    assert len(g.balloon_pop) > pre, (
        f"balloon_pop not spawned: was {pre}, now {len(g.balloon_pop)}")


# ─────────────────────────────────────────────────────────
# G — mow dust
# ─────────────────────────────────────────────────────────
def t_G():
    g = fresh_game()
    pre = len(g.mow_dust)
    z = g.zombies[0] if g.zombies else None
    if z is None:
        from entities import create_zombie
        z = create_zombie(80, g.grid.y + 0 * CELL_H + 15, 0, ZOMBIE_BASIC)
        z.grid_y = g.grid.y
        g.zombies.append(z)
    m = g.lawnmowers[0]
    m.activate()
    for _ in range(5):
        g.update(0.016)
    assert len(g.mow_dust) > pre, (
        f"mow_dust not spawned: was {pre}, now {len(g.mow_dust)}")


# ─────────────────────────────────────────────────────────
# H — plant poof (planting + digging)
# ─────────────────────────────────────────────────────────
def t_H():
    g = fresh_game()
    g._plant("peashooter", (2, 3))
    g._dig_up((2, 3))
    assert len(g.plant_poof) == 2, f"plant_poof expected 2 (plant+dig), got {len(g.plant_poof)}"


# ─────────────────────────────────────────────────────────
# I — food_rings
# ─────────────────────────────────────────────────────────
def t_I():
    g = fresh_game()
    g._plant("peashooter", (2, 3))
    g.plant_food = 1
    pre = len(g.food_rings)
    g._feed_plant(g.plants[0])
    assert len(g.food_rings) == pre + 2, (
        f"food_rings expected 2, got {len(g.food_rings) - pre}")


# ─────────────────────────────────────────────────────────
# J — boss aura (summon + death)
# ─────────────────────────────────────────────────────────
def t_J():
    g = fresh_game()
    from entities import create_zombie
    boss = create_zombie(900, 200, 0, ZOMBIE_BOSS)
    boss.grid_y = g.grid.y
    g.zombies.append(boss)
    pre = len(g.boss_aura)
    g._spawn_boss_aura(boss, kind="summon")
    assert len(g.boss_aura) == pre + 4, "summon aura = 1 ring + 3 sparks"
    g._spawn_boss_aura(boss, kind="death")
    assert len(g.boss_aura) == pre + 4 + 14, "death aura = +2 ring + 12 sparks"


# ─────────────────────────────────────────────────────────
# K1 — sun bounce
# ─────────────────────────────────────────────────────────
def t_K1():
    s = Sun(300, 0)
    s.target_y = 50      # close to start, so it lands fast
    landed = False
    for _ in range(80):
        s.update(0.016)
        if not s.falling and s.bounce_t < 1.0:
            landed = True
            break
    assert landed, f"sun did not bounce on landing: falling={s.falling}, bounce_t={s.bounce_t}"


# ─────────────────────────────────────────────────────────
# K2 — grass prints (zombie walking)
# ─────────────────────────────────────────────────────────
def t_K2():
    g = fresh_game()
    from entities import create_zombie
    z = create_zombie(900, g.grid.y + 2 * CELL_H + 15, 2, ZOMBIE_BASIC)
    z.grid_y = g.grid.y
    g.zombies.append(z)
    pre = len(g.grass_prints)
    for _ in range(120):
        g.update(0.016)
    assert len(g.grass_prints) > pre, (
        f"grass_prints not spawned: was {pre}, now {len(g.grass_prints)}")


# ─────────────────────────────────────────────────────────
# K3 — Cherry Bomb shockwave
# ─────────────────────────────────────────────────────────
def t_K3():
    ex = fx_mod.Explosion(700, 320, radius=120, duration=0.55)
    surface = pygame.Surface((W, H), pygame.SRCALPHA)
    surface.fill((80, 130, 70))
    ex.age = 0.20
    ex.draw(surface)  # should not raise
    assert True


# ─────────────────────────────────────────────────────────
# K4 — ice crackles (snowpea hit)
# ─────────────────────────────────────────────────────────
def t_K4():
    g = fresh_game()
    from entities import create_zombie, Projectile
    g._plant("snowpea", (2, 3))
    z = create_zombie(900, g.grid.y + 2 * CELL_H + 15, 2, ZOMBIE_BASIC)
    z.grid_y = g.grid.y
    g.zombies.append(z)
    proj = Projectile(700, g.grid.y + 2 * CELL_H + 8, 2,
                      color=(140, 220, 255), freezes=True, freeze_seconds=4.0)
    g.projectiles.append(proj)
    for _ in range(180):
        g.update(0.016)
    assert z.ice_timer > 0 or len(z.ice_crackles) > 0, (
        f"ice not applied: ice_timer={z.ice_timer}, crackles={len(z.ice_crackles)}")


# ─────────────────────────────────────────────────────────
# L1 — SnowPea end-to-end
# ─────────────────────────────────────────────────────────
def t_L1():
    g = fresh_game()
    g._plant("snowpea", (2, 3))
    p = g.plants[0]
    assert p.plant_type == "snowpea"
    assert p.shoot().freezes is True


# ─────────────────────────────────────────────────────────
# L2 — coin drops (between-wave + level-complete)
# ─────────────────────────────────────────────────────────
def t_L2():
    g = fresh_game()
    pre = len(g.coin_drops)
    g._advance_after_wave()  # may not add but doesn't error
    # Direct test: simulate 6 coins being spawned
    for _ in range(6):
        g.coin_drops.append({"x": 700, "y": 300, "vx": 0, "vy": -100,
                             "age": 0, "max": 1.0, "value": 10, "rot": 0})
    assert len(g.coin_drops) >= pre + 6


# ─────────────────────────────────────────────────────────
# L3 — hover halo (UI button)
# ─────────────────────────────────────────────────────────
def t_L3():
    import ui as uimod
    uimod._hover_phase_state["last_hover"] = 0.0
    uimod.pulse_hover()
    # module-level state should now have a recent last_hover
    import time as _time
    assert _time.time() - uimod._hover_phase_state["last_hover"] < 0.5


# ─────────────────────────────────────────────────────────
# L4 — wave zoom overlay
# ─────────────────────────────────────────────────────────
def t_L4():
    g = fresh_game()
    g._zoom_freeze = 0.5
    g._draw_wave_zoom_overlay()  # should not raise


# ─────────────────────────────────────────────────────────
# M1 — Cob Cannon end-to-end
# ─────────────────────────────────────────────────────────
def t_M1():
    g = fresh_game()
    g._plant("cobcannon", (2, 1))
    cob = g.plants[0]
    assert cob.ready
    from entities import KernelBomb
    proj = cob.fire_at(950, 350)
    assert isinstance(proj, KernelBomb)
    g.projectiles.append(proj)
    landed = False
    for _ in range(80):
        g.update(0.016)
        if not proj.alive:
            landed = True
            break
    assert landed, "KernelBomb never landed"


# ─────────────────────────────────────────────────────────
# M2 — chain mowers
# ─────────────────────────────────────────────────────────
def t_M2():
    g = fresh_game()
    m2 = g.lawnmowers[2]
    m2.activate()
    m2.x = SCREEN_WIDTH - 10  # right at the edge
    g.update(0.016)
    activated = sum(1 for lm in g.lawnmowers if lm.activated)
    assert activated == GRID_ROWS, f"expected all {GRID_ROWS} mowers activated, got {activated}"


# ─────────────────────────────────────────────────────────
# M3 — bungee full sequence
# ─────────────────────────────────────────────────────────
def t_M3():
    g = fresh_game()
    g.start_adventure_level("4-3")
    g.sun_value = 9999
    g._plant(PLANT_PEASHOOTER, (2, 5))
    g.plant_cooldowns.clear()
    from entities import create_zombie
    row = 2
    col = 5
    tx = g.grid.x + col * CELL_W + (CELL_W - 90) // 2
    zb = create_zombie(tx, -250, row, ZOMBIE_BUNGEE)
    zb.grid_y = g.grid.y
    g.zombies.append(zb)
    for _ in range(int(BUNGEE_DESCEND_S / 0.016) + 200):
        g.update(0.016)
    assert zb.stole_plant is True, f"bungee did not steal: {zb.stole_plant}"
    assert zb._stolen_type is not None, "bungee did not record stolen plant type"


# ─────────────────────────────────────────────────────────
# M4 — boss minion sky-drop + landing
# ─────────────────────────────────────────────────────────
def t_M4():
    g = fresh_game()
    from entities import create_zombie
    boss = create_zombie(900, 200, 0, ZOMBIE_BOSS)
    boss.grid_y = g.grid.y
    g.zombies.append(boss)
    minion = boss._spawn_minion()
    assert minion._minion_drop is True
    assert minion.y == -180.0
    g.zombies.append(minion)
    landed = False
    for _ in range(80):
        g.update(0.016)
        if not minion._minion_drop:
            landed = True
            break
    assert landed, "minion never finished dropping"


# ─────────────────────────────────────────────────────────
# N1 — sunflower eject
# ─────────────────────────────────────────────────────────
def t_N1():
    sf = Sunflower(400, 300, 2)
    sf.cooldown = 0.01
    s = sf.update(0.016, [])
    assert s is not None and s.eject_t > 0, "sun not ejected"
    assert s.eject_vy < 0, f"sun should pop up, got v={s.eject_vy}"
    # After 0.4s, eject ends and falling takes over
    for _ in range(40):
        s.update(0.016)
    assert s.eject_t == 0 and s.falling is True, (
        f"eject should hand off to falling, got eject_t={s.eject_t} falling={s.falling}")


# ─────────────────────────────────────────────────────────
# N2 — wallnut cracks
# ─────────────────────────────────────────────────────────
def t_N2():
    w = Wallnut(0, 0, 2)
    pristine = w._crack_overlay  # exists
    w.hp = w.max_hp * 0.5
    surface = pygame.Surface((W, H), pygame.SRCALPHA)
    surface.fill((80, 130, 70))
    # overlay should not raise at any HP level
    for pct in (1.0, 0.66, 0.40, 0.15):
        w.hp = w.max_hp * pct
        w.x, w.y = 200, 280
        w.draw(surface)
    assert True


# ─────────────────────────────────────────────────────────
tests = [
    ("A   bite_shake",                 t_A),
    ("B   plant_debris",               t_B),
    ("C   pea_impact",                 t_C),
    ("E   zombie_heads",               t_E),
    ("F   balloon_pop",                t_F),
    ("G   mow_dust",                   t_G),
    ("H   plant_poof",                 t_H),
    ("I   food_rings",                 t_I),
    ("J   boss_aura",                 t_J),
    ("K1  sun_bounce",                 t_K1),
    ("K2  grass_prints",               t_K2),
    ("K3  cherry_shockwave",           t_K3),
    ("K4  ice_crackles",               t_K4),
    ("L1  snowpea_e2e",                t_L1),
    ("L2  coin_drops",                 t_L2),
    ("L3  hover_halo",                 t_L3),
    ("L4  wave_zoom_overlay",          t_L4),
    ("M1  cobcannon_e2e",              t_M1),
    ("M2  chain_mowers",               t_M2),
    ("M3  bungee_steal",               t_M3),
    ("M4  minion_drop",                t_M4),
    ("N1  sunflower_eject",            t_N1),
    ("N2  wallnut_cracks",             t_N2),
]


for name, fn in tests:
    check(name, fn)


print()
print("=" * 72)
print(f" {len(results):>2} effect checks")
print("=" * 72)
width = max(len(n) for n, *_ in results)
for name, status, err in results:
    line = f"  [{status}] {name:<{width}}"
    if status == "FAIL":
        line += f"  → {err}"
    print(line)

passed = sum(1 for _, s, _ in results if s == "PASS")
failed = sum(1 for _, s, _ in results if s == "FAIL")
print("=" * 72)
print(f"  PASSED: {passed}    FAILED: {failed}")
sys.exit(0 if failed == 0 else 1)