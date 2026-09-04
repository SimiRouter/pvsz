"""Wave spawner for zombies."""

import random
from constants import *
import i18n
tr = i18n.tr
from entities import create_zombie
from fx import cached_text


class WaveSystem:
    def __init__(self):
        self.wave_index = 0
        self.wave_active = False
        self.zombies_to_spawn = []
        self.spawn_timer = 0
        self.zombies_spawned = 0
        self.wave_zombies_remaining = 0
        self.total_zombies_remaining = 0
        self.waves = list(WAVES)  # default to module-level waves; can be replaced
        self.wave_count = len(self.waves)
        self.between_waves = False
        self.between_wave_timer = 0
        self.between_wave_duration = 5.0  # seconds between waves
        self.wave_cleared = False
        self.grid_y = GRID_Y  # current grid Y offset (changes for roof level)
        # Survival scaling: when True, every wave's zombies get faster and
        # bite harder as the global wave number grows (endless mode).
        self.scaling = False

    @staticmethod
    def scaling_for_wave(wave_number):
        """(speed_mult, dmg_mult) for a 1-based endless wave number."""
        speed = min(SURVIVAL_SPEED_CAP, 1.0 + SURVIVAL_SPEED_PER_WAVE * (wave_number - 1))
        dmg = min(SURVIVAL_DMG_CAP, 1.0 + SURVIVAL_DMG_PER_WAVE * (wave_number - 1))
        return speed, dmg

    def start_wave(self):
        if self.wave_index >= self.wave_count:
            return False
        wave_def = self.waves[self.wave_index]
        # support both 4-tuple (num, count, types, delay) and 3-tuple (count, types, delay)
        if len(wave_def) == 4:
            _, count, types, delay = wave_def
        else:
            count, types, delay = wave_def
        wave_number = self.wave_index + 1
        self.wave_active = True
        self.zombies_to_spawn = []
        if self.scaling:
            self.current_speed_mult, self.current_dmg_mult = self.scaling_for_wave(wave_number)
        else:
            self.current_speed_mult, self.current_dmg_mult = 1.0, 1.0
        self.current_spacing = max(
            WAVE_ZOMBIE_SPACING_MIN / 1000.0,
            min(3.2, delay / 2000.0 if delay > 0 else
                (WAVE_ZOMBIE_SPACING_BASE - (self.wave_index + 1) * 300) / 1000.0),
        )
        for i in range(count):
            ztype = random.choice(types)
            row = random.randint(0, GRID_ROWS - 1)
            self.zombies_to_spawn.append((ztype, row))
        # Huge waves in the endless mode drop a Bungee Zombie from the sky —
        # the original's nasty surprise for unguarded columns.
        if self.scaling and wave_number % 5 == 0:
            col = random.randint(1, GRID_COLS - 1)
            self.zombies_to_spawn.append((ZOMBIE_BUNGEE, random.randint(0, GRID_ROWS - 1), col))
        self.spawn_timer = 0
        self.zombies_spawned = 0
        self.wave_zombies_remaining = len(self.zombies_to_spawn)
        self.total_zombies_remaining = len(self.zombies_to_spawn)
        self.wave_index += 1
        return True

    def update(self, dt, zombies_list):
        if not self.wave_active:
            return

        # spawn zombies
        if self.zombies_spawned < len(self.zombies_to_spawn):
            self.spawn_timer += dt
            if self.spawn_timer >= self.current_spacing:
                spawn_def = self.zombies_to_spawn[self.zombies_spawned]
                self.zombies_spawned += 1
                self.spawn_timer -= self.current_spacing
                if len(spawn_def) == 3:
                    # bungee: (type, row, column) — enters from the sky
                    ztype, row, col = spawn_def
                    x = GRID_X + col * CELL_W + (CELL_W - 90) // 2
                    y = -250
                    z = create_zombie(x, y, row, ztype,
                                      self.current_speed_mult, self.current_dmg_mult)
                else:
                    ztype, row = spawn_def
                    x = SCREEN_WIDTH + 8  # fully off-canvas but visible almost immediately
                    y = self.grid_y + row * CELL_H + 15
                    z = create_zombie(x, y, row, ztype,
                                      self.current_speed_mult, self.current_dmg_mult)
                z.grid_y = self.grid_y
                zombies_list.append(z)

        # check if wave complete
        if self.zombies_spawned >= len(self.zombies_to_spawn) and self.wave_zombies_remaining <= 0:
            self.wave_active = False
            self.between_waves = True
            self.between_wave_timer = 0
            self.wave_cleared = True

    def zombie_died(self):
        # Defensive clamp: a projectile kill and the later death-animation cleanup
        # must never decrement the same wave zombie twice.
        self.wave_zombies_remaining = max(0, self.wave_zombies_remaining - 1)
        self.total_zombies_remaining = max(0, self.total_zombies_remaining - 1)

    def update_between_waves(self, dt):
        if self.between_waves:
            self.between_wave_timer += dt
            if self.between_wave_timer >= self.between_wave_duration:
                self.between_waves = False
                self.wave_cleared = False
                return True  # start next wave
        return False

    def draw_wave_indicator(self, screen, font):
        # Keep wave HUD left of the shovel (right edge starts around x=1320).
        if self.wave_active:
            text = cached_text(i18n.fmt_wave(self.wave_index), 22, COLOR_WHITE, outline=(0, 0, 0))
        elif self.between_waves:
            secs = max(0, (self.between_wave_duration - self.between_wave_timer))
            text = cached_text(i18n.fmt_next_wave(secs), 22, COLOR_WHITE, outline=(0, 0, 0))
        else:
            return
        x = min(SCREEN_WIDTH - 300, SCREEN_WIDTH - text.get_width() - 190)
        screen.blit(text, (max(SEED_CARD_START_X + 380, x), 10))

    def is_last_wave(self):
        return self.wave_index >= self.wave_count