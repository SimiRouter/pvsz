"""Game entities: plants, zombies, projectiles, sun."""

import pygame
import math
import random
import assets_loader
import fx
from constants import *

# ============================================================
# Projectile
# ============================================================
# Pre-rendered pea / fume sprites + trails. Building a 42x18 SRCALPHA surface
# with three circles *per projectile per frame* was the biggest hidden cost in
# heavy fights; these are built once, lazily, and blitted forever after.
_sprite_cache = {}


def _ball_sprite(color, rim, core):
    key = ("ball", color)
    img = _sprite_cache.get(key)
    if img is None:
        img = pygame.Surface((22, 22), pygame.SRCALPHA)
        pygame.draw.circle(img, rim, (11, 11), 10)
        pygame.draw.circle(img, (40, 70, 20), (11, 11), 10, 2)
        pygame.draw.circle(img, core, (11, 11), 7)
        pygame.draw.circle(img, COLOR_WHITE, (9, 9), 2)
        _sprite_cache[key] = img
    return img


def _trail_sprite(trail_color):
    key = ("trail", trail_color)
    img = _sprite_cache.get(key)
    if img is None:
        img = pygame.Surface((42, 18), pygame.SRCALPHA)
        for i, (radius, alpha) in enumerate(((6, 45), (5, 75), (4, 110))):
            pygame.draw.circle(img, (*trail_color, alpha), (8 + i * 9, 9), radius)
        _sprite_cache[key] = img
    return img


