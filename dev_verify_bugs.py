"""Headless verification for the three reported bugs + alpha-cache hardening."""
import os, sys
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
pygame.init()
pygame.font.init()
screen = pygame.display.set_mode((1280, 720))

import i18n
import fx, entities, assets_loader, grid, game as game_mod
from constants import *
# Never touch the shipped save: verifications run against a scratch file.
import save as save_mod
save_mod.SAVE_PATH = os.path.join(os.environ.get("TMPDIR", "/tmp"), "pvsz_bugs_save.json")

fails = []
def check(name, cond, extra=""):
    print(("PASS" if cond else "FAIL"), name, extra)
    if not cond:
        fails.append(name)

# ---------------------------------------------------------------- Bug 2
# circular hit test vs the old square
s = entities.Sun(600, 400)
s.phase = "rest"
r = s.rect()
check("sun rect size", r.width == 48 and r.height == 48, str(r))
# corner of the square box: inside rect(), outside contains()
cx, cy = r.center
corner = (cx + 23, cy + 23)  # dist ~32.5 > 24
check("corner outside contains", not s.contains(*corner), str(corner))
check("corner inside old rect", r.collidepoint(*corner))
# edge midpoint at r=20: inside both
check("edge inside contains", s.contains(cx + 20, cy))
# just past radius: outside
check("far outside contains", not s.contains(cx + 25, cy))
# collected: never contains
s.collected = True
check("collected excluded", not s.contains(cx, cy))
s.collected = False

# bob desync: rect() must follow the visual center
s2 = entities.Sun(600, 400)
s2.phase = "rest"
s2.age = 3.14159 / 2 / 2.4  # sin(age*2.4)=1 -> bob=+2
rc = s2.rect()
check("rect follows bob", abs(rc.centery - 401) <= 1, f"centery={rc.centery}")
vcx, vcy = s2._visual_center()
check("visual_center bobs", abs(vcy - 402.0) < 0.01, f"{vcy}")
check("contains uses bob", s2.contains(600, 402) and not s2.contains(600, 377.9))

# ----------------------------------------------------- Bug 2/3: game hover
g = game_mod.Game.__new__(game_mod.Game)  # bare object, wire minimal state
# instead of half-initializing Game, do a live scene via dev harness style:
# just check Grid suppress_hover
gr = grid.Grid()
gr.update_hover(GRID_X + 50, GRID_Y + 50)
check("grid hover set", gr.hover_cell == (0, 0), str(gr.hover_cell))
screen.fill((60, 120, 40))
gr.draw(screen, suppress_hover=False)
px_washed = screen.get_at((GRID_X + 50, GRID_Y + 50))
screen.fill((60, 120, 40))
gr.draw(screen, suppress_hover=True)
px_plain = screen.get_at((GRID_X + 50, GRID_Y + 50))
check("suppress_hover removes wash", px_plain == (60, 120, 40, 255), str(px_plain))
check("wash present when not suppressed", px_washed[0] > 60 + 20, str(px_washed))

# ------------------------------------------------- alpha cache hardening
sh = assets_loader.shadow(40, 14)
before = sh.get_alpha()
assets_loader.blit_shadow(screen, 300, 300, 40, 14, alpha=150)
check("shadow cache alpha untouched", sh.get_alpha() == before, f"{before} -> {sh.get_alpha()}")

# particles: dot cache not mutated after draw
import particles
p = particles.Particle.__new__(particles.Particle)
for attr, val in [("x", 100.0), ("y", 100.0), ("life", 0.5), ("max_life", 1.0),
                  ("size", 6.0), ("color", (255, 0, 0)), ("kind", "dot"),
                  ("fade_in", 0.0), ("rot", 0), ("r0", 6.0), ("r1", 6.0),
                  ("width", 2), ("gravity", 0.0), ("drag", 0.0), ("spin", 0.0),
                  ("layer", 0), ("alive", True), ("x2", 0.0), ("y2", 0.0)]:
    object.__setattr__(p, attr, val) if not hasattr(p, attr) else setattr(p, attr, val)
eff = particles.Effects.__new__(particles.Effects)
dot = particles._dot((255, 0, 0), 6)
alpha_before = dot.get_alpha()
eff._draw_one(screen, p)
dot = particles._dot((255, 0, 0), 6)
check("dot cache alpha untouched", dot.get_alpha() == alpha_before,
      f"{alpha_before} -> {dot.get_alpha()}")
# ring cache
ring = particles._ring_sprite((255, 255, 0), 20, 3)
ra = ring.get_alpha()
p.kind = "ring"
eff._draw_ring(screen, p)
ring = particles._ring_sprite((255, 255, 0), 20, 3)
check("ring cache alpha untouched", ring.get_alpha() == ra, f"{ra} -> {ring.get_alpha()}")

# entities: PlantFood glow cache not mutated across draws
glow_cache = getattr(entities, "_food_glow_cache", None)
check("food glow cache exists", glow_cache is not None)
if glow_cache is not None:
    pf = entities.PlantFood(200, 200)
    pf.draw(screen)  # builds cache
    g = glow_cache.get("glow")
    a0 = g.get_alpha() if g is not None else None
    pf.draw(screen)
    a1 = g.get_alpha() if g is not None else None
    check("food glow cache untouched", a0 == a1, f"{a0} -> {a1}")

# ---------------------------------------------------------------- Bug 1
# banner backdrop must blend with lawn (translucent), not solid black
lawn_green = (60, 120, 40)
screen.fill((*lawn_green, 255))
w = fx.WaveWarning()
w.show("一大波僵尸正在接近！", "僵尸数量：超多", COLOR_RED, duration=3.0)
w.age = 1.5  # fully faded in
w.draw(screen)
# backdrop area at center should be dark green-ish, NOT pure black
px = screen.get_at((640, 205))
check("backdrop not solid black", not (px[0] < 8 and px[1] < 8 and px[2] < 8), str(px))
check("backdrop darkens lawn", px[0] < 60 and px[1] < 120 and px[2] < 40, str(px))
# rounded corner: at the very corner of the backdrop bbox, should stay lawn
bw = w._main.get_width() + 40
bh = w._main.get_height() + 24 + w._sub.get_height() + 4
bx = 1280 // 2 - bw // 2
corner_px = screen.get_at((bx + 2, 202))  # outside the r=18 round
check("corner rounded (bg shows)", corner_px[:3] == lawn_green, str(corner_px))
# subtext inside backdrop: bottom edge of subtext < by+bh
sub_h = w._sub.get_height()
sub_top = 200 + 12 + w._main.get_height() + 6
check("subtext inside backdrop", sub_top + sub_h <= 200 + bh, f"{sub_top + sub_h} vs {200 + bh}")

# banner expired -> nothing at feet area (A/B: 260 frames later)
w2 = fx.WaveWarning()
w2.show("僵尸 approaching", duration=3.0)
w2.age = 3.5
w2.update(0.016)
check("banner dead after duration", not w2.alive)

print()
print("RESULT:", "ALL PASS" if not fails else f"FAILED: {fails}")
sys.exit(1 if fails else 0)
