"""Development harness: headless capture + frame-time benchmark.

Not part of the shipped game. Run it to render deterministic battle scenes to
`screenshots/dev/` and print per-frame update/draw timings so visual and
performance changes can be compared before/after.

    SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy \
        ./venv/bin/python dev_harness.py [scenario ...]
"""
import os
import sys
import time

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
pygame.init()
SCREEN = pygame.display.set_mode((1400, 600))

import assets_loader
assets_loader.init()

from constants import *          # noqa: F403
from game import Game            # noqa: E402
import entities                  # noqa: E402

# Redirect the save file into TMPDIR so campaign runs (which complete every
# level) never pollute the real save.json shipped with the project.
import save as save_mod          # noqa: E402
save_mod.SAVE_PATH = os.path.join(os.environ.get("TMPDIR", "/tmp"), "pvsz_harness_save.json")

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "screenshots", "dev")


def _out(name):
    os.makedirs(OUT, exist_ok=True)
    return os.path.join(OUT, name)


def shoot(game, name):
    game.draw()
    game.draw_state()
    pygame.image.save(game.screen, _out(name))
    return _out(name)


def inset(game, name, x, y, half=64, zoom=4):
    """Save a magnified window centred on ``(x, y)`` of the last drawn frame.

    Judging a 30 px effect on a 1400x600 screenshot is guesswork; this crops
    the neighbourhood and nearest-neighbour zooms it so the shape, edges and
    layering are actually visible.
    """
    scr = game.screen
    r = pygame.Rect(int(x) - half, int(y) - half, half * 2, half * 2)
    r = r.clip(scr.get_rect())
    if r.w <= 0 or r.h <= 0:
        return None
    big = pygame.transform.scale(scr.subsurface(r), (r.w * zoom, r.h * zoom))
    pygame.image.save(big, _out("zoom_" + name))
    return _out("zoom_" + name)


def fresh(level_id="1-1"):
    g = Game(SCREEN)
    g.start_adventure_level(level_id)
    return g


def setup_defense(g, rows=range(GRID_ROWS), peashooter_cols=(1, 2), wall_col=6):
    g.sun_value = 99999
    for row in rows:
        for col in peashooter_cols:
            g._plant(PLANT_PEASHOOTER, (row, col))
            g.plant_cooldowns.clear()
        if wall_col is not None:
            g._plant(PLANT_WALLNUT, (row, wall_col))
            g.plant_cooldowns.clear()
    g.sun_value = 500


def spawn(g, ztype, row, x=None, y=None):
    if x is None:
        x = GRID_X + 6 * CELL_W
    if y is None:
        y = g.grid.y + row * CELL_H + 15
    z = entities.create_zombie(x, y, row, ztype)
    z.grid_y = g.grid.y
    g.zombies.append(z)
    return z


# ---------------------------------------------------------------- scenarios

def scene_zombies(g):
    """One of every zombie type, spread across the lawn."""
    types = [ZOMBIE_BASIC, ZOMBIE_CONEHEAD, ZOMBIE_FLAG, ZOMBIE_BUCKETHEAD,
             ZOMBIE_NEWSPAPER, ZOMBIE_POLE, ZOMBIE_BALLOON]
    for i, t in enumerate(types):
        z = spawn(g, t, i % GRID_ROWS, x=GRID_X + (4 + i) * CELL_W)
        z.anim_time = 0.3 + i * 0.11
    for _ in range(30):
        g.update(1 / 60.0)
    shoot(g, "zombies.png")
    # magnified crop of two zombies so art quality is judgeable
    crop = g.screen.subsurface(pygame.Rect(GRID_X + 4 * CELL_W - 40, GRID_Y + 10,
                                           320, 220)).copy()
    pygame.image.save(pygame.transform.scale(crop, (960, 660)),
                      _out("zombies_zoom.png"))
    return 0


