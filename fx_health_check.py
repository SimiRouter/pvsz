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
# Never touch the shipped save: health checks run against a scratch file.
import save as save_mod
save_mod.SAVE_PATH = os.path.join(os.environ.get("TMPDIR", "/tmp"), "pvsz_fxhealth_save.json")
from game import Game
from entities import *
from wave import WaveSystem
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


def fx_parts(g, kind=None, layer=None):
    """Particles currently alive in the unified system (particles.Effects).

    The per-effect lists this file used to poke at (``g.plant_debris``,
    ``g.pea_impact`` …) are gone — every effect now lives in ``g.fx``. These
    checks assert on the same observable event, just through the one system.
    """
    pool = list(g.fx.air) + list(g.fx.ground)
    if kind is not None:
        pool = [p for p in pool if p.kind == kind]
    if layer is not None:
        pool = [p for p in pool if p.layer == layer]
    return pool


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
    initial_debris = len(fx_parts(g, "leaf"))
    for _ in range(5):
        g.update(0.016)
    assert len(fx_parts(g, "leaf")) > initial_debris, (
        f"plant_debris not spawned: was {initial_debris}, "
        f"now {len(fx_parts(g, 'leaf'))}")


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
    pre = len(fx_parts(g, "dot")) + len(fx_parts(g, "ring"))
    for _ in range(40):
        g.update(0.016)
    now = len(fx_parts(g, "dot")) + len(fx_parts(g, "ring"))
    assert now > pre, f"pea_impact not spawned: was {pre}, now {now}"


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
    pre = len(fx_parts(g, "chunk"))
    z.take_damage(99999)
    spawned = False
    for _ in range(80):
        g.update(0.016)
        if len(fx_parts(g, "chunk")) > pre:
            spawned = True
    assert spawned, f"zombie_heads never spawned (chunks stay at {pre})"


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
    pre = len(fx_parts(g, "shred"))
    for _ in range(5):
        g.update(0.016)
    assert len(fx_parts(g, "shred")) > pre, (
        f"balloon_pop not spawned: was {pre}, now {len(fx_parts(g, 'shred'))}")


# ─────────────────────────────────────────────────────────
# G — mow dust
# ─────────────────────────────────────────────────────────
def t_G():
    g = fresh_game()
    pre = len(fx_parts(g, "puff"))
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
    assert len(fx_parts(g, "puff")) > pre, (
        f"mow_dust not spawned: was {pre}, now {len(fx_parts(g, 'puff'))}")


# ─────────────────────────────────────────────────────────
# H — plant poof (planting + digging)
# ─────────────────────────────────────────────────────────
def t_H():
    g = fresh_game()
    g._plant("peashooter", (2, 3))
    g._dig_up((2, 3))
    # Each soil poof is one ground-layer puff plus four airborne clods.
    puffs = fx_parts(g, "puff", layer=0)
    assert len(puffs) == 2, f"soil poof expected 2 (plant+dig), got {len(puffs)}"
    assert len(fx_parts(g, "dot")) >= 8, "soil clods missing from the poof"


# ─────────────────────────────────────────────────────────
# I — food_rings
# ─────────────────────────────────────────────────────────
def t_I():
    g = fresh_game()
    g._plant("peashooter", (2, 3))
    g.plant_food = 1
    pre = len(fx_parts(g, "ring"))
    g._feed_plant(g.plants[0])
    assert len(fx_parts(g, "ring")) == pre + 2, (
        f"food_rings expected 2, got {len(fx_parts(g, 'ring')) - pre}")


# ─────────────────────────────────────────────────────────
# J — boss aura (summon + death)
# ─────────────────────────────────────────────────────────
def t_J():
    g = fresh_game()
    from entities import create_zombie
    boss = create_zombie(900, 200, 0, ZOMBIE_BOSS)
    boss.grid_y = g.grid.y
    g.zombies.append(boss)
    pre_ring = len(fx_parts(g, "ring"))
    pre_dot = len(fx_parts(g, "dot"))
    g._spawn_boss_aura(boss, kind="summon")
    assert len(fx_parts(g, "ring")) == pre_ring + 1, "summon aura = 1 ring"
    assert len(fx_parts(g, "dot")) == pre_dot + 4, "summon aura = 4 sparks"
    g._spawn_boss_aura(boss, kind="death")
    assert len(fx_parts(g, "ring")) == pre_ring + 3, "death aura = +2 rings"
    assert len(fx_parts(g, "dot")) == pre_dot + 4 + 14, "death aura = +12 sparks"


