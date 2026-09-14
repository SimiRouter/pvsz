"""One particle system for the whole game.

The old code kept nine separate effect lists on ``Game`` (``plant_debris``,
``pea_impact``, ``zombie_heads``, ``balloon_pop``, ``mow_dust``,
``food_rings``, ``boss_aura``, ``grass_prints``, ``plant_poof``), each a bare
``list`` of numbers indexed positionally — ``d[5] < d[6]`` was a lifetime
check — with its update loop and its draw loop written out again in a
different place. Adding an effect meant touching four of them.

Everything now goes through :class:`Effects`:

* ``Effects.update(dt)`` advances every pool once.
* ``draw_ground()`` renders the layer that belongs *under* the actors (grass
  prints, soil) and ``draw_air()`` the layer that belongs *over* them.
* Emitters are named for what they look like, not for which list they append
  to, so callers read as intent.

Performance notes: particles are recycled through a free pool instead of being
reallocated per burst, and every sprite is pre-rendered and cached per
(colour, quantized radius) so the draw path is one ``blit`` per particle
rather than a scratch-surface allocate + shape draw + blit.
"""

import math
import random

import pygame

import fade_cache

# ------------------------------------------------------------------ sprites
_sprite_cache = {}


def _faded(surface, alpha):
    """A copy of ``surface`` stamped with surface-level ``alpha``.

    ``set_alpha`` mutates the surface persistently — every later blit of it
    uses the new value — so it must never be called on a shared cached
    sprite (two particles of different ages would clobber each other).

    Delegates to :mod:`fade_cache`, which memoizes one stamped copy per
    (sprite, quantized alpha): dot/puff sprites re-fade at nearly the same
    alpha every frame and used to allocate 70+ copies per frame on a busy
    lawn."""
    return fade_cache.faded(surface, alpha)


