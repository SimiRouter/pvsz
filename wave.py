"""Wave spawner for zombies."""

import random
from constants import *
import ai
import i18n
tr = i18n.tr
from entities import create_zombie
from fx import cached_text


# AI zombie types the director may introduce. A level "unlocks" one simply by
# naming it somewhere in its own wave table — so the authored ramp in
# levels.py is what decides when the player first meets each of them, and the
# director only varies *how many* show up from there on.
_AI_TYPES = (ZOMBIE_TACTICIAN, ZOMBIE_DIGGER, ZOMBIE_HEALER, ZOMBIE_COMMANDER)


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
        # Adaptive wave composition. Reads the per-frame battlefield snapshot
        # in ai.intel and biases each wave toward whatever the player's
        # defense is weak against (see ai.Director).
        self.director = ai.Director(enabled=DIRECTOR_ENABLED)

    @staticmethod
    def scaling_for_wave(wave_number):
        """(speed_mult, dmg_mult) for a 1-based endless wave number."""
        speed = min(SURVIVAL_SPEED_CAP, 1.0 + SURVIVAL_SPEED_PER_WAVE * (wave_number - 1))
        dmg = min(SURVIVAL_DMG_CAP, 1.0 + SURVIVAL_DMG_PER_WAVE * (wave_number - 1))
        return speed, dmg

    # ------------------------------------------------------ director support
    @staticmethod
    def _types_of(wave_def):
        """The type list of a wave, which may be a 3- or 4-tuple."""
        return wave_def[2] if len(wave_def) == 4 else wave_def[1]

    def _allowed_types(self, upto=None):
        """Types the level has introduced *so far*, through wave ``upto``.

        Deliberately progressive rather than the union over the whole table:
        a level that saves Bucketheads for its final wave must not have the
        Director sprinkle them through wave one. Counting only the waves the
        player has already seen keeps the authored ramp intact while still
        letting the Director bring back anything already met.

        ``upto`` defaults to the wave currently being composed.
        """
        if upto is None:
            upto = self.wave_index
        allowed = set()
        for wave_def in self.waves[:upto + 1]:
            allowed.update(self._types_of(wave_def))
        return allowed

    def _ai_unlocked(self):
        """Whether the AI zombie roster is in play for this level at all.

        Adventure levels gate on their wave table — a level gains an AI zombie
        the moment (and not before) the player reaches the wave that names it.
        Endless survival has no authored table to gate on, so it introduces
        them by wave number instead: early waves stay a warm-up, then the
        smart ones start showing up.
        """
        if self.scaling:
            return self.wave_index + 1 >= AI_UNLOCK_WAVE
        whole = set()
        for wave_def in self.waves:
            whole.update(self._types_of(wave_def))
        return any(t in _AI_TYPES for t in whole)

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
        # Composition: the level's scripted pool is the floor, and the
        # Director swaps up to DIRECTOR_MAX_ADAPT of the slots for counters to
        # whatever the player has actually built — bucketheads against massed
        # shooters, diggers against a wall line, a tactician against one
        # overloaded lane. The row is left as None and resolved at spawn time,
        # so it reflects the board as it is when the zombie walks on rather
        # than as it was when the wave was queued.
        allowed = self._allowed_types()
        if self.scaling and self._ai_unlocked():
            # Endless survival has no authored table naming AI zombies, so the
            # progressive allowed-set above never contains them. Merge them in
            # once the wave-number gate (_ai_unlocked) opens, otherwise the
            # director's unlock_ai flag would be silently dead in survival.
            allowed = allowed | set(_AI_TYPES)
        roster = self.director.compose(types, count, allowed,
                                       unlock_ai=self._ai_unlocked())
        for ztype in roster:
            self.zombies_to_spawn.append((ztype, None))
        # Huge waves in the endless mode drop a Bungee Zombie from the sky —
        # the original's nasty surprise for unguarded columns.
        if self.scaling and wave_number % 5 == 0:
            col = random.randint(1, GRID_COLS - 1)
            # Bungee descends onto a lawn row — water rows have nothing to
            # steal and a hovering zombie over open pool reads as a bug.
            self.zombies_to_spawn.append(
                (ZOMBIE_BUNGEE, random.choice(ai.intel.land_rows()), col))
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
                    if row is None:
                        # Resolved now, not when the wave was queued: the
                        # Director picks the softest lane as it stands at the
                        # moment this zombie actually walks on.
                        row = self.director.choose_row()
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