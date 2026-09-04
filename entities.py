"""Game entities: plants, zombies, projectiles, sun."""

import pygame
import math
import random
import assets_loader
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
class Sun:
    def __init__(self, x, y):
        self.x = x
        self.y = y
        self.target_y = y
        self.falling = True
        self.alive = True
        self.collect_radius = 30
        # Eject arc — when > 0, sun pops up before falling. Set by Sunflower.
        self.eject_t = 0.0           # 0..0.4s eject duration
        self.eject_vy = 0.0          # initial upward velocity (px/s)
        self.eject_from_y = float(y)
        self.angle = 0
        self.wobble = random.uniform(-0.05, 0.05)
        self.age = 0.0
        self.settled_age = 0.0
        # fly-to-jar collection (original PvZ feel)
        self.collected = False
        self.arrived = False
        self.amount = SUN_VALUE  # sunflowers at higher level produce more
        self._cx0 = 0.0
        self._cy0 = 0.0
        self._ctarget = (0.0, 0.0)
        self._ct = 0.0
        self._cdur = 0.3
        # bounce animation when first touching the lawn
        self.bounce_t = 1.0   # 1.0 = done; <1 = mid bounce
        self._bounce_amp = 6  # vertical bounce amplitude in px

    def collect(self, target):
        """Start the flight into the sun jar; game credits the sun on arrival."""
        if self.collected:
            return
        self.collected = True
        self.falling = False
        self._cx0, self._cy0 = self.x, self.y
        self._ctarget = (float(target[0]), float(target[1]))
        dist = math.hypot(self._ctarget[0] - self.x, self._ctarget[1] - self.y)
        self._cdur = max(0.22, min(0.5, dist / 2400.0))
        self._ct = 0.0

    def update(self, dt, player_x=None, player_y=None):
        self.age += dt
        self.angle += 2.2 * dt
        if self.collected:
            self._ct += dt / self._cdur
            t = min(1.0, self._ct)
            ease = t * t  # accelerate into the jar
            self.x = self._cx0 + (self._ctarget[0] - self._cx0) * ease
            self.y = self._cy0 + (self._ctarget[1] - self._cy0) * ease
            if self._ct >= 1.0:
                self.arrived = True
                self.alive = False
            return
        # Eject arc: short upward bounce when Sunflower produces a sun. The
        # sun pops out of the flower head with a brief ~160 px/s upward kick
        # before gravity (the falling phase) takes over. We delay the
        # falling handoff by 1 frame so the sun visibly continues downward
        # for a moment after the eject peak — without this, the very next
        # frame finds the sun already "at" its target and snaps to settled.
        if self.eject_t > 0:
            self.eject_t = max(0.0, self.eject_t - dt)
            self.y += self.eject_vy * dt
            self.eject_vy += 480 * dt   # gravity pulls the eject back down
            if self.eject_t <= 0:
                # hand off to falling — set falling target 30px below where
                # we are now so the falling phase actually has room to play.
                self.target_y = self.y + 30
                self.falling = True
            return
        if self.falling:
            self.y += 60 * dt
            if self.y >= self.target_y:
                self.y = self.target_y
                self.falling = False
                self.settled_age = 0.0
                self.bounce_t = 0.0   # start bounce right when we hit the lawn
        else:
            # Sun stays where it landed until the player clicks it.
            self.settled_age += dt
            if self.settled_age >= SUN_LIFETIME / 1000.0:
                self.alive = False
        # advance bounce (~0.45s total)
        if self.bounce_t < 1.0:
            self.bounce_t = min(1.0, self.bounce_t + dt / 0.45)
        return 0

    def draw(self, screen):
        offset_x = math.sin(self.angle) * 3
        # Bounce curve: dampened sin — peak at t=0.3, returns to 0 at t=1.0
        if self.bounce_t < 1.0:
            bounce_dy = -math.sin(self.bounce_t * math.pi) * self._bounce_amp * (1.0 - self.bounce_t)
        else:
            bounce_dy = 0.0
        sun_img = assets_loader.rotated("ui_sun", 40, 40,
                                        int((self.angle * 18) / 15))
        if sun_img is not None:
            # 24 cached rotation frames: stable and cheap even with many suns.
            screen.blit(sun_img, sun_img.get_rect(center=(int(self.x + offset_x), int(self.y + bounce_dy))))
        else:
            pygame.draw.circle(screen, COLOR_YELLOW, (int(self.x + offset_x), int(self.y)), 18)
            pygame.draw.circle(screen, COLOR_ORANGE, (int(self.x + offset_x), int(self.y)), 18, 2)
            pygame.draw.circle(screen, COLOR_WHITE, (int(self.x + offset_x - 4), int(self.y - 4)), 4)

    def rect(self):
        r = SUN_COLLECT_RADIUS
        return pygame.Rect(self.x - r, self.y - r, r * 2, r * 2)