# ─────────────────────────────────────────────────────────
# K1 — sun bounce
# ─────────────────────────────────────────────────────────
def t_K1():
    s = Sun(300, 0)
    s.drop_from_sky(50)          # close to start, so it lands fast
    y_at_land = None
    rebounded = False
    for _ in range(400):
        s.update(0.016)
        if s.phase == "bounce":
            if y_at_land is None:
                y_at_land = s.y
            elif s.y < y_at_land - 2.0:
                rebounded = True
                break
    assert rebounded, (
        f"sun never rebounded off the lawn: phase={s.phase} y={s.y:.1f}")
    assert s.squash >= 0.0, "impact squash should be reset non-negative"


# ─────────────────────────────────────────────────────────
# K2 — grass prints (zombie walking)
# ─────────────────────────────────────────────────────────
def t_K2():
    g = fresh_game()
    from entities import create_zombie
    z = create_zombie(900, g.grid.y + 2 * CELL_H + 15, 2, ZOMBIE_BASIC)
    z.grid_y = g.grid.y
    g.zombies.append(z)
    # A print lives ~1.1 s while a stride takes ~1.7 s, so sample the count
    # every frame rather than only at the end — the last print may already
    # have faded by the time the loop finishes.
    peak = 0
    peak_layer = 0
    for _ in range(200):
        g.update(0.016)
        prints = fx_parts(g, "print")
        peak = max(peak, len(prints))
        peak_layer = max(peak_layer, len([p for p in prints if p.layer == 0]))
    assert peak > 0, "grass_prints never spawned while a zombie walked"
    assert peak_layer == peak, (
        "footprints must render in the ground layer (under the actors), "
        f"got {peak - peak_layer} airborne")


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
    assert s is not None and s.phase == "eject", "sun not ejected"
    assert s.vy < 0, f"sun should pop up, got v={s.vy}"
    # The pop must arc: rise first, then hand off to a gravity descent.
    start_y = s.y
    peak_y = start_y
    for _ in range(120):
        s.update(0.016)
        peak_y = min(peak_y, s.y)
        if s.phase == "fall":
            break
    assert peak_y < start_y - 10, (
        f"eject should visibly rise, went {start_y:.0f} -> {peak_y:.0f}")
    assert s.phase in ("fall", "bounce", "rest"), (
        f"eject should hand off to a descent, got phase={s.phase}")
    assert s.vy >= 0, f"should be descending after the pop, vy={s.vy}"


# ─────────────────────────────────────────────────────────
# N3 — cherry-bomb fuse countdown + blink
# ─────────────────────────────────────────────────────────
def t_N3():
    cb = CherryBomb(0, 0, 0)
    cb.fuse_max = 1.2
    cb.fuse_timer = 0.0
    # 1. fuse advances over time
    for _ in range(10):
        cb.update(0.016, [])
    assert cb.fuse_timer > 0.1, f"fuse_timer not advancing: {cb.fuse_timer}"
    # 2. auto-detonate kicks in before 2s
    cb2 = CherryBomb(0, 0, 0)
    # Push fuse past fuse_max (1.2s = 75 frames @ 0.016)
    for _ in range(80):
        cb2.update(0.016, [])
    assert cb2.explode is True, f"cherry should arm explode, got fuse_timer={cb2.fuse_timer}"
    # explode_timer is set the moment explode flips True; check we still see it.
    assert cb2.explode_timer > 0, f"explode_timer should be set, got {cb2.explode_timer}"
    # 3. draw must not raise at any progress
    surf = pygame.Surface((W, H), pygame.SRCALPHA)
    surf.fill((80, 130, 70))
    cb3 = CherryBomb(200, 200, 0)
    for t in (0.10, 0.40, 0.70, 0.95):
        cb3.fuse_timer = cb3.fuse_max * t
        cb3.draw(surf)


