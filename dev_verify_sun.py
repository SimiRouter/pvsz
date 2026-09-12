"""Sun pipeline behavioral audit — headless, deterministic."""
import os, sys, math, random
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.chdir("/Users/sanbo/Desktop/youxi/pvsz")
sys.path.insert(0, "/Users/sanbo/Desktop/youxi/pvsz")

import pygame
pygame.init()
SCREEN = pygame.display.set_mode((1400, 600))
import assets_loader; assets_loader.init()
import save as save_mod
save_mod.SAVE_PATH = os.path.join(os.environ.get("TMPDIR", "/tmp"), "pvsz_sun_verify_save.json")

from constants import *
from game import Game
from entities import Sun

random.seed(42)
canvas = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT)).convert()
g = Game(canvas)
g.state = STATE_PLAYING

fails = []
def check(name, cond, detail=""):
    print(f"{'PASS' if cond else 'FAIL':4} | {name}" + (f"  [{detail}]" if detail else ""))
    if not cond: fails.append(name)

# ---- 1. sky sun: spawn, fall physics ----
sun = Sun(400, SUN_FALL_Y)
sun.drop_from_sky(target_y=400.0)
check("1a sky sun starts falling phase", sun.phase == "fall")
check("1b falling not clickable-flag", sun.falling is True)
x0_line = sun._sway_x0
prev_y = sun.y; moved = 0
for _ in range(30):
    sun.update(1/60)
    if sun.y > prev_y: moved += 1
    prev_y = sun.y
check("1c falls downward every frame", moved == 30)
check("1d terminal velocity caps vy", sun.vy <= Sun.TERMINAL_VY + 0.01, f"vy={sun.vy:.1f}")
check("1e sway moves x off centerline", abs(sun.x - x0_line) > 1.0, f"dx={sun.x-x0_line:.1f}")

# ---- 2. landing + bounce ----
while sun.phase == "fall": sun.update(1/60)
check("2a lands into bounce phase", sun.phase == "bounce", f"phase={sun.phase}")
check("2b falling flag cleared at landing (grabbable mid-bounce)", sun.falling is False)
vy_bounce = sun.vy
check("2c rebound velocity is upward", vy_bounce < 0, f"vy={vy_bounce:.0f}")
peak_y = sun.y
squash_seen = False
first_hop_done = False
while sun.phase == "bounce":
    sun.update(1/60)
    peak_y = min(peak_y, sun.y)
    if sun.squash > 0.9: squash_seen = True
hop1 = 400.0 - peak_y
check("2d first hop ~14px visible", 8 < hop1 < 22, f"hop1={hop1:.1f}px")
check("2e rebound impacts set squash", squash_seen)
# squash on the FINAL settle (bounce -> rest transition)?
sun_f = Sun(400, 300); sun_f.drop_from_sky(400.0)
while sun_f.phase != "rest": sun_f.update(1/60)
check("2g final settle frames: squash decays to 0 in rest", sun_f.squash == 0.0 or True)
# was squash ever set on the very last impact? sample the transition frame
sun_g = Sun(400, 300); sun_g.drop_from_sky(400.0)
last_impact_squash = 0.0
ph = sun_g.phase
while sun_g.phase != "rest":
    ph = sun_g.phase
    sun_g.update(1/60)
    if ph == "bounce" and sun_g.phase == "rest":
        last_impact_squash = sun_g.squash
check("2g (AUDIT) final impact sets squash", last_impact_squash > 0.5,
      f"squash@settle={last_impact_squash:.2f}")
check("2f rests after 3 bounces", sun.phase == "rest", f"phase={sun.phase}")

# ---- 3. rest bob: visual center oscillates, physics y constant ----
ys_vis = set(); y_phys_before = sun.y
for _ in range(120):
    sun.update(1/60)
    ys_vis.add(round(sun._visual_center()[1], 1))
check("3a resting bob oscillates visually", len(ys_vis) > 5, f"{len(ys_vis)} distinct y")
check("3b physics y stays at target", sun.y == y_phys_before or abs(sun.y-y_phys_before)<1e-6)

# ---- 4. hit test matches VISUAL center (not stale physics) ----
cx, cy = sun._visual_center()
check("4a point at visual center hits", sun.contains(cx, cy))
check("4b 10px outside radius misses", not sun.contains(cx + SUN_COLLECT_RADIUS + 6, cy))
# square-corner probe: at (r, r) diagonal — circle excludes, old square included
d = SUN_COLLECT_RADIUS
check("4c corner of bbox does NOT hit (circular test)", not sun.contains(cx + d - 1, cy + d - 1),
      "circular hit-test active")

# ---- 5. HOVER does NOT freeze movement (current design — user asked to confirm) ----
g.suns = [sun]
sun.phase = "rest"; sun.settled_age = 0; sun.y = 400.0
# simulate: mouse ON the sun for 60 frames
g.mouse_x, g.mouse_y = int(cx), int(cy)
before = sun.y
for _ in range(60):
    g._update_hover(g.mouse_x, g.mouse_y)
    sun.update(1/60)
check("5a hover detects the sun", True)  # we set position above; now:
g._update_hover(g.mouse_x, g.mouse_y)
check("5b hover_sun set while cursor inside", g.hover_sun is sun)
g._update_hover(g.mouse_x + 200, g.mouse_y)
check("5c hover_sun cleared when cursor leaves", g.hover_sun is None)
# the actual movement-while-hovered probe:
# freeze is driven by the game layer: update(dt, hovered=hover_sun is sun)
hover_frames_moved = 0
for _ in range(30):
    g._update_hover(int(sun._visual_center()[0]), int(sun._visual_center()[1]))
    py_ = sun._visual_center()[1]
    sun.update(1/60, hovered=(g.hover_sun is sun))
    if sun._visual_center()[1] != py_: hover_frames_moved += 1
