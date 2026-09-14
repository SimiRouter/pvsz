"""Main game loop and state manager. Supports Adventure and Survival modes."""

import math
import pygame
import random
from constants import *
from entities import *
from grid import Grid
from wave import WaveSystem
from ui import *
from fx import FloatingText, WaveWarning, Explosion, cached_text, alpha_rect
import assets_loader
assets_loader.init()
from levels import *
from levels import ADVENTURE_LEVELS, SURVIVAL_MODES
import save as save_mod
from save import derive_unlocked
import audio as audio_mod
import ai
import particles
import i18n
tr = i18n.tr


class Game:
    def __init__(self, screen):
        self.screen = screen
        self.state = STATE_MENU
        self.mode = None  # MODE_ADVENTURE or MODE_SURVIVAL
        self.current_level = None  # level dict for adventure, survival mode dict for survival
        self.level_id = None
        self.bg_type = BG_DAY
        self.grid = Grid()
        self.wave = WaveSystem()
        self.plants = []
        self.zombies = []
        self.projectiles = []
        self.suns = []
        self.lawnmowers = []
        self.lily_pads = []
        self.roof_tiles = []
        self.fog_layers = []
        self.shovel = None
        self.sun_value = 150
        self.font = i18n.font(22)
        self.big_font = i18n.font(32)
        self.title_font = i18n.font(48)
        self.tooltip = Tooltip()
        self.message = Message()
        self.seed_buttons = []
        self.sun_spawn_timer = 0.0
        self.house_hp = HOUSE_HP
        self.plant_cooldowns = {}
        self.completed_levels = set()
        self.survival_waves = 0
        # persistent progress
        self.save = save_mod.SaveData.load()
        i18n.set_lang(self.save.settings.get("lang", "zh"))
        self.completed_levels = set(self.save.completed_levels)
        self.unlocked_levels = derive_unlocked(self.completed_levels)
        self.pending_level = None  # level awaiting seed selection
        self.menu = MenuScreen()
        self.mode_select = ModeSelectScreen()
        self.level_select = LevelSelectScreen()
        self.seed_select = SeedSelectScreen()
        self.game_over = GameOverScreen()
        self.level_complete = LevelCompleteScreen()
        self.survival_complete = SurvivalCompleteScreen()
        self.pause_screen = PauseScreen()
        self.mouse_x = 0
        self.mouse_y = 0
        self._init_seed_buttons()
        self._load_sounds()
        # ---- FX / feel layers ----
        self.floating_texts = []   # damage numbers, sun collection, etc.
        self.wave_warning = WaveWarning()
        self.hover_plant = None    # Plant instance currently hovered
        self.hover_zombie = None   # Zombie instance currently hovered
        self.hover_sun = None      # Sun under the cursor (claims the click)
        self.last_wave_announced = -1  # which wave index we already announced
        # Every transient visual effect — soil poofs, pea sparks, balloon
        # shreds, mower dust, zombie chunks, plant-food rings, boss auras and
        # grass prints — lives in one particle system (particles.py) instead
        # of nine hand-rolled lists with nine update loops and nine draw loops.
        self.fx = particles.Effects()
        self.coin_drops = []       # gold coin pops when wave/level complete
        # Wave-start cinematic zoom + freeze: applied when wave_warning is alive.
        # Stored as a state so the draw side can read & interpolate.
        self._zoom_freeze = 0.0    # seconds remaining; <0 means inactive
        self.explosions = []       # cherry-bomb fireballs
        self.plant_foods = []      # 能量豆 drops on the lawn
        self.plant_food = 0        # stored plant food (feed a plant: click it)
        self.food_timer = random.uniform(11.0, 18.0)  # first drop comes early
        self.groan_timer = random.uniform(5.0, 10.0)  # ambient zombie moans
        # ---- feel / flow state ----
        self.speed_mult = 1.0      # 1x or 2x fast-forward
        self.shake = 0.0           # screen shake magnitude (px)
        self.sun_pulse = 0.0       # sun-counter highlight after collection
        self.flash_timer = 0.0     # white flash on explosions
        self.current_loadout = None  # picked seed cards of the running level
        self._press = None         # (seed button, origin pos) while pressing a card
        self._cob_armed = None     # selected Cob Cannon, or None when not targeting
        self._cursor_hidden = False
        self._ghost_cache = {}
        # Scratch surfaces for particle drawing — keyed by (w, h) to avoid
        # allocating tiny SRCALPHA surfaces every frame.
        self._scratch_cache = {}
        # Cached 45°-step tilt variants of the coin's "$" mark, so the coin
        # pop never allocates a transform.rotate per coin per frame.
        self._coin_mark_cache = {}
        # Reusable translucent layers (avoid allocating full-screen surfaces every frame)
        self._seed_bar_surface = pygame.Surface((SCREEN_WIDTH, UI_BAR_H), pygame.SRCALPHA)
        self._seed_bar_surface.fill((70, 50, 30, 230))
        # A flat wash, so it wants a constant alpha rather than a per-pixel one:
        # an SRCALPHA fill makes SDL blend every pixel separately where a plain
        # set_alpha() blends the whole surface in one pass. Measured over a full
        # screen, 0.65 ms per frame against 0.37 ms. Same pixels either way.
        self._fog_veil = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT))
        self._fog_veil.fill((180, 190, 200))
        self._fog_veil.set_alpha(60)
        # placement-preview tint overlays (green ok / red blocked)
        self._preview_ok = pygame.Surface((CELL_W, CELL_H), pygame.SRCALPHA)
        self._preview_ok.fill((70, 220, 90, 70))
        self._preview_bad = pygame.Surface((CELL_W, CELL_H), pygame.SRCALPHA)
        self._preview_bad.fill((230, 60, 60, 80))
        self._flash_surface = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
        self._flash_surface.fill((255, 245, 220))
        # static background layers built per level (pool water / roof tiles)
        self._water_layer = None
        self._water_row0 = 0
        self._roof_layer = None
        # top-bar quick buttons (fast-forward, pause) — left of the shovel
        self.btn_ff = pygame.Rect(SCREEN_WIDTH - 80 - 46, UI_BAR_Y + 14, 40, 48)
        self.btn_pause = pygame.Rect(SCREEN_WIDTH - 80 - 46 * 2 - 8, UI_BAR_Y + 14, 40, 48)
        self._topbar_hover = None

    def _init_seed_buttons(self):
        x = SEED_CARD_START_X
        y = UI_BAR_Y + 4
        for ptype in [PLANT_PEASHOOTER, PLANT_SUNFLOWER, PLANT_WALLNUT,
                      PLANT_CHERRYBOMB, PLANT_FUMESHROOM, PLANT_SNOWPEA,
                      PLANT_COBCANNON]:
            btn = SeedButton(ptype, x, y, SEED_CARD_W, SEED_CARD_H)
            self.seed_buttons.append(btn)
            x += SEED_CARD_W + SEED_CARD_GAP

    def _load_sounds(self):
        audio_mod.init()

    def _play_sound(self, name, volume=1.0):
        if self.save.settings.get("mute"):
            return
        audio_mod.play(name, volume)

    def _toggle_mute(self):
        cur = self.save.settings.get("mute", False)
        self.save.settings["mute"] = not cur
        self.save.save()
        if cur:
            self.message.show(tr("Sound ON"), 1200)
        else:
            self.message.show(tr("Sound OFF"), 1200)

    def _toggle_language(self):
        """Switch zh ↔ en and remember the choice."""
        lang = "en" if i18n.is_zh() else "zh"
        i18n.set_lang(lang)
        self.save.settings["lang"] = lang
        self.save.save()
        # Cached text renders are keyed on the translated string, but the
        # module-level caches in ui/fx survive screen rebuilds — drop them so
        # the old language's surfaces don't linger and any screen that isn't
        # rebuilt below (menu/mode/pause overlays) re-renders in the new one.
        invalidate_text_caches()
        # refresh cached screen titles
        if self.state == STATE_LEVEL_SELECT:
            if getattr(self, '_survival_select', False):
                self.level_select.set_items(SURVIVAL_MODES, tr("Survival Mode"))
            else:
                self.unlocked_levels = derive_unlocked(self.completed_levels)
                self.level_select.set_items(ADVENTURE_LEVELS, tr("Adventure Mode"),
                                            unlocked_ids=self.unlocked_levels)
        elif self.state == STATE_SEED_SELECT and self.pending_level is not None:
            self.seed_select.set_level(self.pending_level)

    def _setup_background(self, bg_type):
        """Set up background elements based on level type."""
        self.bg_type = bg_type
        self.lily_pads = []     # kept empty: lily pads are now player-planted
        self.roof_tiles = []
        self.fog_layers = []
        self._water_layer = None
        self._water_row0 = 0
        self._roof_layer = None

        if bg_type == BG_POOL:
            # Pre-render the water lanes once (animated per-frame line drawing
            # used to cost ~60 draw calls every frame).
            # Sized to just the water band rather than to the whole grid: the
            # surface has per-pixel alpha, and an alpha blit costs roughly ten
            # times an opaque one (measured 0.65 ms against 0.06 ms for a full
            # grid), so every transparent row it carries is paid for on every
            # frame while painting nothing. POOL_WATER_ROWS is contiguous today;
            # deriving the band from min/max keeps this correct if it ever is
            # not, at the cost of repainting the rows between two disjoint bands.
            self._water_row0 = min(POOL_WATER_ROWS)
            band_h = (max(POOL_WATER_ROWS) - self._water_row0 + 1) * CELL_H
            self._water_layer = pygame.Surface((GRID_W, band_h), pygame.SRCALPHA)
            for row in POOL_WATER_ROWS:
                y = (row - self._water_row0) * CELL_H
                water = pygame.Rect(0, y, GRID_W, CELL_H)
                pygame.draw.rect(self._water_layer, (48, 130, 190), water)
                for line_y in range(y + 12, y + CELL_H, 22):
                    pygame.draw.line(self._water_layer, (110, 195, 225),
                                     (4, line_y), (GRID_W - 4, line_y), 2)
                pygame.draw.rect(self._water_layer, (25, 92, 145), water, 3)

        # Tell the battlefield-intel singleton which rows are open water so
        # the Director's row picks, bungee drops and tactician transfers never
        # send a ground zombie onto a lane it cannot swim.
        ai.intel.water_rows = (frozenset(POOL_WATER_ROWS)
                               if bg_type == BG_POOL else frozenset())

        if bg_type == BG_ROOF:
            # one visible roof tile per playable cell, pre-rendered as a layer
            layer = pygame.Surface((GRID_W, GRID_H), pygame.SRCALPHA)
            for row in range(GRID_ROWS):
                for col in range(GRID_COLS):
                    x = col * CELL_W
                    y = row * CELL_H
                    base = (164, 74, 52) if (row + col) % 2 == 0 else (147, 61, 45)
                    pygame.draw.rect(layer, base, (x, y, CELL_W, CELL_H))
                    pygame.draw.rect(layer, (205, 105, 68),
                                     (x + 3, y + 3, CELL_W - 6, CELL_H - 6), 2)
                    pygame.draw.line(layer, (98, 38, 34),
                                     (x, y + CELL_H - 2), (x + CELL_W, y + CELL_H - 2), 3)
                    pygame.draw.line(layer, (115, 44, 37),
                                     (x + CELL_W - 2, y), (x + CELL_W - 2, y + CELL_H), 2)
            # Every cell paints an opaque rect, so the layer's alpha channel is
            # uniformly 255 and never consulted — but an SRCALPHA blit still
            # goes through the per-pixel alpha path. convert() drops the channel
            # and takes the blit from 0.65 ms to 0.06 ms. If a future roof
            # decoration wants to show the lawn through a gap, this has to go
            # back to convert_alpha().
            self._roof_layer = layer.convert()
            for row in range(GRID_ROWS):
                for col in range(GRID_COLS):
                    x = GRID_X + col * CELL_W
                    y = ROOF_GRID_Y + row * CELL_H
                    self.roof_tiles.append(RoofTile(x, y, row=row, col=col))
            self.grid.y = ROOF_GRID_Y
        else:
            self.grid.y = GRID_Y

        if bg_type == BG_FOG:
            # fog layers on right side, one per row
            for row in range(GRID_ROWS):
                self.fog_layers.append(FogLayer(row, SCREEN_WIDTH))

        if bg_type == BG_NIGHT:
            pass  # night sky handled in draw

    def _setup_seed_buttons(self, plant_types):
        """Rebuild seed buttons for the given plant types."""
        self.seed_buttons = []
        x = SEED_CARD_START_X
        y = UI_BAR_Y + 4
        for ptype in plant_types:
            btn = SeedButton(ptype, x, y, SEED_CARD_W, SEED_CARD_H)
            self.seed_buttons.append(btn)
            x += SEED_CARD_W + SEED_CARD_GAP

    def _setup_waves(self, wave_config):
        """Set up wave system with custom wave config."""
        self.wave = WaveSystem()
        self.wave.waves = wave_config
        self.wave.wave_count = len(wave_config)

    def _preload_level_sprites(self):
        """Warm the body-sprite cache for everything this level can spawn.

        The cache is keyed per (sheet, frame, height), so any animation cell
        that has not been drawn yet costs a scale2x plus a smoothscale the
        first time it appears. Doing it here, during the level fade-in, moves
        the whole cost off the critical path.

        Only the sheets this level can actually field are warmed, so an early
        level does not pay for the elite variants it will never spawn.
        """
        sheets = ("anim_zombie_a", "anim_zombie_b")
        prefixes = [f"{s}_{state}" for s in sheets
                    for state in ("idle", "eat", "die")]
        # Elite skins only exist once the Director has unlocked them.
        tints = AI_ZOMBIE_TINTS if self.wave._ai_unlocked() else ()
        assets_loader.preload(prefixes, ZOMBIE_BODY_H, tints)
        # Suns spin through a 24-step rotation set over their lifetime; the
        # same argument as above applies to each step, just spread thin.
        assets_loader.preload_rotations("ui_sun", SUN_SPRITE_SIZE,
                                       SUN_SPRITE_SIZE)

    def _open_adventure_map(self):
        """Refresh the adventure map with the current unlock state."""
        self.unlocked_levels = derive_unlocked(self.completed_levels)
        self.level_select.set_items(ADVENTURE_LEVELS, tr("Adventure Mode"),
                                    unlocked_ids=self.unlocked_levels)
        self.state = STATE_LEVEL_SELECT

    def _reset_game_state(self, start_sun=150):
        """Reset all gameplay lists and timers to a clean state for a new level."""
        self.speed_mult = 1.0
        self._press = None
        self._cob_armed = None
        self.plant_foods = []
        self.plant_food = 0
        self.food_timer = random.uniform(11.0, 18.0)
        self.fx.clear()
        self.coin_drops = []
        self.grid = Grid()
        self.plants = []
        self.zombies = []
        self.projectiles = []
        self.suns = []
        self.lawnmowers = []
        self.sun_value = start_sun
        self.house_hp = HOUSE_HP
        self.plant_cooldowns = {}
        self.sun_spawn_timer = 0.0
        # Also clear any leftover FX from a previous game
        self.floating_texts = []
        self.explosions = []
        self.fx.clear()
        self.shake = 0.0
        self.flash_timer = 0.0
        self._zoom_freeze = 0.0

    def start_adventure_level(self, level_id, picked_plants=None):
        """Start a specific adventure level.

        picked_plants: optional list of plant types chosen in the seed-select
        screen. Defaults to the level's full plant roster.
        """
        level = None
        for lv in ADVENTURE_LEVELS:
            if lv["id"] == level_id:
                level = lv
                break
        if not level:
            return

        self.mode = MODE_ADVENTURE
        self.current_level = level
        self.level_id = level_id
        self.bg_type = level["bg"]
        self._reset_game_state(start_sun=level["start_sun"])

        # setup background first because roof mode changes grid.y
        self._setup_background(level["bg"])
        self.lawnmowers = [Lawnmower(row, self.grid.y) for row in range(GRID_ROWS)]

        # setup seed buttons from the chosen loadout (fall back to full roster)
        roster = picked_plants if picked_plants else level["plants"]
        self.current_loadout = list(roster)
        self._setup_seed_buttons(roster)

        # setup waves
        self._setup_waves(level["waves"])
        self.wave.grid_y = self.grid.y
        self.wave.scaling = False  # adventure keeps authored difficulty

        # Build the sprite variants this level can field now, while the level
        # is still fading in, rather than the first time each one is drawn.
        self._preload_level_sprites()

        # shovel
        self.shovel = Shovel()

        # start first wave
        self.wave.start_wave()
        self._announce_wave(self.wave.wave_index)

        if self.bg_type == BG_NIGHT:
            self.message.show(tr("Night! No sun falls from the sky. Plant Sunflowers!"), 4500)

        self.state = STATE_PLAYING

    def start_survival(self, survival_id):
        """Start survival mode with the given environment."""
        mode = None
        for m in SURVIVAL_MODES:
            if m["id"] == survival_id:
                mode = m
                break
        if not mode:
            return

        self.mode = MODE_SURVIVAL
        self.current_level = mode
        self.level_id = survival_id
        self.bg_type = mode["bg"]
        self.survival_waves = 0
        self._reset_game_state(start_sun=150)

        # setup background first because roof mode changes grid.y
        self._setup_background(mode["bg"])
        self.lawnmowers = [Lawnmower(row, self.grid.y) for row in range(GRID_ROWS)]

        # night survival: no sky sun either — grant more starting sun
        if mode["bg"] == BG_NIGHT:
            self.sun_value = 250

        # setup seed buttons; Lily Pad only belongs to pool survival
        roster = list(SURVIVAL_PLANTS)
        if mode["bg"] != BG_POOL and PLANT_LILYPAD in roster:
            roster.remove(PLANT_LILYPAD)
        self._setup_seed_buttons(roster)

        # generate endless waves from a fresh WaveSystem every run
        self.wave = WaveSystem()
        self.wave.waves = []
        self.wave.wave_count = 0
        self.wave.scaling = True  # endless: faster + harder-biting every wave
        self._generate_survival_waves()
        self.wave.grid_y = self.grid.y

        # Warm the body-sprite cache before the first wave walks on, same as
        # the adventure path — survival fields every sheet variant from wave 1.
        self._preload_level_sprites()

        # shovel
        self.shovel = Shovel()

        # start first wave
        self.wave.start_wave()
        self._announce_wave(self.wave.wave_index)

        if self.bg_type == BG_NIGHT:
            self.message.show(tr("Night! No sun falls from the sky. Plant Sunflowers!"), 4500)

        self.state = STATE_PLAYING

    def _generate_survival_waves(self):
        """Append the next 50 survival waves with monotonically increasing difficulty.

        ``wave.wave_index`` keeps growing forever — spawning gets faster and
        zombie mixes get tougher, exactly like an endless mode.
        """
        base = len(self.wave.waves)  # waves already queued
        waves = []
        for k in range(1, 51):
            i = base + k  # global consecutive wave number
            count = 2 + int(i * 0.9)
            count = min(count, 22)  # cap a single wave so it stays fair
            types = [ZOMBIE_BASIC]
            if i >= 3:
                types.append(ZOMBIE_CONEHEAD)
            if i >= 6:
                types.append(ZOMBIE_FLAG)
            if i >= 10:
                types.append(ZOMBIE_BUCKETHEAD)
            if i >= 14:
                types.append(ZOMBIE_NEWSPAPER)
            if i >= 20:
                types.append(ZOMBIE_POLE)
            if i >= 8:
                types.append(ZOMBIE_BALLOON)  # floats in over the defenses
            if i > 16 and random.random() < 0.35:
                types.append(ZOMBIE_BUCKETHEAD)
            waves.append((count, types, 0))
        self.wave.waves.extend(waves)
        self.wave.wave_count = len(self.wave.waves)

    def handle_event(self, event):
        # Primary mouse button drives all UI/game actions; right-click cancels
        # the active tool while playing.
        if event.type in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP) \
                and getattr(event, "button", 1) != 1:
            if (event.type == pygame.MOUSEBUTTONDOWN and getattr(event, "button", 0) == 3
                    and self.state == STATE_PLAYING):
                self._cancel_tool_selection()
            return

        # Pause automatically when the window loses focus.
        if event.type == pygame.WINDOWFOCUSLOST and self.state == STATE_PLAYING:
            self.state = STATE_PAUSED
            self._press = None  # a half-finished card drag must not fire on resume
            self._cob_armed = None
            # _refresh_cursor only runs in the PLAYING branch of update();
            # without this the OS cursor stays hidden on the pause screen
            # when a seed card / shovel was selected.
            self._refresh_cursor()
            return

        # M toggles sound from anywhere
        if event.type == pygame.KEYDOWN and event.key == pygame.K_m:
            self._toggle_mute()

        # Menu
        if self.state == STATE_MENU:
            self._survival_select = False
            if event.type == pygame.MOUSEMOTION:
                self.menu.update_hover(event.pos[0], event.pos[1])
            elif event.type == pygame.MOUSEBUTTONDOWN:
                action = self.menu.handle_mouse(event.pos[0], event.pos[1])
                if action == "start":
                    self.state = STATE_MODE_SELECT
                elif action == "help":
                    self.menu.show_help = not self.menu.show_help
                elif action == "quit":
                    pygame.event.post(pygame.event.Event(pygame.QUIT))
                elif action == "lang":
                    self._toggle_language()
            elif event.type == pygame.KEYDOWN and event.key in (pygame.K_RETURN, pygame.K_SPACE):
                self.state = STATE_MODE_SELECT
            return

        # Mode select
        if self.state == STATE_MODE_SELECT:
            if event.type == pygame.MOUSEMOTION:
                self.mode_select.handle_mouse(event.pos[0], event.pos[1], activate=False)
            elif event.type == pygame.MOUSEBUTTONDOWN:
                mx, my = event.pos
                mode = self.mode_select.handle_mouse(mx, my)
                if mode == MODE_ADVENTURE:
                    self._survival_select = False
                    self._open_adventure_map()
                elif mode == MODE_SURVIVAL:
                    self._survival_select = True
                    self.level_select.set_items(SURVIVAL_MODES, tr("Survival Mode"))
                    self.state = STATE_LEVEL_SELECT
                else:
                    self.state = STATE_MENU
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                self.state = STATE_MENU
            return

        # Level select
        if self.state == STATE_LEVEL_SELECT:
            if event.type == pygame.MOUSEMOTION:
                self.level_select.handle_mouse(event.pos[0], event.pos[1], activate=False)
            elif event.type == pygame.MOUSEBUTTONDOWN:
                mx, my = event.pos
                level_id = self.level_select.handle_mouse(mx, my)
                if level_id:
                    if getattr(self, '_survival_select', False):
                        # find survival mode
                        for m in SURVIVAL_MODES:
                            if m["id"] == level_id:
                                self.start_survival(level_id)
                                break
                        self._survival_select = False
                    else:
                        # adventure: pick a loadout first (PvZ seed selection)
                        for lv in ADVENTURE_LEVELS:
                            if lv["id"] == level_id:
                                self.pending_level = lv
                                break
                        if self.pending_level is not None:
                            self.seed_select.set_level(self.pending_level)
                            self.state = STATE_SEED_SELECT
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_BACKSPACE:
                self.state = STATE_MODE_SELECT
                self._survival_select = False
            return

        # Seed select (adventure loadout)
        if self.state == STATE_SEED_SELECT:
            if event.type == pygame.MOUSEMOTION:
                self.seed_select.handle_mouse(event.pos[0], event.pos[1], activate=False)
            elif event.type == pygame.MOUSEBUTTONDOWN:
                mx, my = event.pos
                action = self.seed_select.handle_mouse(mx, my)
                if action == "start":
                    if self.seed_select.picked:
                        lv = self.pending_level
                        self.pending_level = None
                        self.start_adventure_level(lv["id"], list(self.seed_select.picked))
                elif action == "back":
                    self.pending_level = None
                    self._open_adventure_map()
                elif isinstance(action, tuple) and action[0] == "toggle":
                    ptype = action[1]
                    if ptype in self.seed_select.picked:
                        self.seed_select.picked.remove(ptype)
                    else:
                        self.seed_select.picked.append(ptype)
            elif event.type == pygame.KEYDOWN and event.key in (pygame.K_RETURN, pygame.K_SPACE):
                if self.seed_select.picked:
                    lv = self.pending_level
                    self.pending_level = None
                    self.start_adventure_level(lv["id"], list(self.seed_select.picked))
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_BACKSPACE:
                self.pending_level = None
                self._open_adventure_map()
            return

        # Paused
        if self.state == STATE_PAUSED:
            if event.type == pygame.MOUSEMOTION:
                self.pause_screen.update_hover(event.pos[0], event.pos[1])
            elif event.type == pygame.MOUSEBUTTONDOWN:
                self._handle_pause_action(self.pause_screen.handle_mouse(event.pos[0], event.pos[1]))
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_p:
                self._handle_pause_action("resume")
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                self._handle_pause_action("menu")
            return

        # Game over
        if self.state == STATE_GAME_OVER:
            if event.type == pygame.MOUSEMOTION:
                self.game_over.update_hover(event.pos[0], event.pos[1])
            elif event.type == pygame.MOUSEBUTTONDOWN:
                action = self.game_over.handle_mouse(event.pos[0], event.pos[1])
                if action == "retry":
                    self._retry_current()
                elif action == "menu":
                    self.state = STATE_MENU
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_RETURN:
                self._retry_current()
            return

        # Level complete — refresh map with newly unlocked level
        if self.state == STATE_LEVEL_COMPLETE:
            if event.type == pygame.MOUSEMOTION:
                self.level_complete.update_hover(event.pos[0], event.pos[1])
            elif event.type == pygame.MOUSEBUTTONDOWN:
                action = self.level_complete.handle_mouse(event.pos[0], event.pos[1])
                if action == "next":
                    self._goto_next_level()
                elif action == "map":
                    self._open_adventure_map()
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_RETURN:
                self._goto_next_level()
            return

        # Survival complete
        if self.state == STATE_SURVIVAL_COMPLETE:
            if event.type == pygame.MOUSEMOTION:
                self.survival_complete.update_hover(event.pos[0], event.pos[1])
            elif event.type == pygame.MOUSEBUTTONDOWN:
                action = self.survival_complete.handle_mouse(event.pos[0], event.pos[1])
                if action == "retry":
                    self._retry_current()
                elif action == "menu":
                    self.state = STATE_MENU
            return

        # Playing
        if self.state != STATE_PLAYING:
            return

        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_p:
                self.state = STATE_PAUSED
                self._press = None
                self._cob_armed = None
                self._refresh_cursor()
            elif event.key == pygame.K_f:
                # fast-forward toggle (also clickable in the top bar)
                self.speed_mult = 2.0 if self.speed_mult == 1.0 else 1.0
                self._play_sound("click", 0.5)
            elif event.key == pygame.K_d:
                self._debug_add_sun()
            elif event.key == pygame.K_SPACE and self.wave.between_waves:
                # Skip wait and use the same transition path as the timer.
                self.wave.between_waves = False
                self.wave.between_wave_timer = 0
                self.wave.wave_cleared = False
                self._advance_after_wave()
            elif event.key in (pygame.K_1, pygame.K_2, pygame.K_3, pygame.K_4, pygame.K_5, pygame.K_6):
                # number keys select seed cards
                idx = event.key - pygame.K_1
                self._select_seed_by_index(idx)
            elif event.key == pygame.K_ESCAPE:
                # deselect current tool
                self._cancel_tool_selection()

        if event.type == pygame.MOUSEBUTTONDOWN:
            mx, my = event.pos
            self.mouse_x = mx
            self.mouse_y = my

            # top-bar quick buttons (pause / fast-forward)
            if self._topbar_click(mx, my):
                return

            # check shovel toggle
            if self.shovel and self.shovel.contains(mx, my):
                self.shovel.selected = not self.shovel.selected
                if self.shovel.selected:
                    for b in self.seed_buttons:
                        b.selected = False
                self.grid.clear_selection()
                self._play_sound("click", 0.5)
                return

            # check seed buttons — pressing a card starts a click OR a drag
            for btn in self.seed_buttons:
                if btn.contains(mx, my):
                    self._press = [btn, (mx, my), False]
                    return

            # check plant food drops (能量豆)
            for pf in self.plant_foods[:]:
                if pf.rect().collidepoint(mx, my):
                    # Start the rolling arc into the energy jar — credits
                    # only land once the vial arrives. This replaces the
                    # old instant-pickup that made the collect feel cheap.
                    jar_target = (self.btn_pause.x - 24
                                  - min(self.plant_food, PLANT_FOOD_MAX - 1) * 22,
                                  self.btn_pause.centery)
                    if self.plant_food >= PLANT_FOOD_MAX:
                        self.message.show(tr("Plant food storage is full!"), 1200)
                        return
                    if not pf.collect(jar_target):
                        # Still falling — ignore the click; let it land first.
                        return
                    self._play_sound("food", 0.8)
                    self.floating_texts.append(FloatingText(
                        int(pf.x), int(pf.y) - 12, tr("Plant food!"),
                        color=(130, 255, 130), size=20, vy=-50, lifetime=1.1))
                    return

            # check sun collection (collected suns are already flying to the jar)
            for sun in self.suns[:]:
                if sun.contains(mx, my):
                    sun.collect((SUN_JAR_X + SUN_JAR_W // 2, SUN_JAR_Y + SUN_JAR_W // 2))
                    self._spawn_collect_text(int(sun.x), int(sun.y) - 8, sun.amount)
                    self._play_sound(SOUND_SUN_COLLECT, 0.5)
                    return

            # Cob Cannon uses the original two-step interaction: click the
            # cannon to arm it, then click a lawn cell to choose the target.
            if not any(btn.selected for btn in self.seed_buttons) and not (self.shovel and self.shovel.selected):
                for cob in self.plants:
                    if (cob.alive and getattr(cob, "plant_type", "") == PLANT_COBCANNON
                            and pygame.Rect(cob.x, cob.y, cob.w, cob.h).collidepoint(mx, my)):
                        self._cob_armed = None if self._cob_armed is cob else cob
                        self.message.show(tr("Cob Cannon armed — choose a target!") if self._cob_armed is cob
                                          else tr("Cob Cannon cancelled"), 1200)
                        return

            # shovel: click cell to dig up plant
            if self.shovel and self.shovel.selected:
                cell = self.grid.get_cell(mx, my)
                if cell:
                    self._dig_up(cell)
                return

            # check grid planting
            cell = self.grid.get_cell(mx, my)

            # ---- Cob Cannon: tap any lawn cell to fire a KernelBomb arc ----
            # If a CobCannon exists on the lawn, the click is consumed as a
            # targeting shot before falling through to normal plant handling.
            has_selected_seed = any(btn.selected for btn in self.seed_buttons)
            if cell and self._cob_armed is not None and not has_selected_seed and not (self.shovel and self.shovel.selected):
                cob = self._cob_armed
                if cob.alive and cob.ready:
                    proj = cob.fire_at(int(mx), int(my))
                    if proj is not None:
                        self.projectiles.append(proj)
                        self._play_sound("cannon", 0.6)
                        self.floating_texts.append(FloatingText(
                            int(mx), int(my) - 16, tr("FIRE!"),
                            color=(255, 80, 60), size=18, vy=-50, lifetime=0.8))
                        self._cob_armed = None
                        return  # don't fall through to plant on this click
                self._cob_armed = None
                self.message.show(tr("Cob Cannon is reloading!"), 900)

            if cell:
                selected = None
                for btn in self.seed_buttons:
                    if btn.selected:
                        selected = btn.plant_type
                        break
                if selected:
                    self._plant(selected, cell)
                else:
                    # no tool in hand + stored plant food → feed the plant
                    cx, _cy = self.grid.get_cell_center(*cell)
                    p = self._cell_plant(cell[0], cx)
                    if p is not None and self.plant_food > 0:
                        self._feed_plant(p)
                    else:
                        self.grid.selected_cell = cell
            else:
                self.grid.selected_cell = None

        if event.type == pygame.MOUSEBUTTONUP and self._press is not None:
            btn, origin, _dragged = self._press
            self._press = None
            mx, my = event.pos
            moved = (mx - origin[0]) ** 2 + (my - origin[1]) ** 2 > 100
            if moved:
                # drag-to-plant: carry the card onto the lawn and drop it
                for other in self.seed_buttons:
                    other.selected = other is btn
                if self.shovel:
                    self.shovel.selected = False
                cell = self.grid.get_cell(mx, my)
                planted = cell is not None and self._plant(btn.plant_type, cell)
                if not planted:
                    btn.selected = False
            else:
                # plain click — toggle the card as before
                self._select_seed_button(btn)
            return

        if event.type == pygame.MOUSEMOTION:
            mx, my = event.pos
            self.mouse_x = mx
            self.mouse_y = my
            if self._press is not None:
                bx, by = self._press[1]
                if (mx - bx) ** 2 + (my - by) ** 2 > 100:
                    self._press[2] = True
            self.grid.update_hover(mx, my)

    def _cell_plant(self, row, cx):
        """Return the alive plant occupying the cell around x=cx in row, if any."""
        for p in self.plants:
            if p.alive and p.row == row and abs(p.x - cx) < CELL_W * 0.6:
                return p
        return None

    def _first_cob_cannon(self):
        """Return the first alive Cob Cannon on the lawn, or None."""
        for p in self.plants:
            if p.alive and getattr(p, "plant_type", "") == PLANT_COBCANNON:
                return p
        return None

    def _is_water_cell(self, row):
        return self.bg_type == BG_POOL and row in POOL_WATER_ROWS

    def _upgrade_target(self, plant_type, cell):
        """The existing same-type plant in this cell, if it can level up."""
        row, col = cell
        cx, _ = self.grid.get_cell_center(row, col)
        for p in self.plants:
            if (p.alive and p.row == row and p.plant_type == plant_type
                    and abs(p.x + p.w // 2 - cx) < CELL_W * 0.6):
                if getattr(p, "level", 1) < PLANT_LEVEL_MAX:
                    return p
                return None
        return None

    def _can_place(self, plant_type, cell):
        """Return (allowed, message_key) without changing game state."""
        row, col = cell
        info = PLANT_INFO[plant_type]
        # upgrading an own plant is always allowed on its own cell
        if self._upgrade_target(plant_type, cell) is not None:
            if self.sun_value < info["cost"]:
                return False, "Not enough sun!"
            if self.plant_cooldowns.get(plant_type, 0) > 0:
                return False, "Plant cooling down!"
            return True, None
        if self.sun_value < info["cost"]:
            return False, "Not enough sun!"
        if self.plant_cooldowns.get(plant_type, 0) > 0:
            return False, "Plant cooling down!"
        # replanting onto a fully-upgraded own plant is a no-op — say so
        row_c, col_c = cell
        cx, _ = self.grid.get_cell_center(row_c, col_c)
        for p in self.plants:
            if (p.alive and p.row == row_c and p.plant_type == plant_type
                    and abs(p.x + p.w // 2 - cx) < CELL_W * 0.6
                    and getattr(p, "level", 1) >= PLANT_LEVEL_MAX):
                return False, "Already at max level!"
        cx, _ = self.grid.get_cell_center(row, col)
        bodies = [p for p in self.plants if p.alive and p.row == row
                  and abs(p.x - cx) < CELL_W * 0.6 and p.plant_type != PLANT_LILYPAD]
        lilies = [p for p in self.plants if p.alive and p.row == row
                  and abs(p.x - cx) < CELL_W * 0.6 and p.plant_type == PLANT_LILYPAD]
        is_lily = plant_type == PLANT_LILYPAD
        on_water = self._is_water_cell(row)
        if is_lily:
            if bodies or lilies:
                return False, "Cell occupied!"
            if not on_water:
                return False, "Lily Pads only grow on water!"
        else:
            if bodies:
                return False, "Cell occupied!"
            if on_water and not lilies:
                return False, "Need a Lily Pad first!"
        return True, None

    def _plant(self, plant_type, cell):
        allowed, reason = self._can_place(plant_type, cell)
        if not allowed:
            self.message.show(tr(reason), 1500)
            self._play_sound("error", 0.5)
            return False
        row, col = cell
        info = PLANT_INFO[plant_type]
        cx, cy = self.grid.get_cell_center(row, col)
        # Upgrade path: replanting the same type levels the plant up (Lv3 max)
        # — damage / sun output / HP multiply several times per level.
        target = self._upgrade_target(plant_type, cell)
        if target is not None:
            self.sun_value -= info["cost"]
            self.plant_cooldowns[plant_type] = info["cooldown"]
            apply_plant_level(target, target.level + 1)
            self.grid.clear_selection()
            for btn in self.seed_buttons:
                if btn.plant_type == plant_type:
                    btn.selected = False
            self.fx.soil_poof(cx, cy)
            self.floating_texts.append(FloatingText(
                int(cx), int(cy) - 40, i18n.fmt_level_up(target.level),
                color=(130, 255, 130), size=24, vy=-45, lifetime=1.2))
            self._play_sound("upgrade", 0.8)
            return True
        plant_cls = PLANT_CLASSES[plant_type]
        plant = plant_cls(0, 0, row)
        plant.x = cx - plant.w // 2
        plant.y = cy - plant.h // 2
        plant.spawn_t = 0.25  # drop-in animation
        self.plants.append(plant)
        self.sun_value -= info["cost"]
        self.plant_cooldowns[plant_type] = info["cooldown"]
        self.grid.clear_selection()
        for btn in self.seed_buttons:
            if btn.plant_type == plant_type:
                btn.selected = False
        # soil poof effect at plant position
        self.fx.soil_poof(cx, cy)
        self._play_sound(SOUND_PLANT)
        return True

    def _dig_up(self, cell):
        """Remove plant in the clicked cell when shovel is selected.

        Original PvZ rules: no sun refund. Digging prefers the plant body on a
        lily pad; only remove the lily pad itself when nothing stands on it.
        """
        row, col = cell
        cx, cy = self.grid.get_cell_center(row, col)
        in_cell = [p for p in self.plants if p.alive and p.row == row
                   and abs(p.x - cx) < CELL_W * 0.6]
        if not in_cell:
            return
        # prefer the non-lily plant (its body sits above the lily pad)
        target = None
        for p in in_cell:
            if p.plant_type != PLANT_LILYPAD:
                target = p
                break
        if target is None:
            target = in_cell[0]  # only a lily pad here
        target.alive = False
        self._play_sound("shovel", 0.7)
        self.fx.soil_poof(cx, cy)
        if self.shovel:
            self.shovel.selected = False

    def _feed_plant(self, p):
        """Spend one stored plant food on the plant's super effect (PvZ2)."""
        if self.plant_food <= 0 or not p.alive:
            return
        self.plant_food -= 1
        self._play_sound("food", 0.9)
        cx = int(p.x + p.w // 2)
        cy = int(p.y - 8)
        self.floating_texts.append(FloatingText(
            cx, cy, tr("Plant food!"), color=(130, 255, 130),
            size=20, vy=-55, lifetime=1.1))
        pcx, pcy = p.x + p.w // 2, p.y + p.h // 2
        self.fx.soil_poof(pcx, pcy)
        # PvZ2-style plant food release: two staggered mint-green rings.
        for k in range(2):
            self.fx.ring(pcx, pcy, 18, 110, (130, 255, 160),
                         duration=0.55, delay=k * 0.10, width=3)
        if p.plant_type == PLANT_PEASHOOTER:
            p.food_boost = FOOD_BOOST_SHOOT_S  # machine-gun peas
        elif p.plant_type == PLANT_SUNFLOWER:
            for _ in range(FOOD_SUN_BURST):
                sun = Sun(p.x + random.randint(-20, 70), p.y - 20)
                sun.amount = 25
                # Plant-food sun also arcs out of the head.
                sun.eject(vy=-230.0, target_y=p.y + random.randint(20, 60))
                self.suns.append(sun)
        elif p.plant_type == PLANT_WALLNUT:
            p.hp = p.max_hp  # full repair
        elif p.plant_type == PLANT_FUMESHROOM:
            for z in self.zombies:
                if z.row == p.row and z.alive and z.hp > 0 and z.dying_timer <= 0:
                    z.take_damage(FOOD_FUME_DAMAGE)
        elif p.plant_type == PLANT_CHERRYBOMB and not p.explode:
            p.explode = True       # detonate right now
            p.explode_timer = 0.12
        elif p.plant_type == PLANT_SNOWPEA:
            # PvZ2 Snow Pea plant food: freeze every zombie on the lawn
            for z in self.zombies:
                if z.alive and z.hp > 0 and z.dying_timer <= 0:
                    z.apply_ice(6.0)   # longer freeze for the ultimate
        elif p.plant_type == PLANT_LILYPAD:
            p.hp = p.max_hp

    def _debug_add_sun(self):
        self.sun_value += 100

    def _cancel_tool_selection(self):
        for b in self.seed_buttons:
            b.selected = False
        if self.shovel:
            self.shovel.selected = False
        self.grid.clear_selection()
        self._press = None
        self._cob_armed = None

    def _topbar_click(self, mx, my):
        """Handle the quick pause / fast-forward buttons in the top bar."""
        if self.btn_pause.collidepoint(mx, my):
            self.state = STATE_PAUSED
            self._press = None
            self._cob_armed = None
            self._refresh_cursor()
            self._play_sound("click", 0.5)
            return True
        if self.btn_ff.collidepoint(mx, my):
            self.speed_mult = 2.0 if self.speed_mult == 1.0 else 1.0
            self._play_sound("click", 0.5)
            return True
        return False

    def _handle_pause_action(self, action):
        if action == "resume":
            self._play_sound("click", 0.5)
            self.state = STATE_PLAYING
        elif action == "restart":
            self._play_sound("click", 0.5)
            self._retry_current()
        elif action == "menu":
            self._record_survival_run()
            self.state = STATE_MENU

    def _retry_current(self):
        """Restart the level/environment the player is currently in."""
        if self.mode == MODE_ADVENTURE and self.level_id:
            self.start_adventure_level(self.level_id, self.current_loadout)
        elif self.mode == MODE_SURVIVAL and self.level_id:
            self.start_survival(self.level_id)
        else:
            self.state = STATE_MENU

    def _next_adventure_level(self):
        for i, lv in enumerate(ADVENTURE_LEVELS):
            if lv["id"] == self.level_id:
                if i + 1 < len(ADVENTURE_LEVELS):
                    return ADVENTURE_LEVELS[i + 1]
                break
        return None

    def _goto_next_level(self):
        lv = self._next_adventure_level()
        if lv is None:
            self.state = STATE_MENU
            return
        self._play_sound("click", 0.5)
        self.pending_level = lv
        self.seed_select.set_level(lv)
        self.state = STATE_SEED_SELECT

    def add_shake(self, magnitude):
        self.shake = max(self.shake, float(magnitude))

    def shake_offset(self):
        """Random pixel offset for the final blit while the screen shakes."""
        if self.shake <= 0.3:
            return (0, 0)
        return (random.randint(-int(self.shake), int(self.shake)),
                random.randint(-int(self.shake) // 2, int(self.shake) // 2))

    def _refresh_cursor(self):
        """Hide the OS cursor while a seed card / shovel is selected — the
        ghost sprite drawn at the cursor position replaces it."""
        want_hidden = (self.state == STATE_PLAYING and
                       (any(b.selected for b in self.seed_buttons)
                        or bool(self.shovel and self.shovel.selected)))
        if want_hidden == self._cursor_hidden:
            return
        self._cursor_hidden = want_hidden
        try:
            if want_hidden:
                pygame.mouse.set_cursor((8, 8), (0, 0),
                                        (0, 0, 0, 0, 0, 0, 0, 0),
                                        (0, 0, 0, 0, 0, 0, 0, 0))
            else:
                pygame.mouse.set_system_cursor(pygame.SYSTEM_CURSOR_ARROW)
        except Exception:
            pass

    def restore_cursor(self):
        """Called from main before quitting so the pointer never stays hidden."""
        if self._cursor_hidden:
            try:
                pygame.mouse.set_system_cursor(pygame.SYSTEM_CURSOR_ARROW)
            except Exception:
                pass
            self._cursor_hidden = False

    def _complete_adventure(self):
        """Mark the current level done, persist it, and go to the win screen."""
        if self.mode != MODE_ADVENTURE:
            return
        self.completed_levels.add(self.level_id)
        self.save.complete_level(self.level_id)
        self.unlocked_levels = derive_unlocked(self.completed_levels)
        self._play_sound("win")
        # Big coin shower across the screen — 24 coins over 1.5s
        for i in range(24):
            delay = i * 0.05
            cx = random.randint(GRID_X + 60, GRID_X + GRID_W - 60)
            cy = random.randint(GRID_Y + 60, GRID_Y + GRID_H - 120)
            self.coin_drops.append({
                "x": float(cx),
                "y": float(cy),
                "vx": random.uniform(-80, 80),
                "vy": random.uniform(-260, -160),
                "age": -delay,
                "max": 1.5,
                "value": 25,
                "rot": random.uniform(0, 6.28),
            })
        self.state = STATE_LEVEL_COMPLETE

    def _record_survival_run(self):
        """Persist the waves survived when a survival run ends."""
        if self.mode == MODE_SURVIVAL and self.level_id:
            self.save.record_survival(self.level_id, max(0, self.wave.wave_index - 1))

    def _advance_after_wave(self):
        """Start the next wave or finish/extend the current mode."""
        # Endless survival regenerates its wave table every 50 waves, so
        # wave_idx == wave_count recurs (wave 50, 100, ...) — only adventure
        # has a real "last wave".
        if (self.mode == MODE_ADVENTURE
                and self.wave.wave_index == self.wave.wave_count):
            # On a boss wave, free-spawned minions may remain after the boss
            # dies. Keep the level in a cleared-final-wave state until every
            # enemy is gone.
            if any(z.alive and z.hp > 0 for z in self.zombies):
                self.wave.wave_active = False
                self.wave.between_waves = False
                self.wave.wave_cleared = True
            else:
                self._complete_adventure()
            return
        if self.wave.wave_index < self.wave.wave_count:
            # Reward popup: 6 coin drops fan upward in the lawn center
            cx = GRID_X + GRID_W // 2
            cy = GRID_Y + GRID_H // 2
            for i in range(6):
                ang = math.radians(random.uniform(-100, -50))
                speed = random.uniform(150, 220)
                self.coin_drops.append({
                    "x": float(cx + random.randint(-40, 40)),
                    "y": float(cy + random.randint(-30, 30)),
                    "vx": math.cos(ang) * speed * 0.45,
                    "vy": math.sin(ang) * speed,
                    "age": -i * 0.04,
                    "max": 1.0,
                    "value": 10,
                    "rot": random.uniform(0, 6.28),
                })
            if self.wave.start_wave():
                self._announce_wave(self.wave.wave_index)
            return
        if self.mode == MODE_SURVIVAL:
            self.survival_waves = self.wave.wave_index
            self._generate_survival_waves()
            if self.wave.start_wave():
                self._announce_wave(self.wave.wave_index)

    def _select_seed_button(self, btn):
        """Shared mouse/keyboard seed selection with affordability/cooldown checks."""
        btn.update(self.sun_value, self.plant_cooldowns)
        if btn.cooldown_remaining > 0:
            self.message.show(f"{i18n.plant_name(btn.plant_type)}：{tr('Plant cooling down!')}", 1000)
            self._play_sound("error", 0.4)
            return False
        if not btn.can_afford:
            self.message.show(tr("Not enough sun!"), 1000)
            self._play_sound("error", 0.4)
            return False
        btn.selected = not btn.selected
        if btn.selected:
            for other in self.seed_buttons:
                if other is not btn:
                    other.selected = False
            if self.shovel:
                self.shovel.selected = False
        self.grid.clear_selection()
        self._play_sound("click", 0.6)
        return True

    def _select_seed_by_index(self, idx):
        """Select the i-th available seed card (for keyboard shortcut)."""
        if idx >= len(self.seed_buttons):
            return
        self._select_seed_button(self.seed_buttons[idx])

    def _update_hover(self, mx, my):
        """Per-frame hover tracking: seed-card/shovel tooltips in the top bar,
        plant/zombie tooltips and highlights on the lawn."""
        self.hover_plant = None
        self.hover_zombie = None
        self.hover_sun = None
        if my < UI_BAR_H:
            # top bar: show card info on hover
            for btn in self.seed_buttons:
                if btn.contains(mx, my):
                    self.tooltip.show(btn.tooltip_lines(), mx + 14, UI_BAR_H + 4)
                    return
            if self.shovel and self.shovel.contains(mx, my):
                self.tooltip.show(tr("Shovel: dig up a plant"), mx + 14, UI_BAR_H + 4)
                return
            self.tooltip.hide()
            return
        # Suns sit on top of everything on the lawn and are click-to-collect,
        # so they claim the cursor first. The cell-hover wash is suppressed
        # underneath (阳光卡在两块草地中间时半边被刷白、看起来被"分隔开"的根源)
        # and the sun itself gets a pickup ring so the click target reads.
        for sun in self.suns:
            if sun.alive and sun.contains(mx, my):
                self.hover_sun = sun
                break
        if self.hover_sun is not None:
            self.tooltip.hide()
            return
        # plants
        for p in self.plants:
            if not p.alive:
                continue
            pr = pygame.Rect(p.x, p.y, p.w, p.h)
            if pr.collidepoint(mx, my):
                self.hover_plant = p
                break
        if self.hover_plant is None:
            for z in self.zombies:
                if not z.alive:
                    continue
                zr = pygame.Rect(z.x, z.y, z.w, z.h)
                if zr.collidepoint(mx, my):
                    self.hover_zombie = z
                    break
        # tooltip text
        if self.hover_plant is not None:
            name = i18n.plant_name(self.hover_plant.plant_type)
            text = f"{name}\n{tr('HP:')} {int(self.hover_plant.hp)}/{int(self.hover_plant.max_hp)}"
            self.tooltip.show(text, mx + 12, my - 40)
        elif self.hover_zombie is not None:
            type_name = i18n.zombie_name(self.hover_zombie.zombie_type)
            text = f"{type_name}\n{tr('HP:')} {int(self.hover_zombie.hp)}/{int(self.hover_zombie.max_hp)}"
            self.tooltip.show(text, mx + 12, my - 40)
        else:
            self.tooltip.hide()

    def _spawn_damage_text(self, x, y, dmg, color=COLOR_YELLOW):
        if len(self.floating_texts) >= 80:
            self.floating_texts.pop(0)
        self.floating_texts.append(FloatingText(x, y, f"-{int(dmg)}", color=color, size=20, vy=-60, lifetime=1.0))

    def _spawn_collect_text(self, x, y, amount):
        if len(self.floating_texts) >= 80:
            self.floating_texts.pop(0)
        self.floating_texts.append(FloatingText(x, y, f"+{int(amount)}", color=COLOR_YELLOW, size=18, vy=-50, lifetime=0.9))

    def _spawn_plant_debris(self, plant):
        """Burst of petals/leaves when a plant is eaten, tinted per species."""
        palette = {
            PLANT_PEASHOOTER:   [(60, 170, 70), (110, 200, 90), (40, 130, 50)],
            PLANT_SUNFLOWER:    [(255, 215, 60), (255, 245, 160), (220, 150, 30)],
            PLANT_WALLNUT:      [(170, 130, 70), (130, 95, 50), (90, 60, 30)],
            PLANT_CHERRYBOMB:   [(220, 30, 30), (255, 100, 80), (160, 20, 20)],
            PLANT_FUMESHROOM:   [(160, 60, 200), (200, 120, 255), (100, 30, 150)],
            PLANT_LILYPAD:      [(60, 170, 70), (110, 200, 90), (40, 130, 50)],
            PLANT_SNOWPEA:      [(120, 210, 255), (200, 240, 255), (60, 150, 210)],
        }.get(plant.plant_type, [(255, 255, 255)])
        self.fx.plant_debris(plant.x + plant.w // 2, plant.y + plant.h // 2,
                             palette=palette)

    def _spawn_pea_impact(self, x, y, is_fume=False, is_frost=False):
        """Spark burst when a pea/fume/frost projectile hits a zombie."""
        self.fx.pea_impact(x, y, is_fume=is_fume, is_frost=is_frost)

    def _spawn_balloon_pop(self, zombie):
        """Red rubber shreds where the balloon was — slightly above the head."""
        self.fx.balloon_pop(zombie.x + zombie.w // 2, zombie.y - 24)

    def _spawn_mow_dust(self, mower, big=False):
        """Grey dust puff trailing behind the mower (it travels rightward)."""
        # The emitter fans leftward; `big` is a wider burst for a fresh start.
        self.fx.mow_dust(mower.x - 4, mower.y + mower.h * 0.5, big=big)

    def _spawn_minion_landing(self, zombie):
        """Impact wave + dust where a boss-summoned minion touches down."""
        cx = zombie.x + zombie.w // 2
        cy = zombie.y + zombie.h - 8
        self.fx.ring(cx, cy, 12, 70, (255, 230, 120), duration=0.45, width=4)
        self.fx.burst(cx, cy, (175, 145, 90), n=6, speed=(45, 110),
                      size=(3, 7), life=(0.5, 0.8), gravity=180, kind="puff")
        self.add_shake(3)

    def _chain_trigger_mowers(self, exclude_row=None):
        """Activate every still-idle mower in adjacent rows. Triggered when a
    rolling mower exits the screen right edge — PvZ2 chain reaction feel.
    Each newly-activated mower spawns its starter dust puff + shake.
        """
        triggered = 0
        for other in self.lawnmowers:
            if not other.alive or other.activated:
                continue
            if exclude_row is not None and other.row == exclude_row:
                continue
            other.activate()
            # starter dust + shake so the chain is audible/visible
            self._spawn_mow_dust(other, big=True)
            self._play_sound("mow", 0.6)
            triggered += 1
        if triggered:
            self.add_shake(min(8, 2 + triggered))

    def _spawn_zombie_head(self, zombie):
        """Chunks of gear/gore flung off when a zombie dies.

        Conehead/Buckethead/Flag/Newspaper shed their signature equipment in
        its own colour; a basic zombie just throws a grey shoulder knob, so
        ordinary deaths don't turn the lawn into confetti.
        """
        palette = {
            ZOMBIE_CONEHEAD:   (230, 112, 28),    # orange cone
            ZOMBIE_BUCKETHEAD: (160, 168, 175),   # metal bucket
            ZOMBIE_FLAG:       (210, 35, 35),     # red flag
            ZOMBIE_NEWSPAPER:  (235, 232, 220),   # off-white news
            ZOMBIE_TACTICIAN:  (168, 138, 240),   # AI: violet sash
            ZOMBIE_DIGGER:     (196, 150, 90),    # AI: work gloves
            ZOMBIE_HEALER:     (140, 235, 190),   # AI: apothecary green
            ZOMBIE_COMMANDER:  (255, 196, 90),    # AI: officer gold
        }
        color = palette.get(zombie.zombie_type, (90, 90, 95))
        n = 3 if zombie.zombie_type in palette else 1
        cx = zombie.x + zombie.w // 2
        cy = zombie.y + 16
        for _ in range(n):
            ang = random.uniform(-math.pi * 0.85, -math.pi * 0.15)
            spd = random.uniform(80, 200)
            self.fx._emit(x=cx + random.randint(-20, 20),
                          y=cy + random.randint(-10, 10),
                          vx=math.cos(ang) * spd * 0.4,
                          vy=math.sin(ang) * spd,
                          gravity=480, drag=0.35,
                          size=random.uniform(3, 5.5),
                          max_life=random.uniform(0.7, 1.0),
                          color=color, kind="chunk")

    def _spawn_grass_print(self, zombie):
        """Faint pressed-grass footprint below the zombie's feet."""
        self.fx.grass_print(zombie.x + zombie.w // 2 + random.randint(-3, 3),
                            zombie.y + zombie.h - 6)

    def _consume_zombie_ai_fx(self, z):
        """Drain the FX flags an AI zombie set during its update.

        ``entities.py`` deliberately knows nothing about the particle system —
        it just records intent (``_beam_pending``, ``_hop_pending``,
        ``_dig_dust_pending`` …) and the game translates that into effects
        once per frame. Keeps the zombie logic unit-testable and free of
        pygame draw calls.
        """
        beam = z._beam_pending
        if beam is not None:
            z._beam_pending = None
            target, kind = beam
            hx = z.x + z.w // 2
            hy = z.y + 14
            if kind == "heal" and target is not None:
                self.fx.beam(hx, hy, target.x + target.w // 2, target.y + 14,
                             (140, 250, 190), duration=0.45, width=3)
                # A soft green motes drift up off the mended zombie.
                self.fx.burst(target.x + target.w // 2, target.y + 14,
                              (150, 255, 200), n=5, speed=(20, 70),
                              size=(2, 3.6), life=(0.35, 0.6), gravity=-40)
                self.fx.ring(target.x + target.w // 2, target.y + 16,
                             4, 26, (140, 250, 190), duration=0.4, width=2)
            elif kind == "rally":
                self.fx.ring(hx, hy, 12, COMMANDER_RANGE,
                             (255, 208, 120), duration=0.6, width=3)
                self.fx.burst(hx, hy, (255, 226, 150), n=8, speed=(70, 190),
                              size=(2, 4), life=(0.4, 0.7), gravity=120)

        hop = z._hop_pending
        if hop is not None:
            z._hop_pending = None
            hx, y0, y1 = hop
            self.fx.hop_trail(hx, y0, y1, hx)
            self.fx.ring(hx, y1 + 16, 4, 30, (168, 138, 240),
                         duration=0.4, width=2, layer=0)

        if getattr(z, "_dig_dust_pending", False):
            z._dig_dust_pending = False
            self.fx.dig_dust(z.x + z.w // 2, z.y + z.h - 6)

        if getattr(z, "_emerge_pending", False):
            z._emerge_pending = False
            ex, ey = z.x + z.w // 2, z.y + z.h - 6
            self.fx.dig_dust(ex, ey)
            self.fx.ring(ex, ey, 4, 40, (150, 116, 66),
                         duration=0.45, width=3, layer=0)
            self.add_shake(2)

        # Bungee reaches the plant: yellow lift-up dust right before the snatch.
        if getattr(z, "_steal_burst_pending", False):
            z._steal_burst_pending = False
            cx, cy = z.x + z.w // 2, z.y + z.h - 10
            self.fx.burst(cx, cy, (240, 220, 120), n=8, speed=(40, 120),
                          size=(2, 4), life=(0.3, 0.6), gravity=300)
            self.fx.ring(cx, cy, 4, 30, (255, 230, 140),
                         duration=0.35, width=2)

        # Newspaper zombie's paper finally gave out — red anger flare + groan.
        if getattr(z, "_play_anger", False):
            z._play_anger = False
            cx, cy = z.x + z.w // 2, z.y + 14
            self.fx.burst(cx, cy, (220, 60, 50), n=10, speed=(60, 180),
                          size=(2, 4), life=(0.35, 0.6), gravity=120)
            self.fx.ring(cx, cy, 6, 40, (230, 70, 60), duration=0.4, width=3)
            self._play_sound("groan", 0.9)

    def _spawn_coin_drop(self, x, y, value=25):
        """Gold coin popup that arcs up + falls back. Used as a wave-clear /
        level-complete reward.
        """
        import math as _m
        # arc with slight side drift; gravity pulls it back down
        angle = _m.radians(random.uniform(-80, -55))  # mostly upward, slight fan
        speed = random.uniform(170, 240)
        self.coin_drops.append({
            "x": float(x),
            "y": float(y),
            "vx": math.cos(angle) * speed * random.choice([-1, 1]) * 0.4,
            "vy": math.sin(angle) * speed,
            "age": 0.0,
            "max": 1.2,
            "value": value,
            "rot": random.uniform(0, 6.28),
        })

    def _detonate_kernel(self, proj):
        """A Cob Cannon KernelBomb reached its target — spawn a big explosion,
        deal AOE damage to all zombies within `radius`, and add a screen shake.
        """
        cx, cy = int(proj.target_x), int(proj.target_y)
        # Big explosion — re-use Explosion for the visual
        self.explosions.append(Explosion(cx, cy, radius=int(proj.radius),
                                          duration=0.65))
        # AOE damage
        for z in self.zombies:
            if not z.alive or z.hp <= 0 or z.dying_timer > 0:
                continue
            dx = (z.x + z.w // 2) - cx
            dy = (z.y + z.h // 2) - cy
            if dx * dx + dy * dy <= proj.radius * proj.radius:
                z.take_damage(proj.damage)
                self._spawn_damage_text(z.x + z.w // 2, z.y - 6, proj.damage)
        # shake for impact weight
        self.add_shake(6)
        self._play_sound("explode", 0.8)

    def _spawn_boss_aura(self, boss, kind="summon"):
        """A halo + sparks at the boss on a summon, or a shockwave on death.

        Sparks are emitted at the boss's *current* position rather than being
        baked as a live-tracked entity, so a walking boss doesn't drag them.
        """
        cx = boss.x + boss.w // 2
        cy = boss.y + 18
        if kind == "summon":
            # Magenta halo + upward sparks: a minion is inbound.
            self.fx.ring(cx, cy, 16, 80, (200, 80, 230), duration=0.55, width=4)
            for _ in range(4):
                ang = random.uniform(-math.pi * 0.85, -math.pi * 0.15)
                spd = random.uniform(60, 130)
                self.fx._emit(x=cx + random.randint(-10, 10),
                              y=cy + random.randint(-6, 6),
                              vx=math.cos(ang) * spd * 0.4,
                              vy=math.sin(ang) * spd - 30,
                              gravity=260, drag=1.5,
                              size=random.uniform(2, 4),
                              max_life=random.uniform(0.5, 0.8),
                              color=(220, 130, 255), kind="dot")
        elif kind == "death":
            # Two staggered shockwaves: a bright white flash then a magenta core.
            self.fx.ring(cx, cy, 24, 220, (255, 255, 255), duration=0.9, width=5)
            self.fx.ring(cx, cy, 24, 200, (220, 80, 240), duration=0.9, width=5,
                         delay=0.10)
            # Full-circle spray of white/magenta embers.
            for _ in range(14):
                ang = random.uniform(0, math.tau)
                spd = random.uniform(140, 240)
                self.fx._emit(x=cx + random.randint(-12, 12),
                              y=cy + random.randint(-8, 8),
                              vx=math.cos(ang) * spd,
                              vy=math.sin(ang) * spd - 30,
                              gravity=260, drag=1.5,
                              size=random.uniform(2, 5),
                              max_life=random.uniform(0.7, 1.0),
                              color=(255, 200, 255) if random.random() < 0.5
                              else (240, 240, 255), kind="dot")

    def _announce_wave(self, wave_idx):
        # Endless survival regenerates its wave table every 50 waves, so
        # wave_idx == wave_count recurs (wave 50, 100, ...) — only adventure
        # has a real "last wave".
        if self.mode == MODE_ADVENTURE and wave_idx == self.wave.wave_count:
            self.wave_warning.show(tr("FINAL WAVE!"), tr("Brace yourself!"), COLOR_RED, 3.5)
            self._play_sound("bigwave")
            self._zoom_freeze = 0.55   # longest zoom for final
        elif wave_idx == 1:
            self.wave_warning.show(tr("Here They Come!"), "", COLOR_RED, 2.5)
            self._play_sound("wave", 0.6)
            self._zoom_freeze = 0.35
        elif wave_idx % 5 == 0 and wave_idx > 5:
            self.wave_warning.show(tr("A Huge Wave of Zombies!"), i18n.fmt_wave(wave_idx), COLOR_RED, 3.0)
            self._play_sound("bigwave")
            self._zoom_freeze = 0.50
        else:
            self.wave_warning.show(i18n.fmt_wave(wave_idx), tr("is Approaching!"), COLOR_RED, 2.2)
            self._play_sound("wave", 0.4)
            self._zoom_freeze = 0.30
        # Sky ambush in the later worlds: a Bungee Zombie drops with every
        # huge / final wave (its endless-mode counterpart comes from WaveSystem).
        if (self.bg_type in (BG_FOG, BG_ROOF) and self.mode == MODE_ADVENTURE
                and (wave_idx % 5 == 0 or wave_idx == self.wave.wave_count)):
            col = random.randint(1, GRID_COLS - 1)
            row = random.choice(ai.intel.land_rows())
            z = create_zombie(GRID_X + col * CELL_W + (CELL_W - 90) // 2,
                              -250, row, ZOMBIE_BUNGEE)
            z.grid_y = self.grid.y
            z.in_wave = False  # extra ambush — must not clear the wave early
            self.zombies.append(z)

    def announce_cherry_explosion(self, x, y, zombies_killed):
        """Big floating text for cherry bomb kills."""
        if zombies_killed > 0:
            txt = (tr("BOOM!") + f" -{zombies_killed}") if zombies_killed > 1 else tr("BOOM!")
            color = COLOR_RED
        else:
            txt = tr("*fizzle*")
            color = (180, 180, 180)
        self.floating_texts.append(FloatingText(x, y, txt, color=color, size=28, vy=-80, lifetime=1.4))

    def update(self, dt):
        # Decay feel timers in real time, before the state check: main.py
        # applies shake_offset() unconditionally, so if a state change
        # (game over / victory / pause) lands while shake or flash is
        # non-zero, the end screen would otherwise shake/flash forever.
        self.shake = max(0.0, self.shake - 26.0 * dt)
        self.sun_pulse = max(0.0, self.sun_pulse - 2.2 * dt)
        self.flash_timer = max(0.0, self.flash_timer - dt)
        if self.state != STATE_PLAYING:
            if self.state in (STATE_LEVEL_COMPLETE, STATE_SURVIVAL_COMPLETE):
                self._update_coin_drops(dt)
            return

        # Fast-forward scales the whole simulation uniformly.
        dt *= self.speed_mult
        # Wave-start cinematic: visual overlay (vignette + red wash) drawn below
        # signals the "time freeze" feel. We deliberately do NOT slow dt here,
        # because gameplay-critical timers (bungee descent, cherry fuse, plant
        # food) need real-time progression to keep their mechanics intact.

        # ambient zombie groans while the horde is on the lawn
        if any(z.alive and z.hp > 0 and z.dying_timer <= 0 for z in self.zombies):
            self.groan_timer -= dt
            if self.groan_timer <= 0:
                self.groan_timer = random.uniform(7.0, 14.0)
                self._play_sound("groan", 0.35)

        # Sky-sun timer uses game dt, so pausing/window dragging cannot create
        # bursts or skip economy time.
        if self.bg_type != BG_NIGHT:
            self.sun_spawn_timer += dt
            interval = SUN_FALL_INTERVAL / 1000.0
            if self.sun_spawn_timer >= interval:
                self.sun_spawn_timer -= interval
                for _ in range(SUN_FALL_COUNT):
                    if len(self.suns) >= 60:
                        break
                    x = random.randint(GRID_X + 20, GRID_X + GRID_W - 20)
                    y = SUN_FALL_Y
                    target_y = random.randint(self.grid.y + 20,
                                              self.grid.y + GRID_H - 40)
                    sun = Sun(x, y)
                    # Sky sun: gravity-accelerated fall + a couple of
                    # rebounds when it hits the lawn (see entities._Pickup).
                    sun.drop_from_sky(target_y)
                    self.suns.append(sun)

        # update suns — collected ones fly into the jar and credit on arrival
        for sun in self.suns:
            # Hovering suspends the sun's motion (entities.Sun.update): the
            # one-frame lag vs _update_hover is imperceptible on a 2px bob.
            sun.update(dt, hovered=(sun is self.hover_sun))
            # First touchdown: a soft dust ring so the landing has weight.
            if sun._landed_pending:
                sun._landed_pending = False
                self.fx.ring(sun.x, sun.y + 12, 6, 30, (255, 236, 150),
                             duration=0.34, width=2, layer=0)
                self.fx.burst(sun.x, sun.y + 12, (255, 228, 140), n=6,
                              speed=(40, 120), size=(2, 3.6), life=(0.25, 0.45),
                              gravity=260)
                self._play_sound("sun_land", 0.25)
            if getattr(sun, "arrived", False):
                sun.arrived = False
                self.sun_value += sun.amount
                self.sun_pulse = 1.0
        self.suns = [s for s in self.suns if s.alive]

        # plant food (能量豆) sky drops — day and night alike
        self.food_timer -= dt
        if self.food_timer <= 0:
            self.food_timer = random.uniform(*PLANT_FOOD_INTERVAL) / 1000.0
            if len(self.plant_foods) < 2:
                pf = PlantFood(random.randint(GRID_X + 40, GRID_X + GRID_W - 40),
                               SUN_FALL_Y)
                pf.drop_from_sky(random.randint(self.grid.y + 40,
                                                self.grid.y + GRID_H - 60))
                self.plant_foods.append(pf)
        for pf in self.plant_foods:
            pf.update(dt)
            if pf.arrived and not pf.alive:
                # Vial just landed in the jar — credit the player.
                if self.plant_food < PLANT_FOOD_MAX:
                    self.plant_food += 1
                pf.arrived = False   # one-shot
        self.plant_foods = [pf for pf in self.plant_foods if pf.alive]

        # update plant cooldowns
        for ptype in list(self.plant_cooldowns.keys()):
            self.plant_cooldowns[ptype] -= dt
            if self.plant_cooldowns[ptype] <= 0:
                del self.plant_cooldowns[ptype]

        # update plants
        new_projectiles = []
        # snapshot HP for damage-event detection
        plant_hp_before = {id(p): p.hp for p in self.plants if p.alive}
        for p in self.plants:
            if not p.alive:
                continue
            st = getattr(p, "spawn_t", 0.0)
            if st > 0:
                p.spawn_t = max(0.0, st - dt)
            if isinstance(p, Sunflower):
                result = p.update(dt, self.zombies, allow_production=len(self.suns) < 60)
            else:
                result = p.update(dt, self.zombies)
            if isinstance(result, Projectile):
                new_projectiles.append(result)
            elif isinstance(result, Sun):
                # Prevent pathological accumulation in long survival sessions.
                if len(self.suns) < 60:
                    self.suns.append(result)
            elif isinstance(result, list):
                kills = sum(1 for z in result if z.hp <= 0)
                if p.plant_type == PLANT_CHERRYBOMB:
                    self.announce_cherry_explosion(int(p.x + p.w // 2), int(p.y), kills)
                    self._play_sound("explode")
                    self.explosions.append(Explosion(p.x + p.w // 2, p.y + p.h // 2))
                    self.add_shake(9)
                    self.flash_timer = 0.12
        if new_projectiles:
            self._play_sound(SOUND_SHOOT, 0.25)
        # detect plants damaged this tick
        for p in self.plants:
            if not p.alive:
                continue
            prev = plant_hp_before.get(id(p))
            if prev is not None and p.hp < prev:
                dmg = int(prev - p.hp)
                if dmg > 0:
                    self._spawn_damage_text(int(p.x + p.w // 2), int(p.y - 4),
                                             dmg, color=COLOR_RED)
                    self._play_sound("eat", 0.3)
        self.projectiles.extend(new_projectiles)

        # update projectiles
        surviving_projectiles = []
        for proj in self.projectiles:
            proj.update(dt)
            if isinstance(proj, KernelBomb):
                # Cob Cannon: detonates at target — explodes on landing
                if not proj.alive:
                    self._detonate_kernel(proj)
                else:
                    surviving_projectiles.append(proj)
                continue
            if not proj.alive:
                continue
            hit = False
            for z in self.zombies:
                if (not z.alive or z.hp <= 0 or z.dying_timer > 0
                        or z.underground or z.row != proj.row):
                    continue
                if proj.swept_rect().colliderect(z.rect()):
                    z.take_damage(proj.damage)
                    self._spawn_damage_text(z.x + z.w // 2, z.y - 6, proj.damage)
                    self._play_sound("zombie_hit", 0.25)
                    # impact spark burst at the hit point (left edge of zombie body)
                    self._spawn_pea_impact(proj.x + 4, z.y + 18,
                                           is_fume=proj.is_fume,
                                           is_frost=getattr(proj, "freezes", False))
                    # Snow Pea style: apply ice debuff + slow
                    if getattr(proj, "freezes", False):
                        z.apply_ice(proj.freeze_seconds)
                    hit = True
                    break
            if not hit:
                surviving_projectiles.append(proj)
        self.projectiles = surviving_projectiles

        # Refresh the battlefield snapshot the AI zombies read this frame.
        # One O(plants) pass instead of every tactician/digger scanning the
        # whole plant list for itself.
        if DIRECTOR_ENABLED or self.zombies:
            ai.refresh_intel(self.plants)

        # update zombies (bosses may spawn minions → collected here)
        new_zombies = []
        zlist = self.zombies
        for z in zlist[:]:
            r = z.update(dt, self.plants, zlist)
            if isinstance(r, Zombie):
                new_zombies.append(r)
                # Boss aura: when the boss spawns a minion, flash a halo so the
                # player can read the incoming threat on the lawn.
                if z.is_boss:
                    self._spawn_boss_aura(z, kind="summon")
            # Walking zombie takes a step → drop a faint grass print.
            if getattr(z, "_step_just_done", False) and z.alive and z.dying_timer <= 0:
                z._step_just_done = False
                if not z.floating and not z.reached_house:
                    self._spawn_grass_print(z)
            # AI zombie reaction hooks (heal beam, rally pulse, lane hop,
            # digger dust). Emitted here so entities stay free of the FX layer.
            self._consume_zombie_ai_fx(z)
        self.zombies.extend(new_zombies)
        # Boss-summoned minion landing: emit ground-impact ring + dust the
        # frame the minion touches down. _minion_drop_landed is set by
        # Zombie.update when the sky-drop ease-in completes.
        for nz in new_zombies:
            if getattr(nz, "_minion_drop_landed", False):
                nz._minion_drop_landed = False
                self._spawn_minion_landing(nz)
        # bungee theft announcement
        for z in self.zombies:
            if z.is_bungee and z.stole_plant and not z.steal_announced:
                z.steal_announced = True
                self.message.show(tr("A Bungee Zombie stole your plant!"), 2200)
                self._play_sound("steal", 0.8)

        # lawnmowers: idle ones trigger when a zombie passes their slot;
        # activated ones roll right, killing every zombie in their row
        for lm in self.lawnmowers[:]:
            if not lm.alive:
                continue
            if lm.activated:
                # First-frame starter puff (bigger than the steady trail).
                if getattr(lm, "_activated_just_now", False):
                    lm._activated_just_now = False
                    self._spawn_mow_dust(lm, big=True)
                lm.update(dt)
                # Trailing puffs while moving
                if getattr(lm, "_needs_dust_puff", False):
                    lm._needs_dust_puff = False
                    self._spawn_mow_dust(lm, big=False)
                if not lm.alive:
                    continue
                for z in self.zombies:
                    if (z.alive and z.hp > 0 and z.row == lm.row
                            and not z.floating and not z.is_bungee
                            and not z.reached_house
                            and lm.rect().colliderect(z.rect())):
                        z.take_damage(99999)
                # Chain trigger: when this mower exits the right edge, fire any
                # surviving mowers in adjacent rows. PvZ2 surprise — the whole
                # lawn's mowers activate in cascade when one exits the screen.
                if lm.x > SCREEN_WIDTH - 20:
                    self._chain_trigger_mowers(exclude_row=lm.row)
            else:
                for z in self.zombies:
                    if (z.alive and z.hp > 0 and z.row == lm.row
                            and not z.floating and not z.is_bungee
                            and not z.reached_house
                            and z.rect().left <= lm.rect().right + 12):
                        # zombie reached the mower slot → mow!
                        lm.activate()
                        z.take_damage(99999)
                        self._play_sound("mow", 0.8)
                        self.add_shake(4)
                        break

        # post-zombie death handling
        dead_zombies = []
        for z in self.zombies:
            if not z.alive:
                dead_zombies.append(z)
                continue
            # Balloon pop! Floating was True last frame and is now False —
            # the popped flag is set by Zombie.take_damage (entities.py).
            if getattr(z, "_balloon_popped", False):
                z._balloon_popped = False
                self._spawn_balloon_pop(z)
            if z.reached_house:
                # original PvZ: once a zombie reaches the house, it's over.
                # (a still-present mower would have mowed it; reaching here means
                #  the row's mower is gone.)
                self.house_hp = 0
                self._record_survival_run()
                self._play_sound("lose")
                self.state = STATE_GAME_OVER
        for z in dead_zombies:
            if not z.death_counted:
                z.death_counted = True
                if z.escaped:
                    # A bungee that climbed off-screen released its wave slot
                    # (otherwise the wave would never clear) but it was never
                    # killed: no sun reward, no death FX, no kill sound.
                    if z.in_wave:
                        self.wave.zombie_died()
                    continue
                if z.is_boss:
                    self.add_shake(10)
                    self.flash_timer = 0.1
                    self._spawn_boss_aura(z, kind="death")
                if z.in_wave:
                    self.wave.zombie_died()
                self.sun_value += z.reward
                self._spawn_collect_text(z.x + z.w // 2, z.y - 6, z.reward)
                self._play_sound(SOUND_ZOMBIE_DIE, 0.5)
                self._spawn_zombie_head(z)
        self.zombies = [z for z in self.zombies if z.alive]

        # update fog
        respawned_fog = []
        for f in self.fog_layers:
            f.update(dt)
            if not f.alive:
                respawned_fog.append(FogLayer(f.row, SCREEN_WIDTH))
        self.fog_layers = [f for f in self.fog_layers if f.alive] + respawned_fog

        # update wave system
        self.wave.update(dt, self.zombies)

        # check between waves
        if self.wave.between_waves and self.wave.update_between_waves(dt):
            self._advance_after_wave()

        # check level complete (adventure only). Final-wave minions spawned by
        # the boss must also be cleared before showing victory.
        if (self.mode == MODE_ADVENTURE and self.wave.wave_cleared
                and self.wave.is_last_wave() and not self.wave.wave_active
                and not any(z.alive and z.hp > 0 for z in self.zombies)):
            self._complete_adventure()

        # update UI
        for btn in self.seed_buttons:
            btn.update(self.sun_value, self.plant_cooldowns, dt)

        self.message.update(dt)
        self.tooltip.update(dt)
        # update floating text + plant poof + explosions + wave warning
        for ft in self.floating_texts:
            ft.update(dt)
        self.floating_texts = [ft for ft in self.floating_texts if ft.alive]
        for ex in self.explosions:
            ex.update(dt)
        self.explosions = [ex for ex in self.explosions if ex.alive]
        # One pass advances every particle (ground + air); the system culls
        # expired ones and recycles them into its free pool.
        self.fx.update(dt)
        self._update_coin_drops(dt)
        self.wave_warning.update(dt)
        # Drain wave-zoom freeze. Once at 0 the wave cinematic is over and the
        # simulation runs at full speed again.
        if self._zoom_freeze > 0:
            self._zoom_freeze = max(0.0, self._zoom_freeze - dt)

        # Detect plants that died this frame and emit 6-8 leaf/petal particles
        # at their last known position. We capture the alive set BEFORE the
        # compact step below wipes the dead plants from self.plants.
        for p in self.plants:
            if not p.alive and not getattr(p, "_debris_spawned", False):
                p._debris_spawned = True
                self._spawn_plant_debris(p)

        # Compact long-running lists. Keep a dead lily only until this frame;
        # no gameplay code needs dead plants or off-screen mowers afterwards.
        self.plants = [p for p in self.plants if p.alive]
        self.lawnmowers = [lm for lm in self.lawnmowers if lm.alive]
        if self.hover_plant is not None and not self.hover_plant.alive:
            self.hover_plant = None
        if self.hover_zombie is not None and not self.hover_zombie.alive:
            self.hover_zombie = None

        # hover tracking runs every frame so tooltips follow moving bodies
        self._update_hover(self.mouse_x, self.mouse_y)
        self._refresh_cursor()

    def _update_coin_drops(self, dt):
        """Advance reward coins while either the game or result screen is visible."""
        for c in self.coin_drops:
            c["age"] += dt
            if c["age"] >= 0:
                c["x"] += c["vx"] * dt
                c["y"] += c["vy"] * dt
                c["vy"] += 540 * dt
                c["vx"] *= (1.0 - 0.8 * dt)
                c["rot"] += 6.0 * dt
        self.coin_drops = [c for c in self.coin_drops if c["age"] < c["max"]]

    def draw(self):
        # Real PvZ lawn background (includes house, fence, sidewalk, sky)
        self._draw_lawn_background()

        # background-specific overlays (pool water, roof tiles, fog)
        self._draw_bg_overlays()

        # roof as one pre-rendered layer (Roof mode) — sits on top of lawn
        if self._roof_layer is not None:
            self.screen.blit(self._roof_layer, (self.grid.x, self.grid.y))
        else:
            for rt in self.roof_tiles:
                rt.draw(self.screen)

        # draw lawnmowers
        for lm in self.lawnmowers:
            lm.draw(self.screen)

        # draw grid (only hover/selection overlays)
        self.grid.draw(self.screen,
                       shovel_active=bool(self.shovel and self.shovel.selected),
                       suppress_hover=self.hover_sun is not None)
        self._draw_placement_preview()

        # draw lily pads (Pool mode — on water rows)
        for lp in self.lily_pads:
            lp.draw(self.screen)

        # draw plants
        for p in self.plants:
            if p.alive:
                p.draw(self.screen)

        # draw projectiles
        for proj in self.projectiles:
            proj.draw(self.screen)

        # Ground particle layer: pressed-grass footprints, soil poofs and
        # digger dirt — all below the actors, so they read as marks on the lawn.
        self.fx.draw_ground(self.screen)

        # draw zombies
        for z in self.zombies:
            if z.alive:
                z.draw(self.screen)

        # draw floating text (damage / sun) on top of plants & zombies
        for ft in self.floating_texts:
            ft.draw(self.screen)

        # draw coin drops (gold coins flying up + falling back)
        for c in self.coin_drops:
            if c["age"] < 0:
                continue
            t = c["age"] / c["max"]
            # bright at peak (t≈0.4), fade out as it lands
            alpha = int(255 if t < 0.7 else 255 * (1.0 - (t - 0.7) / 0.3))
            if alpha <= 0:
                continue
            r = 9
            cx = int(c["x"])
            cy = int(c["y"])
            # outer gold ring (rotates by tilt angle)
            coin = self._get_scratch(r * 2 + 2, r * 2 + 2)
            # face (warm gold)
            pygame.draw.circle(coin, (255, 215, 60, alpha), (r + 1, r + 1), r)
            # inner highlight
            pygame.draw.circle(coin, (255, 240, 150, int(alpha * 0.8)),
                               (r + 1 - 2, r + 1 - 2), max(2, r // 2))
            # dark rim
            pygame.draw.circle(coin, (180, 130, 30, alpha), (r + 1, r + 1), r, 2)
            # "$" mark on the face — small dark ellipse, rotated to a cached
            # 45°-step variant (transform.rotate allocates; cache it). The
            # mark's own alpha bakes into its pixels, so the key carries it.
            ma = int(alpha * 0.9)
            slot = int(c["rot"] * 4 / math.tau) % 8
            key = (r, ma, slot)
            dot_mark = self._coin_mark_cache.get(key)
            if dot_mark is None:
                mark = self._get_scratch(r, r)
                pygame.draw.ellipse(mark, (130, 95, 25, ma),
                                    (r // 3, 1, r // 3, r - 2))
                dot_mark = pygame.transform.rotate(mark, slot * 45)
                self._coin_mark_cache[key] = dot_mark
            coin.blit(dot_mark, ((r * 2 + 2 - dot_mark.get_width()) // 2,
                                 (r * 2 + 2 - dot_mark.get_height()) // 2))
            self.screen.blit(coin, (cx - r - 1, cy - r - 1))

        # explosions (cherry bombs / boss deaths)
        for ex in self.explosions:
            ex.draw(self.screen)

        # ---- particle layer (over actors) -------------------------------
        # Pea sparks, balloon shreds, mower dust, zombie chunks, plant-food
        # rings, boss auras and AI beams all render through one system.
        self.fx.draw_air(self.screen)

        # hover highlight on plant / zombie
        if self.hover_plant is not None and self.hover_plant.alive:
            pr = pygame.Rect(self.hover_plant.x - 2, self.hover_plant.y - 2,
                             self.hover_plant.w + 4, self.hover_plant.h + 4)
            pygame.draw.rect(self.screen, (255, 230, 120), pr, 2, border_radius=4)
        elif self.hover_zombie is not None and self.hover_zombie.alive:
            zr = pygame.Rect(self.hover_zombie.x - 2, self.hover_zombie.y - 2,
                             self.hover_zombie.w + 4, self.hover_zombie.h + 4)
            pygame.draw.rect(self.screen, (255, 100, 100), zr, 2, border_radius=4)

        # draw suns
        for sun in self.suns:
            sun.draw(self.screen)
        # Hovered sun: a soft ring so the (now circular) click target reads
        # under the cursor — previously the only feedback was the cursor
        # change, which made collection feel unresponsive (阳光点击效果不对).
        if self.hover_sun is not None and self.hover_sun.alive:
            s = self.hover_sun
            cx, cy = (int(v) for v in s._visual_center())
            t = pygame.time.get_ticks() / 1000.0
            rad = SUN_COLLECT_RADIUS + 3 + math.sin(t * 6.0) * 1.5
            pygame.draw.circle(self.screen, (255, 244, 170), (cx, cy), int(rad), 2)

        # draw plant food drops (能量豆)
        for pf in self.plant_foods:
            pf.draw(self.screen)

        # upgrade level pips above upgraded plants
        for p in self.plants:
            n = level_pips(p)
            if n > 0 and p.alive:
                pip_w = 13
                x0 = p.x + p.w // 2 - (n * pip_w) // 2 + 2
                for i in range(n):
                    px = int(x0) + i * pip_w
                    pygame.draw.circle(self.screen, (255, 215, 60), (px, p.y - 17), 5)
                    pygame.draw.circle(self.screen, (150, 105, 15), (px, p.y - 17), 5, 2)

        # draw fog (Fog mode — on top of lawn)
        for f in self.fog_layers:
            f.draw(self.screen)

        # draw seed bar + sun jar + shovel + quick buttons
        self._draw_seed_bar()
        self._draw_plant_food_hud()
        self._draw_topbar_buttons()
        if self.shovel:
            self.shovel.draw(self.screen)

        # wave progress bar (PvZ-style flag markers)
        self._draw_progress_bar()

        # draw wave indicator
        self.wave.draw_wave_indicator(self.screen, self.font)

        # draw survival wave counter
        if self.mode == MODE_SURVIVAL:
            t = cached_text(i18n.fmt_survival_wave(self.wave.wave_index), 22,
                            COLOR_WHITE, outline=(0, 0, 0))
            self.screen.blit(t, (SCREEN_WIDTH - t.get_width() - 20, UI_BAR_H + 8))

        # draw message / tooltip / wave banner only while actually playing —
        # end screens must not show stale banners behind their overlays
        playing = self.state == STATE_PLAYING
        if playing:
            self.message.draw(self.screen, self.font)
            self.tooltip.draw(self.screen, self.font)
            # ---- Wave-start cinematic: radial vignette + red tint while frozen ----
            if self._zoom_freeze > 0:
                self._draw_wave_zoom_overlay()
            self.wave_warning.draw(self.screen)

        # draw between waves message
        if self.wave.between_waves and self.state == STATE_PLAYING:
            secs = max(0, (self.wave.between_wave_duration - self.wave.between_wave_timer))
            t = cached_text(i18n.fmt_get_ready(secs), 32, COLOR_WHITE, outline=(0, 0, 0))
            bg = pygame.Rect(SCREEN_WIDTH // 2 - t.get_width() // 2 - 10, 10, t.get_width() + 20, t.get_height() + 10)
            alpha_rect(self.screen, (0, 0, 0, 180), bg, radius=6)
            self.screen.blit(t, (SCREEN_WIDTH // 2 - t.get_width() // 2, 15))

        # explosion white flash (brief, right after detonation)
        if self.flash_timer > 0:
            self._flash_surface.set_alpha(int(120 * min(1.0, self.flash_timer / 0.12)))
            self.screen.blit(self._flash_surface, (0, 0))

        # ghost seed packet / shovel under the cursor
        if self.state == STATE_PLAYING:
            self._draw_ghost_cursor()

    def _draw_lawn_background(self):
        """Draw the PvZ lawn background image that matches the current bg_type."""
        import assets_loader
        if self.bg_type == BG_NIGHT:
            img = assets_loader.get("bg_night_full")
        else:
            # Pool gets explicit water lanes; fog/roof use overlays below.
            img = assets_loader.get("bg_day_full")
        if img is None:
            # fallback to plain grass
            img = assets_loader.get("bg_fallback")
        if img is not None:
            self.screen.blit(img, (0, 0))
        else:
            self.screen.fill((34, 139, 34))

    def _draw_bg_overlays(self):
        """Per-mode overlays on top of the lawn image."""
        if self.bg_type == BG_POOL:
            # Water lanes pre-rendered once at level start.
            if self._water_layer is not None:
                self.screen.blit(self._water_layer,
                                 (self.grid.x,
                                  self.grid.y + self._water_row0 * CELL_H))
        elif self.bg_type == BG_FOG:
            self.screen.blit(self._fog_veil, (0, 0))
        elif self.bg_type == BG_ROOF:
            # The pre-rendered roof layer paints the full playable surface.
            pass

    def _draw_seed_bar(self):
        import assets_loader
        # Top bar background — cached wood-like surface
        self.screen.blit(self._seed_bar_surface, (0, UI_BAR_Y))
        # Seed bank panel with a rounded right edge (original PvZ look):
        # the sun jar and the seed cards sit on their own darker wood plate.
        bank_w = SEED_CARD_START_X + len(self.seed_buttons) * (SEED_CARD_W + SEED_CARD_GAP) + 8
        bank = pygame.Rect(0, UI_BAR_Y, bank_w, UI_BAR_H)
        pygame.draw.rect(self.screen, (56, 36, 17), bank,
                         border_top_right_radius=18, border_bottom_right_radius=18)
        pygame.draw.rect(self.screen, (128, 88, 42),
                         (2, UI_BAR_Y + 2, bank_w - 4, UI_BAR_H - 4), 2,
                         border_top_right_radius=16, border_bottom_right_radius=16)
        pygame.draw.line(self.screen, (40, 30, 15), (0, UI_BAR_H), (SCREEN_WIDTH, UI_BAR_H), 2)
        self._draw_sun_jar()
        for btn in self.seed_buttons:
            btn.draw(self.screen, self.font)

    def _draw_placement_preview(self):
        """Show selected plant ghost and green/red/gold target cell under cursor."""
        if self.state != STATE_PLAYING or self.grid.hover_cell is None:
            return
        selected = next((b.plant_type for b in self.seed_buttons if b.selected), None)
        if selected is None:
            return
        row, col = self.grid.hover_cell
        allowed, _ = self._can_place(selected, (row, col))
        upgrade = self._upgrade_target(selected, (row, col)) is not None
        rect = pygame.Rect(self.grid.x + col * CELL_W, self.grid.y + row * CELL_H,
                           CELL_W, CELL_H)
        if upgrade:
            # gold tint = replant here to level the plant up
            overlay = self._preview_bad if not allowed else self._preview_ok
            self.screen.blit(overlay, rect.topleft)
            pygame.draw.rect(self.screen, (255, 215, 60), rect, 3)
        else:
            self.screen.blit(self._preview_ok if allowed else self._preview_bad,
                             rect.topleft)
            pygame.draw.rect(self.screen, (110, 255, 120) if allowed else (255, 100, 100),
                             rect, 3)
        icon = assets_loader.cursor_icon(selected, 64)
        if icon is not None:
            # cached translucent copy (icon.copy() every frame adds up)
            ck = ("preview", selected, 150 if allowed else 85)
            ghost = self._ghost_cache.get(ck)
            if ghost is None:
                ghost = icon.copy()
                ghost.set_alpha(150 if allowed else 85)
                self._ghost_cache[ck] = ghost
            self.screen.blit(ghost, ghost.get_rect(center=rect.center))

    def _draw_wave_zoom_overlay(self):
        """Red-tinted radial vignette while _zoom_freeze > 0.
        Cheap approach: 4 dark corner gradients + faint red wash on top half.
        Surfaces are built once and cached — they never change between calls.
        """
        sw, sh = SCREEN_WIDTH, SCREEN_HEIGHT
        if not hasattr(self, '_zoom_corner'):
            # Build corner gradient once: alpha = 180 at vertex, 0 along edges.
            # Filled per pixel from the corner distance — drawing it as 1px
            # rings left a dithered, banded blob over the sun jar.
            cx0, cy0 = sw // 3, sh // 3
            corner = pygame.Surface((cx0, cy0), pygame.SRCALPHA)
            corner.fill((0, 0, 0, 0))
            span = 60.0
            corner.lock()
            for y in range(int(span)):
                for x in range(int(span)):
                    a = int(180 * (1.0 - math.hypot(x, y) / span))
                    if a > 0:
                        corner.set_at((x, y), (0, 0, 0, a))
            corner.unlock()
            # Pre-flip for the other three corners
            self._zoom_corner = corner
            self._zoom_corner_tr = pygame.transform.flip(corner, True, False)
            self._zoom_corner_bl = pygame.transform.flip(corner, False, True)
            self._zoom_corner_br = pygame.transform.flip(corner, True, True)
            self._zoom_cx0 = cx0
            self._zoom_cy0 = cy0
            # Red flash wash (top half) — built once
            wash = pygame.Surface((sw, sh // 2), pygame.SRCALPHA)
            for y in range(sh // 2):
                a = int(60 * (1.0 - y / (sh // 2)))
                pygame.draw.line(wash, (180, 30, 30, a), (0, y), (sw, y), 1)
            self._zoom_wash = wash
        # Blit cached surfaces. The top corners start below the seed bar so the
        # cinematic never dims the sun jar / seed cards the player is reading.
        self.screen.blit(self._zoom_corner, (0, UI_BAR_H))
        self.screen.blit(self._zoom_corner_tr, (sw - self._zoom_cx0, UI_BAR_H))
        self.screen.blit(self._zoom_corner_bl, (0, sh - self._zoom_cy0))
        self.screen.blit(self._zoom_corner_br, (sw - self._zoom_cx0, sh - self._zoom_cy0))
        self.screen.blit(self._zoom_wash, (0, UI_BAR_H))

    def _draw_sun_jar(self):
        import assets_loader
        jar_cx = SUN_JAR_X + SUN_JAR_W // 2
        jar_cy = SUN_JAR_Y + SUN_JAR_W // 2
        # collection pulse ring around the jar
        if self.sun_pulse > 0:
            glow_r = int(28 + 16 * self.sun_pulse)
            pygame.draw.circle(self.screen, (255, 230, 90),
                               (jar_cx, jar_cy), glow_r,
                               max(2, int(4 * self.sun_pulse)))
        # Use the clean 240px sun artwork; the small v_Sun.png leaves a dark
        # speckled halo after matte removal. The smoothscale is size-stable,
        # so cache it — scaling a 240px source every frame is pure waste.
        sun_jar_img = assets_loader.get("ui_sun")
        if sun_jar_img:
            if getattr(self, "_sun_jar_scaled", None) is None:
                self._sun_jar_scaled = pygame.transform.smoothscale(
                    sun_jar_img, (SUN_JAR_W, SUN_JAR_W))
            self.screen.blit(self._sun_jar_scaled, (SUN_JAR_X, SUN_JAR_Y - 2))
        else:
            pygame.draw.circle(self.screen, COLOR_YELLOW, (jar_cx, jar_cy), SUN_JAR_W // 2)
            pygame.draw.circle(self.screen, COLOR_ORANGE, (jar_cx, jar_cy), SUN_JAR_W // 2, 2)
        t = cached_text(str(self.sun_value), 22, COLOR_WHITE, outline=(0, 0, 0))
        ty = SUN_JAR_Y + SUN_JAR_W // 2 - 7
        self.screen.blit(t, (SUN_JAR_X + SUN_JAR_W + 6, ty))

    def _draw_plant_food_hud(self):
        """Stored 能量豆 slots, left of the pause button."""
        x0 = self.btn_pause.x - 24
        cy = self.btn_pause.centery
        for i in range(PLANT_FOOD_MAX):
            x = x0 - i * 22
            if i < self.plant_food:
                pygame.draw.circle(self.screen, (80, 200, 60), (x, cy), 8)
                pygame.draw.circle(self.screen, (40, 140, 40), (x, cy), 8, 2)
                pygame.draw.lines(self.screen, (255, 255, 210), False,
                                  [(x - 2, cy - 4), (x + 2, cy - 1), (x - 1, cy),
                                   (x + 2, cy + 4)], 2)
            else:
                pygame.draw.circle(self.screen, (45, 70, 45), (x, cy), 8)
                pygame.draw.circle(self.screen, (70, 110, 70), (x, cy), 8, 1)

    def _draw_topbar_buttons(self):
        """Quick pause / fast-forward buttons, left of the shovel."""
        mx, my = self.mouse_x, self.mouse_y
        # fast-forward
        ff_on = self.speed_mult > 1.0
        ff_hover = self.btn_ff.collidepoint(mx, my)
        col = (70, 170, 80) if ff_on else ((90, 120, 90) if ff_hover else (55, 80, 55))
        pygame.draw.rect(self.screen, col, self.btn_ff, border_radius=8)
        pygame.draw.rect(self.screen, (20, 30, 20), self.btn_ff, 2, border_radius=8)
        cxm, cym = self.btn_ff.centerx, self.btn_ff.centery
        col2 = (240, 255, 240) if ff_on else (200, 210, 200)
        for off in (-8, 4):
            pygame.draw.polygon(self.screen, col2, [
                (cxm + off - 6, cym - 11), (cxm + off + 8, cym), (cxm + off - 6, cym + 11)])
        # pause (two bars)
        p_hover = self.btn_pause.collidepoint(mx, my)
        pcol = (110, 120, 110) if p_hover else (55, 80, 55)
        pygame.draw.rect(self.screen, pcol, self.btn_pause, border_radius=8)
        pygame.draw.rect(self.screen, (20, 30, 20), self.btn_pause, 2, border_radius=8)
        px, py = self.btn_pause.centerx, self.btn_pause.centery
        pygame.draw.rect(self.screen, (220, 230, 220), (px - 9, py - 11, 6, 22), border_radius=2)
        pygame.draw.rect(self.screen, (220, 230, 220), (px + 3, py - 11, 6, 22), border_radius=2)

    def _wave_progress(self):
        """0..1 fraction of the current wave cycle, for the progress bar."""
        w = self.wave
        total = w.wave_count
        if total <= 0:
            return 0.0
        if w.wave_active and len(w.zombies_to_spawn) > 0:
            not_spawned = len(w.zombies_to_spawn) - w.zombies_spawned
            alive_spawned = max(0, w.wave_zombies_remaining - not_spawned)
            killed = w.zombies_spawned - alive_spawned
            frac = killed / len(w.zombies_to_spawn)
            return min(1.0, (w.wave_index - 1 + frac) / total)
        return min(1.0, w.wave_index / total)

    def _draw_progress_bar(self):
        """PvZ-style wave progress bar with flag markers, bottom-right."""
        if self.mode is None or self.wave.wave_count <= 0:
            return
        bw, bh = 240, 12
        x = SCREEN_WIDTH - bw - 26
        y = SCREEN_HEIGHT - bh - 14
        pygame.draw.rect(self.screen, (30, 25, 15), (x - 3, y - 3, bw + 6, bh + 6), border_radius=7)
        pygame.draw.rect(self.screen, (66, 56, 34), (x, y, bw, bh), border_radius=5)
        frac = self._wave_progress()
        fill_w = int(bw * frac)
        if fill_w > 0:
            pygame.draw.rect(self.screen, (128, 205, 70), (x, y, fill_w, bh), border_radius=5)
        # flags on huge waves + the final wave
        total = self.wave.wave_count
        for i in range(1, total + 1):
            if (i % 5 == 0 and i > 5) or i == total:
                fx_pos = x + int(bw * (i - 1) / total)
                big = i == total
                fh = 14 if big else 10
                pygame.draw.line(self.screen, (150, 105, 55),
                                 (fx_pos, y - fh), (fx_pos, y + bh), 2)
                pygame.draw.polygon(self.screen, (215, 40, 40), [
                    (fx_pos, y - fh), (fx_pos + (9 if big else 6), y - fh + 3),
                    (fx_pos, y - fh + 6)])

    def _get_scratch(self, w, h):
        """Return a reusable SRCALPHA surface of the given size, cleared to transparent."""
        key = (w, h)
        s = self._scratch_cache.get(key)
        if s is None:
            s = pygame.Surface((w, h), pygame.SRCALPHA)
            self._scratch_cache[key] = s
        else:
            s.fill((0, 0, 0, 0))
        return s

    def _draw_ghost_cursor(self):
        """Seed packet / shovel sprite glued to the cursor while a tool is held."""
        selected = next((b for b in self.seed_buttons if b.selected), None)
        plant_type = None
        icon_key = None
        if selected is not None:
            plant_type = selected.plant_type
            icon_key = f"ghost_{plant_type}"
        elif self.shovel and self.shovel.selected:
            icon_key = "ui_shovel"
        if icon_key is None:
            return
        img = self._ghost_cache.get(icon_key)
        if img is None:
            if plant_type is not None:
                # Clean sprite art: the wiki icons are photos of the plant on a
                # grass backdrop and blitted as an opaque box that swallowed a
                # sun sitting under the cursor.
                base = assets_loader.cursor_icon(plant_type, 56)
            else:
                base = assets_loader.scale("ui_shovel", 56, 56)
            if base is None:
                return
            w, h = base.get_size()
            img = pygame.Surface((w, h), pygame.SRCALPHA)
            img.lock()
            for y in range(h):
                for x in range(w):
                    p = base.get_at((x, y))
                    if plant_type is None and p.a > 240 and p.r > 240 \
                            and p.g > 240 and p.b > 240:
                        # shovel sprite keeps an opaque white matte
                        img.set_at((x, y), (255, 255, 255, 0))
                    else:
                        img.set_at((x, y), (p.r, p.g, p.b, int(p.a * 0.52)))
            img.unlock()
            self._ghost_cache[icon_key] = img
        self.screen.blit(img, img.get_rect(center=(self.mouse_x, self.mouse_y + 6)))

    def draw_state(self):
        if self.state == STATE_MENU:
            self.menu.draw(self.screen,
                           muted=bool(self.save.settings.get("mute")))
        elif self.state == STATE_MODE_SELECT:
            self.mode_select.draw(self.screen)
        elif self.state == STATE_LEVEL_SELECT:
            self.level_select.draw(self.screen)
        elif self.state == STATE_SEED_SELECT:
            self.seed_select.draw(self.screen)
        elif self.state == STATE_PAUSED:
            self.pause_screen.draw(self.screen)
        elif self.state == STATE_GAME_OVER:
            self.game_over.draw(self.screen, self.wave.wave_index,
                                survival=self.mode == MODE_SURVIVAL)
        elif self.state == STATE_LEVEL_COMPLETE:
            self.level_complete.draw(self.screen)
        elif self.state == STATE_SURVIVAL_COMPLETE:
            self.survival_complete.draw(self.screen, self.survival_waves)
