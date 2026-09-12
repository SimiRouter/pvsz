"""End-to-end check of the sun-hover/click/suppress wiring in a live Game."""
import os, sys
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
sys.argv = ["dev_verify_hover"]

import pygame
import dev_harness as H
from entities import Sun
from constants import *


def click(gm, x, y):
    ev = pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=(x, y))
    gm.handle_event(ev)


def park_sun(g, x, y):
    g.suns.clear()
    sun = Sun(x, y)
    sun.phase = "rest"
    sun.falling = False
    sun.target_y = float(y)
    g.suns.append(sun)
    for _ in range(30):
        g.update(1 / 60.0)
    return sun


g = H.fresh("1-1")

# park a sun exactly on the col2/col3 tile boundary — the exact Bug 3 case
sx = float(g.grid.x + 3 * CELL_W)
sy = float(g.grid.y + 2 * CELL_H + CELL_H // 2)
sun = park_sun(g, sx, sy)
mx, my = int(sun.x), int(sun.y)

# --- hover detection ---
g._update_hover(mx, my)
assert g.hover_sun is sun, f"hover_sun not claimed: {g.hover_sun}"
print("PASS hover claims straddling sun")

# the wash on the hovered tile must be suppressed while the sun is hovered.
# Set BOTH pieces of state the real mouse path sets: grid.hover_cell comes
# from MOUSEMOTION, hover_sun from _update_hover() during draw.
g.grid.update_hover(mx, my)
g._update_hover(mx, my)
assert g.hover_sun is sun and g.grid.hover_cell == (2, 3), \
    f"setup wrong: sun={g.hover_sun} cell={g.grid.hover_cell}"
# pixel inside the hovered cell (col3) but 60px from the sun center, so the
# sprite art itself doesn't cover it in either arm
probe = (g.grid.x + 3 * CELL_W + 60, g.grid.y + 2 * CELL_H + 50)
g.draw()
sup_px = g.screen.get_at(probe)      # sun hovered -> wash suppressed
g.hover_sun = None
g.draw()
show_px = g.screen.get_at(probe)     # no sun -> wash drawn
assert sup_px != show_px, "wash did not change when sun claims the cursor"
assert show_px[0] > sup_px[0], f"wash missing even without sun: {show_px} vs {sup_px}"
print("PASS tile wash suppressed while sun hovered (Bug 3)")

# sanity: with no sun hovered the wash returns (so we didn't break hover)
g.grid.update_hover(*probe)
g._update_hover(*probe)
assert g.hover_sun is None and g.grid.hover_cell == (2, 3)
g.draw()
on_px = g.screen.get_at(probe)
assert on_px == show_px, "cell hover wash vanished entirely (regression)"
print("PASS normal cell hover wash still works when no sun under cursor")

# --- click collects ---
before = g.sun_value
assert sun.contains(mx, my)
g._update_hover(mx, my)
click(g, mx, my)
assert sun.collected, "click on sun did not mark it collected"
# the jar credit lands when the collect-flight arrives, inside update()
for _ in range(40):
    g.update(1 / 60.0)
assert g.sun_value > before, f"sun value not added: {before} -> {g.sun_value}"
print(f"PASS click collects straddling sun (+{g.sun_value - before} sun, Bug 2)")

# --- corner click must NOT collect (circle vs old square) ---
g2 = H.fresh("1-1")
sun2 = park_sun(g2, sx, sy)
r = sun2.rect()
cx, cy = r.center
g2._update_hover(cx + 23, cy + 23)
assert g2.hover_sun is None, "hover claimed a point outside the circle"
before2 = g2.sun_value
click(g2, cx + 23, cy + 23)
assert not sun2.collected, "corner click collected (hit test still square)"
print("PASS square-corner click no longer steals the sun")

print("RESULT: ALL PASS")