# ============================================================
# Plant Food (能量豆 — PvZ2 signature pickup)
# ============================================================
_food_glow_cache = {}


class PlantFood:
    """Falls from the sky like a sun; clicking stores it for feeding a plant."""

    def __init__(self, x, y):
        self.x = x
        self.y = y
        self.target_y = y
        self.falling = True
        self.alive = True
        self.age = 0.0
        self.settled_age = 0.0

    def update(self, dt):
        self.age += dt
        if self.falling:
            self.y += 55 * dt
            if self.y >= self.target_y:
                self.y = self.target_y
                self.falling = False
        else:
            self.settled_age += dt
            if self.settled_age >= PLANT_FOOD_LIFETIME / 1000.0:
                self.alive = False

    def draw(self, screen):
        pulse = 1.0 + 0.10 * math.sin(self.age * 5)
        glow = _food_glow_cache.get("glow")
        if glow is None:
            glow = pygame.Surface((64, 64), pygame.SRCALPHA)
            for r, a in ((30, 40), (24, 60), (18, 80)):
                pygame.draw.circle(glow, (120, 255, 120, a), (32, 32), r)
            _food_glow_cache["glow"] = glow
        glow.set_alpha(int(140 + 90 * math.sin(self.age * 5)))
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
        bw = 40
        bh = 4
        bx = self.x + 10
        by = self.y - 8
        pygame.draw.rect(screen, COLOR_BAR_BG, (bx, by, bw, bh))
        fill_w = int(bw * (self.hp / self.max_hp))
        pygame.draw.rect(screen, COLOR_BAR_FILL, (bx, by, fill_w, bh))

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
        bw = 40
        bh = 4
        bx = self.x + 10
        by = self.y - 8
        pygame.draw.rect(screen, COLOR_BAR_BG, (bx, by, bw, bh))
        fill_w = int(bw * (self.hp / self.max_hp))
        pygame.draw.rect(screen, COLOR_BAR_FILL, (bx, by, fill_w, bh))

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
        proj = KernelBomb(sx, sy, target_x, target_y)
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
        bw = 50
        bh = 4
        bx = self.x + 10
        by = self.y - 8
        pygame.draw.rect(screen, COLOR_BAR_BG, (bx, by, bw, bh))
        fill_w = int(bw * (self.hp / self.max_hp))
        pygame.draw.rect(screen, COLOR_BAR_FILL, (bx, by, fill_w, bh))

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
            # Eject arc: pop the sun up briefly so it visibly leaves the
            # flower head instead of appearing out of thin air.
            sun.falling = False
            sun.eject_t = 0.40
            sun.eject_vy = -160.0
            sun.eject_from_y = sun.y
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
            halo.set_alpha(strength)
            screen.blit(halo, (self.x + 4 + dx, self.y + 4 - dy))
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
        bw = 40
        bh = 4
        bx = self.x + 10
        by = self.y - 8
        pygame.draw.rect(screen, COLOR_BAR_BG, (bx, by, bw, bh))
        fill_w = int(bw * (self.hp / self.max_hp))
        pygame.draw.rect(screen, COLOR_BAR_FILL, (bx, by, fill_w, bh))

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
        n_cracks = int(1 + damage * 5)           # 1..6 cracks
        # center of the visible sprite (relative to the sprite box)
        cx = self.x + self.w // 2
        cy = self.y + self.h // 2 - 4
        rng = random.Random(int(self.x) * 31 + int(self.y))  # deterministic per plant
        for _ in range(n_cracks):
            # random bite anchor on the wallnut body
            bx = cx + rng.randint(-22, 22)
            by = cy + rng.randint(-22, 22)
            # zig-zag crack with 3-5 segments
            n_segs = rng.randint(3, 5)
            pts = [(bx, by)]
            for s in range(n_segs):
                last = pts[-1]
                # each segment drifts away from bite and varies direction
                pts.append((last[0] + rng.randint(-7, 7),
                            last[1] + rng.randint(-9, 9)))
            # darker shade as wallnut gets chewed
            shade = 50 + int(60 * damage)
            color = (shade, shade // 2, shade // 3)
            for i in range(len(pts) - 1):
                pygame.draw.line(screen, color, pts[i], pts[i + 1], 2)

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
        bw = 40
        bh = 4
        bx = self.x + 10
        by = self.y - 8
        pygame.draw.rect(screen, COLOR_BAR_BG, (bx, by, bw, bh))
        fill_w = int(bw * (self.hp / self.max_hp))
        pygame.draw.rect(screen, COLOR_BAR_FILL, (bx, by, fill_w, bh))

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
        if img is not None:
            if self.explode:
                # bright explosion overlay
                screen.blit(img, (self.x + dx, self.y - dy))
                flash = pygame.Surface((self.w + 20, self.h + 20), pygame.SRCALPHA)
                pygame.draw.circle(flash, (255, 200, 100, 180), (self.w // 2 + 10, self.h // 2 + 10), 35)
                screen.blit(flash, (self.x - 10 + dx, self.y - 10 - dy))
            else:
                screen.blit(img, (self.x + dx, self.y - dy))
            # fuse spark when close to detonation
            progress = self.fuse_timer / self.fuse_max
            if not self.explode and progress > 0.4:
                spark_size = 4 + int(progress * 4)
                spark_color = (255, int(200 * (1 - progress)), 0)
                pygame.draw.circle(screen, spark_color, (int(self.x + self.w // 2 + dx), int(self.y + 8)), spark_size)
        else:
            color = (220, 20, 20) if not self.explode else (255, 100, 0)
            pygame.draw.circle(screen, color, (int(self.x + 30 + dx), int(self.y + 30)), 18)
            pygame.draw.circle(screen, (255, 50, 50), (int(self.x + 30), int(self.y + 30)), 18, 2)
            pygame.draw.line(screen, (0, 80, 0), (int(self.x + 30), int(self.y + 10)), (int(self.x + 30), int(self.y + 20)), 2)
            if self.explode:
                pygame.draw.circle(screen, COLOR_ORANGE, (int(self.x + 30), int(self.y + 30)), 30, 3)
        self._draw_hp(screen)

    def _draw_hp(self, screen):
        bw = 40
        bh = 4
        bx = self.x + 10
        by = self.y - 8
        pygame.draw.rect(screen, COLOR_BAR_BG, (bx, by, bw, bh))
        fill_w = int(bw * (self.hp / self.max_hp))
        pygame.draw.rect(screen, COLOR_BAR_FILL, (bx, by, fill_w, bh))

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
        bw = 40
        bh = 4
        bx = self.x + 10
        by = self.y - 8
        pygame.draw.rect(screen, COLOR_BAR_BG, (bx, by, bw, bh))
        fill_w = int(bw * (self.hp / self.max_hp))
        pygame.draw.rect(screen, COLOR_BAR_FILL, (bx, by, fill_w, bh))

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
                img.set_alpha(90 - i * 20)
                screen.blit(img, (int(self.x) - 16 * (i + 1), self.y + 14))

    def rect(self):
        return pygame.Rect(self.x, self.y, self.w, self.h)


# ============================================================
# Zombies
# ============================================================
class Zombie:
    def __init__(self, x, y, row, zombie_type=ZOMBIE_BASIC):
        self.x = x
        self.y = y
        self.row = row
        self.zombie_type = zombie_type
        info = ZOMBIE_INFO[zombie_type]
        self.max_hp = info["hp"]
        self.hp = info["hp"]
        self.base_speed = info["speed"]
        self.speed = info["speed"]
        self.reward = info["reward"]
        self.w = 90   # sprite frame is 60 wide; doubled to look big
        self.h = 116  # sprite frame is 58 tall; doubled
        self.alive = True
        self.eaten_plant = None
        self.eat_timer = 0
        self.shake = 0
        self.hit_flash = 0
        self.reached_house = False
        self.reached_lawnmower = False
        self.anim_time = 0
        self.is_eating = False
        self.dying_timer = 0
        # zombie's intrinsic offset for walking (offset within frame)
        self.walk_offset = 0
        self._step_just_done = False
        # Frozen state (e.g. Snow Pea, Winter Melon). ice_timer > 0 means
        # zombie is slow + covered in ice crackles. Crackle overlay is drawn
        # on top of the zombie sprite by Zombie.draw.
        self.ice_timer = 0.0
        self.ice_max = 0.0
        self.ice_crackles = []  # list of (x_offset, y_offset, age, max_age)
        self.use_b_sheet = random.random() < 0.5  # alternate between two zombie sprites for variety
        self.is_boss = (zombie_type == ZOMBIE_BOSS)
        self.in_wave = True  # counts toward the current wave (boss minions don't)
        self.death_counted = False
        self.grid_y = GRID_Y
        self.spawn_request = None

        # Newspaper Zombie: enrages once the paper takes enough damage
        self.enraged = False
        self.rage_dmg = 0
        self.rage_threshold = 90
        # Pole Vaulting Zombie: one jump over the first plant
        self.has_vaulted = False
        self.vault_timer = 0
        # Boss: summons minions
        self.summon_timer = 3.0
        self.minion_pool = [ZOMBIE_BASIC, ZOMBIE_CONEHEAD]
        # bite damage scales in survival mode (game applies the wave multiplier)
        self.eat_damage = 30
        # Balloon Zombie: floats over plants and mowers until the balloon pops
        self.floating = (zombie_type == ZOMBIE_BALLOON)
        self.balloon_hp = BALLOON_HP if self.floating else 0
        # Bungee Zombie: drops from the sky on a cord and steals a plant
        self.is_bungee = (zombie_type == ZOMBIE_BUNGEE)
        self.bungee_phase = "descend" if self.is_bungee else None
        self._steal_timer = 0.0
        self.stole_plant = False
        self.steal_announced = False
        self._stolen_type = None       # plant_type carried in bungee hand
        self._steal_burst_pending = False
        if self.is_bungee:
            self.y = -250  # starts above the canvas, descends in update()

        if self.is_boss:
            self.w = 170
            self.h = 210
            self.use_b_sheet = False

    def update(self, dt, plants):
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
        if self.dying_timer > 0:
            self.dying_timer -= dt
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
            # Place the zombie's right edge just left of the plant. This avoids
            # tunnelling through two cells while still clearing the first plant.
            self.x = blocking_plant.x - self.w - 8
            self.vault_timer = 0.35
            self.speed = 15
            self.is_eating = False
            self.eat_timer = 0
            return None

        if self.vault_timer > 0:
            self.vault_timer -= dt
            # landing — hold position for a moment
            return None

        # Boss: periodically request a minion spawn. The game appends it after
        # the current zombie iteration, avoiding list mutation during traversal.
        if self.is_boss:
            self.summon_timer -= dt
            if self.summon_timer <= 0:
                self.summon_timer = max(3.5, 7.0 - self.anim_time * 0.02)
                return self._spawn_minion()

        if blocking_plant and not self.floating:
            self.is_eating = True
            self.eat_timer += dt
            if self.eat_timer > 1.0:
                blocking_plant.take_damage(self.eat_damage)
                self.eat_timer = 0
        elif self.reached_house:
            # zombie is at the door, eating it — no longer walks
            self.is_eating = True
            self.eat_timer += dt
            if self.eat_timer > 1.0:
                self.eat_timer = 0
                # house HP is drained by game loop when a zombie has reached the door;
                # here we just keep the zombie planted at the door frame
        else:
            self.is_eating = False
            self.eat_timer = 0
            # Frozen zombies walk at half speed (and the slow lingers for ~half
            # the remaining ice time so they "thaw" smoothly).
            move_dt = dt * (0.5 if self.ice_timer > self.ice_max * 0.4 else 0.7)
            self.x -= self.speed * move_dt
            self.walk_offset = (self.walk_offset + 4 * move_dt) % 1.0
            # Emit a "step taken" signal every full step cycle (0→1→0).
            # Game layer reads this to drop a faint grass-print ellipse.
            self._step_just_done = True
            # zombies walk past the lawnmower slot; the lawnmower trigger is
            # handled in game.py (mower may already have been used)
            # Entering the house is based on the visible/combat body's left edge,
            # matching mower collision and eliminating the old 7px dead zone.
            if self.rect().left < HOUSE_LEFT_WALL:
                self.x += HOUSE_LEFT_WALL - self.rect().left
                self.reached_house = True
        return None

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
        row = random.randint(0, GRID_ROWS - 1)
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

    def draw(self, screen):
        prefix = self._sheet_prefix()
        frame_idx = int(self.anim_time * 8) % 6
        frame = assets_loader.frame(prefix, frame_idx)
        if frame is not None:
            if self.is_boss:
                # boss drawn big & tinted dark with a red aura
                big = assets_loader.scaled_frame(prefix, frame_idx, self.w, self.h)
                big = big.copy()
                dark = pygame.Surface(big.get_size(), pygame.SRCALPHA)
                dark.fill((60, 0, 0, 90))
                big.blit(dark, (0, 0))
                screen.blit(big, (self.x, self.y))
                vx, vy = self.x, self.y
            else:
                # Anchor every frame by its opaque foot-contact point. The raw
                # 60x58 slots shift the body horizontally by up to ~30 px, so
                # fixed-slot blitting made a 0.3 px/frame walk look like jumping.
                VW, VH = 99, 96
                foot_x = self.x + self.w // 2
                foot_y = self.y + CELL_H - 15
                if self.floating:
                    foot_y -= 24  # airborne body hovers above the lawn
                if self.is_bungee:
                    foot_y = self.y + 92  # hanging under the cord
                scaled, anchor_x, _ = assets_loader.frame_body(
                    prefix, frame_idx, VW, VH)
                vx = foot_x - anchor_x
                # foot sits at the bottom of the padded sprite — never clips
                vy = foot_y - VH
                # tiny vertical bob is intentional, but never changes foot X.
                if not self.is_eating and self.dying_timer <= 0 \
                        and not self.floating and not self.is_bungee:
                    vy += int(math.sin(self.anim_time * 9) * 1.5)
                if self.is_bungee:
                    # bungee cord from the top of the sky down to the harness
                    pygame.draw.line(screen, (50, 50, 58),
                                     (foot_x, -40), (foot_x, vy + 10), 3)
                    pygame.draw.line(screen, (90, 90, 100),
                                     (foot_x, -40), (foot_x, vy + 10), 1)
                screen.blit(scaled, (vx, vy))
        else:
            # fallback to wiki 96x96 zombie icon, scaled up
            img = assets_loader.scale(f"zombie_{self.zombie_type}", 96, 96)
            if img is not None:
                vx = self.x + (self.w - 96) // 2
                foot = self.y + CELL_H - 15
                vy = foot - 96
                screen.blit(img, (vx, vy))
            else:
                vx, vy = self.x, self.y + 20
                pygame.draw.ellipse(screen, (80, 80, 85), (self.x + 10, self.y + 20, 35, 30))
        # cache draw anchor for accessories below
        self._vx = vx
        self._vy = vy
        self._vh = 96 if not self.is_boss else self.h

        # type accessories (drawn on top of the animated body)
        ax = self._vx
        ay = self._vy + 34 if self.is_boss else self._vy + 52  # chest height
        if self.zombie_type == ZOMBIE_CONEHEAD:
            pygame.draw.polygon(screen, (230, 112, 28), [
                (ax + 28, self._vy + 8), (ax + 57, self._vy + 8),
                (ax + 45, self._vy - 27),
            ])
            pygame.draw.polygon(screen, (255, 165, 55), [
                (ax + 31, self._vy + 4), (ax + 54, self._vy + 4),
                (ax + 45, self._vy - 21),
            ], 2)
        elif self.zombie_type == ZOMBIE_BUCKETHEAD:
            bucket = pygame.Rect(ax + 26, self._vy - 19, 36, 30)
            pygame.draw.rect(screen, (120, 128, 135), bucket, border_radius=4)
            pygame.draw.rect(screen, (205, 210, 215), bucket, 3, border_radius=4)
            pygame.draw.line(screen, (70, 75, 80), bucket.bottomleft, bucket.bottomright, 3)
        elif self.zombie_type == ZOMBIE_FLAG:
            pole_x = ax + 20
            pygame.draw.line(screen, (150, 105, 55),
                             (pole_x, self._vy + 20), (pole_x, self._vy + 82), 3)
            pygame.draw.polygon(screen, (210, 35, 35), [
                (pole_x, self._vy + 20), (pole_x + 34, self._vy + 27),
                (pole_x, self._vy + 42),
            ])
        if self.zombie_type == ZOMBIE_NEWSPAPER and not self.enraged:
            # newspaper in hands
            nx = ax + 12
            ny = ay
            pygame.draw.rect(screen, (235, 232, 220), (nx, ny, 28, 18), border_radius=2)
            pygame.draw.line(screen, (120, 120, 120), (nx + 2, ny + 5), (nx + 25, ny + 5), 1)
            pygame.draw.line(screen, (120, 120, 120), (nx + 2, ny + 10), (nx + 25, ny + 10), 1)
        elif self.zombie_type == ZOMBIE_NEWSPAPER and self.enraged:
            # torn paper flying off
            pygame.draw.rect(screen, (235, 232, 220), (ax + 2, self._vy + 26, 14, 9), border_radius=2)
        if self.zombie_type == ZOMBIE_POLE and not self.has_vaulted:
            # carrying the pole before the jump
            pygame.draw.line(screen, (150, 90, 40),
                             (ax + 34, self._vy + 6),
                             (ax + 66, self._vy + 42), 3)
        if self.is_boss:
            # boss crown/helmet + warning glow
            cx = self.x + self.w // 2
            pygame.draw.circle(screen, (200, 20, 20), (cx, self.y - 12), 14, 3)
            for i in range(4):
                a = self.anim_time * 6 + i * 1.57
                pygame.draw.circle(screen, (255, 60, 40),
                                   (int(cx + 20 * math.cos(a)), int(self.y - 12 + 20 * math.sin(a))), 4)

        # Balloon Zombie: red balloon above the head, shrinking as it soaks
        if self.floating and self.balloon_hp > 0:
            ratio = max(0.15, self.balloon_hp / BALLOON_HP)
            br = int(17 * (0.55 + 0.45 * ratio))
            bcx = self._vx + 49 + int(math.sin(self.anim_time * 3) * 3)
            bcy = self._vy - 26 - br
            pygame.draw.line(screen, (80, 70, 70),
                             (bcx, bcy + br - 2), (self._vx + 49, self._vy + 8), 1)
            pygame.draw.circle(screen, (200, 40, 40), (bcx, bcy), br)
            pygame.draw.circle(screen, (245, 100, 85), (bcx - br // 3, bcy - br // 3),
                               max(2, br // 3))
            pygame.draw.circle(screen, (140, 20, 20), (bcx, bcy), br, 2)

        # HP bar above head
        self._draw_hp(screen)
        # hit flash overlay
        if self.hit_flash > 0:
            flash = pygame.Surface((self.w, self._vh + 8), pygame.SRCALPHA)
            flash.fill((255, 255, 255, 100))
            screen.blit(flash, (self.x, self._vy))

        # ---- Bungee steal visuals ----
        if self.is_bungee:
            # 1) glow ring on the lawn during the steal phase
            if self.bungee_phase == "steal" and self._steal_timer > 0:
                t = 1.0 - (self._steal_timer / 0.55)   # 0..1 across the steal
                ring_r = int(28 + t * 24)
                alpha = int(220 * (1.0 - t * 0.7))
                # cyan ring on the lawn
                ring = pygame.Surface((ring_r * 2, ring_r * 2), pygame.SRCALPHA)
                pygame.draw.circle(ring, (180, 240, 255, alpha),
                                   (ring_r, ring_r), ring_r, 3)
                pygame.draw.circle(ring, (255, 255, 255, int(alpha * 0.6)),
                                   (ring_r, ring_r), ring_r // 2, 2)
                cx = self._vx + self.w // 2
                cy = self._vy + self._vh - 12
                screen.blit(ring, (cx - ring_r, cy - ring_r))
            # 2) the bungee is climbing away with a stolen plant in hand
            elif self.bungee_phase == "climb" and self._stolen_type is not None:
                carry_x = self._vx + self.w // 2 - 18
                carry_y = self._vy + self._vh - 8
                # draw a tiny plant sprite: green leafy ball
                pygame.draw.circle(screen, (60, 160, 60),
                                   (carry_x, carry_y), 14)
                pygame.draw.circle(screen, (90, 200, 90),
                                   (carry_x - 4, carry_y - 4), 6)
                # tiny stem
                pygame.draw.rect(screen, (70, 130, 50),
                                 (carry_x - 2, carry_y + 8, 4, 8))

        # ---- Frozen overlay: ice crackles drawn on top of the body ----
        # Each crackle is a 3-segment zig-zag line that fades out.
        if self.ice_timer > 0 and self.ice_crackles:
            for (xf, yf, age, max_age) in self.ice_crackles:
                t = age / max_age
                # bright at the start, fading out
                alpha = int(220 * (1.0 - t))
                if alpha <= 0:
                    continue
                cx = self._vx + self.w // 2 + int(xf * self.w)
                cy = self._vy + self._vh // 2 + int(yf * self._vh)
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

    def _draw_hp(self, screen):
        bw = 60 if self.is_boss else 52
        bh = 5 if self.is_boss else 4
        # above the (now upscaled) head: normal head ≈ self.y-13
        by = (self.y - 30) if self.is_boss else (self.y - 26)
        if self.floating:
            by -= 24
        bx = self.x + (self.w - bw) // 2
        pygame.draw.rect(screen, COLOR_BAR_BG, (bx, by, bw, bh))
        total = self.hp + max(0, self.balloon_hp)
        fill_w = int(bw * (total / self.max_hp))
        pygame.draw.rect(screen, (200, 50, 50), (bx, by, fill_w, bh))

    def rect(self):
        """Combat hitbox aligned to the visible body, not the oversized cell box."""
        if self.is_boss:
            return pygame.Rect(int(self.x + 20), int(self.y + 15),
                               max(20, self.w - 40), max(30, self.h - 25))
        return pygame.Rect(int(self.x + 18), int(self.y + 8), 58, 98)

    def take_damage(self, dmg):
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
                self.speed = 16  # grounded shuffle
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
                self.speed = max(self.base_speed * 3.0, 30)
                self._play_anger = True
        if self.hp <= 0 and self.dying_timer <= 0:
            self.dying_timer = 1.0  # play dying animation 1 second


def create_zombie(x, y, row, zombie_type=ZOMBIE_BASIC, speed_mult=1.0, dmg_mult=1.0):
    """Spawn a zombie; speed/eat-damage multipliers power survival scaling."""
    z = Zombie(x, y, row, zombie_type)
    if speed_mult != 1.0 and not z.is_bungee:
        z.speed = z.base_speed * speed_mult
    if dmg_mult != 1.0:
        z.eat_damage = int(30 * dmg_mult)
    return z