class Projectile:
    def __init__(self, x, y, row, damage=20, speed=380, color=(255, 255, 0),
                 freezes=False, freeze_seconds=4.0):
        self.x = x
        self.y = y
        self.prev_x = x
        self.row = row
        self.damage = damage
        self.speed = speed
        self.color = color
        self.w = 16
        self.h = 16
        self.alive = True
        self.anim_time = 0.0
        self.is_fume = color[2] > color[1] * 1.6
        # Snow Pea-style: hit applies a freeze debuff on the zombie
        self.freezes = freezes
        self.freeze_seconds = freeze_seconds

    def update(self, dt):
        self.prev_x = self.x
        self.x += self.speed * dt
        self.anim_time += dt
        if self.x > SCREEN_WIDTH:
            self.alive = False

    def draw(self, screen):
        cx = int(self.x + self.w // 2)
        cy = int(self.y + self.h // 2)
        # motion trail: makes the horizontal firing lane legible on every lawn
        if self.is_fume:
            screen.blit(_trail_sprite((205, 85, 255)), (cx - 40, cy - 9))
            ball = _ball_sprite("fume", (245, 175, 255), (185, 45, 235))
            screen.blit(ball, ball.get_rect(center=(cx, cy)))
        else:
            screen.blit(_trail_sprite((190, 255, 80)), (cx - 40, cy - 9))
            ball = _ball_sprite("pea", (255, 235, 60), (115, 215, 35))
            screen.blit(ball, ball.get_rect(center=(cx, cy)))

    def rect(self):
        return pygame.Rect(int(self.x), int(self.y), self.w, self.h)

    def swept_rect(self):
        """Collision bounds covering the full distance moved this frame."""
        left = int(min(self.prev_x, self.x))
        right = int(max(self.prev_x, self.x) + self.w)
        return pygame.Rect(left, int(self.y), max(1, right - left), self.h)


# ============================================================
# Sun
# ============================================================
class _Pickup:
    """Shared life cycle for a sun / plant-food vial: fall, bounce, expire.

    Both pickups used to run their own near-identical two-line physics
    (``self.y += 60 * dt`` then ``self.alive = False``) in separate classes.
    Lifting the motion into one base means the trajectories, the bounce feel
    and the expiry warning stay in sync, and there is one place to tune them.

    States, in order:

    ``eject``   ballistic pop out of a sunflower (only for plant-produced sun)
    ``fall``    gravity-accelerated descent with a terminal velocity + sway
    ``bounce``  2-3 damped rebounds that actually move the body
    ``rest``    settled on the lawn, gently bobbing
    ``fading``  last ``EXPIRE_WARN_S`` seconds: blink, shrink, tilt out
    ``collect`` fly into the jar / energy counter

    Subclasses supply :meth:`_motion_done` and :meth:`_draw_body`.
    """

    # Tuning shared by sun and plant food. The fall is gravity driven but
    # capped, so a sun dropped from the top of the screen takes about two
    # seconds to reach the lawn — slow enough to click, fast enough to feel
    # alive rather than floaty.
    GRAVITY = 640.0
    TERMINAL_VY = 215.0
    SWAY_AMP = 13.0          # peak horizontal excursion, in px
    SWAY_HZ = 0.85
    EJECT_GRAVITY = 700.0
    # 0.62 gives a first hop of ~14 px, then ~5, then ~2 — a visible decay
    # that still reads as "landed" rather than "bouncing ball".
    BOUNCE_RESTITUTION = 0.62
    BOUNCE_COUNT = 3
    EXPIRE_WARN_S = 3.0      # how long the fade-out warning lasts

    def _init_motion(self, x, y):
        self.x = float(x)
        self.y = float(y)
        self.vx = 0.0
        self.vy = 0.0
        self.phase = "fall"          # see the class docstring
        self.alive = True
        self.falling = True          # kept: gameplay code checks this
        self.bounces_left = 0
        self.squash = 0.0            # 0..1 impact squash, decays
        self.alpha = 255
        self.scale = 1.0
        self.tilt = 0.0              # degrees, used by the fade-out
        self.age = 0.0
        self.settled_age = 0.0
        self._sway_phase = 0.0
        self._sway_x0 = self.x        # centre line the sway oscillates around
        self._sway_dir = random.choice((-1.0, 1.0))
        self._landed_pending = False  # drained by the game layer for FX

    # ------------------------------------------------------------- motion
    def _start_fall(self, target_y, speed=0.0):
        self.target_y = float(target_y)
        self.phase = "fall"
        self.falling = True
        self.vy = speed
        # Re-anchor the sway from wherever the eject arc left off, and restart
        # the phase at zero so the descent begins exactly on the centre line.
        self._sway_x0 = self.x
        self._sway_phase = 0.0

    def _step_motion(self, dt):
        """Advance one frame. Returns True when the caller should stop."""
        self.age += dt
        if self.squash > 0:
            self.squash = max(0.0, self.squash - dt * 5.0)
        if self.phase == "collect":
            return self._step_collect(dt)

        if self.phase == "eject":
            self.vy += self.EJECT_GRAVITY * dt
            self.x += self.vx * dt
            self.y += self.vy * dt
            # Once the pop has turned over and we are heading back down,
            # hand off to the normal descent.
            if self.vy > 0 and self.y >= self.target_y:
                self._start_fall(self.target_y, self.vy)
            return False

        if self.phase == "fall":
            self.vy = min(self.TERMINAL_VY, self.vy + self.GRAVITY * dt)
            self.y += self.vy * dt
            # Sway: a slow horizontal drift so sky suns don't fall down a
            # ruler-straight line. Placed absolutely against the centre line
            # rather than integrated — integrating a sinusoid as a velocity
            # divides the amplitude by 2*pi*f, which made a 13 px setting
            # drift a barely visible 2.4 px.
            self._sway_phase += math.tau * self.SWAY_HZ * dt
            self.x = (self._sway_x0
                      + math.sin(self._sway_phase) * self.SWAY_AMP * self._sway_dir)
            if self.y >= self.target_y:
                self.y = self.target_y
                self._on_land()
            return False

        if self.phase == "bounce":
            self.vy += self.GRAVITY * dt
            self.y += self.vy * dt
            if self.y >= self.target_y:
                self.y = self.target_y
                self.bounces_left -= 1
                if self.bounces_left <= 0:
                    self.rest_y = self.target_y
                    self.phase = "rest"
                    self.settled_age = 0.0
                    self.falling = False
                    self.vy = 0.0
                    # The final settle is still an impact — a soft squash so
                    # the sun "thuds" to rest instead of snapping still
                    # (审计发现：只有前几次落地有形变，最后一次没有).
                    self.squash = 0.6
                else:
                    self.vy = -abs(self.vy) * self.BOUNCE_RESTITUTION
                    self.squash = 1.0
            return False

        if self.phase == "rest":
            self.settled_age += dt
            if self.settled_age >= self.lifetime() - self.EXPIRE_WARN_S:
                self.phase = "fading"
            return False

        if self.phase == "fading":
            self.settled_age += dt
            left = self.lifetime() - self.settled_age
            t = max(0.0, min(1.0, left / self.EXPIRE_WARN_S))
            # Blink faster as it runs out, shrink, and sag over.
            blink = 0.55 + 0.45 * math.sin(self.settled_age * (10.0 + 26.0 * (1.0 - t)))
            self.alpha = int(255 * t * (0.5 + 0.5 * blink))
            self.scale = 0.55 + 0.45 * t
            self.tilt = (1.0 - t) * 16.0
            if left <= 0:
                self.alive = False
            return False
        return False

    def _on_land(self):
        """First contact with the lawn: start the rebound and flag the game."""
        # ``falling`` means "still in the air, not yet clickable" — the
        # rebound happens *on* the lawn, so the pickup is already grabbable
        # and the flag clears here rather than after the last bounce.
        self.falling = False
        if self.bounces_left > 0:
            self.phase = "bounce"
            self.vy = -abs(self.vy) * self.BOUNCE_RESTITUTION
        else:
            self.phase = "rest"
            self.settled_age = 0.0
            self.vy = 0.0
        self.squash = 1.0
        self._landed_pending = True

    def _step_collect(self, dt):
        self._ct += dt / self._cdur
        t = min(1.0, self._ct)
        self._motion_collect(t, dt)
        if self._ct >= 1.0:
            self.arrived = True
            self.alive = False
        return True

    def _motion_collect(self, t, dt):
        ease = t * t
        self.x = self._cx0 + (self._ctarget[0] - self._cx0) * ease
        self.y = self._cy0 + (self._ctarget[1] - self._cy0) * ease

    # ------------------------------------------------------------- helpers
    def lifetime(self):
        raise NotImplementedError

    def visible_rect(self):
        r = 20
        return pygame.Rect(self.x - r, self.y - r, r * 2, r * 2)

    def rect(self):
        r = SUN_COLLECT_RADIUS
        cx, cy = self._visual_center()
        return pygame.Rect(cx - r, cy - r, r * 2, r * 2)

    def _visual_center(self):
        """Where the sprite is actually drawn this frame.

        ``rect`` has to be built around this, not around the raw physics
        position — the resting bob is a draw-only offset, so a sun drawn 2 px
        high used to have its click box 2 px low (阳光点击不跟手的来源之一).
        """
        return self.x, self.y

    def contains(self, mx, my):
        """Circular hit test matching the round sprite.

        ``rect().collidepoint`` is a square: corners sit ~10 px outside the
        visible disc and the top/bottom middles ~10 px inside it, so clicks
        near the sun's edge failed while clicks on empty lawn beside it won.
        """
        if self.collected:
            return False
        cx, cy = self._visual_center()
        r = SUN_COLLECT_RADIUS
        return (mx - cx) ** 2 + (my - cy) ** 2 <= r * r


class Sun(_Pickup):
    """A sun: falls from the sky or pops out of a sunflower, then waits.

    阳光出现轨迹 — a sunflower's sun leaves on a real ballistic arc (up, over,
    down) rather than the old "nudge y by 30px and hand off", and a sky sun
    drifts sideways as it falls so a row of them doesn't look like a sprite
    sheet being scrolled.

    反弹轨迹 — landing plays 3 damped rebounds that actually move the body,
    with a squash on each impact, instead of a 6px sine offset that never
    touched the ground.

    消失机制 — an uncollected sun no longer pops out of existence. It blinks
    and shrinks for the last three seconds, so an expiring sun reads as a
    warning you can still act on.
    """

    def __init__(self, x, y):
        self._init_motion(x, y)
        self.target_y = float(y)
        self.collect_radius = 30
        self.angle = 0.0
        self.amount = SUN_VALUE       # sunflowers at higher level give more
        # Collect-flight state
        self.collected = False
        self.arrived = False
        self._cx0 = self._cy0 = 0.0
        self._ctarget = (0.0, 0.0)
        self._ct = 0.0
        self._cdur = 0.3
        self.collect_scale = 1.0

    def lifetime(self):
        return SUN_LIFETIME / 1000.0

    def eject(self, vy=-210.0, vx=None, target_y=None):
        """Pop out of a sunflower head: an upward kick on a ballistic arc."""
        self.phase = "eject"
        self.vy = vy
        self.vx = vx if vx is not None else random.uniform(-34.0, 34.0)
        self.target_y = float(target_y if target_y is not None else self.y + 46)
        self.falling = True

    def drop_from_sky(self, target_y):
        """Enter from above and accelerate down to ``target_y``."""
        self.bounces_left = self.BOUNCE_COUNT
        self._start_fall(target_y, speed=0.0)

    def collect(self, target):
        """Start the flight into the sun jar; game credits the sun on arrival."""
        if self.collected:
            return
        self.collected = True
        self.falling = False
        self.phase = "collect"
        # A sun clicked during its expiry blink must not keep fading while it
        # flies to the jar — restore full opacity for the collect animation.
        self.alpha = 255
        self._cx0, self._cy0 = self.x, self.y
        self._ctarget = (float(target[0]), float(target[1]))
        dist = math.hypot(self._ctarget[0] - self.x, self._ctarget[1] - self.y)
        self._cdur = max(0.22, min(0.5, dist / 2400.0))
        self._ct = 0.0

    def _motion_collect(self, t, dt):
        ease = t * t                       # accelerate into the jar
        self.x = self._cx0 + (self._ctarget[0] - self._cx0) * ease
        self.y = self._cy0 + (self._ctarget[1] - self._cy0) * ease
        self.collect_scale = 1.0 - 0.35 * t

    def update(self, dt, hovered=False):
        self.angle += 2.2 * dt
        # Cursor parked on a sun suspends its motion: fall, rebound, resting
        # bob and the expiry blink all hold their breath while the sun is
        # hovered (阳光停在光标下), resuming the instant the cursor leaves.
        # The spin keeps turning so it still reads as alive. The game passes
        # ``hovered`` from its own per-frame hit test, so the freeze region
        # is exactly the click/hover circle — no second geometry to drift.
        if hovered and not self.collected:
            return
        self._step_motion(dt)
        return 0

    def _visual_center(self):
        bob = math.sin(self.age * 2.4) * 2.0 if self.phase == "rest" else 0.0
        return self.x, self.y + bob

    def draw(self, screen):
        base = SUN_SPRITE_SIZE
        # Spin the sprite at its natural size first, then deform. Doing it the
        # other way round — scaling to (w, h) and *then* rotating, which is what
        # assets_loader.rotated does internally — drags the squash axis around
        # with the sprite: at a 90 degrees step the "wide and short" impact
        # squash rendered tall and narrow. It also minted a fresh cache entry
        # per distinct (w, h, step) triple, so the 0.2 s squash animation
        # allocated ~15 throwaway surfaces every landing.
        img = assets_loader.rotated("ui_sun", base, base, int((self.angle * 18) / 15))
        # Single source of truth for the resting bob: the click/hover tests
        # read the same _visual_center the sprite is drawn through.
        cx, cy = (int(v) for v in self._visual_center())
        if img is None:
            pygame.draw.circle(screen, COLOR_YELLOW, (cx, cy), base // 2)
            pygame.draw.circle(screen, COLOR_ORANGE, (cx, cy), base // 2, 2)
            return
        if self.tilt:
            img = pygame.transform.rotate(img, self.tilt)
        # Screen-space deformation: wide-and-short on impact, uniform shrink
        # while flying into the jar.
        if self.phase == "collect":
            sx = sy = self.collect_scale
        else:
            sx = self.scale * (1.0 + 0.30 * self.squash)
            sy = self.scale * (1.0 - 0.26 * self.squash)
        if abs(sx - 1.0) > 0.01 or abs(sy - 1.0) > 0.01:
            w = max(8, int(img.get_width() * sx))
            h = max(8, int(img.get_height() * sy))
            img = pygame.transform.smoothscale(img, (w, h))
        if self.alpha < 255:
            img = fx.faded(img, self.alpha)
        screen.blit(img, img.get_rect(center=(cx, cy)))


# ============================================================
# Plant Food (能量豆 — PvZ2 signature pickup)
# ============================================================
_food_glow_cache = {}


class PlantFood(_Pickup):
    """The 能量豆 vial: drops from the sky, then waits to be fed to a plant.

    Shares the whole motion life cycle with :class:`Sun` — gravity-driven
    fall, one heavy rebound on landing, and the same blink-and-shrink expiry
    warning instead of vanishing mid-thought.
    """

    def __init__(self, x, y):
        self._init_motion(x, y)
        self.target_y = float(y)
        self.bounces_left = 1        # a vial thuds rather than bounces
        # Fly-to-jar curve animation. Mirrors Sun.collect but uses an arc
        # (up-then-over parabola) and a rolling sprite rotation so the vial
        # visibly tumbles into the energy jar instead of teleporting.
        self.collected = False
        self.arrived = False
        self._cx0 = self._cy0 = 0.0
        self._ctarget = (0.0, 0.0)
        self._ct = 0.0
        self._cdur = 0.5
        self.collect_angle = 0.0
        self.collect_scale = 1.0

    def collect(self, target):
        """Start the arc flight into the energy jar; game credits on arrival."""
        if self.collected or self.falling:
            # Wait for it to land first — collecting a vial mid-air feels
            # cheap and clashes with the existing fall-and-bounce motion.
            return False
        self.collected = True
        self.falling = False
        self.phase = "collect"
        self._cx0, self._cy0 = self.x, self.y
        self._ctarget = (float(target[0]), float(target[1]))
        dist = math.hypot(self._ctarget[0] - self.x, self._ctarget[1] - self.y)
        self._cdur = max(0.45, min(0.9, dist / 1800.0))
        self._ct = 0.0
        self.collect_angle = 0.0
        self.collect_scale = 1.0
        return True

    def lifetime(self):
        return PLANT_FOOD_LIFETIME / 1000.0

    def drop_from_sky(self, target_y):
        """Enter from above and accelerate down to ``target_y``."""
        self.bounces_left = 1
        self._start_fall(target_y, speed=0.0)

    def _motion_collect(self, t, dt):
        # ease-in-out (smoother than t*t) — feels like a real toss
        ease = t * t * (3.0 - 2.0 * t)
        self.x = self._cx0 + (self._ctarget[0] - self._cx0) * ease
        # Parabolic arc: peak height scales with horizontal distance.
        peak = max(60.0, math.hypot(self._ctarget[0] - self._cx0,
                                    self._ctarget[1] - self._cy0) * 0.25)
        self.y = self._cy0 + (self._ctarget[1] - self._cy0) * ease \
                 - peak * 4.0 * t * (1.0 - t)
        # Roll the sprite so it visibly tumbles during flight.
        self.collect_angle += 720.0 * dt
        # Shrink toward the end so it "lands in" the jar.
        self.collect_scale = 1.0 - 0.55 * t

    def update(self, dt):
        self._step_motion(dt)

    def draw(self, screen):
        if self.collected:
            cx, cy = int(self.x), int(self.y)
            # spin + shrink during collect flight
            r = max(2, int(13 * self.collect_scale))
            # trailing after-image (only visible mid-flight)
            if self._ct < 0.7:
                trail_n = 3
                for i in range(trail_n):
                    t_trail = max(0.0, self._ct - 0.05 * (i + 1))
                    ease_trail = t_trail * t_trail * (3.0 - 2.0 * t_trail)
                    tx = self._cx0 + (self._ctarget[0] - self._cx0) * ease_trail
                    ty = self._cy0 + (self._ctarget[1] - self._cy0) * ease_trail
                    tr = max(2, int(r * (1.0 - 0.15 * (i + 1))))
                    alpha = 80 - 25 * i
                    ghost = pygame.Surface((r * 4 + 4, r * 4 + 4), pygame.SRCALPHA)
                    pygame.draw.circle(ghost, (80, 200, 60, alpha),
                                       (tr * 2 + 2, tr * 2 + 2), tr)
                    screen.blit(ghost, ghost.get_rect(center=(int(tx), int(ty))))
            # main body
            pygame.draw.circle(screen, (80, 200, 60), (cx, cy), r)
            pygame.draw.circle(screen, (40, 140, 40), (cx, cy), r, 2)
            pygame.draw.circle(screen, (220, 255, 200),
                               (cx - r // 3, cy - r // 3), max(2, r // 3))
            # lightning-bolt rotated with the roll angle
            ang = math.radians(self.collect_angle)
            cos_a, sin_a = math.cos(ang), math.sin(ang)
            pts = [(-2, -6), (3, -1), (-1, 0), (2, 6)]
            rot = [(int(cx + x*cos_a - y*sin_a), int(cy + x*sin_a + y*cos_a))
                   for x, y in pts]
            pygame.draw.lines(screen, (255, 255, 210), False, rot, 2)
            return
        pulse = 1.0 + 0.10 * math.sin(self.age * 5)
        glow = _food_glow_cache.get("glow")
        if glow is None:
            glow = pygame.Surface((64, 64), pygame.SRCALPHA)
            for r, a in ((30, 40), (24, 60), (18, 80)):
                pygame.draw.circle(glow, (120, 255, 120, a), (32, 32), r)
            _food_glow_cache["glow"] = glow
        # fx.faded copies before stamping — the glow surface is a shared cache
        glow = fx.faded(glow, int(140 + 90 * math.sin(self.age * 5)))
        screen.blit(glow, glow.get_rect(center=(int(self.x), int(self.y))))
        r = int(13 * pulse)
        pygame.draw.circle(screen, (80, 200, 60), (int(self.x), int(self.y)), r)
        pygame.draw.circle(screen, (40, 140, 40), (int(self.x), int(self.y)), r, 2)
        pygame.draw.circle(screen, (220, 255, 200),
                           (int(self.x) - r // 3, int(self.y) - r // 3), max(2, r // 3))
        # the signature lightning-bolt marking
        bx, by = int(self.x), int(self.y)
        pygame.draw.lines(screen, (255, 255, 210), False,
                          [(bx - 2, by - 6), (bx + 3, by - 1), (bx - 1, by),
                           (bx + 2, by + 6)], 2)

    def rect(self):
        return pygame.Rect(self.x - 22, self.y - 22, 44, 44)


# ============================================================
# Plants
# ============================================================
def _spawn_dy(plant):
    """Drop-in offset for a freshly planted plant (spawn_t counts 0.25 → 0)."""
    st = getattr(plant, "spawn_t", 0.0)
    if st <= 0.0:
        return 0
    return int(12 * (min(1.0, st / 0.25) ** 2))


def _draw_hp_bar(screen, x, y, w, ratio, fill_color=COLOR_BAR_FILL):
    bw, bh = w, 4
    pygame.draw.rect(screen, COLOR_BAR_BG, (x, y, bw, bh))
    pygame.draw.rect(screen, fill_color, (x, y, int(bw * max(0.0, min(1.0, ratio))), bh))


_CRACK_R = 64                      # half-size of the cached crack overlay
_crack_cache = {}


def _crack_sprite(n_cracks, seed, shade):
    """Crack overlay pre-rendered around a local centre of (R, R).

    The cracks were re-rolled every frame from a seeded RNG — around 20
    ``pygame.draw.line`` calls plus a fresh ``random.Random`` per wallnut per
    frame, for a pattern that only changes when the plant takes damage. The
    seed is derived from the plant's position, and plants sit on fixed grid
    cells, so the key space is small and naturally bounded.
    """
    key = (n_cracks, seed, shade)
    hit = _crack_cache.get(key)
    if hit is not None:
        return hit
    r, img = _CRACK_R, pygame.Surface((_CRACK_R * 2, _CRACK_R * 2), pygame.SRCALPHA)
    rng = random.Random(seed)          # deterministic per plant
    color = (shade, shade // 2, shade // 3)
    for _ in range(n_cracks):
        # random bite anchor on the wallnut body
        bx = r + rng.randint(-22, 22)
        by = r + rng.randint(-22, 22)
        # zig-zag crack with 3-5 segments
        n_segs = rng.randint(3, 5)
        pts = [(bx, by)]
        for _s in range(n_segs):
            last = pts[-1]
            # each segment drifts away from bite and varies direction
            pts.append((last[0] + rng.randint(-7, 7),
                        last[1] + rng.randint(-9, 9)))
        for i in range(len(pts) - 1):
            pygame.draw.line(img, color, pts[i], pts[i + 1], 2)
    _crack_cache[key] = img
    return img


def _draw_plant_hp(screen, plant, bw=40):
    """Health bar for a plant — hidden until it has actually been chewed.

    Matches what :meth:`Zombie._draw_hp` already does, and for the same
    reason: a gauge over every healthy plant is visual noise. It is also the
    single busiest primitive in the frame — a full lawn is ~28 plants, and
    drawing each one unconditionally cost 56 ``pygame.draw.rect`` calls every
    frame to render something the player has no reason to read.

    Every plant class used to carry its own byte-identical copy of this; they
    now share this one.
    """
    if plant.hp >= plant.max_hp:
        return
    ratio = max(0.0, min(1.0, plant.hp / float(plant.max_hp)))
    _draw_hp_bar(screen, plant.x + 10, plant.y - 8, bw, ratio)


def apply_plant_level(plant, level):
    """Scale a plant's stats to its upgrade level (1..PLANT_LEVEL_MAX).

    Replanting the same type onto the same plant upgrades it — damage, sun
    output and health multiply several times, exactly like PvZ2 plant levels.
    """
    plant.level = level
    stats = PLANT_LEVEL_STATS.get(plant.plant_type, {})
    lvl = max(1, min(PLANT_LEVEL_MAX, level)) - 1
    if "damage" in stats:
        plant.damage = stats["damage"][lvl]
    if "sun" in stats:
        plant.sun_amount = stats["sun"][lvl]
    if "hp" in stats:
        new_max = stats["hp"][lvl]
        if hasattr(plant, "max_hp"):
            plant.hp += max(0, new_max - plant.max_hp)
            plant.max_hp = new_max
    if "radius" in stats:
        plant.blast_radius = stats["radius"][lvl]
    if "bomb_radius" in stats:
        plant.bomb_radius = stats["bomb_radius"][lvl]


def level_pips(plant):
    """(level-1) = number of upgrade pips to draw above the plant."""
    return getattr(plant, "level", 1) - 1


class Peashooter:
    def __init__(self, x, y, row):
        self.x = x
        self.y = y
        self.row = row
        self.plant_type = PLANT_PEASHOOTER
        self.hp = PLANT_INFO[PLANT_PEASHOOTER]["hp"]
        self.max_hp = PLANT_INFO[PLANT_PEASHOOTER]["hp"]
        self.level = 1
        self.damage = PLANT_LEVEL_STATS[PLANT_PEASHOOTER]["damage"][0]
        self.cooldown = 0
        self.cooldown_max = 1.5  # seconds between shots
        self.food_boost = 0.0    # plant-food machine-gun timer
        self.w = 84
        self.h = 84
        self.alive = True
        self.shoot_timer = 0
        self.anim_time = 0
        self.attacking = False
        self.attack_timer = 0
        self.bob = random.uniform(0, 6.28)
        self.bite_shake = 0.0   # horizontal wiggle after being bitten (seconds left)

    def update(self, dt, zombies):
        if self.food_boost > 0:
            self.food_boost -= dt
        effective_cd = 0.09 if self.food_boost > 0 else self.cooldown_max
        if self.cooldown > 0:
            self.cooldown -= dt
        self.anim_time += dt
        if self.attack_timer > 0:
            self.attack_timer -= dt
            self.attacking = True
        else:
            self.attacking = False
        if self.bite_shake > 0:
            self.bite_shake = max(0.0, self.bite_shake - dt)
        # find target in same row
        target = None
        for z in zombies:
            if (z.row == self.row and z.x > self.x and z.alive
                    and z.hp > 0 and z.dying_timer <= 0):
                if target is None or z.x < target.x:
                    target = z
        if target and self.cooldown <= 0:
            self.cooldown = effective_cd
            self.attack_timer = 0.25  # play attack animation briefly
            return self.shoot()
        return None

    def shoot(self):
        return Projectile(self.x + self.w, self.y + self.h // 2, self.row,
                          damage=self.damage, speed=380, color=COLOR_YELLOW)

    def draw(self, screen):
        prefix = "anim_peashooter_attack" if self.attacking else "anim_peashooter_idle"
        frame_idx = int(self.anim_time * 6) % 6
        frame = assets_loader.frame(prefix, frame_idx)
        # bite_shake decays ±3px horizontal wiggle when zombie is eating us
        shake_amp = (self.bite_shake / 0.18) if self.bite_shake > 0 else 0.0
        dx = int(math.sin(self.anim_time * 60) * 3 * shake_amp)
        if frame is not None:
            # bob slightly like a real plant
            by = int(math.sin(self.bob + self.anim_time * 2) * 1.5)
            screen.blit(frame, (self.x + dx, self.y + by - _spawn_dy(self)))
        else:
            # fallback to wiki 96x96 sprite, scaled
            img = assets_loader.scale("plant_peashooter", self.w, self.h)
            if img is not None:
                screen.blit(img, (self.x + dx, self.y - _spawn_dy(self)))
            else:
                pygame.draw.rect(screen, COLOR_BROWN, (self.x + 15 + dx, self.y + 45, 30, 15))
                pygame.draw.ellipse(screen, (0, 150, 0), (self.x + 10 + dx, self.y + 20, 40, 35))
                pygame.draw.circle(screen, (50, 180, 50), (int(self.x + 30 + dx), int(self.y + 30)), 18)
        self._draw_hp(screen)

    def _draw_hp(self, screen):
        _draw_plant_hp(screen, self)

    def rect(self):
        return pygame.Rect(self.x, self.y, self.w, self.h)

    def take_damage(self, dmg):
        self.hp -= dmg
        # visible bite-shake reaction when a zombie chomps on us
        self.bite_shake = max(self.bite_shake, 0.18)
        if self.hp <= 0:
            self.alive = False


class SnowPea:
    """Variant of Peashooter that fires frozen peas. Each projectile applies
    a 4-second ice debuff on the zombie it hits (slow + ice crackles)."""

    def __init__(self, x, y, row):
        self.x = x
        self.y = y
        self.row = row
        self.plant_type = PLANT_SNOWPEA
        self.hp = PLANT_INFO[PLANT_SNOWPEA]["hp"]
        self.max_hp = PLANT_INFO[PLANT_SNOWPEA]["hp"]
        self.level = 1
        self.damage = PLANT_LEVEL_STATS[PLANT_SNOWPEA]["damage"][0]
        self.cooldown = 0
        self.cooldown_max = 1.5
        self.food_boost = 0.0
        self.w = 84
        self.h = 84
        self.alive = True
        self.shoot_timer = 0
        self.anim_time = 0
        self.attacking = False
        self.attack_timer = 0
        self.bob = random.uniform(0, 6.28)
        self.bite_shake = 0.0

    def update(self, dt, zombies):
        if self.food_boost > 0:
            self.food_boost -= dt
        effective_cd = 0.09 if self.food_boost > 0 else self.cooldown_max
        if self.cooldown > 0:
            self.cooldown -= dt
        self.anim_time += dt
        if self.attack_timer > 0:
            self.attack_timer -= dt
            self.attacking = True
        else:
            self.attacking = False
        if self.bite_shake > 0:
            self.bite_shake = max(0.0, self.bite_shake - dt)
        target = None
        for z in zombies:
            if (z.row == self.row and z.x > self.x and z.alive
                    and z.hp > 0 and z.dying_timer <= 0):
                if target is None or z.x < target.x:
                    target = z
        if target and self.cooldown <= 0:
            self.cooldown = effective_cd
            self.attack_timer = 0.25
            return self.shoot()
        return None

    def shoot(self):
        # Cyan / icy projectile that freezes on hit. Color is the cheapest hook
        # to Projectile; game.py reads `proj.freezes` to apply ice debuff.
        return Projectile(self.x + self.w, self.y + self.h // 2, self.row,
                          damage=self.damage, speed=380,
                          color=(140, 220, 255),
                          freezes=True, freeze_seconds=4.0)

    def draw(self, screen):
        prefix = "anim_snowpea_attack" if self.attacking else "anim_snowpea_idle"
        frame_idx = int(self.anim_time * 6) % 6
        frame = assets_loader.frame(prefix, frame_idx)
        shake_amp = (self.bite_shake / 0.18) if self.bite_shake > 0 else 0.0
        dx = int(math.sin(self.anim_time * 60) * 3 * shake_amp)
        if frame is not None:
            by = int(math.sin(self.bob + self.anim_time * 2) * 1.5)
            screen.blit(frame, (self.x + dx, self.y + by - _spawn_dy(self)))
        else:
            # Fallback: peashooter sprite with a cyan tint on top so it reads
            # as a frozen variant without needing dedicated PNG art.
            img = assets_loader.scale("plant_peashooter", self.w, self.h)
            if img is not None:
                tinted = img.copy()
                tint = pygame.Surface(tinted.get_size(), pygame.SRCALPHA)
                tint.fill((110, 200, 255, 70))
                tinted.blit(tint, (0, 0))
                screen.blit(tinted, (self.x + dx, self.y - _spawn_dy(self)))
            else:
                pygame.draw.rect(screen, (90, 130, 170), (self.x + 15 + dx, self.y + 45, 30, 15))
                pygame.draw.ellipse(screen, (60, 140, 200), (self.x + 10 + dx, self.y + 20, 40, 35))
                pygame.draw.circle(screen, (140, 220, 255), (int(self.x + 30 + dx), int(self.y + 30)), 18)
        self._draw_hp(screen)

    def _draw_hp(self, screen):
        _draw_plant_hp(screen, self)

    def rect(self):
        return pygame.Rect(self.x, self.y, self.w, self.h)

    def take_damage(self, dmg):
        self.hp -= dmg
        self.bite_shake = max(self.bite_shake, 0.18)
        if self.hp <= 0:
            self.alive = False


class CobCannon:
    """Tap-to-fire heavy artillery. Picks up where the player clicks, fires a
    big corn kernel that arcs to the target cell, and detonates on impact with
    a large explosion. Reuses fx.Explosion for the visual blast.

    The plant stays alive while reloading; a long reload timer prevents spam.
    Plant food shortcut: feeding a Cob Cannon instantly triggers a full-power
    shot at every zombie in its row.
    """

    RELOAD_S = 12.0   # seconds between manual shots
    MAX_ARC_S = 1.2    # flight time cap

    def __init__(self, x, y, row):
        self.x = x
        self.y = y
        self.row = row
        self.plant_type = PLANT_COBCANNON
        self.hp = PLANT_INFO[PLANT_COBCANNON]["hp"]
        self.max_hp = self.hp
        self.level = 1
        self.w = 100
        self.h = 100
        self.alive = True
        self.anim_time = 0.0
        self.bob = random.uniform(0, 6.28)
        self.bite_shake = 0.0
        # aim + fire state
        self.aim_t = 0.0    # 0..1 idle, 1 = "ready, listening for click"
        self.reload = 0.0   # seconds until next shot is allowed

    @property
    def ready(self):
        return self.reload <= 0

    def update(self, dt, zombies):
        if self.bite_shake > 0:
            self.bite_shake = max(0.0, self.bite_shake - dt)
        self.anim_time += dt
        if self.reload > 0:
            self.reload = max(0.0, self.reload - dt)
            self.aim_t = max(0.0, self.aim_t - dt * 2.0)
        else:
            self.aim_t = min(1.0, self.aim_t + dt * 1.5)
        return None

    def fire_at(self, target_x, target_y):
        """Launch a KernelBomb arc towards (target_x, target_y). Returns the
        new projectile (or None if reloading)."""
        if self.reload > 0:
            return None
        self.reload = self.RELOAD_S
        self.aim_t = 0.0
        # start position: top of plant
        sx = self.x + self.w // 2
        sy = self.y + 8
        # Level upgrades (apply_plant_level) scale the payload; unsprinkled
        # cannons fall back to the level-1 defaults.
        proj = KernelBomb(sx, sy, target_x, target_y,
                         damage=getattr(self, "damage", 1800),
                         radius=getattr(self, "bomb_radius", 110))
        return proj

    def draw(self, screen):
        shake_amp = (self.bite_shake / 0.18) if self.bite_shake > 0 else 0.0
        dx = int(math.sin(self.anim_time * 60) * 3 * shake_amp)
        # Fallback visual: corn cob body + cob launcher on top
        cx = self.x + self.w // 2 + dx
        cy = self.y + self.h // 2
        # base pot
        pygame.draw.rect(screen, (120, 80, 40),
                         (cx - 38, cy + 22, 76, 28), border_radius=4)
        # cob body — yellow corn
        pygame.draw.ellipse(screen, (245, 220, 95),
                            (cx - 32, cy - 8, 64, 56))
        # cob highlight
        pygame.draw.ellipse(screen, (255, 245, 180),
                            (cx - 28, cy - 4, 56, 24))
        # kernel bumps
        for i in range(4):
            for j in range(5):
                bx = cx - 24 + i * 14
                by = cy - 2 + j * 11
                pygame.draw.circle(screen, (210, 175, 60), (bx, by), 4)
                pygame.draw.circle(screen, (250, 225, 130), (bx - 1, by - 1), 2)
        # green leaves on top
        for k, dx_l in enumerate([-10, 0, 10]):
            pygame.draw.polygon(screen, (90, 170, 70), [
                (cx + dx_l, cy - 8),
                (cx + dx_l - 6, cy - 24 - k),
                (cx + dx_l + 6, cy - 24 - k),
            ])
        # ready pip on top — pulses when ready to fire
        if self.aim_t > 0.5:
            pulse = int(180 * (0.5 + 0.5 * math.sin(self.anim_time * 6)))
            pygame.draw.circle(screen, (255, 80, 80, pulse),
                               (cx, cy - 36), 4)
        # reload bar
        if self.reload > 0:
            fill = 1.0 - self.reload / self.RELOAD_S
            pygame.draw.rect(screen, (50, 50, 60),
                             (self.x + 10, self.y + self.h - 6, self.w - 20, 4))
            pygame.draw.rect(screen, (140, 220, 110),
                             (self.x + 10, self.y + self.h - 6,
                              int((self.w - 20) * fill), 4))
        self._draw_hp(screen)

    def _draw_hp(self, screen):
        _draw_plant_hp(screen, self, bw=50)      # wide body, wide gauge

    def rect(self):
        return pygame.Rect(self.x, self.y, self.w, self.h)

    def take_damage(self, dmg):
        self.hp -= dmg
        self.bite_shake = max(self.bite_shake, 0.18)
        if self.hp <= 0:
            self.alive = False


class KernelBomb:
    """Big corn-kernel projectile that arcs to a target point and explodes.

    Each entry: x, y, vx, vy, start_x, start_y, target_x, target_y, t, max_t,
    radius, damage, alive, anim_time, splash (list of (x,y) hit).
    """

    def __init__(self, sx, sy, tx, ty, damage=1800, radius=110):
        self.x = float(sx)
        self.y = float(sy)
        self.start_x = float(sx)
        self.start_y = float(sy)
        self.target_x = float(tx)
        self.target_y = float(ty)
        # compute horizontal distance & flight time
        dx = tx - sx
        # arc time scales with horizontal distance; clamp so close shots still arc
        self.max_t = max(0.45, min(1.2, abs(dx) / 600.0))
        # initial velocity: x = dx / max_t, y = (dy - 0.5 * g * t^2) / t
        self.vx = dx / self.max_t
        g = 1100.0   # gravity for the arc
        dy = ty - sy
        self.vy = (dy - 0.5 * g * self.max_t * self.max_t) / self.max_t
        self.gravity = g
        self.t = 0.0
        self.damage = damage
        self.radius = radius
        self.anim_time = 0.0
        self.alive = True
        self.rotation = 0.0

    def update(self, dt):
        self.anim_time += dt
        self.rotation += 8.0 * dt
        self.t += dt
        self.x += self.vx * dt
        self.vy += self.gravity * dt
        self.y += self.vy * dt
        if self.t >= self.max_t:
            self.alive = False  # game will spawn the explosion

    def draw(self, screen):
        cx, cy = int(self.x), int(self.y)
        # shadow on the ground — scales with height
        height_factor = max(0.2, 1.0 - (self.y - self.start_y) / 200.0)
        sh_r = int(8 * height_factor)
        sh = pygame.Surface((sh_r * 2, sh_r), pygame.SRCALPHA)
        pygame.draw.ellipse(sh, (0, 0, 0, 100), (0, 0, sh_r * 2, sh_r))
        screen.blit(sh, (self.target_x - sh_r, self.target_y - sh_r // 2 + 8))
        # rotating kernel sprite
        r = 10
        surf = pygame.Surface((r * 2 + 4, r * 2 + 4), pygame.SRCALPHA)
        pygame.draw.circle(surf, (245, 220, 95), (r + 2, r + 2), r)
        pygame.draw.circle(surf, (255, 245, 180), (r, r), r // 2)
        pygame.draw.circle(surf, (200, 165, 50), (r + 2, r + 2), r, 2)
        rotated = pygame.transform.rotate(surf, math.degrees(self.rotation))
        screen.blit(rotated, rotated.get_rect(center=(cx, cy)))
        # arc trail — light yellow streak
        trail_alpha = 180
        trail = pygame.Surface((24, 6), pygame.SRCALPHA)
        pygame.draw.ellipse(trail, (255, 250, 180, trail_alpha),
                            (0, 0, 24, 6))
        screen.blit(trail, (cx - 28, cy - 3))


_halo_cache = {}


def _halo_surface():
    """Pre-rendered sun-production halo ring (shared, alpha set before blit)."""
    img = _halo_cache.get("halo")
    if img is None:
        img = pygame.Surface((76, 76), pygame.SRCALPHA)
        pygame.draw.circle(img, (255, 225, 60), (38, 38), 34, 5)
        pygame.draw.circle(img, (255, 245, 160), (38, 38), 28, 3)
        _halo_cache["halo"] = img
    return img


class Sunflower:
    def __init__(self, x, y, row):
        self.x = x
        self.y = y
        self.row = row
        self.plant_type = PLANT_SUNFLOWER
        self.hp = PLANT_INFO[PLANT_SUNFLOWER]["hp"]
        self.max_hp = PLANT_INFO[PLANT_SUNFLOWER]["hp"]
        self.cooldown_max = 7.0  # seconds between sun production
        self.level = 1
        self.sun_amount = PLANT_LEVEL_STATS[PLANT_SUNFLOWER]["sun"][0]
        # Stagger first production so several Sunflowers never burst on one frame.
        self.cooldown = random.uniform(2.0, self.cooldown_max)
        self.w = 84
        self.h = 84
        self.alive = True
        self.sun_timer = 0
        self.anim_time = 0
        self.glow_timer = 0
        self.bite_shake = 0.0   # horizontal wiggle when a zombie is eating us

    def update(self, dt, zombies, allow_production=True):
        # When the shared sun pool is full, freeze the production countdown
        # instead of resetting it and silently discarding the player's reward.
        if allow_production and self.cooldown > 0:
            self.cooldown -= dt
        self.anim_time += dt
        if self.bite_shake > 0:
            self.bite_shake = max(0.0, self.bite_shake - dt)
        if self.glow_timer > 0:
            self.glow_timer -= dt
        if allow_production and self.cooldown <= 0:
            self.cooldown = self.cooldown_max
            self.glow_timer = 0.6
            sun = Sun(self.x + 30, self.y - 20)
            sun.amount = self.sun_amount
            # Eject arc: pop the sun out of the flower head on a real
            # ballistic arc so it visibly leaves the plant rather than
            # appearing on the lawn out of thin air.
            sun.eject(vy=-195.0, target_y=self.y + random.randint(30, 62))
            return sun

    def draw(self, screen):
        # The bundled "glow" sheet contains a black-backed double-sun graphic,
        # not a clean sunflower animation. Keep the normal animated body and
        # draw a transparent halo when producing sun.
        prefix = "anim_sunflower_idle"
        frame_idx = int(self.anim_time * 6) % 6
        frame = assets_loader.frame(prefix, frame_idx)
        dy = _spawn_dy(self)
        # bite_shake decays ±3px horizontal wiggle when zombie is eating us
        shake_amp = (self.bite_shake / 0.18) if self.bite_shake > 0 else 0.0
        dx = int(math.sin(self.anim_time * 60) * 3 * shake_amp)
        if self.glow_timer > 0:
            halo = _halo_surface()
            strength = int(70 + 70 * min(1.0, self.glow_timer / 0.6))
            screen.blit(fx.faded(halo, strength), (self.x + 4 + dx, self.y + 4 - dy))
        if frame is not None:
            screen.blit(frame, (self.x + dx, self.y - dy))
        else:
            img = assets_loader.scale("plant_sunflower", self.w, self.h)
            if img is not None:
                screen.blit(img, (self.x + dx, self.y - dy))
            else:
                pygame.draw.rect(screen, COLOR_BROWN, (self.x + 20 + dx, self.y + 45, 20, 15))
                pygame.draw.circle(screen, COLOR_YELLOW, (int(self.x + 30 + dx), int(self.y + 30)), 20)
        self._draw_hp(screen)

    def _draw_hp(self, screen):
        _draw_plant_hp(screen, self)

    def rect(self):
        return pygame.Rect(self.x, self.y, self.w, self.h)

    def take_damage(self, dmg):
        self.hp -= dmg
        # visible bite-shake reaction when a zombie chomps on us
        self.bite_shake = max(self.bite_shake, 0.18)
        if self.hp <= 0:
            self.alive = False


class Wallnut:
    def __init__(self, x, y, row):
        self.x = x
        self.y = y
        self.row = row
        self.plant_type = PLANT_WALLNUT
        self.level = 1
        self.hp = PLANT_INFO[PLANT_WALLNUT]["hp"]
        self.max_hp = PLANT_INFO[PLANT_WALLNUT]["hp"]
        self.w = 84
        self.h = 84
        self.alive = True
        self.anim_time = 0
        self.bite_shake = 0.0   # horizontal wiggle when a zombie is eating us

    def update(self, dt, zombies):
        self.anim_time += dt
        if self.bite_shake > 0:
            self.bite_shake = max(0.0, self.bite_shake - dt)

    def _crack_state(self):
        ratio = self.hp / self.max_hp
        if ratio > 0.66:
            return "anim_wallnut_idle"
        elif ratio > 0.33:
            return "anim_wallnut_cracked"
        else:
            return "anim_wallnut_verycracked"

    def _crack_overlay(self, screen):
        """Procedural crack overlay — drawn ON TOP of the wallnut sprite.
        Number of cracks grows with damage; cracks are jittered zig-zag lines
        that radiate from bite marks. Always visible (not just at thresholds).
        """
        damage = 1.0 - (self.hp / self.max_hp)   # 0..1 as wallnut is chewed
        if damage <= 0.05:
            return  # pristine — no cracks yet
        n_cracks = min(6, int(1 + damage * 5))   # 1..6 cracks
        # Darker shade as the wallnut gets chewed, quantised onto the same
        # ladder as the crack count so the sprite cache stays small: the shade
        # is now a step function of the damage tier rather than of continuous
        # HP, which also keeps a crack looking consistent as it deepens.
        tier = n_cracks - 1                      # 0..5
        shade = 50 + int(60 * tier / 5.0)
        img = _crack_sprite(n_cracks, int(self.x) * 31 + int(self.y), shade)
        # center of the visible sprite (relative to the sprite box)
        cx = self.x + self.w // 2
        cy = self.y + self.h // 2 - 4
        screen.blit(img, (cx - _CRACK_R, cy - _CRACK_R))

    def draw(self, screen):
        prefix = self._crack_state()
        frame_idx = int(self.anim_time * 6) % 6
        frame = assets_loader.frame(prefix, frame_idx)
        dy = _spawn_dy(self)
        # bite_shake decays ±3px horizontal wiggle when zombie is eating us
        shake_amp = (self.bite_shake / 0.18) if self.bite_shake > 0 else 0.0
        dx = int(math.sin(self.anim_time * 60) * 3 * shake_amp)
        if frame is not None:
            screen.blit(frame, (self.x + dx, self.y - dy))
        else:
            img = assets_loader.scale("plant_wallnut", self.w, self.h)
            if img is not None:
                screen.blit(img, (self.x + dx, self.y - dy))
            else:
                pygame.draw.ellipse(screen, (160, 120, 60), (self.x + 5 + dx, self.y + 10, 50, 45))
                pygame.draw.ellipse(screen, (180, 140, 80), (self.x + 15 + dx, self.y + 15, 30, 35))
        # Procedural crack overlay on top of the sprite (1..6 cracks)
        self._crack_overlay(screen)
        self._draw_hp(screen)

    def _draw_hp(self, screen):
        _draw_plant_hp(screen, self)

    def rect(self):
        return pygame.Rect(self.x, self.y, self.w, self.h)

    def take_damage(self, dmg):
        self.hp -= dmg
        # visible bite-shake reaction when a zombie chomps on us
        self.bite_shake = max(self.bite_shake, 0.18)
        if self.hp <= 0:
            self.alive = False


class CherryBomb:
    def __init__(self, x, y, row):
        self.x = x
        self.y = y
        self.row = row
        self.plant_type = PLANT_CHERRYBOMB
        self.level = 1
        self.hp = 100
        self.max_hp = 100
        self.damage = PLANT_LEVEL_STATS[PLANT_CHERRYBOMB]["damage"][0]
        self.blast_radius = PLANT_LEVEL_STATS[PLANT_CHERRYBOMB]["radius"][0]
        self.explode = False
        self.explode_timer = 0
        self.fuse_timer = 0
        self.fuse_max = 1.2  # seconds before detonation (PvZ original)
        self.w = 60
        self.h = 60
        self.alive = True
        self.bite_shake = 0.0   # horizontal wiggle when a zombie is eating us

    def update(self, dt, zombies):
        if self.explode:
            self.explode_timer -= dt
            if self.explode_timer <= 0:
                self.alive = False
                return self._explode(zombies)
        else:
            # tick fuse and detonate when any zombie is in adjacent 3x3
            self.fuse_timer += dt
            for z in zombies:
                if not z.alive or z.hp <= 0 or z.dying_timer > 0:
                    continue
                dz_row = abs(z.row - self.row)
                dz_col = abs((z.x - self.x) / CELL_W)
                if dz_row <= 1 and dz_col <= 1.5:
                    self.explode = True
                    self.explode_timer = 0.3
                    break
            # auto-detonate at end of fuse regardless of zombies
            if not self.explode and self.fuse_timer >= self.fuse_max:
                self.explode = True
                self.explode_timer = 0.3
        if self.bite_shake > 0:
            self.bite_shake = max(0.0, self.bite_shake - dt)

    def _explode(self, zombies):
        affected = []
        for z in zombies:
            if not z.alive:
                continue
            dz_row = abs(z.row - self.row)
            dz_col = abs((z.x - self.x) / CELL_W)
            if dz_row <= 1 and dz_col <= self.blast_radius:
                z.take_damage(self.damage)
                affected.append(z)
        return affected

    def draw(self, screen):
        dy = _spawn_dy(self)
        img = assets_loader.scale("plant_cherrybomb", self.w, self.h)
        # bite_shake decays ±3px horizontal wiggle when zombie is eating us
        shake_amp = (self.bite_shake / 0.18) if self.bite_shake > 0 else 0.0
        dx = int(math.sin(self.fuse_timer * 60) * 3 * shake_amp)
        # --- Fuse visual: progress 0..1, color shifts green→yellow→red and
        #     flash rate climbs so the cherry pulses faster the closer it is
        #     to detonation. Blink is a sin wave (0..1..0) at a frequency
        #     that itself scales with progress.
        progress = min(1.0, self.fuse_timer / self.fuse_max) if not self.explode else 1.0
        blink_hz = 1.5 + progress * 6.0   # 1.5 Hz at start → 7.5 Hz at fuse end
        blink = (math.sin(self.fuse_timer * blink_hz * 2.0 * math.pi) + 1.0) * 0.5
        if img is not None:
            if self.explode:
                # bright explosion overlay
                screen.blit(img, (self.x + dx, self.y - dy))
                flash = pygame.Surface((self.w + 20, self.h + 20), pygame.SRCALPHA)
                pygame.draw.circle(flash, (255, 200, 100, 180), (self.w // 2 + 10, self.h // 2 + 10), 35)
                screen.blit(flash, (self.x - 10 + dx, self.y - 10 - dy))
            else:
                # Red tint overlay that pulses faster as the fuse nears zero.
                screen.blit(img, (self.x + dx, self.y - dy))
                if progress > 0.2:
                    tint = pygame.Surface((self.w, self.h), pygame.SRCALPHA)
                    tint_alpha = int((80 + 100 * blink) * min(1.0, (progress - 0.2) / 0.8))
                    tint.fill((255, 60, 60, tint_alpha))
                    screen.blit(tint, (self.x + dx, self.y - dy))
            # fuse spark when close to detonation
            if not self.explode and progress > 0.4:
                spark_size = 4 + int(progress * 4)
                spark_color = (255, int(200 * (1 - progress)), 0)
                pygame.draw.circle(screen, spark_color, (int(self.x + self.w // 2 + dx), int(self.y + 8)), spark_size)
            # --- Fuse countdown bar above the cherry (only while armed)
            if not self.explode:
                bar_w = self.w
                bar_h = 4
                bx = int(self.x)
                by = int(self.y - 8)
                pygame.draw.rect(screen, COLOR_BAR_BG, (bx, by, bar_w, bar_h))
                # color: green → yellow → red as progress climbs
                if progress < 0.5:
                    bar_color = (90 + int(160 * progress * 2), 200, 60)
                else:
                    p2 = (progress - 0.5) * 2
                    bar_color = (250, int(200 * (1 - p2)), 60)
                fill_w = int(bar_w * progress)
                pygame.draw.rect(screen, bar_color, (bx, by, fill_w, bar_h))
                # red border tightens when flashing
                if blink > 0.5:
                    pygame.draw.rect(screen, (255, 50, 50),
                                     (bx - 1, by - 1, bar_w + 2, bar_h + 2), 1)
        else:
            color = (220, 20, 20) if not self.explode else (255, 100, 0)
            pygame.draw.circle(screen, color, (int(self.x + 30 + dx), int(self.y + 30)), 18)
            pygame.draw.circle(screen, (255, 50, 50), (int(self.x + 30), int(self.y + 30)), 18, 2)
            pygame.draw.line(screen, (0, 80, 0), (int(self.x + 30), int(self.y + 10)), (int(self.x + 30), int(self.y + 20)), 2)
            if self.explode:
                pygame.draw.circle(screen, COLOR_ORANGE, (int(self.x + 30), int(self.y + 30)), 30, 3)
        self._draw_hp(screen)

    def _draw_hp(self, screen):
        _draw_plant_hp(screen, self)

    def rect(self):
        return pygame.Rect(self.x, self.y, self.w, self.h)

    def take_damage(self, dmg):
        self.hp -= dmg
        # visible bite-shake reaction when a zombie chomps on us
        self.bite_shake = max(self.bite_shake, 0.18)
        if self.hp <= 0:
            self.alive = False


class Fumeshroom:
    def __init__(self, x, y, row):
        self.x = x
        self.y = y
        self.row = row
        self.plant_type = PLANT_FUMESHROOM
        self.hp = PLANT_INFO[PLANT_FUMESHROOM]["hp"]
        self.max_hp = PLANT_INFO[PLANT_FUMESHROOM]["hp"]
        self.level = 1
        self.damage = PLANT_LEVEL_STATS[PLANT_FUMESHROOM]["damage"][0]
        self.cooldown = 0
        self.cooldown_max = 2.0
        self.w = 60
        self.h = 60
        self.alive = True
        self.anim_time = 0
        self.bite_shake = 0.0   # horizontal wiggle when a zombie is eating us

    def update(self, dt, zombies):
        self.anim_time += dt
        if self.bite_shake > 0:
            self.bite_shake = max(0.0, self.bite_shake - dt)
        if self.cooldown > 0:
            self.cooldown -= dt
        # find target in same row
        target = None
        for z in zombies:
            if (z.row == self.row and z.x > self.x and z.alive
                    and z.hp > 0 and z.dying_timer <= 0):
                if target is None or z.x < target.x:
                    target = z
        if target and self.cooldown <= 0:
            self.cooldown = self.cooldown_max
            return self.shoot()

    def shoot(self):
        return Projectile(self.x + self.w, self.y + self.h // 2, self.row,
                          damage=self.damage, speed=380, color=(180, 0, 255))

    def draw(self, screen):
        img = assets_loader.scale("plant_fumeshroom", self.w, self.h)
        dy = _spawn_dy(self)
        # bite_shake decays ±3px horizontal wiggle when zombie is eating us
        shake_amp = (self.bite_shake / 0.18) if self.bite_shake > 0 else 0.0
        dx = int(math.sin(self.anim_time * 60) * 3 * shake_amp)
        if img is not None:
            screen.blit(img, (self.x + dx, self.y - dy))
        else:
            pygame.draw.rect(screen, COLOR_BROWN, (self.x + 20 + dx, self.y + 45 - dy, 20, 15))
            pygame.draw.ellipse(screen, (80, 0, 120), (self.x + 15 + dx, self.y + 20 - dy, 30, 35))
            pygame.draw.circle(screen, (120, 0, 180), (int(self.x + 30 + dx), int(self.y + 30 - dy)), 12)
            pygame.draw.circle(screen, COLOR_WHITE, (int(self.x + 28 + dx), int(self.y + 28 - dy)), 2)
        self._draw_hp(screen)

    def _draw_hp(self, screen):
        _draw_plant_hp(screen, self)

    def rect(self):
        return pygame.Rect(self.x, self.y, self.w, self.h)

    def take_damage(self, dmg):
        self.hp -= dmg
        # visible bite-shake reaction when a zombie chomps on us
        self.bite_shake = max(self.bite_shake, 0.18)
        if self.hp <= 0:
            self.alive = False


# ============================================================
# Lily Pad (plantable foundation for pool levels)
# ============================================================
class LilyPad:
    """A plantable lily pad. Must be planted on a water cell first;
    then one normal plant can be placed on top of it."""

    def __init__(self, x, y, row):
        self.x = x
        self.y = y
        self.row = row
        self.plant_type = PLANT_LILYPAD
        self.level = 1
        self.w = CELL_W - 4
        self.h = CELL_H - 26
        self.alive = True
        self.hp = PLANT_LEVEL_STATS[PLANT_LILYPAD]["hp"][0]
        self.max_hp = PLANT_LEVEL_STATS[PLANT_LILYPAD]["hp"][0]
        self.anim_time = 0
        self.bite_shake = 0.0   # horizontal wiggle when a zombie is eating us
        # narrow hitbox so zombies collide with the plant body on top first,
        # and only eat the lily pad when nothing else is planted here
        self.collide_w = 36

    def update(self, dt, zombies):
        self.anim_time += dt
        if self.bite_shake > 0:
            self.bite_shake = max(0.0, self.bite_shake - dt)
        return None

    def draw(self, screen):
        # water glint underneath
        glint = pygame.Surface((self.w, 14), pygame.SRCALPHA)
        glint.fill((150, 200, 255, 60))
        # bite_shake decays ±3px horizontal wiggle when zombie is eating us
        shake_amp = (self.bite_shake / 0.18) if self.bite_shake > 0 else 0.0
        dx = int(math.sin(self.anim_time * 60) * 3 * shake_amp)
        screen.blit(glint, (self.x + dx, self.y + self.h - 8))
        img = assets_loader.scale("ui_lily_pad", self.w, self.h)
        if img is not None:
            screen.blit(img, (self.x + dx, self.y))
        else:
            pygame.draw.ellipse(screen, (40, 130, 50), (self.x + dx, self.y, self.w, self.h))
            pygame.draw.ellipse(screen, (30, 100, 40), (self.x + 4 + dx, self.y + 2, self.w - 8, self.h - 4))
        # slight bob animation
        # low-HP shading handled by generic hp bar below

    def rect(self):
        return pygame.Rect(self.x, self.y, self.w, self.h)

    def take_damage(self, dmg):
        self.hp -= dmg
        # visible bite-shake reaction when a zombie chomps on us
        self.bite_shake = max(self.bite_shake, 0.18)
        if self.hp <= 0:
            self.alive = False


PLANT_CLASSES = {
    PLANT_PEASHOOTER: Peashooter,
    PLANT_SUNFLOWER: Sunflower,
    PLANT_WALLNUT: Wallnut,
    PLANT_CHERRYBOMB: CherryBomb,
    PLANT_FUMESHROOM: Fumeshroom,
    PLANT_LILYPAD: LilyPad,
    PLANT_SNOWPEA: SnowPea,
    PLANT_COBCANNON: CobCannon,
}


# ============================================================
# Roof Tile (for roof levels)
# ============================================================
class RoofTile:
    def __init__(self, x, y, row=0, col=0):
        self.x = x
        self.y = y
        self.row = row
        self.col = col
        self.w = CELL_W
        self.h = CELL_H
        self.alive = True

    def draw(self, screen):
        # Alternating terracotta tiles clearly distinguish roof from lawn.
        base = (164, 74, 52) if (self.row + self.col) % 2 == 0 else (147, 61, 45)
        pygame.draw.rect(screen, base, (self.x, self.y, self.w, self.h))
        pygame.draw.rect(screen, (205, 105, 68),
                         (self.x + 3, self.y + 3, self.w - 6, self.h - 6), 2)
        pygame.draw.line(screen, (98, 38, 34),
                         (self.x, self.y + self.h - 2),
                         (self.x + self.w, self.y + self.h - 2), 3)
        pygame.draw.line(screen, (115, 44, 37),
                         (self.x + self.w - 2, self.y),
                         (self.x + self.w - 2, self.y + self.h), 2)


# ============================================================
# Fog (for fog levels)
# ============================================================
class FogLayer:
    _strip_cache = {}

    def __init__(self, row, right_x):
        self.row = row
        self.x = right_x
        self.y = GRID_Y + row * CELL_H
        self.w = 300
        self.h = CELL_H
        self.alive = True
        self.speed = 12  # pixels per second
        self.strip = self._get_strip(self.w, self.h)

    @classmethod
    def _get_strip(cls, w, h):
        """One pre-rendered gradient strip per size. The old draw() built 20
        SRCALPHA surfaces per row per frame (100+/frame in fog levels)."""
        key = (w, h)
        img = cls._strip_cache.get(key)
        if img is None:
            img = pygame.Surface((w, h), pygame.SRCALPHA)
            cols = 20
            col_w = w // cols
            for i in range(cols):
                alpha = int(120 * (1 - i / cols))
                img.fill((200, 200, 220, alpha),
                         (i * col_w, 0, col_w, h))
            cls._strip_cache[key] = img
        return img

    def update(self, dt):
        self.x -= self.speed * dt
        if self.x < GRID_X - self.w:
            self.alive = False

    def draw(self, screen):
        # gradient fog from right to left — single blit
        screen.blit(self.strip, (int(self.x), self.y))


# ============================================================
# Shovel (tool for digging up plants)
# ============================================================
class Shovel:
    def __init__(self):
        self.x = SCREEN_WIDTH - 80
        self.y = UI_BAR_Y + 5
        self.w = 50
        self.h = 60
        self.selected = False
        self.alive = True

    def draw(self, screen):
        color = (180, 130, 60) if not self.selected else (220, 170, 80)
        img = assets_loader.scale("ui_shovel", self.w, self.h)
        if img is not None:
            if self.selected:
                # highlight overlay
                screen.blit(img, (self.x, self.y))
                overlay = pygame.Surface((self.w, self.h), pygame.SRCALPHA)
                pygame.draw.rect(overlay, (255, 255, 100, 60), (0, 0, self.w, self.h), border_radius=6)
                screen.blit(overlay, (self.x, self.y))
                pygame.draw.rect(screen, (255, 220, 100), (self.x - 2, self.y - 2, self.w + 4, self.h + 4), 3, border_radius=6)
            else:
                screen.blit(img, (self.x, self.y))
        else:
            # handle
            pygame.draw.line(screen, (100, 70, 30), (int(self.x + 25), int(self.y + 5)),
                             (int(self.x + 25), int(self.y + 35)), 4)
            # blade
            pygame.draw.polygon(screen, color, [
                (self.x + 10, self.y + 45),
                (self.x + 40, self.y + 45),
                (self.x + 30, self.y + 58),
                (self.x + 15, self.y + 58),
            ])
            pygame.draw.polygon(screen, (140, 100, 40), [
                (self.x + 10, self.y + 45),
                (self.x + 40, self.y + 45),
                (self.x + 30, self.y + 58),
                (self.x + 15, self.y + 58),
            ], 2)
            pygame.draw.circle(screen, (200, 150, 50), (int(self.x + 25), int(self.y + 10)), 6)

    def contains(self, mx, my):
        return self.x <= mx <= self.x + self.w and self.y <= my <= self.y + self.h

    def rect(self):
        return pygame.Rect(self.x, self.y, self.w, self.h)


# ============================================================
# Lawnmower
# ============================================================
_dust_cache = {}


def _dust_sprite():
    img = _dust_cache.get("dust")
    if img is None:
        img = pygame.Surface((14, 8), pygame.SRCALPHA)
        pygame.draw.ellipse(img, (180, 170, 140), (0, 0, 14, 8))
        _dust_cache["dust"] = img
    return img


class Lawnmower:
    def __init__(self, row, grid_y=GRID_Y):
        self.row = row
        self.x = LAWNMOWER_X
        self.y = grid_y + row * CELL_H + (CELL_H - LAWNMOWER_H) // 2
        self.w = LAWNMOWER_W
        self.h = LAWNMOWER_H
        self.alive = True
        self.hp = 1
        self.activated = False
        self.mow_dust = 0  # for visual dust puff when moving

    def activate(self):
        self.activated = True
        # Game layer will read this flag and emit a starter puff next frame.
        self._activated_just_now = True

    def update(self, dt):
        """Move the activated mower right; returns nothing (kills handled in game)."""
        if not self.activated:
            return
        self.x += LAWNMOWER_SPEED * dt
        self.mow_dust += dt
        # Tell the game layer to emit periodic trailing dust while moving.
        if self.mow_dust >= 0.06:
            self.mow_dust = 0
            self._needs_dust_puff = True
        if self.x > SCREEN_WIDTH + 60:
            self.alive = False

    def draw(self, screen):
        img = assets_loader.scale("ui_lawnmower", self.w, self.h)
        if img is not None:
            screen.blit(img, (self.x, self.y))
        else:
            # deck
            pygame.draw.rect(screen, (60, 60, 65), (self.x + 8, self.y + 20, 26, 22), border_radius=4)
            # engine
            pygame.draw.ellipse(screen, (40, 40, 45), (self.x + 12, self.y + 30, 18, 12))
            # wheels
            pygame.draw.ellipse(screen, (20, 20, 20), (self.x + 6, self.y + 38, 12, 12))
            pygame.draw.ellipse(screen, (20, 20, 20), (self.x + 24, self.y + 38, 12, 12))
            # handle
            pygame.draw.line(screen, (80, 80, 85), (int(self.x + 5), int(self.y + 22)), (int(self.x + 5), int(self.y + 8)), 3)
            pygame.draw.line(screen, (80, 80, 85), (int(self.x + 37), int(self.y + 22)), (int(self.x + 37), int(self.y + 8)), 3)
            pygame.draw.line(screen, (100, 100, 105), (int(self.x + 5), int(self.y + 8)), (int(self.x + 37), int(self.y + 8)), 3)
        # mower trail dust when active (pre-rendered puffs, not per-frame draws)
        if self.activated:
            img = _dust_sprite()
            for i in range(4):
                # _dust_sprite is a shared cache — fx.faded copies per blit
                screen.blit(fx.faded(img, 90 - i * 20),
                            (int(self.x) - 16 * (i + 1), self.y + 14))

    def rect(self):
        return pygame.Rect(self.x, self.y, self.w, self.h)


# ============================================================
# Shared effect sprites (built once, blitted many times)
# ============================================================
_aura_cache = {}


def _rally_aura():
    """Soft red ring drawn around a zombie that a commander has rallied."""
    img = _aura_cache.get("rally")
    if img is None:
        r = 56
        img = pygame.Surface((r * 2, r * 2), pygame.SRCALPHA)
        for i, (rr, a) in enumerate(((r, 22), (int(r * 0.82), 30),
                                     (int(r * 0.62), 34))):
            pygame.draw.circle(img, (255, 90, 60, a), (r, r), rr, 3)
        pygame.draw.circle(img, (255, 180, 120, 60), (r, r), int(r * 0.45), 2)
        _aura_cache["rally"] = img
    return img


def _burrow_mound():
    """Churned-earth mound a digger leaves behind while underground."""
    img = _aura_cache.get("burrow")
    if img is None:
        w, h = 54, 26
        img = pygame.Surface((w, h), pygame.SRCALPHA)
        pygame.draw.ellipse(img, (86, 62, 34), (0, 6, w, h - 6))
        pygame.draw.ellipse(img, (118, 88, 48), (4, 2, w - 12, h - 8))
        pygame.draw.ellipse(img, (146, 112, 62), (10, 0, w - 26, h - 12))
        for i, (dx, dy, rr) in enumerate(((6, 12, 3), (16, 8, 2), (30, 14, 3),
                                          (42, 10, 2), (24, 16, 2))):
            pygame.draw.circle(img, (108, 80, 44), (dx, dy), rr)
        _aura_cache["burrow"] = img
    return img


_ring_cache = {}


def _get_ring_sprite(radius, color, alpha):
    """Cached two-tone ring, quantized to 4 px so the cache stays small."""
    radius = max(3, int(radius))
    q = (radius // 4) * 4
    key = (q, color, alpha // 24)
    img = _ring_cache.get(key)
    if img is not None:
        return img
    img = pygame.Surface((q * 2, q * 2), pygame.SRCALPHA)
    pygame.draw.circle(img, (*color, alpha), (q, q), q, 3)
    pygame.draw.circle(img, (255, 255, 255, int(alpha * 0.6)), (q, q), q // 2, 2)
    _ring_cache[key] = img
    return img


# Elite skin for the AI variants. Every non-boss zombie draws from one shared
# walk sheet, so without this a tactician and a basic zombie are the same
# silhouette with different accessories. Each entry is (rgb, overlay alpha):
# strong enough to name the variant, light enough to keep the shading.
_AI_TINT = {
    ZOMBIE_TACTICIAN: ((158, 132, 240), 255),   # violet
    ZOMBIE_DIGGER:    ((226, 188, 132), 255),   # dust / khaki
    ZOMBIE_HEALER:    ((132, 228, 192), 255),   # apothecary mint
    ZOMBIE_COMMANDER: ((246, 146, 146), 255),   # officer crimson
}
# Public view of the same table, for the level preloader (game._preload_...).
AI_ZOMBIE_TINTS = tuple(_AI_TINT.values())

# On-screen body height every zombie sheet is scaled to. Module level so the
# preloader warms the exact cache key the draw path will ask for.
ZOMBIE_BODY_H = 96

# Edge length the sun sprite is drawn at before its impact squash. Same reason
# as ZOMBIE_BODY_H: the preloader has to warm the identical rotation key.
SUN_SPRITE_SIZE = 40


# ============================================================
# Zombies
# ============================================================
class Zombie:
    """A single zombie, from a shambling basic to the lane-reading tactician.

    Animation is *distance driven* for the walk cycle (``walk_phase`` advances
    with the pixels actually travelled), so the feet stay planted at any speed
    and a frozen zombie visibly trudges instead of moonwalking. Eating and
    dying keep their own clocks so switching state never snaps the sprite.
    """

    _FRAMES = 7          # cells per bundled zombie strip
    STRIDE_PX = 30.0     # px of travel per full walk cycle
    EAT_FPS = 7.0
    EAT_BITE_S = 1.0     # one bite per this many seconds (matches the old rate)
    # Shorter-limbed / quicker variants use a tighter stride so the feet do
    # not appear to skate; a longer stride reads as a loping commander.
    _STRIDE_BY_TYPE = {
        ZOMBIE_TACTICIAN: 26.0,
        ZOMBIE_DIGGER: 24.0,
        ZOMBIE_HEALER: 32.0,
        ZOMBIE_COMMANDER: 36.0,
        ZOMBIE_FLAG: 27.0,
        ZOMBIE_POLE: 28.0,
    }

    def __init__(self, x, y, row, zombie_type=ZOMBIE_BASIC):
        self.x = float(x)
        self.y = float(y)
        self.row = row
        self.zombie_type = zombie_type
        info = ZOMBIE_INFO[zombie_type]
        self.max_hp = info["hp"]
        self.hp = info["hp"]
        self.base_speed = info["speed"]
        self.speed = info["speed"]
        # Survival wave scaling multiplier captured at spawn. Mid-life speed
        # transitions (pole vault landing, balloon pop, newspaper rage) are
        # derived from base_speed * this so late-wave zombies never snap back
        # to early-game absolute speeds.
        self._speed_mult = 1.0
        self.reward = info["reward"]
        self.w = 90   # logical box; the drawn body is ~55x96 anchored on the foot
        self.h = 116
        self.alive = True
        self.eaten_plant = None
        self.eat_timer = 0
        self.hit_flash = 0
        self.reached_house = False
        self.reached_lawnmower = False
        self.anim_time = 0
        self.is_eating = False
        self.dying_timer = 0
        # --- animation clocks (see class docstring) ---
        self.walk_phase = random.random()
        self.eat_clock = 0.0
        self.die_clock = 0.0
        self._step_just_done = False
        # --- status effects ---
        # Frozen state (e.g. Snow Pea, Winter Melon). ice_timer > 0 means
        # zombie is slow + covered in ice crackles.
        self.ice_timer = 0.0
        self.ice_max = 0.0
        self.ice_crackles = []  # list of (x_offset, y_offset, age, max_age)
        # Commander rally: multiplies speed / bite damage while > 0.
        self.rally_timer = 0.0
        self.rally_speed = 1.0
        self.rally_dmg = 1.0
        self.use_b_sheet = random.random() < 0.5  # two walk sheets for variety
        self.is_boss = (zombie_type == ZOMBIE_BOSS)
        self.in_wave = True  # counts toward the current wave (boss minions don't)
        self.death_counted = False
        self.grid_y = GRID_Y
        self.spawn_request = None

        # Newspaper Zombie: enrages once the paper takes enough damage
        self.enraged = False
        self.rage_dmg = 0
        self.rage_threshold = 90
        # Pole Vaulting Zombie: one jump over the first plant. The leap is a
        # dt-driven arc (see update): the old single-frame x-snap teleported
        # ~180px and froze mid-air, which read as a teleport.
        self.has_vaulted = False
        self.vault_timer = 0
        self.vault_t = 0.0
        self._vault_from_x = 0.0
        self._vault_to_x = 0.0
        self.vault_lift = 0.0   # visual hop offset, applied in draw()
        # Boss: summons minions
        self.summon_timer = 3.0
        self.minion_pool = [ZOMBIE_BASIC, ZOMBIE_CONEHEAD]
        # bite damage scales in survival mode (game applies the wave multiplier)
        self.eat_damage = 30
        # Balloon Zombie: floats over plants and mowers until the balloon pops
        self.floating = (zombie_type == ZOMBIE_BALLOON)
        self.balloon_hp = BALLOON_HP if self.floating else 0
        # Rendered hover offset, eased toward ±target in update() so the pop
        # (and spawn entry) glides instead of snapping 24px in one frame.
        self._air_lift = 24.0 if self.floating else 0.0
        # Bungee Zombie: drops from the sky on a cord and steals a plant
        self.is_bungee = (zombie_type == ZOMBIE_BUNGEE)
        self.bungee_phase = "descend" if self.is_bungee else None
        self.escaped = False   # bungee that climbed off-screen (no kill reward)
        self._steal_timer = 0.0
        self.stole_plant = False
        self.steal_announced = False
        self._stolen_type = None       # plant_type carried in bungee hand
        self._steal_burst_pending = False
        if self.is_bungee:
            self.y = -250  # starts above the canvas, descends in update()

        # ---- AI zombies (see ai.py) ----
        self.is_tactician = (zombie_type == ZOMBIE_TACTICIAN)
        self.is_digger = (zombie_type == ZOMBIE_DIGGER)
        self.is_healer = (zombie_type == ZOMBIE_HEALER)
        self.is_commander = (zombie_type == ZOMBIE_COMMANDER)
        self.is_smart = self.is_tactician or self.is_digger or self.is_healer \
            or self.is_commander
        # Elite skin: every non-boss zombie shares one walk sheet, so a colour
        # wash is what makes an AI variant readable at a glance. (tint, alpha).
        self.body_tint = _AI_TINT.get(zombie_type)
        # Tactician: lane hop state
        self.transfer_timer = random.uniform(1.5, TACTICIAN_TRANSFER_S)
        self.transfer_t = 0.0
        self._transfer_from_y = 0.0
        self._transfer_to_y = 0.0
        # Digger: burrow → tunnel → surface
        self.dig_phase = None          # None | "burrow" | "under" | "emerge"
        self.dig_t = 0.0
        self._dig_remaining = 0.0      # px still to tunnel
        self.underground = False
        # Healer / commander action clocks
        self.action_timer = random.uniform(0.6, 1.6)
        # --- FX intents, drained once per frame by Game._consume_zombie_ai_fx.
        # The entity records *what happened*; the game layer decides how it
        # looks. Nothing here touches pygame draw calls.
        self._beam_pending = None      # (target, "heal"|"rally")
        self._hop_pending = None       # (x, y_from, y_to) tactician lane hop
        self._dig_dust_pending = False # digger kicked up dirt
        self._emerge_pending = False   # digger broke the surface
        # Draw-time scratch (set every frame by draw(), read by the game layer)
        self._vx = self._vy = 0
        self._bcx = self._btop = 0
        self._bw = self._bh = 0
        self._hit_rect = pygame.Rect(0, 0, 58, 98)   # reused by rect()
        self.STRIDE_PX = self._STRIDE_BY_TYPE.get(zombie_type, self.STRIDE_PX)

        if self.is_boss:
            self.w = 170
            self.h = 210
            self.use_b_sheet = False

    def update(self, dt, plants, zombies=None):
        # ---- Boss-spawned minion sky-drop animation ----
        # The minion falls from sky to its lawn position; game.py listens for
        # the landing moment via the `_minion_drop_landed` flag to spawn a
        # ground-impact ring + dust.
        if getattr(self, "_minion_drop", False):
            self._drop_t += dt
            t = min(1.0, self._drop_t / self._drop_max)
            # ease-in (gravity feel)
            ease = t * t
            self.y = self._drop_from_y + (self._drop_to_y - self._drop_from_y) * ease
            if t >= 1.0:
                self._minion_drop = False
                self._minion_drop_landed = True
                self.y = self._drop_to_y
            # while dropping, the minion doesn't move / attack
            return None

        if self.hit_flash > 0:
            self.hit_flash -= dt
        self.anim_time += dt
        # Ease the rendered hover lift toward the floating target (0 when the
        # balloon pops) so the descent is a glide, not a 24px one-frame snap.
        _lift_target = 24.0 if self.floating else 0.0
        if self._air_lift != _lift_target:
            step = dt / 0.15
            if self._air_lift > _lift_target:
                self._air_lift = max(_lift_target, self._air_lift - 24.0 * step)
            else:
                self._air_lift = min(_lift_target, self._air_lift + 24.0 * step)
        if self.rally_timer > 0:
            self.rally_timer -= dt
            if self.rally_timer <= 0:
                self.rally_speed = 1.0
                self.rally_dmg = 1.0
        if self.dying_timer > 0:
            self.dying_timer -= dt
            # Death animation is a one-shot: play the 7-cell strip once across
            # the (1 s) dying window and hold the last frame.
            self.die_clock += dt
            if self.dying_timer <= 0:
                self.alive = False
            return
        # ---- Frozen state: half speed, crackles fade out ----
        if self.ice_timer > 0:
            self.ice_timer -= dt
            # ease in ice crackles: spawn new ones near the start of the freeze
            if self.ice_max > 0 and self.ice_timer > self.ice_max * 0.4 and len(self.ice_crackles) < 5:
                if random.random() < 0.18:
                    self.ice_crackles.append((
                        random.uniform(-0.3, 0.3),    # x_offset factor of w
                        random.uniform(-0.5, 0.0),    # y_offset factor of h
                        0.0,                            # age
                        random.uniform(0.45, 0.85),     # max_age
                    ))
            # advance + drop dead crackles
            self.ice_crackles = [
                (x, y, a + dt, m) for (x, y, a, m) in self.ice_crackles
                if a + dt < m
            ]
            # freeze ending: clear crackles early so they don't pop out
            if self.ice_timer <= 0:
                self.ice_crackles.clear()
        if self.is_bungee:
            return self._update_bungee(dt, plants)

        # ---- Digger: burrow / tunnel / surface state machine ----
        # Runs before the normal walk so the digger never has to path around
        # the plants it is explicitly built to bypass.
        if self.is_digger and self.dig_phase is not None:
            return self._update_digger(dt)

        # ---- Support AI: healers mend, commanders rally ----
        if self.is_healer or self.is_commander:
            self.action_timer -= dt
            if self.action_timer <= 0:
                if self.is_commander:
                    self.action_timer = COMMANDER_PULSE_S
                    self._rally_allies(zombies)
                else:
                    self.action_timer = HEALER_INTERVAL
                    self._heal_ally(zombies)

        # find the first blocking plant in this row. Plants on a lily pad are
        # eaten before the lily pad itself; lily pads use a narrow hitbox so
        # the plant body is what the zombie first runs into.
        overlaps = []
        for p in plants:
            if not p.alive:
                continue
            if p.row != self.row:
                continue
            if p.plant_type == PLANT_LILYPAD:
                cw = getattr(p, "collide_w", 36)
                cl = p.x + (p.w - cw) // 2
                cr = cl + cw
                if cr > self.x and cl < self.x + self.w:
                    overlaps.append(p)
            else:
                if p.x + p.w > self.x and p.x < self.x + self.w:
                    overlaps.append(p)
        blocking_plant = None
        if overlaps:
            # bodies (non-lily) first, then the closest lily pad
            bodies = [p for p in overlaps if p.plant_type != PLANT_LILYPAD]
            pool = bodies if bodies else overlaps
            blocking_plant = max(pool, key=lambda p: p.x)  # nearest to zombie

        # Pole Vaulting Zombie: vault exactly past the first blocking body.
        if (self.zombie_type == ZOMBIE_POLE and not self.has_vaulted
                and blocking_plant is not None):
            self.has_vaulted = True
            # Land with the right edge just left of the plant (same semantic
            # as before: clears the first plant without tunnelling two cells)
            # but travel there on a dt-driven arc instead of a single-frame
            # x-snap, and keep the wave speed scaled after landing.
            self._vault_from_x = self.x
            self._vault_to_x = blocking_plant.x - self.w - 8
            self.vault_timer = POLE_VAULT_T
            self.vault_t = 0.0
            self.is_eating = False
            self.eat_timer = 0
            return None

        if self.vault_timer > 0:
            self.vault_timer -= dt
            k = min(1.0, 1.0 - max(0.0, self.vault_timer) / POLE_VAULT_T)
            ease = k * k * (3.0 - 2.0 * k)
            self.x = self._vault_from_x + (self._vault_to_x - self._vault_from_x) * ease
            self.vault_lift = math.sin(k * math.pi) * POLE_VAULT_LIFT
            if self.vault_timer <= 0:
                self.x = self._vault_to_x
                self.vault_lift = 0.0
                # Post-vault shuffle: relative to the zombie's scaled speed so
                # late-wave poles stay late-wave fast.
                self.speed = self.base_speed * self._speed_mult * POLE_VAULT_LAND_MULT
            return None

        # Boss: periodically request a minion spawn. The game appends it after
        # the current zombie iteration, avoiding list mutation during traversal.
        if self.is_boss:
            self.summon_timer -= dt
            if self.summon_timer <= 0:
                self.summon_timer = max(3.5, 7.0 - self.anim_time * 0.02)
                return self._spawn_minion()

        # ---- Tactician: pick a softer lane and hop sideways into it ----
        if self.is_tactician:
            if self.transfer_t > 0:
                self.transfer_t = max(0.0, self.transfer_t - dt)
                t = 1.0 - self.transfer_t / TACTICIAN_TRANSFER_T
                ease = t * t * (3.0 - 2.0 * t)
                self.y = (self._transfer_from_y
                          + (self._transfer_to_y - self._transfer_from_y) * ease
                          - math.sin(t * math.pi) * 26.0)
            else:
                self.transfer_timer -= dt
                if self.transfer_timer <= 0:
                    self.transfer_timer = TACTICIAN_TRANSFER_S
                    self._try_lane_transfer()

        if blocking_plant and not self.floating and not self.underground:
            if not self.is_eating:
                # Restart the chew cycle from frame 0 — eat_clock only ever
                # grew, so a zombie that stopped and resumed eating would
                # start mid-animation with a stale frame offset.
                self.eat_clock = 0.0
            self.is_eating = True
            self.eat_clock += dt
            phase = self.freeze_factor()
            self.eat_timer += dt * phase
            if self.eat_timer > self.EAT_BITE_S:
                blocking_plant.take_damage(self.eat_damage * self.rally_dmg)
                self.eat_timer = 0
        elif self.reached_house:
            # zombie is at the door, eating it — no longer walks
            if not self.is_eating:
                self.eat_clock = 0.0
            self.is_eating = True
            self.eat_clock += dt
            self.eat_timer += dt
            if self.eat_timer > self.EAT_BITE_S:
                self.eat_timer = 0
                # house HP is drained by game loop when a zombie has reached the door;
                # here we just keep the zombie planted at the door frame
        else:
            self.is_eating = False
            self.eat_timer = 0
            # Frozen zombies walk slower (and the slow eases off in the last
            # stretch so they visibly "thaw" instead of snapping back).
            move_dt = dt * self.freeze_factor()
            dist = self.speed * self.rally_speed * move_dt
            self.x -= dist
            # Distance-driven walk cycle: feet stay planted at any speed, and
            # a slowed zombie visibly trudges rather than sliding.
            previous_phase = self.walk_phase
            self.walk_phase = (self.walk_phase + dist / self.STRIDE_PX) % 1.0
            self._step_just_done = self.walk_phase < previous_phase
            # Digger: start tunnelling as it reaches the front line.
            if self.is_digger and self.dig_phase is None:
                self._maybe_start_dig()
            # zombies walk past the lawnmower slot; the lawnmower trigger is
            # handled in game.py (mower may already have been used)
            # Entering the house is based on the visible/combat body's left edge,
            # matching mower collision and eliminating the old 7px dead zone.
            r = self.rect()
            if r.left < HOUSE_LEFT_WALL:
                self.x += HOUSE_LEFT_WALL - r.left
                self.reached_house = True
        return None

    # ------------------------------------------------------------ AI brains
    def freeze_factor(self):
        """Motion scale from the ice slow: 1.0 thawed, 0.5 deeply frozen."""
        if self.ice_timer <= 0:
            return 1.0
        return 0.5 if self.ice_timer > self.ice_max * 0.4 else 0.7

    def _try_lane_transfer(self):
        """Hop to a softer row if one is worth the trip (tactician brain)."""
        import ai
        it = ai.intel
        if not it.row_threat or self.underground or self.reached_house:
            return
        # Never abandon a lane we are actively chewing through.
        if self.eaten_plant is not None:
            return
        target = it.best_transfer(self.row)
        if target is None or target == self.row:
            return
        self._transfer_from_y = self.y
        self._transfer_to_y = float(self.grid_y + target * CELL_H + 15)
        self.transfer_t = TACTICIAN_TRANSFER_T
        self.row = target
        self.is_eating = False
        self.eat_timer = 0
        # FX hook for the game layer (dashed arc + landing ring).
        self._hop_pending = (self.x, self.y, self._transfer_to_y)

    def _maybe_start_dig(self):
        """Begin burrowing once the front line is close, or after a while."""
        import ai
        if self.x > GRID_X + GRID_W:
            return
        front = ai.intel.row_front_x[self.row]
        near_front = front < SCREEN_WIDTH and self.x <= front + CELL_W * 0.5
        # Nothing in the lane: still tunnel a fixed distance so the digger
        # crosses open ground fast and arrives as a surprise.
        open_ground = front >= SCREEN_WIDTH and self.x < GRID_X + GRID_W * 0.62
        if not (near_front or open_ground):
            return
        self.dig_phase = "burrow"
        self.dig_t = 0.0
        if front < SCREEN_WIDTH:
            self._dig_target_x = max(GRID_X + 6.0, front - CELL_W * 0.85)
        else:
            self._dig_target_x = max(GRID_X + 6.0, self.x - DIGGER_MIN_TUNNEL)

    def _update_digger(self, dt):
        """0.55 s sink → fast underground travel → 0.55 s surface."""
        half = DIGGER_BURROW_S * 0.5
        self.dig_t += dt
        if self.dig_phase == "burrow":
            if self.dig_t >= half:
                self.underground = True
            if self.dig_t >= DIGGER_BURROW_S:
                self.dig_phase = "under"
                self.dig_t = 0.0
                self._dig_dust_pending = True
        elif self.dig_phase == "under":
            step = self.speed * self.rally_speed * DIGGER_SPEED_MULT * dt
            self.x -= step
            self.walk_phase = (self.walk_phase + step / self.STRIDE_PX) % 1.0
            # Turn up some dirt while tunnelling (game layer spawns the puff).
            self._dig_dust_timer = getattr(self, "_dig_dust_timer", 0.0) + dt
            if self._dig_dust_timer >= 0.05:
                self._dig_dust_timer = 0.0
                self._dig_dust_pending = True
            if self.x <= self._dig_target_x:
                self.x = self._dig_target_x
                self.dig_phase = "emerge"
                self.dig_t = 0.0
                self._emerge_pending = True
        else:  # emerge
            if self.dig_t >= half:
                self.underground = False
            if self.dig_t >= DIGGER_BURROW_S:
                self.dig_phase = None
                self.dig_t = 0.0
                self.underground = False
        return None

    def _heal_ally(self, zombies):
        """Mend the worst-hurt zombie in range (healer brain)."""
        if not zombies:
            return
        best, best_ratio = None, 1.0
        for z in zombies:
            if z is self or not z.alive or z.dying_timer > 0 or z.hp <= 0:
                continue
            if z.underground:
                continue
            if abs(z.x - self.x) > HEALER_RANGE or abs(z.row - self.row) > 1:
                continue
            ratio = z.hp / float(z.max_hp)
            if ratio < best_ratio:
                best, best_ratio = z, ratio
        if best is None or best_ratio >= 0.995:
            return
        best.hp = min(best.max_hp, best.hp + HEALER_AMOUNT)
        best.hit_flash = 0.0
        self._beam_pending = (best, "heal")

    def _rally_allies(self, zombies):
        """Buff every zombie in range: +speed, +bite damage (commander brain)."""
        if not zombies:
            return
        n = 0
        for z in zombies:
            if not z.alive or z.dying_timer > 0 or z.hp <= 0:
                continue
            if abs(z.x - self.x) > COMMANDER_RANGE or abs(z.row - self.row) > 2:
                continue
            z.rally_timer = COMMANDER_PULSE_S * 0.7
            z.rally_speed = COMMANDER_SPEED_BUFF
            z.rally_dmg = COMMANDER_DMG_BUFF
            n += 1
        if n:
            self._beam_pending = (None, "rally")

    def _update_bungee(self, dt, plants):
        """Sky-drop state machine: descend → steal a plant → climb away."""
        target_y = self.grid_y + self.row * CELL_H + 15
        total = target_y + 250
        if self.bungee_phase == "descend":
            self.y += total / BUNGEE_DESCEND_S * dt
            if self.y >= target_y:
                self.y = target_y
                self.bungee_phase = "steal"
                self._steal_timer = 0.55
                # Visual: yellow lift-up dust at the plant's spot right before
                # the bungee snatches it.
                self._steal_burst_pending = True
        elif self.bungee_phase == "steal":
            self._steal_timer -= dt
            if self._steal_timer <= 0:
                stolen = self._steal_plant(plants)
                self.bungee_phase = "climb"
                if stolen is not None:
                    self._stolen_type = stolen.plant_type
                    self._stolen_hp = 1  # for visual scale only
        else:  # climb back up with the loot
            self.y -= total / BUNGEE_CLIMB_S * dt
            if self.y < -260:
                # Climbed off with the loot — an escape, not a death; the
                # game's settlement skips rewards for escaped zombies.
                self.escaped = True
                self.alive = False
        return None

    def _steal_plant(self, plants):
        """Grab the plant under the drop point (Bungee's signature move).
        Returns the stolen plant (for visual carry) or None."""
        body_cx = self.x + self.w // 2
        best = None
        for p in plants:
            if not p.alive or p.row != self.row:
                continue
            if abs((p.x + p.w // 2) - body_cx) < CELL_W * 0.6:
                if best is None or p.plant_type != PLANT_LILYPAD:
                    best = p
        if best is not None:
            best.alive = False
            self.stole_plant = True
            return best
        return None

    def _spawn_minion(self):
        """Boss action: produce a basic zombie on an exact lawn row.
        Minions fall from the sky — game.py reads the returned minion and
        animates the drop via `_minion_fall_t` (a small particle system that
        emits a landing ring + dust at touchdown).
        """
        ztype = random.choice(self.minion_pool)
        import ai
        row = random.choice(ai.intel.land_rows())
        x = SCREEN_WIDTH + 8
        target_y = self.grid_y + row * CELL_H + 15
        m = create_zombie(x, target_y, row, ztype)
        m.grid_y = self.grid_y
        m.in_wave = False  # free spawn — doesn't count toward wave clearing
        # Sky-drop animation state
        m._minion_drop = True
        m._drop_from_y = -180.0   # start above canvas
        m._drop_to_y = float(target_y)
        m._drop_t = 0.0
        m._drop_max = 0.55        # 0.55s fall
        m.y = m._drop_from_y
        return m

    def apply_ice(self, seconds=4.0):
        """Slow + ice crackle overlay for `seconds`. Calling repeatedly refreshes
        the duration up to `seconds`. Plant food / Snow Pea projectiles call
        this on hit.
        """
        if seconds > self.ice_max:
            self.ice_max = seconds
        # refresh the timer (don't stack beyond max)
        self.ice_timer = max(self.ice_timer, min(seconds, self.ice_max))
        # seed one immediate crackle so the first frame after freeze shows ice
        if not self.ice_crackles:
            self.ice_crackles.append((
                random.uniform(-0.3, 0.3),
                random.uniform(-0.5, 0.0),
                0.0,
                random.uniform(0.55, 0.85),
            ))

    def _sheet_prefix(self):
        """Pick sprite sheet based on zombie type + walking/eating/dying state."""
        if self.dying_timer > 0:
            suffix = "_die"
        elif self.is_eating:
            suffix = "_eat"
        else:
            suffix = "_idle"
        kind = "_b" if self.use_b_sheet else "_a"
        return f"anim_zombie{kind}{suffix}"

    def _frame_index(self):
        """Sprite cell for the current state (see the class docstring)."""
        n = self._FRAMES
        if self.dying_timer > 0:
            # one-shot: 7 cells across the 1 s dying window, then hold
            return min(n - 1, int(self.die_clock * n))
        if self.is_bungee:
            return int(self.anim_time * 6) % n
        if self.is_eating:
            return int(self.eat_clock * self.EAT_FPS) % n
        return int(self.walk_phase * n) % n

    def draw(self, screen):
        prefix = self._sheet_prefix()
        frame_idx = self._frame_index()
        foot_x = self.x + self.w // 2
        foot_y = self.y + CELL_H - 15

        # ---- Digger underground: a churning dirt mound instead of the body ----
        if self.underground:
            self._draw_burrow(screen, foot_x, foot_y)
            self._bcx, self._btop = foot_x, foot_y - 30
            self._bw, self._bh = 46, 30
            self._vx, self._vy = foot_x - 23, foot_y - 30
            self._draw_hp(screen)
            return

        frame = assets_loader.frame(prefix, frame_idx)
        if frame is not None:
            if self.is_boss:
                big = assets_loader.tinted_frame(prefix, frame_idx, self.w, self.h,
                                                 (60, 0, 0), 90)
                vx, vy = self.x, self.y
                if big is not None:
                    assets_loader.blit_shadow(screen, foot_x, self.y + self.h - 6,
                                              int(self.w * 0.85), 26, 120)
                    screen.blit(big, (vx, vy))
            else:
                # One constant scale per sheet, anchored on the body centre +
                # foot line (see assets_loader.frame_body) so a zombie never
                # changes size or foot point when its state changes.
                VH = ZOMBIE_BODY_H
                if self._air_lift > 0.1 or self.floating:
                    foot_y -= self._air_lift   # airborne body hovers above the lawn
                if self.vault_lift > 0.1:
                    foot_y -= self.vault_lift  # mid-vault hop arc
                if self.is_bungee:
                    foot_y = self.y + 92   # hanging under the cord
                if self.body_tint is not None:
                    tinted = assets_loader.frame_body_tinted(
                        prefix, frame_idx, VH, *self.body_tint)
                else:
                    tinted = None
                scaled, anchor_x, baseline, body_w, body_h = \
                    tinted or assets_loader.frame_body(prefix, frame_idx, VH)
                vx = foot_x - anchor_x
                vy = foot_y - baseline
                self._bcx = foot_x
                self._bw, self._bh = body_w, body_h
                moving = (not self.is_eating and self.dying_timer <= 0
                          and not self.floating and not self.is_bungee)
                if moving:
                    # Bob is phase-locked to the walk cycle (not to wall time)
                    # so the body rises on the same beat the feet plant.
                    vy += int(math.sin(self.walk_phase * math.tau) * 2.0)
                self._btop = vy + baseline - body_h
                # contact shadow grounds the body on the lawn
                if not self.floating and not self.is_bungee:
                    sw = max(18, int(body_w * 0.95))
                    sh = max(5, int(body_w * 0.30))
                    a = 118 if self.dying_timer <= 0 else 70
                    assets_loader.blit_shadow(screen, foot_x, foot_y - 2, sw, sh, a)
                if self.is_bungee:
                    # bungee cord from the top of the sky down to the harness
                    pygame.draw.line(screen, (50, 50, 58),
                                     (foot_x, -40), (foot_x, vy + 10), 3)
                    pygame.draw.line(screen, (90, 90, 100),
                                     (foot_x, -40), (foot_x, vy + 10), 1)
                screen.blit(scaled, (vx, vy))
                # Hit flash: light up the body's own silhouette rather than
                # painting an opaque white rectangle over the sprite padding.
                if self.hit_flash > 0:
                    if self.body_tint is not None:
                        flash = assets_loader.frame_body_tinted_flash(
                            prefix, frame_idx, VH, *self.body_tint)
                    else:
                        flash = assets_loader.frame_body_flash(prefix, frame_idx, VH)
                    if flash is not None:
                        # frame_body_flash is cached per (sheet,frame,h) —
                        # copy before stamping the flash alpha
                        screen.blit(
                            fx.faded(flash, min(255, int(255 * (self.hit_flash / 0.1) * 0.75))),
                            (vx, vy))
        else:
            # fallback to wiki 96x96 zombie icon, scaled up
            img = assets_loader.scale(f"zombie_{self.zombie_type}", 96, 96)
            if img is not None:
                vx = self.x + (self.w - 96) // 2
                vy = foot_y - 96
                assets_loader.blit_shadow(screen, foot_x, foot_y - 2, 76, 20, 118)
                screen.blit(img, (vx, vy))
            else:
                vx, vy = self.x, self.y + 20
                pygame.draw.ellipse(screen, (80, 80, 85), (self.x + 10, self.y + 20, 35, 30))
            self._bcx = vx + 48
            self._bw = self._bh = 96
            self._btop = vy
        # cache draw anchor for accessories below
        self._vx = vx
        self._vy = vy
        if self.is_boss:
            self._bcx = self.x + self.w // 2
            self._bw, self._bh = self.w, self.h
            self._btop = self.y

        self._draw_gear(screen)
        self._draw_ai_gear(screen)
        if self.is_bungee:
            self._draw_bungee_fx(screen)

        # Balloon Zombie: red balloon above the head, shrinking as it soaks
        bcx = self._bcx
        if self.floating and self.balloon_hp > 0:
            ratio = max(0.15, self.balloon_hp / BALLOON_HP)
            br = int(17 * (0.55 + 0.45 * ratio))
            bx = bcx + int(math.sin(self.anim_time * 3) * 3)
            bcy = self._vy - 26 - br
            pygame.draw.line(screen, (80, 70, 70),
                             (bx, bcy + br - 2), (bcx, self._vy + 8), 1)
            pygame.draw.circle(screen, (200, 40, 40), (bx, bcy), br)
            pygame.draw.circle(screen, (245, 100, 85), (bx - br // 3, bcy - br // 3),
                               max(2, br // 3))
            pygame.draw.circle(screen, (140, 20, 20), (bx, bcy), br, 2)

        # HP bar above head (only once damaged — see _draw_hp)
        self._draw_hp(screen)

        # ---- Frozen overlay: ice crackles drawn on top of the body ----
        # Each crackle is a 3-segment zig-zag line that fades out.
        if self.ice_timer > 0 and self.ice_crackles:
            for (xf, yf, age, max_age) in self.ice_crackles:
                t = age / max_age
                # bright at the start, fading out
                alpha = int(220 * (1.0 - t))
                if alpha <= 0:
                    continue
                cx = bcx + int(xf * self._bw)
                cy = self._btop + self._bh // 2 + int(yf * self._bh)
                # 3 zig-zag segments emanating from (cx, cy)
                line_color = (220, 245, 255, alpha)
                seg = 4
                pts = [
                    (cx - seg * 2, cy),
                    (cx - seg, cy - seg),
                    (cx, cy + seg // 2),
                    (cx + seg, cy - seg),
                    (cx + seg * 2, cy),
                ]
                for i in range(len(pts) - 1):
                    pygame.draw.line(screen, line_color[:3],
                                     pts[i], pts[i + 1], 2)
                # center sparkle dot (icy white)
                pygame.draw.circle(screen, (240, 250, 255), (cx, cy), 2)

    def _draw_gear(self, screen):
        """Headgear / held props, all placed relative to the drawn body box."""
        bcx, btop, bw, bh = self._bcx, self._btop, self._bw, self._bh
        ay = btop + int(bh * 0.42)     # chest height on the drawn body
        if self.zombie_type == ZOMBIE_CONEHEAD:
            w = max(22, int(bw * 0.74))
            h = max(30, int(w * 1.35))
            screen.blit(assets_loader.cone_sprite(w, h), (bcx - w // 2, btop + 12 - h))
        elif self.zombie_type == ZOMBIE_BUCKETHEAD:
            w = max(26, int(bw * 0.72))
            h = max(30, int(w * 1.15))
            screen.blit(assets_loader.bucket_sprite(w, h), (bcx - w // 2, btop + 10 - h))
        elif self.zombie_type == ZOMBIE_FLAG:
            # Pole rises from the shoulder on the trailing side and the banner
            # flies clear of the head — at bcx-18 the flag covered the face.
            fw, fh = max(28, int(bw * 0.80)), max(44, int(bh * 0.70))
            px = bcx + int(bw * 0.28)
            screen.blit(assets_loader.flag_sprite(fw, fh), (px, btop - fh + int(bh * 0.34)))
        if self.zombie_type == ZOMBIE_NEWSPAPER and not self.enraged:
            screen.blit(assets_loader.newspaper_sprite(32, 22), (bcx - 31, ay - 2))
        elif self.zombie_type == ZOMBIE_NEWSPAPER and self.enraged:
            # torn scrap flying off
            pygame.draw.rect(screen, (238, 235, 224), (bcx - 20, btop + 26, 14, 9))
            pygame.draw.rect(screen, (176, 172, 160), (bcx - 20, btop + 26, 14, 9), 1)
        if self.zombie_type == ZOMBIE_POLE and not self.has_vaulted:
            # Held out ahead of the body (zombies walk left) instead of
            # diagonally across the face.
            pw, ph = max(16, int(bw * 0.32)), max(40, int(bh * 0.62))
            screen.blit(assets_loader.pole_sprite(pw, ph),
                        (bcx - int(bw * 0.62), btop + int(bh * 0.10)))
        if self.is_boss:
            cx = self.x + self.w // 2
            pygame.draw.circle(screen, (200, 20, 20), (cx, self.y - 12), 14, 3)
            for i in range(4):
                a = self.anim_time * 6 + i * 1.57
                pygame.draw.circle(screen, (255, 60, 40),
                                   (int(cx + 20 * math.cos(a)),
                                    int(self.y - 12 + 20 * math.sin(a))), 4)

    def _draw_ai_gear(self, screen):
        """Accessories that name each AI variant, plus the rally aura.

        Everything here is placed against a *fractional* body box
        (``_btop``/``_bh`` are the drawn body's real top and height, measured
        from the sprite's own alpha bounds) rather than the sprite slot, so
        the proportions hold for any sheet scale.

        Rule of thumb used throughout: the head occupies the top ~30% of the
        body, the chest ~30-55%, the legs the rest. Gear that covers the face
        makes the zombie unreadable, so head props sit *above* ``head_top``
        and chest props stay in the torso band.
        """
        if not self.is_smart:
            return
        bcx, btop, bw, bh = self._bcx, self._btop, self._bw, self._bh
        head_top = btop + int(bh * 0.02)
        chest = btop + int(bh * 0.42)         # where the torso reads
        half = max(8, bw // 2)

        # Rally aura: a soft ground-glow under any zombie the commander has
        # buffed, drawn first so the body stays on top of it.
        if self.rally_timer > 0:
            pulse = 0.5 + 0.5 * math.sin(self.anim_time * 7.0)
            aura = _rally_aura()
            aura = fx.faded(aura, int(55 + 65 * pulse))
            ax = bcx
            ay = btop + int(bh * 0.80)        # around the feet, not the face
            screen.blit(aura, aura.get_rect(center=(ax, ay)))

        if self.is_tactician:
            # Violet beret sitting on the crown (overlapping the skull by a
            # few px, or it reads as a hat hovering in the air).
            hat_w = int(bw * 0.90)
            hat_h = max(6, int(bh * 0.13))
            hx = bcx - hat_w // 2
            hy = head_top + int(bh * 0.045)
            pygame.draw.ellipse(screen, (74, 48, 122), (hx, hy, hat_w, hat_h))
            pygame.draw.ellipse(screen, (124, 92, 190),
                                (hx + 2, hy + 1, int(hat_w * 0.68), max(3, hat_h - 3)))
            pygame.draw.circle(screen, (172, 142, 246),
                               (bcx + int(hat_w * 0.44), hy + 1),
                               max(2, int(bw * 0.09)))
            # sash across the chest: shoulder → opposite hip
            pygame.draw.line(screen, (132, 98, 200),
                             (bcx - int(bw * 0.30), chest - int(bh * 0.06)),
                             (bcx + int(bw * 0.26), chest + int(bh * 0.20)),
                             max(3, int(bw * 0.16)))
            if self.transfer_t > 0:
                # Ghost marker at the lane being hopped to.
                gy = int(self._transfer_to_y) + 30
                pygame.draw.ellipse(screen, (150, 120, 220),
                                    (bcx - 12, gy - 6, 24, 10), 2)
        elif self.is_digger:
            # Mining helmet with a lit lamp, shovel slung across the back.
            pygame.draw.ellipse(screen, (196, 152, 70),
                                (bcx - half, head_top - 2, bw, int(bh * 0.13)))
            pygame.draw.ellipse(screen, (232, 192, 104),
                                (bcx - half + 2, head_top - 1,
                                 int(bw * 0.70), int(bh * 0.08)))
            lamp_x = bcx
            lamp_y = head_top + int(bh * 0.10)
            pygame.draw.circle(screen, (255, 244, 170), (lamp_x, lamp_y),
                               max(3, int(bw * 0.11)))
            pygame.draw.circle(screen, (255, 255, 235), (lamp_x, lamp_y),
                               max(1, int(bw * 0.05)))
            # Shaft runs behind the shoulder so it never crosses the face.
            pygame.draw.line(screen, (150, 108, 56),
                             (bcx - int(bw * 0.42), head_top),
                             (bcx - int(bw * 0.10), btop + int(bh * 0.74)),
                             max(3, int(bw * 0.07)))
            tip_x, tip_y = bcx - int(bw * 0.14), btop + int(bh * 0.82)
            pygame.draw.polygon(screen, (182, 188, 196), [
                (tip_x - 5, tip_y - 4), (tip_x + 6, tip_y - 2),
                (tip_x + 1, tip_y + 8)])
            if self.dig_phase == "burrow":
                t = min(1.0, self.dig_t / (DIGGER_BURROW_S * 0.5))
                pygame.draw.circle(screen, (120, 92, 55),
                                   (bcx, self._vy + int(bh * (0.55 + 0.4 * t))),
                                   int(14 + 20 * t), 2)
        elif self.is_healer:
            # Apothecary apron + a pulsing cross on the chest (not the face).
            aw = int(bw * 0.38)
            ah = int(bh * 0.26)
            ax0 = bcx - aw // 2
            ay0 = chest + int(bh * 0.01)
            # Off-white, not pure white: at full brightness the apron glared
            # like a placard and swallowed the zombie's own shading.
            pygame.draw.rect(screen, (222, 234, 226), (ax0, ay0, aw, ah),
                             border_radius=3)
            # A soft edge instead of a hard outline, so the apron reads as
            # cloth over the body rather than a pasted-on white box.
            pygame.draw.rect(screen, (186, 202, 190), (ax0, ay0, aw, ah), 1,
                             border_radius=3)
            pygame.draw.line(screen, (210, 222, 212),
                             (ax0 + 1, ay0 + ah - 2), (ax0 + aw - 2, ay0 + ah - 2), 1)
            pulse = 0.5 + 0.5 * math.sin(self.anim_time * 4.5)
            k = max(3, int(bw * 0.12 + 2 * pulse))
            cx2 = bcx
            cy2 = ay0 + ah // 2
            t = max(2, int(bw * 0.06))
            pygame.draw.rect(screen, (54, 190, 96), (cx2 - t // 2, cy2 - k, t, k * 2))
            pygame.draw.rect(screen, (54, 190, 96), (cx2 - k, cy2 - t // 2, k * 2, t))
        elif self.is_commander:
            # Officer: peaked cap, gold epaulettes, a sash — NOT a full cape
            # (a cape this size reads as a red blob and hides the whole body).
            cap_w = int(bw * 0.86)
            pygame.draw.ellipse(screen, (48, 48, 56),
                                (bcx - cap_w // 2, head_top - int(bh * 0.05),
                                 cap_w, int(bh * 0.13)))
            pygame.draw.ellipse(screen, (72, 74, 86),
                                (bcx - cap_w // 2 + 2, head_top - int(bh * 0.05),
                                 int(cap_w * 0.72), int(bh * 0.08)))
            # peaked brim facing the way it walks (left)
            pygame.draw.polygon(screen, (34, 34, 40), [
                (bcx - cap_w // 2, head_top + int(bh * 0.06)),
                (bcx - cap_w // 2 - int(bw * 0.24), head_top + int(bh * 0.09)),
                (bcx - cap_w // 2, head_top + int(bh * 0.02)),
            ])
            # gold badge
            pygame.draw.circle(screen, (232, 196, 84),
                               (bcx, head_top + int(bh * 0.03)),
                               max(2, int(bw * 0.08)))
            # epaulette bars on both shoulders
            for sx in (-1, 1):
                ex = bcx + sx * int(bw * 0.40)
                pygame.draw.rect(screen, (232, 196, 84),
                                 (ex - 5, chest - int(bh * 0.10), 10, 4),
                                 border_radius=2)
            # crimson sash across the chest
            pygame.draw.line(screen, (176, 40, 44),
                             (bcx + int(bw * 0.34), chest - int(bh * 0.12)),
                             (bcx - int(bw * 0.30), chest + int(bh * 0.22)),
                             max(4, int(bw * 0.18)))

    def _draw_burrow(self, screen, foot_x, foot_y):
        """Dirt mound that replaces the body while a digger is underground."""
        w, h = 54, 26
        mound = _burrow_mound()
        screen.blit(mound, (foot_x - w // 2, foot_y - h + 2))
        # churning clods thrown up behind the mound
        for i in range(3):
            ph = (self.anim_time * 3.0 + i * 0.33) % 1.0
            dx = int((ph - 0.5) * 46)
            dy = int(-12 * math.sin(ph * math.pi))
            r = max(1, int(4 * (1.0 - ph)))
            pygame.draw.circle(screen, (118, 90, 52),
                               (foot_x + dx, foot_y - 12 + dy), r)

    def _draw_hp(self, screen):
        """Slim PvZ-style health pip, hidden until the zombie is hurt.

        A bar over every full-health zombie was visual noise — the player only
        needs to read health on the ones they have actually damaged. Bosses and
        balloons keep theirs always visible.
        """
        total = self.hp + max(0, self.balloon_hp)
        if total >= self.max_hp and not self.is_boss and not self.floating:
            return
        bw = 60 if self.is_boss else 40
        bh = 5 if self.is_boss else 4
        by = (self.y - 30) if self.is_boss else (self.y - 26)
        if self.floating:
            by -= 24
        if self.underground:
            by = self.y - 6
        bx = self.x + (self.w - bw) // 2
        ratio = max(0.0, min(1.0, total / float(self.max_hp)))
        # dark backing + rounded ends so it reads as a gauge, not a red slab
        pygame.draw.rect(screen, (28, 22, 22), (bx - 1, by - 1, bw + 2, bh + 2),
                         border_radius=3)
        fill_w = int(bw * ratio)
        if fill_w > 0:
            # green → amber → red as the zombie goes down
            if ratio > 0.6:
                col = (96, 200, 72)
            elif ratio > 0.3:
                col = (226, 178, 52)
            else:
                col = (214, 62, 52)
            pygame.draw.rect(screen, col, (bx, by, fill_w, bh), border_radius=2)
            # Gloss on the top half. A lighter *shade* rather than a
            # translucent white — pygame.draw ignores the alpha of an RGBA
            # colour on the display surface, so (255,255,255,46) painted the
            # whole gauge solid white.
            gloss = tuple(min(255, c + 70) for c in col)
            pygame.draw.rect(screen, gloss, (bx, by, fill_w, max(1, bh // 2)),
                             border_radius=2)

    def _draw_bungee_fx(self, screen):
        """Glow ring while snatching, plus the loot carried back up the cord."""
        bcx = self._bcx
        if self.bungee_phase == "steal" and self._steal_timer > 0:
            t = 1.0 - (self._steal_timer / 0.55)   # 0..1 across the steal
            ring_r = int(28 + t * 24)
            alpha = int(220 * (1.0 - t * 0.7))
            ring = _get_ring_sprite(ring_r, (180, 240, 255), alpha)
            cy = self._btop + self._bh - 12
            screen.blit(ring, (bcx - ring_r, cy - ring_r))
        elif self.bungee_phase == "climb" and self._stolen_type is not None:
            carry_x = bcx - 18
            carry_y = self._btop + self._bh - 8
            pygame.draw.circle(screen, (60, 160, 60), (carry_x, carry_y), 14)
            pygame.draw.circle(screen, (90, 200, 90), (carry_x - 4, carry_y - 4), 6)
            pygame.draw.rect(screen, (70, 130, 50), (carry_x - 2, carry_y + 8, 4, 8))

    def rect(self):
        """Combat hitbox aligned to the visible body, not the oversized cell box.

        The Rect is reused between calls: this runs several times per zombie
        per frame (mower sweep, projectile sweep, house check) and every one
        used to allocate. Callers only read it immediately, never hold it.
        """
        r = self._hit_rect
        if self.is_boss:
            r.update(int(self.x + 20), int(self.y + 15),
                     max(20, self.w - 40), max(30, self.h - 25))
        else:
            r.update(int(self.x + 18), int(self.y + 8), 58, 98)
        return r

    def take_damage(self, dmg):
        # A tunnelling digger is below the lawn: peas sail over it. This is the
        # whole point of the burrow, and it is what makes the digger a real
        # counter to a stacked wall instead of just a fast zombie.
        if self.underground:
            return
        # Airborne balloon soaks damage first (PvZ1 parity: 155 pops the
        # balloon, 290 total kills → the body continues at 135). Overflow
        # beyond the pop carries straight into the body.
        if self.floating and self.balloon_hp > 0:
            self.hit_flash = 0.1
            self.balloon_hp -= dmg
            if self.balloon_hp <= 0:
                overflow = -self.balloon_hp
                self.balloon_hp = 0
                self.floating = False
                # Grounded shuffle stays proportional to the wave-scaled speed.
                self.speed = self.base_speed * self._speed_mult * BALLOON_LAND_MULT
                self.hp = self.max_hp - BALLOON_HP - overflow
                # tell the game layer to emit a balloon-pop particle burst
                self._balloon_popped = True
                if self.hp <= 0 and self.dying_timer <= 0:
                    self.dying_timer = 1.0
            return
        self.hp -= dmg
        self.hit_flash = 0.1
        if (self.zombie_type == ZOMBIE_NEWSPAPER and not self.enraged):
            self.rage_dmg += dmg
            if self.rage_dmg >= self.rage_threshold:
                self.enraged = True
                # 3x the *scaled* walk speed, not the raw base: late-wave
                # newspapers must not regress to early-game absolute speeds.
                self.speed = self.base_speed * self._speed_mult * 3.0
                self._play_anger = True
        if self.hp <= 0 and self.dying_timer <= 0:
            self.dying_timer = 1.0  # play dying animation 1 second


def create_zombie(x, y, row, zombie_type=ZOMBIE_BASIC, speed_mult=1.0, dmg_mult=1.0):
    """Spawn a zombie; speed/eat-damage multipliers power survival scaling."""
    z = Zombie(x, y, row, zombie_type)
    z._speed_mult = speed_mult
    if speed_mult != 1.0 and not z.is_bungee:
        z.speed = z.base_speed * speed_mult
    if dmg_mult != 1.0:
        z.eat_damage = int(30 * dmg_mult)
    return z