def scene_walk_cycle(g):
    """Six consecutive frames of one walking zombie, for foot-slide checks."""
    z = spawn(g, ZOMBIE_BASIC, 2, x=GRID_X + 7 * CELL_W)
    for i in range(6):
        for _ in range(4):
            g.update(1 / 60.0)
            g.draw()
        pygame.image.save(g.screen.subsurface(pygame.Rect(
            int(z.x) - 90, int(z.y) - 60, 260, 200)).copy(), _out(f"walk_{i}.png"))
    return 0


def scene_sun(g):
    """Sun life cycle: sky fall → rebound → rest → expiry warning.

    Traces a single sun's y over time and dumps one frame per *phase change*
    so the trajectory, the bounces and the fade-out are all inspectable.
    Capturing on the transition rather than on a fixed frame index means the
    shots stay pinned to the real landmarks when the tuning changes — the
    original hard-coded frame numbers silently drifted onto empty lawn once
    the fall was slowed to a clickable 2.2 s.
    """
    from entities import Sun
    g.suns.clear()
    sky = Sun(GRID_X + 180, SUN_FALL_Y)
    sky.drop_from_sky(GRID_Y + 300)
    g.suns.append(sky)
    # A sunflower's ejected sun, for the appearance-trajectory half.
    g._plant(PLANT_SUNFLOWER, (1, 2))
    # Track the sky sun by identity, not by list position. The sunflower's
    # ejected sun is a second entry in g.suns, so once the sky sun expires
    # g.suns[0] silently becomes the *other* pickup and the phase-tracking
    # below starts reading a completely different life cycle.
    trace = []
    pending = ["sun_a_spawn", "sun_b_fall", "sun_c_land",
               "sun_d_bounce", "sun_e_rest", "sun_f_fade"]
    prev_phase = None
    apex_done = False
    died_at = None
    for i in range(420):
        g.update(1 / 60.0)
        g.draw()
        if died_at is None and not sky.alive:
            died_at = i
        if sky.alive:
            trace.append((i, round(sky.x, 1), round(sky.y, 1),
                          sky.phase, round(sky.vy, 1)))
        shot = None
        if i == 0:
            shot = "sun_a_spawn"
        elif sky.alive:
            if prev_phase == "fall" and sky.phase == "bounce":
                shot = "sun_c_land"          # includes the impact squash + ring
            elif prev_phase == "fall" and sky.y > 120 and "sun_b_fall" in pending:
                shot = "sun_b_fall"
            elif prev_phase == "bounce" and sky.phase == "rest":
                shot = "sun_e_rest"
            elif prev_phase == "rest" and sky.phase == "fading":
                shot = "sun_f_fade"
        if shot and shot in pending:
            pending.remove(shot)
            shoot(g, shot + ".png")
            if sky.alive:
                inset(g, shot + ".png", sky.x, sky.y + 10)
        # Capture the apex of the first rebound (vy flips negative→positive).
        if sky.alive and not apex_done and sky.phase == "bounce":
            if sky.vy >= 0 and "sun_d_bounce" in pending:
                apex_done = True
                pending.remove("sun_d_bounce")
                shoot(g, "sun_d_bounce.png")
                inset(g, "sun_d_bounce.png", sky.x, sky.y + 10)
        if sky.alive:
            prev_phase = sky.phase
        if i == 230 and sky.phase == "rest":
            # Force the expiry warning so it is captured, not waited out.
            sky.settled_age = sky.lifetime() - 2.2
    print("  sun trace (frame, x, y, phase, vy):")
    for row in trace[::10]:
        print("   ", row)
    print("  sky sun vanished on frame", died_at,
          "| survivors in g.suns:", len(g.suns))
    return 0


def scene_particles(g):
    setup_defense(g)
    for i, row in enumerate(range(GRID_ROWS)):
        for j in range(4):
            spawn(g, ZOMBIE_BASIC if j % 2 else ZOMBIE_CONEHEAD, row,
                  x=GRID_X + (3 + j) * CELL_W)
    g.flash_timer = 0.12
    g.explosions.append(__import__("fx").Explosion(GRID_X + 4 * CELL_W, GRID_Y + 2 * CELL_H))
    for _ in range(20):
        g.update(1 / 60.0)
        g.draw()
    return 30