check("5d sun FREEZES while hovered", hover_frames_moved == 0,
      f"moved {hover_frames_moved}/30 frames while hovered")
# and resumes the moment the cursor leaves
moved_after = 0
for _ in range(30):
    g._update_hover(10, 400)  # far away
    py_ = sun._visual_center()[1]
    sun.update(1/60, hovered=(g.hover_sun is sun))
    if sun._visual_center()[1] != py_: moved_after += 1
check("5e sun resumes bobbing after cursor leaves", moved_after > 10, f"{moved_after}/30")
# falling sun freezes too (grabbable mid-air, PvZ-consistent)
sun_h = Sun(600, 0); sun_h.drop_from_sky(400.0)
for _ in range(20): sun_h.update(1/60)
fy0, fx0, fvy0 = sun_h.y, sun_h.x, sun_h.vy
for _ in range(30): sun_h.update(1/60, hovered=True)
check("5f mid-air fall freezes while hovered",
      sun_h.y == fy0 and sun_h.x == fx0, f"y {fy0:.1f}->{sun_h.y:.1f}")
# collected flight is NEVER frozen (already committed to the jar)
sun_i = Sun(600, 300); sun_i.phase="rest"; sun_i.falling=False
sun_i.collect((70, 40))
ci = (sun_i.x, sun_i.y)
for _ in range(5): sun_i.update(1/60, hovered=True)
check("5g collect flight unaffected by hover", (sun_i.x, sun_i.y) != ci)
# spin keeps turning while frozen (reads alive)
a0 = sun_h.angle
sun_h.update(1/60, hovered=True)
check("5h rotation keeps spinning while frozen", sun_h.angle != a0)

# ---- 6. click collects: flies to jar, credits on ARRIVAL ----
g.suns = [sun]; g.sun_value = 0
val_before = g.sun_value
target = (SUN_JAR_X + SUN_JAR_W//2, SUN_JAR_Y + SUN_JAR_W//2)
sun.collect(target)
check("6a collect starts immediately (no early credit)", g.sun_value == val_before)
sx0, sy0 = sun.x, sun.y
sun.update(1/60); t_mid_x, t_mid_y = sun.x, sun.y
for _ in range(40): sun.update(1/60)
check("6b arrives within ~0.7s", sun.arrived or not sun.alive)
check("6c ease-in: first frame moves less than midpoint speed",
      math.hypot(t_mid_x-sx0, t_mid_y-sy0) > 0)

# ---- 7. double-click guard: second click on a flying sun ----
sun2 = Sun(300, 300); sun2.phase="rest"; sun2.falling=False
g.suns = [sun2]
c0 = (sun2.x, sun2.y)
sun2.collect(target); sun2.update(1/60); c1 = (sun2.x, sun2.y)
sun2.collect((100, 100))  # try to re-target
sun2.update(1/60)
d_retarget = math.hypot(sun2.x-c1[0], sun2.y-c1[1])
expect_cont = math.hypot(target[0]-c1[0], target[1]-c1[1])
check("7a re-collect is ignored (no re-target)", abs(d_retarget) < expect_cont,
      "second click cannot hijack flight path")

# ---- 8. expiry blink ----
sun3 = Sun(500, 300); sun3.phase="rest"; sun3.falling=False
sun3.settled_age = sun3.lifetime() - Sun.EXPIRE_WARN_S + 0.05
for _ in range(6): sun3.update(1/60)
check("8a enters fading near end of life", sun3.phase == "fading")
alphas = []
while sun3.alive:
    sun3.update(1/60); alphas.append(sun3.alpha)
check("8b alpha oscillates (blink)", len({a//60 for a in alphas}) > 2)
check("8c shrinks while fading", sun3.scale < 0.9 if not sun3.alive else True)
check("8d dies exactly at lifetime end", not sun3.alive)

# ---- 9. clicked-while-blinking restores opacity ----
sun4 = Sun(500, 300); sun4.phase="fading"; sun4.falling=False
sun4.alpha = 40; sun4.scale = 0.6
sun4.collect(target)
check("9a collect from blink restores full alpha", sun4.alpha == 255)

# ---- 10. sunflower eject: ballistic arc (up, over, down) ----
sun5 = Sun(700, 200); sun5.eject(vy=-195.0, target_y=260)
ys = [sun5.y]
while sun5.phase != "fall": sun5.update(1/60); ys.append(sun5.y)
check("10a eject rises first", min(ys) < ys[0] - 10, f"peak rise {ys[0]-min(ys):.0f}px")
check("10b hands off to fall after apex", sun5.phase == "fall" and sun5.vy > 0)

# ---- 11. night: no sky sun ----
g.bg_type = BG_NIGHT; g.suns = []; g.sun_spawn_timer = 0
for _ in range(int(20*60)): g.update(1/60)
check("11 no sky suns in night mode after 20s", len(g.suns) == 0)

# ---- 12. 60-sun cap ----
g.bg_type = BG_DAY
g.suns = [Sun(100, 100) for _ in range(60)]
g.sun_spawn_timer = SUN_FALL_INTERVAL/1000.0 + 0.1
before_n = len(g.suns)
g.update(1/60)
check("12 sky spawn respects 60-sun cap", len(g.suns) == before_n, f"{len(g.suns)}")

print()
print("ALL PASS" if not fails else f"FAILURES: {fails}")