def _quantize(radius):
    """Round a radius onto a coarse ladder so the sprite cache stays small."""
    r = max(1, int(radius))
    if r <= 4:
        return r
    if r <= 12:
        return (r // 2) * 2
    return (r // 4) * 4


def _dot(color, radius):
    """Soft-edged filled circle, cached per (colour, quantized radius)."""
    q = _quantize(radius)
    key = ("dot", color, q)
    img = _sprite_cache.get(key)
    if img is None:
        img = pygame.Surface((q * 2 + 2, q * 2 + 2), pygame.SRCALPHA)
        c = q + 1
        pygame.draw.circle(img, (*color, 210), (c, c), q)
        if q > 2:
            pygame.draw.circle(img, (*color, 90), (c, c), q, max(1, q // 2))
            pygame.draw.circle(img, (255, 255, 255, 60), (c - q // 3, c - q // 3),
                               max(1, q // 3))
        _sprite_cache[key] = img
    return img


def _puff(color, radius):
    """Soft dusty blob: concentric translucent rings, no hard edge."""
    q = _quantize(radius)
    key = ("puff", color, q)
    img = _sprite_cache.get(key)
    if img is None:
        img = pygame.Surface((q * 2 + 2, q * 2 + 2), pygame.SRCALPHA)
        c = q + 1
        steps = max(2, min(6, q))
        for i in range(steps, 0, -1):
            k = i / float(steps)
            pygame.draw.circle(img, (*color, int(24 + 44 * (1.0 - k))),
                               (c, c), max(1, int(q * k)))
        _sprite_cache[key] = img
    return img


def _leaf(color, radius):
    """Rotating petal / leaf: a pointed ellipse, cached per rotation step."""
    q = _quantize(radius)
    key = ("leaf", color, q)
    img = _sprite_cache.get(key)
    if img is None:
        w, h = q * 2 + 2, max(3, q + 1)
        img = pygame.Surface((w, h), pygame.SRCALPHA)
        pygame.draw.ellipse(img, (*color, 225), (0, 0, w - 1, h))
        pygame.draw.ellipse(img, (255, 255, 255, 70), (1, 1, max(1, w // 2), max(1, h // 2)))
        _sprite_cache[key] = img
    return img


def _shred(color, radius):
    """Angular rubber shard for balloon pops: a small tilted quad."""
    q = _quantize(radius)
    key = ("shred", color, q)
    img = _sprite_cache.get(key)
    if img is None:
        s = q * 2 + 2
        img = pygame.Surface((s, s), pygame.SRCALPHA)
        pygame.draw.polygon(img, (*color, 235), [
            (1, q), (s - 2, 1), (s - 2, s - 2), (q, s - 2)])
        pygame.draw.polygon(img, (255, 255, 255, 80), [
            (2, q), (s - 3, 2), (q, 2)])
        _sprite_cache[key] = img
    return img


_rot_cache = {}

#: Rotated leaf/shred variants key on a continuously-shrinking radius crossed
#: with a 24-bin angle, so unlike the base sprite caches this key space is not
#: naturally bounded. Cap it the same way ``_beam_cache`` is capped: on
#: overflow drop everything — live particles re-cache one rotate next frame,
#: which is invisible, whereas unbounded growth is a slow leak under endless
#: survival churn.
_ROT_CACHE_MAX = 256


def _rot_cached(key, make):
    img = _rot_cache.get(key)
    if img is None:
        if len(_rot_cache) >= _ROT_CACHE_MAX:
            _rot_cache.clear()
        img = _rot_cache[key] = make()
    return img


def _leaf_rotated(color, radius, rot):
    """Cached 15°-step variants of a rotated leaf, so a spinning burst never
    allocates a ``transform.rotate`` per particle per frame (the old draw
    path re-rotated every leaf every frame while its spin ran)."""
    return _rot_cached(
        ("leaf", color, _quantize(radius), int((rot % 360) / 15)),
        lambda: pygame.transform.rotate(_leaf(color, radius), rot))


def _shred_rotated(color, radius, rot):
    """See :func:`_leaf_rotated` — same 15° ladder for balloon shreds."""
    return _rot_cached(
        ("shred", color, _quantize(radius), int((rot % 360) / 15)),
        lambda: pygame.transform.rotate(_shred(color, radius), rot))


_print_cache = {}


def _print_sprite(color, w, h):
    """A pressed-grass footprint at a fixed size, cached per (colour, w, h).

    The old draw path ``transform.scale`` + ``set_alpha`` ran once per print
    per frame — scaling a blurry puff and stamping a persistent alpha on the
    result. Building the squashed puff here once per (size * colour) means a
    steady lawn only does ``_faded`` (memoized) + blit per footprint."""
    key = ("print", color, w, h)
    img = _print_cache.get(key)
    if img is None:
        base = _puff(color, w / 2.0)
        img = pygame.transform.scale(base, (w, h))
        _print_cache[key] = img
    return img


#: Beams sweep across a lawn as sources and targets move, so a beam cache has
#: no natural size ceiling. Bound it; on overflow drop the whole set — the few
#: live beams re-cache on the next frame, so eviction is invisible.
_BEAM_CACHE_MAX = 192
_beam_cache = {}


def _beam_sprite(color, x1, y1, x2, y2, alpha, w):
    """A mending/rally beam between two fixed points at a fixed alpha, cached.

    The endpoints are pre-quantized by the caller, so one beam's flicker only
    re-keys every ~4px of travel — the same texture is reused across frames
    instead of a fresh SRCALPHA surface + two strokes every frame."""
    key = ("beam", color, x1, y1, x2, y2, alpha, w)
    surf = _beam_cache.get(key)
    if surf is None:
        if len(_beam_cache) >= _BEAM_CACHE_MAX:
            _beam_cache.clear()
        surf = pygame.Surface((abs(x2 - x1) + w * 2 + 2, abs(y2 - y1) + w * 2 + 2),
                              pygame.SRCALPHA)
        ox = min(x1, x2) - w - 1
        oy = min(y1, y2) - w - 1
        pygame.draw.line(surf, (*color, alpha),
                         (x1 - ox, y1 - oy), (x2 - ox, y2 - oy), w)
        pygame.draw.line(surf, (255, 255, 255, alpha // 2),
                         (x1 - ox, y1 - oy), (x2 - ox, y2 - oy), max(1, w // 3))
        _beam_cache[key] = surf
    return surf


_ring_cache = {}


def _ring_sprite(color, radius, width, inner=True):
    q = _quantize(radius)
    key = ("ring", color, q, width, inner)
    img = _ring_cache.get(key)
    if img is None:
        img = pygame.Surface((q * 2 + 4, q * 2 + 4), pygame.SRCALPHA)
        c = q + 2
        pygame.draw.circle(img, (*color, 220), (c, c), q, width)
        if inner and q > 8:
            pygame.draw.circle(img, (*color, 70), (c, c), int(q * 0.55), max(1, width // 2))
        _ring_cache[key] = img
    return img


# ------------------------------------------------------------------ particle
class Particle:
    """A single short-lived effect. Fields are slotted; bursts are pooled."""

    __slots__ = ("x", "y", "vx", "vy", "life", "max_life", "size", "color",
                 "kind", "gravity", "drag", "rot", "spin", "layer", "alive",
                 "r0", "r1", "delay", "x2", "y2", "width", "fade_in", "flat")

    def __init__(self):
        self.alive = False
        self.reset()

    def reset(self):
        self.x = self.y = 0.0
        self.vx = self.vy = 0.0
        self.life = self.max_life = 1.0
        self.size = 3.0
        self.color = (255, 255, 255)
        self.kind = "dot"
        self.gravity = 0.0
        self.drag = 0.0
        self.rot = 0.0
        self.spin = 0.0
        self.layer = 1          # 0 = ground (under actors), 1 = air (over)
        self.alive = True
        self.r0 = self.r1 = 0.0
        self.delay = 0.0
        self.x2 = self.y2 = 0.0
        self.width = 2
        self.fade_in = 0.0
        self.flat = False       # ground-plane sprite (drawn squashed)


# ------------------------------------------------------------------ effects
class Effects:
    """Owns every transient visual effect in a level."""

    #: hard caps so a pathological frame cannot grow the pools without bound
    MAX_PER_LAYER = 900

    def __init__(self):
        self._pool = []
        self.ground = []
        self.air = []
        self._count = 0

    # ---------------------------------------------------------- pool plumbing
    def _new(self):
        if self._pool:
            p = self._pool.pop()
            p.reset()
            return p
        return Particle()

    def _emit(self, **kw):
        layer = kw.get("layer", 1)
        if len(self.ground) + len(self.air) >= self.MAX_PER_LAYER:
            return None
        p = self._new()
        for k, v in kw.items():
            setattr(p, k, v)
        p.max_life = max(0.001, p.max_life)
        p.life = p.max_life
        (self.ground if layer == 0 else self.air).append(p)
        return p

    def clear(self):
        for p in self.ground:
            p.alive = False
            self._pool.append(p)
        for p in self.air:
            p.alive = False
            self._pool.append(p)
        self.ground = []
        self.air = []

    @property
    def count(self):
        return len(self.ground) + len(self.air)

    # -------------------------------------------------------------- emitters
    def soil_poof(self, x, y):
        """Brown ground puff + a few soil clods, when planting or digging up."""
        self._emit(layer=0, kind="puff", x=x, y=y, size=34, max_life=0.34,
                   color=(122, 88, 48), flat=True)
        for i in range(4):
            ang = (i / 4.0) * math.tau
            self._emit(x=x + math.cos(ang) * 4, y=y - 2,
                       vx=math.cos(ang) * 46, vy=-120 - (i * 7) % 30,
                       gravity=430, size=2.6 + (i % 2) * 0.6,
                       max_life=0.42, color=(104, 76, 42), kind="dot")

    def plant_debris(self, x, y, palette=((90, 180, 80),)):
        """Leaf/petal burst when a plant is destroyed.

        ``palette`` is the species tint list; each leaf picks its own colour
        so the burst reads as torn foliage rather than a flash of one hue.
        """
        for i in range(9):
            ang = (i / 9.0) * math.tau + random.uniform(-0.3, 0.3)
            spd = random.uniform(60, 210)
            self._emit(x=x, y=y, vx=math.cos(ang) * spd,
                       vy=math.sin(ang) * spd - 90, gravity=420, drag=0.9,
                       size=random.uniform(2.5, 4.6), max_life=random.uniform(0.55, 1.0),
                       color=random.choice(palette), kind="leaf",
                       spin=random.uniform(-9, 9))

    def pea_impact(self, x, y, is_fume=False, is_frost=False):
        """Impact spark burst where a projectile lands."""
        if is_fume:
            base = (200, 120, 240)
        elif is_frost:
            base = (170, 230, 255)
        else:
            base = (255, 240, 140)
        for i in range(6):
            ang = random.uniform(0, math.tau)
            spd = random.uniform(90, 320)
            self._emit(x=x, y=y, vx=math.cos(ang) * spd, vy=math.sin(ang) * spd - 40,
                       drag=3.2, size=random.uniform(1.8, 3.4),
                       max_life=random.uniform(0.14, 0.3),
                       color=base if i else (255, 255, 255), kind="dot")
        self._emit(x=x, y=y, kind="ring", r0=2, r1=17, width=2, max_life=0.22,
                   color=base)

    def balloon_pop(self, x, y):
        """Red rubber shreds flying outward."""
        for i in range(12):
            ang = random.uniform(0, math.tau)
            spd = random.uniform(80, 260)
            self._emit(x=x, y=y, vx=math.cos(ang) * spd, vy=math.sin(ang) * spd - 70,
                       gravity=200, drag=1.8, size=random.uniform(3, 6),
                       max_life=random.uniform(0.45, 0.85),
                       color=(208, 44, 44), kind="shred",
                       spin=random.uniform(-12, 12))
        self._emit(x=x, y=y, kind="ring", r0=6, r1=44, width=3, max_life=0.32,
                   color=(240, 110, 100))

    def mow_dust(self, x, y, big=False):
        n = 7 if big else 3
        for i in range(n):
            self._emit(x=x + random.uniform(-6, 6), y=y + random.uniform(-4, 8),
                       vx=random.uniform(-90, -30), vy=random.uniform(-40, 10),
                       drag=1.5, size=random.uniform(4, 9) if big else random.uniform(3, 6),
                       max_life=random.uniform(0.3, 0.6),
                       color=(186, 180, 166), kind="puff")

    def zombie_chunks(self, x, y, tint=(120, 120, 126)):
        """Bone/gore chunks thrown when a zombie dies."""
        for i in range(6):
            ang = random.uniform(-math.pi, 0)
            spd = random.uniform(70, 230)
            self._emit(x=x, y=y, vx=math.cos(ang) * spd, vy=math.sin(ang) * spd,
                       gravity=520, drag=0.4, size=random.uniform(2.5, 5),
                       max_life=random.uniform(0.6, 1.0),
                       color=tint, kind="chunk", spin=random.uniform(-7, 7))

    def grass_print(self, x, y, w=30, h=13):
        """Faint pressed-grass footprint under a walking zombie."""
        self._emit(layer=0, kind="print", x=x, y=y, size=w,
                   max_life=1.1, color=(58, 78, 38), flat=True, r0=h)

    def dig_dust(self, x, y):
        """Dirt spray from a tunnelling digger."""
        for i in range(3):
            self._emit(x=x + random.uniform(-8, 8), y=y,
                       vx=random.uniform(-70, 70), vy=random.uniform(-150, -60),
                       gravity=520, size=random.uniform(2, 4.5),
                       max_life=random.uniform(0.3, 0.6),
                       color=(112, 84, 46), kind="dot")
        self._emit(layer=0, kind="puff", x=x, y=y + 8, size=20, max_life=0.45,
                   color=(126, 94, 52), flat=True)

    def hop_trail(self, x, y0, y1, x_end):
        """Dashed arc marking a tactician's lane change."""
        steps = 6
        for i in range(steps):
            t = i / float(steps - 1)
            ease = t * t * (3.0 - 2.0 * t)
            y = y0 + (y1 - y0) * ease - math.sin(t * math.pi) * 26.0
            self._emit(kind="dot", x=x, y=y, size=2.6, max_life=0.42 + 0.12 * t,
                       color=(168, 138, 240), vx=-10)

    def beam(self, x1, y1, x2, y2, color, duration=0.42, width=3):
        """Mending / rally beam between two points."""
        self._emit(kind="beam", x=x1, y=y1, x2=x2, y2=y2, color=color,
                   max_life=duration, width=width)

    def ring(self, x, y, r0, r1, color, duration=0.5, delay=0.0, width=3,
             layer=1):
        """Expanding shockwave / release ring."""
        p = self._emit(x=x, y=y, kind="ring", r0=r0, r1=r1, color=color,
                       max_life=duration, delay=delay, width=width, layer=layer)
        return p

    def burst(self, x, y, color, n=10, speed=(60, 260), size=(2, 4.5),
              life=(0.3, 0.7), gravity=380, kind="dot"):
        """Generic radial spray — used for death sparks and pickup pops."""
        for _ in range(n):
            ang = random.uniform(0, math.tau)
            spd = random.uniform(*speed)
            self._emit(x=x, y=y, vx=math.cos(ang) * spd,
                       vy=math.sin(ang) * spd - 40, gravity=gravity, drag=1.2,
                       size=random.uniform(*size),
                       max_life=random.uniform(*life), color=color, kind=kind)

    # ---------------------------------------------------------------- update
    def update(self, dt):
        for pool in (self.ground, self.air):
            for p in pool:
                if p.delay > 0:
                    p.delay -= dt
                    continue
                p.life -= dt
                if p.life <= 0:
                    p.alive = False
                    continue
                if p.vx or p.vy or p.gravity:
                    p.x += p.vx * dt
                    p.y += p.vy * dt
                    p.vy += p.gravity * dt
                    if p.drag:
                        k = max(0.0, 1.0 - p.drag * dt)
                        p.vx *= k
                        p.vy *= k
                if p.spin:
                    p.rot += p.spin * dt
        self._sweep(self.ground)
        self._sweep(self.air)

    def _sweep(self, pool):
        if not any(not p.alive for p in pool):
            return
        keep = []
        for p in pool:
            if p.alive:
                keep.append(p)
            else:
                self._pool.append(p)
        pool[:] = keep

    # ------------------------------------------------------------------ draw
    def draw_ground(self, screen):
        for p in self.ground:
            if p.delay <= 0:
                self._draw_one(screen, p)

    def draw_air(self, screen):
        for p in self.air:
            if p.delay <= 0:
                self._draw_one(screen, p)

    def _draw_one(self, screen, p):
        kind = p.kind
        if kind == "print":
            self._draw_print(screen, p)
            return
        if kind == "ring":
            self._draw_ring(screen, p)
            return
        if kind == "beam":
            self._draw_beam(screen, p)
            return

        t = 1.0 - p.life / p.max_life          # 0 → 1 over the lifetime
        if kind == "dot":
            img = _dot(p.color, p.size * (1.0 - 0.35 * t))
        elif kind == "puff":
            img = _puff(p.color, p.size * (1.0 + 0.9 * t))
        elif kind == "leaf":
            img = _leaf(p.color, p.size * (1.0 - 0.3 * t))
            if p.rot:
                # p.rot accumulates in radians (spin is rad/s) but
                # transform.rotate takes degrees — converting here makes the
                # 15° bins actually advance during the particle's lifetime.
                img = _leaf_rotated(p.color, p.size * (1.0 - 0.3 * t),
                                    math.degrees(p.rot))
        elif kind == "shred":
            img = _shred(p.color, p.size * (1.0 - 0.2 * t))
            if p.rot:
                img = _shred_rotated(p.color, p.size * (1.0 - 0.2 * t),
                                     math.degrees(p.rot))
        elif kind == "chunk":
            img = _dot(p.color, p.size * (1.0 - 0.3 * t))
        else:
            img = _dot(p.color, p.size)

        fade = 1.0 - t
        if p.fade_in > 0 and t < p.fade_in:
            fade = t / p.fade_in
        # img may be a shared cached sprite (dot/puff/un-rotated leaf) —
        # fade via copy so the cache never keeps a leaked surface alpha
        img = _faded(img, int(255 * max(0.0, min(1.0, fade))))
        screen.blit(img, img.get_rect(center=(int(p.x), int(p.y))))

    def _draw_print(self, screen, p):
        t = 1.0 - p.life / p.max_life
        # fade in fast, out slow — a footprint presses then lifts
        alpha = int(84 * (t / 0.15)) if t < 0.15 else int(84 * (1.0 - (t - 0.15) / 0.85))
        if alpha <= 0:
            return
        w = int(p.size * (1.0 + 0.25 * t))
        h = max(3, int(p.r0 * (1.0 + 0.25 * t)))
        # Quantize the size pair onto a coarse ladder so the scale cache
        # stays small (a footprint is ~30x13 and grows 25% — ~6 entries).
        wq = ((w + 2) // 4) * 4
        hq = max(3, ((h + 1) // 2) * 2)
        img = _print_sprite(p.color, wq, hq)
        # Never set_alpha on the shared cached sprite — fade via copy.
        screen.blit(_faded(img, alpha), img.get_rect(center=(int(p.x), int(p.y))))

    def _draw_ring(self, screen, p):
        t = 1.0 - p.life / p.max_life
        ease = 1.0 - (1.0 - t) ** 2
        radius = p.r0 + (p.r1 - p.r0) * ease
        alpha = int(220 * (1.0 - t))
        if alpha <= 0 or radius < 1:
            return
        img = _ring_sprite(p.color, radius, p.width)
        screen.blit(_faded(img, alpha), img.get_rect(center=(int(p.x), int(p.y))))

    def _draw_beam(self, screen, p):
        t = 1.0 - p.life / p.max_life
        alpha = int(230 * math.sin(min(1.0, t) * math.pi) * 1.4)
        alpha = max(0, min(255, alpha))
        if alpha <= 0:
            return
        w = max(2, int(p.width * (1.0 - 0.4 * t)))
        # Constant-grid beam: quantize size + colour so the scratch surface
        # (and its two strokes) is cached per frame-instance rather than
        # freshly allocated for every particle every frame.
        wq = ((w + 1) // 2) * 2
        x1q, y1q = int(p.x) & ~3, int(p.y) & ~3
        x2q, y2q = int(p.x2) & ~3, int(p.y2) & ~3
        surf = _beam_sprite(p.color, x1q, y1q, x2q, y2q, alpha, wq)
        screen.blit(surf, (min(x1q, x2q) - wq - 1, min(y1q, y2q) - wq - 1))