def scene_ai(g):
    """Every AI zombie mid-action, so the new FX layer is judgeable."""
    setup_defense(g)
    # A stacked lane for the tactician to want to leave, a bare lane for it
    # to want to join, and a wall for the digger to bypass.
    for r in range(GRID_ROWS):
        spawn(g, ZOMBIE_BASIC, r, x=GRID_X + 7 * CELL_W)
    spawn(g, ZOMBIE_TACTICIAN, 2, x=GRID_X + 6 * CELL_W)
    spawn(g, ZOMBIE_DIGGER, 1, x=GRID_X + 6 * CELL_W)
    spawn(g, ZOMBIE_HEALER, 3, x=GRID_X + 5 * CELL_W)
    spawn(g, ZOMBIE_COMMANDER, 0, x=GRID_X + 5 * CELL_W)
    # wound a neighbour so the healer has something to mend
    for r in range(GRID_ROWS):
        for z in g.zombies:
            if z.row == r and z.zombie_type == ZOMBIE_BASIC:
                z.hp = z.max_hp * 0.4
                break
    for i in range(180):
        g.update(1 / 60.0)
        g.draw()
        if i in (40, 90, 150):
            shoot(g, f"ai_{i:03d}.png")
    shoot(g, "ai.png")
    return 0


def bench(g, frames=900, label="bench"):
    """Time update() and draw() separately over `frames` simulated frames."""
    up = []
    dr = []
    for i in range(frames):
        t0 = time.perf_counter()
        g.update(1 / 60.0)
        t1 = time.perf_counter()
        g.draw()
        t2 = time.perf_counter()
        up.append((t1 - t0) * 1000)
        dr.append((t2 - t1) * 1000)
    up.sort(); dr.sort()
    n = len(up)
    print(f"[{label}] update  avg {sum(up)/n:6.2f}ms  p95 {up[int(n*0.95)]:6.2f}ms  max {up[-1]:6.2f}ms")
    print(f"[{label}] draw    avg {sum(dr)/n:6.2f}ms  p95 {dr[int(n*0.95)]:6.2f}ms  max {dr[-1]:6.2f}ms")
    print(f"[{label}] total   avg {(sum(up)+sum(dr))/n:6.2f}ms  (60fps budget 16.67ms), "
          f"zombies={len(g.zombies)} plants={len(g.plants)} proj={len(g.projectiles)}")
    return sum(up) / n + sum(dr) / n


