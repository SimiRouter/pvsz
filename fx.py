"""Juice layer: floating text popups, wave warnings, explosions.

Everything that renders text every frame goes through ``cached_text`` — font
rendering is the single most expensive HUD operation, and damage numbers /
sun counters repeat the same strings thousands of times per session.
"""

import math
import random

import pygame
import fade_cache
import i18n
tr = i18n.tr
from constants import COLOR_WHITE, COLOR_RED, COLOR_YELLOW, SCREEN_WIDTH


# ---------------------------------------------------------------
# Cached text rendering
# ---------------------------------------------------------------
_text_cache = {}


def cached_text(text, size, color, outline=None):
    """Render text once and reuse the surface. ``outline`` draws a dark rim."""
    key = (text, size, color, outline)
    surf = _text_cache.get(key)
    if surf is not None:
        return surf
    font = i18n.font(size)
    surf = font.render(text, True, color)
    if outline:
        w, h = surf.get_size()
        comp = pygame.Surface((w + 4, h + 4), pygame.SRCALPHA)
        for dx in (-2, 0, 2):
            for dy in (-2, 0, 2):
                if dx or dy:
                    comp.blit(font.render(text, True, outline), (2 + dx, 2 + dy))
        comp.blit(surf, (2, 2))
        surf = comp
    _text_cache[key] = surf
    return surf


def faded(surface, alpha):
    """A copy of ``surface`` at the given 0-255 alpha (cached surfaces must
    never be mutated in place — they are shared).

    Delegates to :mod:`fade_cache`, which memoizes one stamped copy per
    (sprite, quantized alpha) instead of allocating a fresh copy per blit:
    steady-state scenes like the lawn re-fade the same halos/auras/shadows
    at nearly the same alpha every frame."""
    return fade_cache.faded(surface, alpha)


# Translucent-primitive scratch cache. The display surface has no per-pixel
# alpha channel, so ``pygame.draw.rect(screen, (0, 0, 0, 180), ...)`` silently
# draws a *solid black* rect — the alpha in the colour tuple is ignored. These
# helpers route the draw through an SRCALPHA surface so the alpha is honoured.
_alpha_cache = {}


def _scratch(w, h):
    w, h = max(1, int(w)), max(1, int(h))
    s = _alpha_cache.get((w, h))
    if s is None:
        s = pygame.Surface((w, h), pygame.SRCALPHA)
        _alpha_cache[(w, h)] = s
    else:
        s.fill((0, 0, 0, 0))
    return s


def alpha_rect(screen, color, rect, radius=0):
    """Draw a translucent rounded rect without leaking into neighbouring px."""
    x, y, w, h = rect
    if w <= 0 or h <= 0:
        return
    s = _scratch(w, h)
    pygame.draw.rect(s, color, (0, 0, w, h), border_radius=radius)
    screen.blit(s, (int(x), int(y)))