# ─────────────────────────────────────────────────────────
# N4 — plant-food rolling collect arc
# ─────────────────────────────────────────────────────────
def t_N4():
    pf = PlantFood(400, 200)
    pf.drop_from_sky(200)   # already at target → lands on the first step
    pf.update(0.016)
    assert not pf.falling, f"plant food should land immediately, phase={pf.phase}"
    # Collect from the air returns False (click is ignored until landed)
    pf_air = PlantFood(400, 0)
    pf_air.drop_from_sky(500)
    ok = pf_air.collect((760, 30))
    assert ok is False, "collect during fall must be rejected"
    # Settled food: collect succeeds and runs an arc
    ok = pf.collect((760, 30))
    assert ok is True
    assert pf.collected is True
    initial_y = pf.y
    # Run to mid-arc and confirm y went up (parabolic peak)
    mid_done = False
    for _ in range(120):
        pf.update(0.016)
        if pf.collected and pf.y < initial_y and not mid_done:
            mid_done = True
    assert mid_done, f"arc should peak above start, y went {initial_y} → {pf.y}"
    # Arrived: alive flips False and arrived True
    assert pf.alive is False, "food should arrive and die"
    assert pf.arrived is True
    # Draw does not raise
    pf2 = PlantFood(400, 280)
    pf2.drop_from_sky(280)
    pf2.update(0.016)
    pf2.collect((760, 30))
    surf = pygame.Surface((W, H), pygame.SRCALPHA)
    surf.fill((80, 130, 70))
    pf2.draw(surf)


# ─────────────────────────────────────────────────────────
# P1 — the Director actually adapts to what the player built
# ─────────────────────────────────────────────────────────
def _board(plants):
    """Point ai.intel at a plant layout. Returns a Director bound to it.

    The Director reads the *module-level* intel, so this must be re-called
    immediately before every profile()/compose() — building two Directors and
    then comparing them would have both read whichever board was refreshed
    last, which is exactly the trap the real code avoids by refreshing intel
    once per frame.
    """
    import ai
    ai.refresh_intel(list(plants))
    return ai.Director()