def scene_heavy(g):
    """Worst case: full lawn of shooters + a big horde + lots of particles."""
    setup_defense(g, peashooter_cols=(0, 1, 2, 3), wall_col=7)
    g.sun_value = 99999
    for row in range(GRID_ROWS):
        for col in (4, 5):
            g._plant(PLANT_SUNFLOWER, (row, col))
            g.plant_cooldowns.clear()
    for i in range(34):
        spawn(g, [ZOMBIE_BASIC, ZOMBIE_CONEHEAD, ZOMBIE_BUCKETHEAD,
                  ZOMBIE_FLAG, ZOMBIE_NEWSPAPER][i % 5], i % GRID_ROWS,
              x=GRID_X + (4 + (i // GRID_ROWS)) * CELL_W)
    g.sun_value = 99999
    return bench(g, frames=900, label="heavy")


def scene_campaign(g):
    """Play every adventure level start to finish through the real game loop.

    Reports the zombie types each level actually fielded and asserts the two
    things the adaptive director promises: a level never fields a type before
    the wave that introduces it, and the AI roster appears only from the level
    that first names it. Catches integration breakage that unit-level checks
    miss — a wave table the Director cannot compose, a spawn path that throws
    only once a real zombie walks on.
    """
    import collections
    from levels import ADVENTURE_LEVELS
    from constants import ZOMBIE_TACTICIAN, ZOMBIE_DIGGER, ZOMBIE_HEALER, \
        ZOMBIE_COMMANDER
    ai_types = {ZOMBIE_TACTICIAN, ZOMBIE_DIGGER, ZOMBIE_HEALER, ZOMBIE_COMMANDER}
    # Types the game injects from outside the wave table, by authored design
    # rather than by Director choice: the fog/roof sky ambush on every huge and
    # final wave, and minions a boss spawns mid-fight. Neither is the Director
    # reaching past a level's table, so neither counts as a pacing violation.
    authored_specials = {ZOMBIE_BUNGEE, ZOMBIE_BOSS}

    failures = []
    for lv in ADVENTURE_LEVELS:
        g.start_adventure_level(lv["id"])
        setup_defense(g)
        seen = collections.Counter()
        early = set()
        frames = 0
        limit = 60 * 60 * 6           # 6 simulated minutes per level
        while frames < limit:
            g.sun_value = 99999
            g.update(1 / 60.0)
            # _allowed_types() with no argument is the progressive set through
            # the wave currently in progress, which is exactly the promise:
            # nothing may appear before the wave that introduces it.
            allowed = g.wave._allowed_types()
            for z in g.zombies:
                t = z.zombie_type
                seen[t] += 1
                if t not in allowed and t not in authored_specials:
                    early.add((t, g.wave.wave_index))
            # Once a wave has put everything on the lawn, clear it out. The
            # harness lawn kills roughly one zombie per 20 s, so a 12-zombie
            # final wave would otherwise outlast the frame budget and the
            # check would never see the later waves. take_damage keeps the
            # normal death path (score, wave tally, death FX) intact.
            if (g.wave.wave_active and g.wave.zombies_to_spawn
                    and g.wave.zombies_spawned >= len(g.wave.zombies_to_spawn)):
                for z in list(g.zombies):
                    if z.alive and z.hp > 0:
                        z.take_damage(999999)
            frames += 1
            # Done when every wave has been composed, the last one has put all
            # its zombies on the lawn, and the lawn is clear. Note this cannot
            # wait on `not between_waves`: after the final wave that flag is
            # set and never cleared, since there is no next wave to advance to.
            if (g.wave.wave_index >= g.wave.wave_count
                    and not g.wave.wave_active
                    and g.wave.zombies_spawned >= len(g.wave.zombies_to_spawn)
                    and not any(z.alive and z.hp > 0 for z in g.zombies)):
                break
        ai_seen = sorted(t for t in seen if t in ai_types)
        complete = g.wave.wave_index >= g.wave.wave_count
        print(f"  {lv['id']:<6} waves={g.wave.wave_index}/{g.wave.wave_count} "
              f"seen={frames:<5} types={len(seen):<2} ai={ai_seen or '-'}")
        if not complete:
            failures.append(f"{lv['id']} only reached wave "
                            f"{g.wave.wave_index}/{g.wave.wave_count}")
        if early:
            failures.append(f"{lv['id']} fielded types ahead of their wave: "
                            f"{sorted(early)}")
        if not g.wave._ai_unlocked() and ai_seen:
            failures.append(f"{lv['id']} fielded AI zombies but never named one")
    for msg in failures:
        print("  FAIL:", msg)
    print("  campaign:", "OK" if not failures else f"{len(failures)} FAILURES")
    return 1 if failures else 0


SCENES = {
    "zombies": scene_zombies,
    "walk": scene_walk_cycle,
    "sun": scene_sun,
    "particles": scene_particles,
    "ai": scene_ai,
    "heavy": scene_heavy,
    "campaign": scene_campaign,
}


def main():
    wanted = sys.argv[1:] or ["zombies"]
    for name in wanted:
        fn = SCENES.get(name)
        if fn is None:
            print(f"unknown scenario: {name}; have {sorted(SCENES)}")
            continue
        g = fresh()
        print(f"--- {name} ---")
        fn(g)


if __name__ == "__main__":
    main()