class FloatingText:
    """A single short-lived text popup that drifts upward and fades out."""

    def __init__(self, x, y, text, color=COLOR_WHITE, size=18, vy=-40, lifetime=1.2):
        self.x = x
        self.y = y
        self.text = text
        self.color = color
        self.size = size
        self.vy = vy  # pixels per second (negative = upward)
        self.lifetime = lifetime
        self.age = 0
        self.alive = True

    def update(self, dt):
        self.age += dt
        if self.age >= self.lifetime:
            self.alive = False
            return
        self.y += self.vy * dt

    def draw(self, screen):
        surf = cached_text(self.text, self.size, self.color, outline=(0, 0, 0))
        alpha = 255
        if self.age > self.lifetime * 0.5:
            alpha = int(255 * max(0.0, 1.0 - (self.age - self.lifetime * 0.5) / (self.lifetime * 0.5)))
        if alpha < 255:
            surf = faded(surf, alpha)
        screen.blit(surf, (self.x - surf.get_width() // 2, int(self.y)))


class WaveWarning:
    """Big banner: 'A Wave of Zombies is Approaching!' / 'FINAL WAVE!'"""

    def __init__(self):
        self.text = ""
        self.subtext = ""
        self.color = COLOR_RED
        self.duration = 3.0
        self.age = 0
        self.alive = False
        self._main = None   # pre-composited outline+text, built on show()
        self._sub = None

    def show(self, text, subtext="", color=COLOR_RED, duration=3.0):
        self.text = text
        self.subtext = subtext
        self.color = color
        self.duration = duration
        self.age = 0
        self.alive = True
        # Composite once per banner instead of 10 font renders per frame.
        self._main = cached_text(text, 56, color, outline=(0, 0, 0))
        self._sub = cached_text(subtext, 28, COLOR_WHITE, outline=(0, 0, 0)) if subtext else None

    def update(self, dt):
        if not self.alive:
            return
        self.age += dt
        if self.age >= self.duration:
            self.alive = False

    def draw(self, screen):
        if not self.alive or self._main is None:
            return
        # slide in from top + fade in for first 0.3s, fade out at end
        fade_in = min(1.0, self.age / 0.3)
        fade_out = 1.0
        if self.age > self.duration - 0.6:
            fade_out = max(0.0, (self.duration - self.age) / 0.6)
        alpha = int(255 * fade_in * fade_out)
        bw = self._main.get_width() + 40
        bh = self._main.get_height() + 24
        if self._sub is not None:
            bh += self._sub.get_height() + 4
        bx = SCREEN_WIDTH // 2 - bw // 2
        by = 200
        # Rounded, half-alpha strip. The old hard-edged (0,0,0,180) rect read
        # as a black square dropped on the lawn in front of the entering
        # zombies (用户报的"僵尸前头脚下的黑方块") — softer corners and a
        # lighter wash make it read as a banner backdrop instead.
        backdrop = pygame.Surface((bw, bh), pygame.SRCALPHA)
        pygame.draw.rect(backdrop, (0, 0, 0, int(120 * fade_in * fade_out)),
                         (0, 0, bw, bh), border_radius=18)
        screen.blit(backdrop, (bx, by))
        main = faded(self._main, alpha)
        screen.blit(main, (SCREEN_WIDTH // 2 - main.get_width() // 2, by + 12))
        if self._sub is not None:
            sub = faded(self._sub, alpha)
            screen.blit(sub, (SCREEN_WIDTH // 2 - sub.get_width() // 2,
                              by + 12 + self._main.get_height() + 6))


# ---------------------------------------------------------------
# Explosion effect (cherry bomb / boss death)
# ---------------------------------------------------------------
def _explosion_blob(step):
    """Soft radial fireball, cached per quantized growth step (0..15)."""
    key = ("_explosion_blob", step)
    hit = _text_cache.get(key)
    if hit is not None:
        return hit
    size = 256
    t = step / 15.0
    img = pygame.Surface((size, size), pygame.SRCALPHA)
    cx = cy = size // 2
    # layered soft circles: white core → yellow → orange → smoke rim
    palette = (
        ((255, 250, 220), 0.00, 0.30),
        ((255, 220, 90), 0.20, 0.52),
        ((255, 140, 40), 0.42, 0.72),
        ((200, 60, 20, ), 0.62, 0.95),
    )
    for color, r0, r1 in palette:
        radius = int(size * 0.48 * (r0 + (r1 - r0) * min(1.0, t * 1.6)))
        radius = max(2, radius)
        layers = 6
        for i in range(layers, 0, -1):
            rr = int(radius * i / layers)
            a = int(90 * (1 - i / (layers + 1)))
            pygame.draw.circle(img, (*color[:3], a), (cx, cy), rr)
    _text_cache[key] = img
    return img


class Explosion:
    """Fireball + sparks for cherry bombs. Cheap: one cached blob blit and a
    handful of solid circles; lives well under a second."""

    def __init__(self, x, y, radius=150, duration=0.55):
        self.x = x
        self.y = y
        self.radius = radius
        self.duration = duration
        self.age = 0.0
        self.alive = True
        self.particles = []
        for _ in range(14):
            ang = random.uniform(0, math.tau)
            spd = random.uniform(120, 420)
            self.particles.append([
                float(x), float(y),
                math.cos(ang) * spd, math.sin(ang) * spd - 120,
                random.uniform(2.5, 5.5),
                random.choice(((255, 220, 120), (255, 160, 50), (230, 70, 30), (120, 90, 80))),
            ])

    def update(self, dt):
        self.age += dt
        if self.age >= self.duration:
            self.alive = False
            return
        for p in self.particles:
            p[0] += p[2] * dt
            p[1] += p[3] * dt
            p[3] += 700 * dt  # gravity

    def draw(self, screen):
        t = min(1.0, self.age / self.duration)
        # ---- shockwave ring (under the fireball) ----
        # Bright white→orange ring expanding outward, ease-out + thin stroke.
        shock_t = min(1.0, self.age / (self.duration * 0.85))
        shock_ease = 1.0 - (1.0 - shock_t) ** 2
        shock_r = int(self.radius * 1.55 * shock_ease)
        shock_alpha = int(220 * (1.0 - shock_t))
        if shock_r > 2 and shock_alpha > 0:
            s = pygame.Surface((shock_r * 2, shock_r * 2), pygame.SRCALPHA)
            pygame.draw.circle(s, (255, 255, 255, shock_alpha),
                               (shock_r, shock_r), shock_r, 4)
            # inner darker ring for layered look
            pygame.draw.circle(s, (255, 180, 60, int(shock_alpha * 0.6)),
                               (shock_r, shock_r), int(shock_r * 0.78), 2)
            screen.blit(s, (int(self.x) - shock_r, int(self.y) - shock_r))
        # ---- fireball blob ----
        # ease-out growth, ease-in fade
        grow = 1.0 - (1.0 - t) ** 2
        step = int(grow * 15)
        blob = _explosion_blob(step)
        size = int(self.radius * 2 * (0.35 + 0.65 * grow))
        img = pygame.transform.smoothscale(blob, (size, size))
        alpha = int(255 * (1.0 - t) ** 1.2)
        img.set_alpha(alpha)
        screen.blit(img, img.get_rect(center=(int(self.x), int(self.y))))
        # sparks
        for p in self.particles:
            r = max(1, int(p[4] * (1 - t)))
            pygame.draw.circle(screen, p[5], (int(p[0]), int(p[1])), r)