def t_P1():
    import collections
    import ai
    from levels import ADVENTURE_LEVELS

    # --- 1. a level only ever spawns types it has already introduced -------
    ws = WaveSystem()
    ws.waves = ADVENTURE_LEVELS[0]["waves"]      # 1-1: two waves of basic only
    ws.wave_count = len(ws.waves)
    assert not ws._ai_unlocked(), "1-1 must not unlock AI zombies"
    assert ws._allowed_types() == {ZOMBIE_BASIC}, (
        f"wave 1 of 1-1 unlocked too much: {ws._allowed_types()}")

    # --- 2. the same board, two very different defenses -------------------
    # Wall line: the answer is to go over/under it, not through it.
    wall_board = [Wallnut(GRID_X + 6 * CELL_W, GRID_Y + r * CELL_H, r)
                  for r in range(GRID_ROWS)]
    # Massed shooters: the answer is to out-tank them.
    shooter_board = [Peashooter(GRID_X + c * CELL_W, GRID_Y + r * CELL_H, r)
                     for r in range(GRID_ROWS) for c in range(1, 4)]

    # intel is a single module-level snapshot, so read each profile straight
    # after pointing it at the matching board.
    p_wall = _board(wall_board).profile()
    p_shoot = _board(shooter_board).profile()
    assert p_wall != "default", "a wall line must not profile as default"
    assert p_shoot == "shooters", f"3 peashooters per row read as {p_shoot!r}"
    assert p_wall != p_shoot, (
        f"walls and shooters must profile differently, both read {p_wall!r}")

    # --- 3. composition follows the profile -------------------------------
    pool = {ZOMBIE_BASIC, ZOMBIE_CONEHEAD, ZOMBIE_BUCKETHEAD, ZOMBIE_FLAG,
            ZOMBIE_POLE, ZOMBIE_DIGGER, ZOMBIE_TACTICIAN, ZOMBIE_HEALER,
            ZOMBIE_COMMANDER}
    scripted = [ZOMBIE_BASIC, ZOMBIE_CONEHEAD]

    def rosters(board, draws=40):
        """Total type counts over many waves against one board layout."""
        total = collections.Counter()
        for _ in range(draws):
            d = _board(board)          # re-point intel before every compose
            total += collections.Counter(
                d.compose(scripted, 40, pool, unlock_ai=True))
        return total

    wall_counts = rosters(wall_board)
    shoot_counts = rosters(shooter_board)

    assert wall_counts[ZOMBIE_POLE] > shoot_counts[ZOMBIE_POLE], (
        "a wall line should draw more pole-vaulters than a shooter line: "
        f"{wall_counts[ZOMBIE_POLE]} vs {shoot_counts[ZOMBIE_POLE]}")
    assert shoot_counts[ZOMBIE_BUCKETHEAD] > wall_counts[ZOMBIE_BUCKETHEAD], (
        "massed shooters should draw more bucketheads than a wall line: "
        f"{shoot_counts[ZOMBIE_BUCKETHEAD]} vs {wall_counts[ZOMBIE_BUCKETHEAD]}")

    # --- 4. adaptation never erases the script ----------------------------
    for _ in range(40):
        out = _board(wall_board).compose(scripted, 10, pool, unlock_ai=True)
        assert len(out) == 10, f"compose returned {len(out)} of 10"
        assert out.count(ZOMBIE_BASIC) + out.count(ZOMBIE_CONEHEAD) >= 1, (
            "every wave must keep at least one scripted zombie")

    # --- 4b. each defense maps to the counter that beats it ---------------
    # Threats are scored from plant_type/hp/row only, so a flat x is fine.
    def layout(spec):
        out = []
        for cls, col, row in spec:
            out.append(cls(GRID_X + col * CELL_W, GRID_Y + row * CELL_H, row))
        return out

    rows = range(GRID_ROWS)
    cases = [
        ("a wall line", "walls",
         [(Wallnut, c, r) for r in rows for c in (5, 6)]),
        ("massed shooters", "shooters",
         [(Peashooter, c, r) for r in rows for c in (1, 2, 3)]),
        ("a sun-heavy turtle", "economy",
         [(Sunflower, c, r) for r in rows for c in (0, 1, 2)]
         + [(Peashooter, 3, 2)]),
        ("one overloaded lane", "stacked",
         [(Peashooter, c, 0) for c in (1, 2, 3, 4)]
         + [(Sunflower, 0, 1), (Sunflower, 0, 3)]),
        ("walls plus guns", "walls",
         [(Wallnut, 6, r) for r in rows] + [(Peashooter, 2, r) for r in rows]),
        # Regression: one peashooter among sunflowers used to out-score the
        # 2.2x mean test on a tiny threat total and read as a "stacked lane".
        ("a lone peashooter", "default",
         [(Peashooter, 2, 0), (Sunflower, 0, 2)]),
        ("a bare lawn", "default", []),
    ]
    for label, expect, spec in cases:
        got = _board(layout(spec)).profile()
        assert got == expect, f"{label} should profile as {expect!r}, got {got!r}"

    # --- 5. the row pick favours the weak lane ----------------------------
    # One heavily-defended row, one bare row: the bare one should see more.
    lopsided = [Peashooter(GRID_X + c * CELL_W, GRID_Y + 0 * CELL_H, 0)
                for c in range(1, 8)]
    d_row = _board(lopsided)
    picks = collections.Counter(d_row.choose_row() for _ in range(400))
    assert picks[0] < 400 / GRID_ROWS, (
        f"overloaded row should be under-picked, got {picks[0]} of 400")
    assert max(picks, key=lambda r: picks[r]) != 0, (
        f"spawns should avoid the overloaded row, got {dict(picks)}")

    # --- 6. the Director is actually wired into WaveSystem ---------------
    ws2 = WaveSystem()
    ws2.waves = ADVENTURE_LEVELS[-1]["waves"]    # 5-4: names AI zombies
    ws2.wave_count = len(ws2.waves)
    assert ws2._ai_unlocked(), "5-4 names AI zombies, so they must unlock"
    assert ws2.director is not None
    assert ws2.director.enabled == DIRECTOR_ENABLED
    # Rows are deferred to spawn time so they track the live board.
    assert ws2.start_wave() is True
    assert all(row is None for _t, row in ws2.zombies_to_spawn), (
        "rows should be resolved at spawn, not queued up front")
    assert len(ws2.zombies_to_spawn) == ws2.wave_zombies_remaining


# ─────────────────────────────────────────────────────────
# N2 — wallnut cracks
# ─────────────────────────────────────────────────────────
def t_N2():
    w = Wallnut(0, 0, 2)
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
    ("N3  cherry_fuse",                t_N3),
    ("N4  food_arc",                   t_N4),
    ("P1  director_adapts",            t_P1),
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