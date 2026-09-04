"""Main game loop and state manager. Supports Adventure and Survival modes."""

import math
import pygame
import random
from constants import *
from entities import *
from grid import Grid
from wave import WaveSystem
from ui import *
from fx import FloatingText, WaveWarning, Explosion, cached_text
import assets_loader
assets_loader.init()
from levels import *
from levels import ADVENTURE_LEVELS, SURVIVAL_MODES
import save as save_mod
from save import derive_unlocked
import audio as audio_mod
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
        self.last_wave_announced = -1  # which wave index we already announced
        self.plant_poof = []       # soil poof circles when planting
        self.plant_debris = []     # leaf/petal particles when a plant is eaten
        self.pea_impact = []       # spark/pea-shard burst on projectile impact
        self.balloon_pop = []      # red rubber shreds when a Balloon pops
        self.mow_dust = []         # grey dust puffs trailing the lawnmower
        self.zombie_heads = []     # head/limb sprites flying off on zombie death
        self.food_rings = []       # plant-food release ring radiating outward
        self.boss_aura = []        # boss summon aura + death shockwave
        self.grass_prints = []     # brown footprint ellipses when a zombie steps
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
        self._cursor_hidden = False
        self._ghost_cache = {}
        # Reusable translucent layers (avoid allocating full-screen surfaces every frame)
        self._seed_bar_surface = pygame.Surface((SCREEN_WIDTH, UI_BAR_H), pygame.SRCALPHA)
        self._seed_bar_surface.fill((70, 50, 30, 230))
        self._fog_veil = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
        self._fog_veil.fill((180, 190, 200, 60))
        # placement-preview tint overlays (green ok / red blocked)
        self._preview_ok = pygame.Surface((CELL_W, CELL_H), pygame.SRCALPHA)
        self._preview_ok.fill((70, 220, 90, 70))
        self._preview_bad = pygame.Surface((CELL_W, CELL_H), pygame.SRCALPHA)
        self._preview_bad.fill((230, 60, 60, 80))
        self._flash_surface = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
        self._flash_surface.fill((255, 245, 220))
        # static background layers built per level (pool water / roof tiles)
        self._water_layer = None
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
        self._roof_layer = None

        if bg_type == BG_POOL:
            # Pre-render the water lanes once (animated per-frame line drawing
            # used to cost ~60 draw calls every frame).
            self._water_layer = pygame.Surface((GRID_W, GRID_H), pygame.SRCALPHA)
            for row in POOL_WATER_ROWS:
                y = row * CELL_H
                water = pygame.Rect(0, y, GRID_W, CELL_H)
                pygame.draw.rect(self._water_layer, (48, 130, 190), water)
                for line_y in range(y + 12, y + CELL_H, 22):
                    pygame.draw.line(self._water_layer, (110, 195, 225),
                                     (4, line_y), (GRID_W - 4, line_y), 2)
                pygame.draw.rect(self._water_layer, (25, 92, 145), water, 3)

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
            self._roof_layer = layer
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

    def _open_adventure_map(self):
        """Refresh the adventure map with the current unlock state."""
        self.unlocked_levels = derive_unlocked(self.completed_levels)
        self.level_select.set_items(ADVENTURE_LEVELS, tr("Adventure Mode"),
                                    unlocked_ids=self.unlocked_levels)
        self.state = STATE_LEVEL_SELECT

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
        self.speed_mult = 1.0
        self._press = None
        self.plant_foods = []
        self.plant_food = 0
        self.food_timer = random.uniform(11.0, 18.0)
        self.food_rings = []
        self.boss_aura = []
        self.grass_prints = []
        self.coin_drops = []

        # reset game state
        self.grid = Grid()
        self.plants = []
        self.zombies = []
        self.projectiles = []
        self.suns = []
        self.lawnmowers = []
        self.sun_value = level["start_sun"]
        self.house_hp = HOUSE_HP
        self.plant_cooldowns = {}
        self.sun_spawn_timer = 0.0

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
        self.speed_mult = 1.0
        self._press = None
        self.plant_foods = []
        self.plant_food = 0
        self.food_timer = random.uniform(11.0, 18.0)
        self.food_rings = []
        self.boss_aura = []
        self.grass_prints = []
        self.coin_drops = []

        # reset game state
        self.grid = Grid()
        self.plants = []
        self.zombies = []
        self.projectiles = []
        self.suns = []
        self.lawnmowers = []
        self.sun_value = 150
        self.house_hp = HOUSE_HP
        self.plant_cooldowns = {}
        self.sun_spawn_timer = 0.0

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
                if not sun.collected and sun.rect().collidepoint(mx, my):
                    sun.collect((SUN_JAR_X + SUN_JAR_W // 2, SUN_JAR_Y + SUN_JAR_W // 2))
                    self._spawn_collect_text(int(sun.x), int(sun.y) - 8, sun.amount)
                    self._play_sound(SOUND_SUN_COLLECT, 0.5)
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
            if cell:
                cob = self._first_cob_cannon()
                if cob is not None and cob.ready:
                    proj = cob.fire_at(int(mx), int(my))
                    if proj is not None:
                        self.projectiles.append(proj)
                        self._play_sound("cannon", 0.6)
                        self._spawn_collect_text(int(mx), int(my) - 16,
                                                 "FIRE!", color=(255, 80, 60),
                                                 size=18, vy=-50, lifetime=0.8)
                        return  # don't fall through to plant on this click

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
            self.plant_poof.append({"x": cx, "y": cy, "age": 0, "max": 0.3})
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
        self.plant_poof.append({"x": cx, "y": cy, "age": 0, "max": 0.3})
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
        self.plant_poof.append({"x": cx, "y": cy, "age": 0, "max": 0.25})
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
        self.plant_poof.append({"x": p.x + p.w // 2, "y": p.y + p.h // 2,
                                "age": 0, "max": 0.35})
        # PvZ2-style plant food release: 2 expanding green rings radiating outward
        for k in range(2):
            self.food_rings.append({
                "x": p.x + p.w // 2, "y": p.y + p.h // 2,
                "age": -k * 0.10,            # staggered start
                "max": 0.55,                 # 0.55s lifetime
                "r0": 18, "r1": 110,         # expands from 18px to 110px
                "color": (130, 255, 160),    # mint-green glow
            })
        if p.plant_type == PLANT_PEASHOOTER:
            p.food_boost = FOOD_BOOST_SHOOT_S  # machine-gun peas
        elif p.plant_type == PLANT_SUNFLOWER:
            for _ in range(FOOD_SUN_BURST):
                sun = Sun(p.x + random.randint(-20, 70), p.y - 20)
                sun.amount = 25
                sun.target_y = p.y + random.randint(-8, 24)
                sun.falling = True
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

    def _topbar_click(self, mx, my):
        """Handle the quick pause / fast-forward buttons in the top bar."""
        if self.btn_pause.collidepoint(mx, my):
            self.state = STATE_PAUSED
            self._press = None
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
        else:
            # On a boss wave, free-spawned minions may remain after the boss dies.
            # Keep the level in a cleared-final-wave state until every enemy is gone.
            if any(z.alive and z.hp > 0 for z in self.zombies):
                self.wave.wave_active = False
                self.wave.between_waves = False
                self.wave.wave_cleared = True
            else:
                self._complete_adventure()

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
        """Burst 8 small petal/leaf particles when a plant is eaten.
        Each debris is [x, y, vx, vy, color, age, lifetime]."""
        # Tint palette per plant type — keeps the burst on-theme
        from constants import (PLANT_PEASHOOTER, PLANT_SUNFLOWER,
                               PLANT_WALLNUT, PLANT_CHERRYBOMB,
                               PLANT_FUMESHROOM, PLANT_LILYPAD)
        palette = {
            PLANT_PEASHOOTER:   [(60, 170, 70), (110, 200, 90), (40, 130, 50)],
            PLANT_SUNFLOWER:    [(255, 215, 60), (255, 245, 160), (220, 150, 30)],
            PLANT_WALLNUT:      [(170, 130, 70), (130, 95, 50), (90, 60, 30)],
            PLANT_CHERRYBOMB:   [(220, 30, 30), (255, 100, 80), (160, 20, 20)],
            PLANT_FUMESHROOM:   [(160, 60, 200), (200, 120, 255), (100, 30, 150)],
            PLANT_LILYPAD:      [(60, 170, 70), (110, 200, 90), (40, 130, 50)],
        }.get(plant.plant_type, [(255, 255, 255)])
        cx = int(plant.x + plant.w // 2)
        cy = int(plant.y + plant.h // 2)
        import random as _r
        for _ in range(8):
            ang = _r.uniform(-math.pi * 0.85, -math.pi * 0.15)  # upward fan
            spd = _r.uniform(110, 230)
            self.plant_debris.append([
                float(cx), float(cy),
                math.cos(ang) * spd,
                math.sin(ang) * spd,
                _r.choice(palette),
                0.0,
                _r.uniform(0.55, 0.85),
            ])

    def _spawn_pea_impact(self, x, y, is_fume=False, is_frost=False):
        """Spark burst when a pea/fume/frost projectile hits a zombie.
        Each entry is [x, y, vx, vy, color, age, lifetime]."""
        # Fume = purple shards, pea = green shards, frost = cyan shards.
        import random as _r
        if is_fume:
            shard_colors = [(180, 0, 255), (215, 140, 255)]
        elif is_frost:
            shard_colors = [(140, 220, 255), (220, 245, 255), (90, 180, 230)]
        else:
            shard_colors = [(115, 215, 35), (255, 235, 60)]
        # 4 colored shards (fast, decay quickly)
        for _ in range(4):
            ang = _r.uniform(0, math.tau)
            spd = _r.uniform(90, 200)
            self.pea_impact.append([
                float(x), float(y),
                math.cos(ang) * spd, math.sin(ang) * spd,
                _r.choice(shard_colors),
                0.0, 0.22,
            ])
        # 1 white center spark that stays bigger but fades
        center_color = (240, 250, 255) if is_frost else (255, 255, 240)
        self.pea_impact.append([
            float(x), float(y), 0.0, 0.0,
            center_color,
            0.0, 0.18,
        ])

    def _spawn_balloon_pop(self, zombie):
        """Spawn red balloon-shard burst when a Balloon Zombie pops.
        Each entry is [x, y, vx, vy, color, age, lifetime]."""
        import random as _r
        # Position the burst where the balloon was — slightly above the head.
        cx = int(zombie.x + zombie.w // 2)
        cy = int(zombie.y - 24)
        palette = [(220, 50, 50), (255, 110, 80), (180, 30, 30), (255, 200, 200)]
        # 8 red rubber shreds flying out in every direction
        for _ in range(8):
            ang = _r.uniform(0, math.tau)
            spd = _r.uniform(140, 280)
            self.balloon_pop.append([
                float(cx), float(cy),
                math.cos(ang) * spd, math.sin(ang) * spd,
                _r.choice(palette),
                0.0,
                _r.uniform(0.45, 0.7),
            ])
        # 1 white center flash that stays a touch longer than the shards
        self.balloon_pop.append([
            float(cx), float(cy), 0.0, 0.0,
            (255, 255, 240),
            0.0, 0.35,
        ])

    def _spawn_mow_dust(self, mower, big=False):
        """Emit a small puff of grey dust trailing the lawnmower.
        Each entry is [x, y, vx, vy, color, age, lifetime]."""
        import random as _r
        # Dust puffs out behind the mower (its left side, since it travels
        # rightward) and slightly up so it hangs in the air.
        cx = int(mower.x - 4)
        cy = int(mower.y + _r.randint(8, mower.h - 6))
        n = 4 if big else 2
        for _ in range(n):
            ang = _r.uniform(math.pi * 0.8, math.pi * 1.4)  # left + upward fan
            spd = _r.uniform(35, 95)
            self.mow_dust.append([
                float(cx + _r.randint(-6, 6)),
                float(cy + _r.randint(-4, 4)),
                math.cos(ang) * spd,
                math.sin(ang) * spd,
                (200, 195, 185),
                0.0,
                _r.uniform(0.5, 0.9),
            ])

    def _spawn_minion_landing(self, zombie):
        """Visual a boss-summoned minion landing on the lawn.
        Emits:
        - 1 expanding white→yellow ring (the impact wave)
        - 5 brown dust puffs radiating outward
        - small screen shake
        """
        cx = int(zombie.x + zombie.w // 2)
        cy = int(zombie.y + zombie.h - 8)
        # 1) expanding ring — uses the existing boss_aura system (sparks=False)
        self.boss_aura.append({
            "x": cx, "y": cy, "age": 0, "max": 0.45,
            "r0": 12, "r1": 70,
            "color": (255, 230, 120),    # warm yellow shockwave
            "phase": "minion_land",
        })
        # 2) dust puffs — reuse mow_dust style
        import random as _r
        import math as _m
        for _ in range(5):
            ang = _r.uniform(_m.pi * 0.8, _m.pi * 1.4)
            spd = _r.uniform(45, 110)
            self.mow_dust.append([
                float(cx + _r.randint(-6, 6)),
                float(cy + _r.randint(-4, 4)),
                _m.cos(ang) * spd,
                _m.sin(ang) * spd,
                (175, 145, 90),    # brown dust tint
                0.0,
                _r.uniform(0.5, 0.8),
            ])
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
        """Spawn 1-2 'limb' sprites flying off when a zombie dies.
        Each entry is [x, y, vx, vy, color, age, lifetime]."""
        import random as _r
        # Conehead / Buckethead / Flag drop a tiny piece of equipment;
        # basic / newspaper drop their signature item (cone/bucket/flag/paper).
        from constants import (ZOMBIE_BASIC, ZOMBIE_CONEHEAD,
                               ZOMBIE_BUCKETHEAD, ZOMBIE_FLAG,
                               ZOMBIE_NEWSPAPER)
        palette = {
            ZOMBIE_CONEHEAD:   (230, 112, 28),    # orange cone
            ZOMBIE_BUCKETHEAD: (160, 168, 175),   # metal bucket
            ZOMBIE_FLAG:       (210, 35, 35),     # red flag
            ZOMBIE_NEWSPAPER:  (235, 232, 220),   # off-white news
        }
        chunk_color = palette.get(zombie.zombie_type, (90, 90, 95))
        # Conehead/Buckethead/Flag/Newspaper drop 3 chunks (visible equipment);
        # basic zombies only get 1 chunk (a shoulder knob — keeps the list small).
        n_chunks = 3 if zombie.zombie_type in palette else 1
        cx = int(zombie.x + zombie.w // 2)
        cy = int(zombie.y + 16)
        for _ in range(n_chunks):
            ang = _r.uniform(-math.pi * 0.85, -math.pi * 0.15)
            spd = _r.uniform(80, 200)
            self.zombie_heads.append([
                float(cx + _r.randint(-20, 20)),
                float(cy + _r.randint(-10, 10)),
                math.cos(ang) * spd * 0.4,
                math.sin(ang) * spd,
                chunk_color,
                0.0,
                _r.uniform(0.7, 1.0),
            ])

    def _spawn_grass_print(self, zombie):
        """Drop a faint brown footprint ellipse below the zombie's feet.
        Each entry: {"x","y","age","max","w","h"} — no physics, just fade.
        """
        self.grass_prints.append({
            "x": int(zombie.x + zombie.w // 2 + random.randint(-3, 3)),
            "y": int(zombie.y + zombie.h - 6),
            "age": 0.0,
            "max": 1.4,            # 1.4s lifetime — short, just a step hint
            "w": 14,
            "h": 4,
        })

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
        """Emit a halo + sparks at the boss when it summons a minion (kind='summon')
        or when the boss itself dies (kind='death'). Each entry:
            {"x", "y", "age", "max", "r0", "r1", "color", "phase", "sparks": [...]}
        Sparks are baked at spawn time so we don't have to live-track boss pos.
        """
        import random as _r
        cx = int(boss.x + boss.w // 2)
        cy = int(boss.y + 18)
        if kind == "summon":
            # Magenta summon halo + 3 upward sparks (signals a minion is coming)
            self.boss_aura.append({
                "x": cx, "y": cy, "age": 0, "max": 0.55,
                "r0": 16, "r1": 80,
                "color": (200, 80, 230),    # magenta-purple
                "phase": "summon",
            })
            for _ in range(3):
                ang = _r.uniform(-math.pi * 0.85, -math.pi * 0.15)
                spd = _r.uniform(60, 110)
                self.boss_aura.append({
                    "spark": True,
                    "x": float(cx + _r.randint(-10, 10)),
                    "y": float(cy + _r.randint(-6, 6)),
                    "vx": math.cos(ang) * spd * 0.4,
                    "vy": math.sin(ang) * spd - 30,
                    "color": (220, 130, 255),
                    "age": 0.0,
                    "max": _r.uniform(0.5, 0.8),
                })
        elif kind == "death":
            # Two big concentric shockwaves, white→magenta, staggered
            for i, (delay, r0, r1, color) in enumerate([
                (0.00, 24, 220, (255, 255, 255)),  # bright white
                (0.10, 24, 200, (220, 80, 240)),   # magenta core
            ]):
                self.boss_aura.append({
                    "x": cx, "y": cy,
                    "age": -delay, "max": 0.9,
                    "r0": r0, "r1": r1,
                    "color": color,
                    "phase": "death",
                })
            # Burst of 12 white/magenta sparks radiating outward in a full circle
            for _ in range(12):
                ang = _r.uniform(0, math.tau)
                spd = _r.uniform(140, 240)
                is_mag = _r.random() < 0.5
                self.boss_aura.append({
                    "spark": True,
                    "x": float(cx + _r.randint(-12, 12)),
                    "y": float(cy + _r.randint(-8, 8)),
                    "vx": math.cos(ang) * spd,
                    "vy": math.sin(ang) * spd - 30,
                    "color": (255, 200, 255) if is_mag else (240, 240, 255),
                    "age": 0.0,
                    "max": _r.uniform(0.7, 1.0),
                })

    def _announce_wave(self, wave_idx):
        if wave_idx == self.wave.wave_count:
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
            row = random.randint(0, GRID_ROWS - 1)
            z = create_zombie(GRID_X + col * CELL_W + (CELL_W - 90) // 2,
                              -250, row, ZOMBIE_BUNGEE)
            z.grid_y = self.grid.y
            z.in_wave = False  # extra ambush — must not clear the wave early
            self.zombies.append(z)

    def announce_cherry_explosion(self, x, y, zombies_killed):
        """Big floating text for cherry bomb kills."""
        if zombies_killed > 0:
            txt = f"BOOM! -{zombies_killed}" if zombies_killed > 1 else "BOOM!"
            color = COLOR_RED
        else:
            txt = "*fizzle*"
            color = (180, 180, 180)
        self.floating_texts.append(FloatingText(x, y, txt, color=color, size=28, vy=-80, lifetime=1.4))

    def update(self, dt):
        if self.state != STATE_PLAYING:
            return

        # Fast-forward scales the whole simulation uniformly.
        dt *= self.speed_mult
        # Wave-start cinematic: visual overlay (vignette + red wash) drawn below
        # signals the "time freeze" feel. We deliberately do NOT slow dt here,
        # because gameplay-critical timers (bungee descent, cherry fuse, plant
        # food) need real-time progression to keep their mechanics intact.

        # decay feel timers
        self.shake = max(0.0, self.shake - 26.0 * dt)
        self.sun_pulse = max(0.0, self.sun_pulse - 2.2 * dt)
        self.flash_timer = max(0.0, self.flash_timer - dt)

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
                    sun.target_y = target_y
                    self.suns.append(sun)

        # update suns — collected ones fly into the jar and credit on arrival
        for sun in self.suns[:]:
            was_falling = sun.falling
            sun.update(dt)
            if was_falling and not sun.falling and not sun.collected:
                self._play_sound("sun_land", 0.25)
            if getattr(sun, "arrived", False):
                sun.arrived = False
                self.sun_value += sun.amount
                self.sun_pulse = 1.0
            if not sun.alive:
                self.suns.remove(sun)

        # plant food (能量豆) sky drops — day and night alike
        self.food_timer -= dt
        if self.food_timer <= 0:
            self.food_timer = random.uniform(*PLANT_FOOD_INTERVAL) / 1000.0
            if len(self.plant_foods) < 2:
                pf = PlantFood(random.randint(GRID_X + 40, GRID_X + GRID_W - 40),
                               SUN_FALL_Y)
                pf.target_y = random.randint(self.grid.y + 40, self.grid.y + GRID_H - 60)
                self.plant_foods.append(pf)
        for pf in self.plant_foods[:]:
            pf.update(dt)
            if pf.arrived and not pf.alive:
                # Vial just landed in the jar — credit the player.
                if self.plant_food < PLANT_FOOD_MAX:
                    self.plant_food += 1
                pf.arrived = False   # one-shot
            if not pf.alive:
                self.plant_foods.remove(pf)

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
        for proj in self.projectiles[:]:
            proj.update(dt)
            if isinstance(proj, KernelBomb):
                # Cob Cannon: detonates at target — explodes on landing
                if not proj.alive:
                    self._detonate_kernel(proj)
                    self.projectiles.remove(proj)
                continue
            if not proj.alive:
                self.projectiles.remove(proj)
                continue
            for z in self.zombies:
                if (not z.alive or z.hp <= 0 or z.dying_timer > 0
                        or z.row != proj.row):
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
                    self.projectiles.remove(proj)
                    break

        # update zombies (bosses may spawn minions → collected here)
        new_zombies = []
        for z in self.zombies[:]:
            r = z.update(dt, self.plants)
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
        for z in self.zombies[:]:
            if not z.alive:
                self.zombies.remove(z)
                if not z.death_counted:
                    z.death_counted = True
                    if z.is_boss:
                        self.add_shake(10)
                        self.flash_timer = 0.1
                        self._spawn_boss_aura(z, kind="death")
                    if z.in_wave:
                        self.wave.zombie_died()
                    self.sun_value += z.reward
                    self._spawn_collect_text(z.x + z.w // 2, z.y - 6, z.reward)
                    self._play_sound(SOUND_ZOMBIE_DIE, 0.5)
                    # Emit head/equipment chunks NOW (just before removing from
                    # the list) so we don't lose the spawn to a later compact.
                    self._spawn_zombie_head(z)
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

        # update fog
        for f in self.fog_layers[:]:
            f.update(dt)
            if not f.alive:
                self.fog_layers.remove(f)
                # respawn fog
                self.fog_layers.append(FogLayer(f.row, SCREEN_WIDTH))

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
        for ft in self.floating_texts[:]:
            ft.update(dt)
            if not ft.alive:
                self.floating_texts.remove(ft)
        for ex in self.explosions[:]:
            ex.update(dt)
            if not ex.alive:
                self.explosions.remove(ex)
        for p in self.plant_poof[:]:
            p["age"] += dt
            if p["age"] >= p["max"]:
                self.plant_poof.remove(p)
        # Update debris physics + cull. Each debris is [x, y, vx, vy, color, age, lifetime].
        for d in self.plant_debris[:]:
            d[0] += d[2] * dt
            d[1] += d[3] * dt
            d[3] += 320 * dt   # gravity (light)
            d[5] += dt
            if d[5] >= d[6]:
                self.plant_debris.remove(d)
        # Update pea-impact sparks: fast moving shards that decay quickly
        for d in self.pea_impact[:]:
            d[0] += d[2] * dt
            d[1] += d[3] * dt
            # drag
            d[2] *= (1.0 - 2.5 * dt)
            d[3] *= (1.0 - 2.5 * dt)
            d[5] += dt
            if d[5] >= d[6]:
                self.pea_impact.remove(d)
        # Update zombie head/limb chunks: gravity-driven, ~1s lifetime
        for d in self.zombie_heads[:]:
            d[0] += d[2] * dt
            d[1] += d[3] * dt
            d[3] += 480 * dt   # heavier gravity than plant debris
            d[5] += dt
            if d[5] >= d[6]:
                self.zombie_heads.remove(d)
        # Update balloon-pop shreds: short-lived, light gravity
        for d in self.balloon_pop[:]:
            d[0] += d[2] * dt
            d[1] += d[3] * dt
            d[3] += 200 * dt   # lighter than zombie heads
            d[2] *= (1.0 - 1.8 * dt)
            d[5] += dt
            if d[5] >= d[6]:
                self.balloon_pop.remove(d)
        # Mow dust: short, fades quickly
        for d in self.mow_dust[:]:
            d[0] += d[2] * dt
            d[1] += d[3] * dt
            d[2] *= (1.0 - 1.5 * dt)
            d[3] *= (1.0 - 1.5 * dt)
            d[5] += dt
            if d[5] >= d[6]:
                self.mow_dust.remove(d)
        # Plant food rings: just advance age; the draw side handles expansion
        for r in self.food_rings[:]:
            r["age"] += dt
            if r["age"] >= r["max"]:
                self.food_rings.remove(r)
        # Boss aura: rings advance age only; sparks have physics (gravity + drag)
        for a in self.boss_aura[:]:
            if a.get("spark"):
                a["x"] += a["vx"] * dt
                a["y"] += a["vy"] * dt
                a["vy"] += 260 * dt    # gravity
                a["vx"] *= (1.0 - 1.5 * dt)
                a["vy"] *= (1.0 - 1.5 * dt)
            a["age"] += dt
            if a["age"] >= a["max"]:
                self.boss_aura.remove(a)
        # Grass prints: just age and fade.
        for gp in self.grass_prints[:]:
            gp["age"] += dt
            if gp["age"] >= gp["max"]:
                self.grass_prints.remove(gp)
        # Coin drops: physics — gravity + slight drag, spin during flight
        for c in self.coin_drops[:]:
            c["age"] += dt
            if c["age"] < 0:
                continue  # waiting for staggered start
            c["x"] += c["vx"] * dt
            c["y"] += c["vy"] * dt
            c["vy"] += 540 * dt       # gravity, slightly heavier than debris
            c["vx"] *= (1.0 - 0.8 * dt)
            c["rot"] += 6.0 * dt      # spin while in flight
            if c["age"] >= c["max"]:
                self.coin_drops.remove(c)
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
                       shovel_active=bool(self.shovel and self.shovel.selected))
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

        # draw grass prints (under zombies — a foot step is below the body)
        for gp in self.grass_prints:
            t = gp["age"] / gp["max"]
            # fade in fast (0..0.15), fade out slow (0.15..1.0)
            if t < 0.15:
                alpha = int(80 * (t / 0.15))
            else:
                alpha = int(80 * (1.0 - (t - 0.15) / 0.85))
            if alpha <= 0:
                continue
            s = pygame.Surface((gp["w"] * 2, gp["h"] * 2), pygame.SRCALPHA)
            # darker rim + filled center for "pressed grass" look
            pygame.draw.ellipse(s, (60, 80, 40, alpha),
                                (0, 0, gp["w"] * 2, gp["h"] * 2))
            pygame.draw.ellipse(s, (40, 60, 25, int(alpha * 0.7)),
                                (0, 0, gp["w"] * 2, gp["h"] * 2), 1)
            self.screen.blit(s, (gp["x"] - gp["w"], gp["y"] - gp["h"]))

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
            coin = pygame.Surface((r * 2 + 2, r * 2 + 2), pygame.SRCALPHA)
            # face (warm gold)
            pygame.draw.circle(coin, (255, 215, 60, alpha), (r + 1, r + 1), r)
            # inner highlight
            pygame.draw.circle(coin, (255, 240, 150, int(alpha * 0.8)),
                               (r + 1 - 2, r + 1 - 2), max(2, r // 2))
            # dark rim
            pygame.draw.circle(coin, (180, 130, 30, alpha), (r + 1, r + 1), r, 2)
            # "$" mark on the face — small dark ellipse rotated
            mark = pygame.Surface((r, r), pygame.SRCALPHA)
            pygame.draw.ellipse(mark, (130, 95, 25, int(alpha * 0.9)),
                                (r // 3, 1, r // 3, r - 2))
            mark = pygame.transform.rotate(mark, math.degrees(c["rot"]))
            coin.blit(mark, ((r * 2 + 2 - mark.get_width()) // 2,
                             (r * 2 + 2 - mark.get_height()) // 2))
            self.screen.blit(coin, (cx - r - 1, cy - r - 1))

        # explosions (cherry bombs / boss deaths)
        for ex in self.explosions:
            ex.draw(self.screen)

        # draw plant_poof (soil dust kicked up at planting/digging time)
        # Original PvZ: a brown ground puff + 3-4 small soil specks arcing up.
        for p in self.plant_poof:
            t = p["age"] / p["max"]
            cx, cy = p["x"], p["y"]
            # (1) ground puff: brown ellipse expands & fades along the soil line
            r = int(18 + t * 26)
            alpha = int(200 * (1 - t))
            puff = pygame.Surface((r * 2, int(r * 0.55)), pygame.SRCALPHA)
            pygame.draw.ellipse(puff, (110, 80, 45, alpha), (0, 0, r * 2, int(r * 0.55)))
            # darker rim to read as "dirt"
            pygame.draw.ellipse(puff, (70, 50, 28, int(alpha * 0.6)), (0, 0, r * 2, int(r * 0.55)), 2)
            self.screen.blit(puff, (cx - r, cy - int(r * 0.18)))
            # (2) 4 small soil specks arcing upward, falling back under gravity
            for i in range(4):
                ang = (i / 4.0) * 6.2831853
                # pre-computed per-particle trajectory baked into the ring key
                seed = (i + 1) * 13
                sx0 = math.cos(ang) * 6
                sy0 = -abs(math.sin(ang)) * 14 - 4
                vx = sx0 * 2.4
                vy = -110 - seed % 30
                tt = min(1.0, t * 1.3)
                x = cx + vx * tt
                y = cy + vy * tt + 240 * tt * tt
                size = max(1, int(3 - i * 0.4))
                a = int(220 * (1 - t * 1.1))
                if a <= 0:
                    continue
                speck = pygame.Surface((size * 2, size * 2), pygame.SRCALPHA)
                pygame.draw.circle(speck, (95, 70, 38, a), (size, size), size)
                self.screen.blit(speck, (int(x) - size, int(y) - size))

        # draw plant_debris (leaf/petal burst on plant death)
        for d in self.plant_debris:
            t = d[5] / d[6]
            r = max(1, int(4 * (1 - t * 0.5)))
            alpha = int(255 * (1 - t))
            petal = pygame.Surface((r * 2 + 2, r * 2 + 2), pygame.SRCALPHA)
            pygame.draw.circle(petal, (*d[4], alpha), (r + 1, r + 1), r)
            self.screen.blit(petal, (int(d[0]) - r - 1, int(d[1]) - r - 1))

        # draw pea_impact sparks (hit feedback)
        for d in self.pea_impact:
            t = d[5] / d[6]
            r = max(1, int(3 * (1 - t * 0.4)))
            alpha = int(255 * (1 - t))
            spark = pygame.Surface((r * 2 + 2, r * 2 + 2), pygame.SRCALPHA)
            pygame.draw.circle(spark, (*d[4], alpha), (r + 1, r + 1), r)
            self.screen.blit(spark, (int(d[0]) - r - 1, int(d[1]) - r - 1))

        # draw zombie head/limb chunks flying off on death
        for d in self.zombie_heads:
            t = d[5] / d[6]
            r = max(2, int(5 * (1 - t * 0.3)))
            alpha = int(255 * (1 - t))
            chunk = pygame.Surface((r * 2 + 2, r * 2 + 2), pygame.SRCALPHA)
            pygame.draw.ellipse(chunk, (*d[4], alpha), (1, 1, r * 2, r * 2))
            self.screen.blit(chunk, (int(d[0]) - r - 1, int(d[1]) - r - 1))

        # draw balloon-pop shreds (red rubber flying outward)
        for d in self.balloon_pop:
            t = d[5] / d[6]
            r = max(2, int(6 * (1 - t * 0.4)))
            alpha = int(255 * (1 - t))
            shard = pygame.Surface((r * 2 + 2, r * 2 + 2), pygame.SRCALPHA)
            pygame.draw.circle(shard, (*d[4], alpha), (r + 1, r + 1), r)
            self.screen.blit(shard, (int(d[0]) - r - 1, int(d[1]) - r - 1))

        # draw lawnmower dust (soft grey puffs)
        for d in self.mow_dust:
            t = d[5] / d[6]
            r = max(3, int(7 * (1 - t * 0.4)))
            alpha = int(180 * (1 - t))
            puff = pygame.Surface((r * 2 + 2, r * 2 + 2), pygame.SRCALPHA)
            pygame.draw.circle(puff, (*d[4], alpha), (r + 1, r + 1), r)
            self.screen.blit(puff, (int(d[0]) - r - 1, int(d[1]) - r - 1))

        # draw plant food rings (green expanding rings — PvZ2 release effect)
        for ring in self.food_rings:
            if ring["age"] < 0:
                continue  # waiting for staggered start
            t = ring["age"] / ring["max"]
            # ease-out: fast expansion early, slow at the end
            ease = 1.0 - (1.0 - t) * (1.0 - t)
            radius = int(ring["r0"] + (ring["r1"] - ring["r0"]) * ease)
            alpha = int(220 * (1.0 - t))
            ring_surf = pygame.Surface((radius * 2, radius * 2), pygame.SRCALPHA)
            pygame.draw.circle(ring_surf, (*ring["color"], alpha),
                               (radius, radius), radius, 3)
            # soft inner halo
            inner = int(radius * 0.55)
            pygame.draw.circle(ring_surf, (*ring["color"], int(alpha * 0.25)),
                               (radius, radius), inner, 2)
            self.screen.blit(ring_surf,
                             (ring["x"] - radius, ring["y"] - radius))

        # draw boss aura (rings + sparks)
        # Rings first (under sparks), then sparks on top
        for a in self.boss_aura:
            if a.get("spark"):
                continue
            if a["age"] < 0:
                continue
            t = a["age"] / a["max"]
            ease = 1.0 - (1.0 - t) * (1.0 - t)
            radius = int(a["r0"] + (a["r1"] - a["r0"]) * ease)
            alpha = int(220 * (1.0 - t))
            if alpha <= 0 or radius <= 0:
                continue
            s = pygame.Surface((radius * 2, radius * 2), pygame.SRCALPHA)
            pygame.draw.circle(s, (*a["color"], alpha),
                               (radius, radius), radius, 4)
            # soft inner halo
            inner = max(2, int(radius * 0.45))
            pygame.draw.circle(s, (*a["color"], int(alpha * 0.30)),
                               (radius, radius), inner, 2)
            self.screen.blit(s, (a["x"] - radius, a["y"] - radius))
        for a in self.boss_aura:
            if not a.get("spark"):
                continue
            t = a["age"] / a["max"]
            r = max(1, int(4 * (1 - t * 0.4)))
            alpha = int(240 * (1 - t))
            if alpha <= 0:
                continue
            sp = pygame.Surface((r * 2 + 2, r * 2 + 2), pygame.SRCALPHA)
            pygame.draw.circle(sp, (*a["color"], alpha), (r + 1, r + 1), r)
            self.screen.blit(sp, (int(a["x"]) - r - 1, int(a["y"]) - r - 1))

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
            pygame.draw.rect(self.screen, (0, 0, 0, 180), bg, border_radius=6)
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
                self.screen.blit(self._water_layer, (self.grid.x, self.grid.y))
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
        icon_key = {
            PLANT_PEASHOOTER: "plant_peashooter", PLANT_SUNFLOWER: "plant_sunflower",
            PLANT_WALLNUT: "plant_wallnut", PLANT_CHERRYBOMB: "plant_cherrybomb",
            PLANT_FUMESHROOM: "plant_fumeshroom", PLANT_LILYPAD: "ui_lily_pad",
            PLANT_SNOWPEA: "plant_peashooter",
        }.get(selected)
        icon = assets_loader.scale(icon_key, 64, 64) if icon_key else None
        if icon is not None:
            # cached translucent copy (icon.copy() every frame adds up)
            ck = ("preview", icon_key, 150 if allowed else 85)
            ghost = self._ghost_cache.get(ck)
            if ghost is None:
                ghost = icon.copy()
                ghost.set_alpha(150 if allowed else 85)
                self._ghost_cache[ck] = ghost
            self.screen.blit(ghost, ghost.get_rect(center=rect.center))

    def _draw_wave_zoom_overlay(self):
        """Red-tinted radial vignette while _zoom_freeze > 0.
        Cheap approach: 4 dark corner gradients + faint red wash on top half.
        """
        sw, sh = SCREEN_WIDTH, SCREEN_HEIGHT
        # Four corner gradients — same surface rotated/blit for each corner.
        # Use a single dark corner gradient and blit it in 4 spots.
        corner = pygame.Surface((sw // 3, sh // 3), pygame.SRCALPHA)
        cx0, cy0 = corner.get_size()
        # Build gradient: alpha = 180 at the corner vertex, 0 along the opposite edges.
        for r in range(60):
            a = int(180 * (1.0 - r / 60))
            if a <= 0:
                continue
            pygame.draw.circle(corner, (0, 0, 0, a), (0, 0), 60 - r, 1)
        # Mirror/rotate to other corners
        self.screen.blit(corner, (0, 0))                                     # TL
        self.screen.blit(pygame.transform.flip(corner, True, False),          # TR
                         (sw - cx0, 0))
        self.screen.blit(pygame.transform.flip(corner, False, True),          # BL
                         (0, sh - cy0))
        self.screen.blit(pygame.transform.flip(corner, True, True),           # BR
                         (sw - cx0, sh - cy0))
        # Red flash wash (top half) — strong, signals alarm
        wash = pygame.Surface((sw, sh // 2), pygame.SRCALPHA)
        for y in range(sh // 2):
            a = int(60 * (1.0 - y / (sh // 2)))
            pygame.draw.line(wash, (180, 30, 30, a), (0, y), (sw, y), 1)
        self.screen.blit(wash, (0, 0))

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
        # speckled halo after matte removal.
        sun_jar_img = assets_loader.get("ui_sun")
        if sun_jar_img:
            jar = pygame.transform.smoothscale(sun_jar_img, (SUN_JAR_W, SUN_JAR_W))
            self.screen.blit(jar, (SUN_JAR_X, SUN_JAR_Y - 2))
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

    def _draw_ghost_cursor(self):
        """Seed packet / shovel sprite glued to the cursor while a tool is held."""
        selected = next((b for b in self.seed_buttons if b.selected), None)
        icon_key = None
        if selected is not None:
            icon_key = {
                PLANT_PEASHOOTER: "plant_peashooter", PLANT_SUNFLOWER: "plant_sunflower",
                PLANT_WALLNUT: "plant_wallnut", PLANT_CHERRYBOMB: "plant_cherrybomb",
                PLANT_FUMESHROOM: "plant_fumeshroom", PLANT_LILYPAD: "ui_lily_pad",
                PLANT_SNOWPEA: "plant_peashooter",
            }.get(selected.plant_type)
        elif self.shovel and self.shovel.selected:
            icon_key = "ui_shovel"
        if icon_key is None:
            return
        img = self._ghost_cache.get(icon_key)
        if img is None:
            base = assets_loader.scale(icon_key, 56, 56)
            if base is None:
                return
            # Drop any opaque white pixels left over from the source sprite's
            # matte; otherwise the ghost cursor leaves a white square behind.
            img = pygame.Surface((56, 56), pygame.SRCALPHA)
            img.lock()
            for y in range(56):
                for x in range(56):
                    p = base.get_at((x, y))
                    if p.a > 240 and p.r > 240 and p.g > 240 and p.b > 240:
                        img.set_at((x, y), (255, 255, 255, 0))
                    else:
                        img.set_at((x, y), (p.r, p.g, p.b, int(p.a * 0.69)))
            img.unlock()
            self._ghost_cache[icon_key] = img
        self.screen.blit(img, img.get_rect(center=(self.mouse_x, self.mouse_y + 6)))

    def draw_state(self):
        if self.state == STATE_MENU:
            self.menu.draw(self.screen)
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