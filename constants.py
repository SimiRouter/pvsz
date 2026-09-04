"""Game constants for Plants vs Zombies."""

# Screen — matches the 1400x600 PvZ lawn background image exactly.
SCREEN_WIDTH = 1400
SCREEN_HEIGHT = 600
FPS = 60

# Colors (RGB)
COLOR_GRASS = (34, 139, 34)
COLOR_GRASS_DARK = (28, 110, 28)
COLOR_DIRT = (139, 90, 43)
COLOR_Sky = (135, 206, 235)
COLOR_WHITE = (255, 255, 255)
COLOR_BLACK = (0, 0, 0)
COLOR_RED = (220, 20, 20)
COLOR_YELLOW = (255, 255, 0)
COLOR_ORANGE = (255, 165, 0)
COLOR_GREEN_DARK = (0, 100, 0)
COLOR_BROWN = (101, 67, 33)
COLOR_BAR_BG = (50, 50, 50)
COLOR_BAR_FILL = (0, 180, 0)

# Grid — matches PvZ lawn: 5 rows x 9 cols of 102x98 cells starting at (260, 80)
# (Background image is 1400x600; lawn spans roughly 260-1190 horizontally, 80-580 vertically)
GRID_ROWS = 5
GRID_COLS = 9
GRID_X = 260
GRID_Y = 80
CELL_W = 103
CELL_H = 98
GRID_W = GRID_COLS * CELL_W
GRID_H = GRID_ROWS * CELL_H

# UI Bar — top of screen, like original PvZ. Cards keep their native art ratio
# (49x69) so they are NOT squashed; bar height leaves room below for the lawn.
UI_BAR_Y = 0
UI_BAR_H = 76
SEED_BAR_X = 10
SEED_BAR_W = SCREEN_WIDTH - 20
# Sun jar (embedded in seed bar, left side)
SUN_JAR_X = SEED_BAR_X + 8
SUN_JAR_Y = UI_BAR_Y + 3
SUN_JAR_W = 48
SUN_JAR_H = 70
# Seed card layout — native PvZ card art is 49x69
SEED_CARD_W = 49
SEED_CARD_H = 69
SEED_CARD_GAP = 8
# Reserve room for both the 48px sun icon and a 62px numeric counter.
SEED_CARD_START_X = SUN_JAR_X + SUN_JAR_W + 70

# Game states
STATE_MENU = "menu"
STATE_MODE_SELECT = "mode_select"
STATE_LEVEL_SELECT = "level_select"
STATE_SEED_SELECT = "seed_select"
STATE_PLAYING = "playing"
STATE_PAUSED = "paused"
STATE_GAME_OVER = "game_over"
STATE_LEVEL_COMPLETE = "level_complete"
STATE_SURVIVAL_COMPLETE = "survival_complete"

# Background types
BG_DAY = "day"
BG_NIGHT = "night"
BG_POOL = "pool"
BG_FOG = "fog"
BG_ROOF = "roof"

# Game modes
MODE_ADVENTURE = "adventure"
MODE_SURVIVAL = "survival"

# Plant types
PLANT_PEASHOOTER = "peashooter"
PLANT_SUNFLOWER = "sunflower"
PLANT_WALLNUT = "wallnut"
PLANT_CHERRYBOMB = "cherrybomb"
PLANT_FUMESHROOM = "fumeshroom"
PLANT_LILYPAD = "lilypad"
PLANT_SNOWPEA = "snowpea"   # freezes zombies it hits
PLANT_COBCANNON = "cobcannon"  # tap-to-fire big kernel that arcs + explodes

PLANT_INFO = {
    PLANT_PEASHOOTER: {"cost": 100, "cooldown": 8, "name": "Peashooter", "hp": 300},
    PLANT_SUNFLOWER: {"cost": 50, "cooldown": 10, "name": "Sunflower", "hp": 300},
    PLANT_WALLNUT: {"cost": 50, "cooldown": 12, "name": "Wall-nut", "hp": 4000},
    PLANT_CHERRYBOMB: {"cost": 150, "cooldown": 20, "name": "Cherry Bomb", "hp": 100},
    PLANT_FUMESHROOM: {"cost": 75, "cooldown": 15, "name": "Fume-shroom", "hp": 300},
    PLANT_LILYPAD: {"cost": 25, "cooldown": 5, "name": "Lily Pad", "hp": 400},
    PLANT_SNOWPEA: {"cost": 175, "cooldown": 8, "name": "Snow Pea", "hp": 300},
    PLANT_COBCANNON: {"cost": 500, "cooldown": 30, "name": "Cob Cannon", "hp": 600},
}

# One-line seed-card descriptions (i18n keys; zh translations live in i18n.py)
PLANT_DESC = {
    PLANT_PEASHOOTER: "Shoots peas at zombies in its lane",
    PLANT_SUNFLOWER: "Produces extra sun for your defense",
    PLANT_WALLNUT: "A tough shell that blocks zombies",
    PLANT_CHERRYBOMB: "Explodes all zombies in a 3x3 area",
    PLANT_FUMESHROOM: "Sprays fumes that damage zombies",
    PLANT_LILYPAD: "Grows on water and carries one plant",
    PLANT_SNOWPEA: "Shoots icy peas that slow + freeze zombies",
    PLANT_COBCANNON: "Tap a zombie to launch a kernel — explodes on impact",
}

# Zombie types
ZOMBIE_BASIC = "basic"
ZOMBIE_CONEHEAD = "conehead"
ZOMBIE_FLAG = "flag"
ZOMBIE_BUCKETHEAD = "buckethead"
ZOMBIE_NEWSPAPER = "newspaper"
ZOMBIE_POLE = "pole"
ZOMBIE_BOSS = "boss"
ZOMBIE_BALLOON = "balloon"   # flies in over the lawn; 155 dmg pops the balloon
ZOMBIE_BUNGEE = "bungee"     # drops from the sky on a cord and steals a plant

ZOMBIE_INFO = {
    ZOMBIE_BASIC: {"hp": 200, "speed": 18, "reward": 5},       # dies to 10 pea shots (PvZ parity)
    ZOMBIE_CONEHEAD: {"hp": 400, "speed": 16, "reward": 10},   # ~20 shots
    ZOMBIE_FLAG: {"hp": 200, "speed": 22, "reward": 15},       # slightly faster
    ZOMBIE_BUCKETHEAD: {"hp": 800, "speed": 14, "reward": 20}, # ~40 shots, slow tank
    ZOMBIE_NEWSPAPER: {"hp": 230, "speed": 11, "reward": 10},  # enrages after losing the paper
    ZOMBIE_POLE: {"hp": 250, "speed": 26, "reward": 15},       # vaults over the first plant
    ZOMBIE_BOSS: {"hp": 2600, "speed": 11, "reward": 500},     # boss: summons minions
    # PvZ1 parity: 290 total, 155 pops the balloon (no Cactus/Blover here, so
    # every shooter can pop it — but it flies over plants and lawnmowers)
    ZOMBIE_BALLOON: {"hp": 290, "speed": 24, "reward": 15},
    ZOMBIE_BUNGEE: {"hp": 450, "speed": 0, "reward": 25},      # PvZ1: 450 HP plant thief
}

BALLOON_HP = 155      # damage needed to pop the balloon (PvZ1 parity)
BUNGEE_DESCEND_S = 2.8  # seconds from sky to lawn
BUNGEE_CLIMB_S = 2.4

# Survival (endless) scaling: zombies get faster and hit harder every wave.
SURVIVAL_SPEED_PER_WAVE = 0.03   # +3% speed per wave
SURVIVAL_SPEED_CAP = 2.0         # up to 2x speed
SURVIVAL_DMG_PER_WAVE = 0.06     # +6% bite damage per wave
SURVIVAL_DMG_CAP = 3.0           # up to 3x bite damage

# Plant upgrades: replant the same type onto the same plant to level it up.
PLANT_LEVEL_MAX = 3
# Per-level stat tables (index = level-1). Damage/sun/hp scale several times.
PLANT_LEVEL_STATS = {
    PLANT_PEASHOOTER: {"damage": (20, 40, 60)},
    PLANT_SUNFLOWER: {"sun": (25, 50, 75)},
    PLANT_WALLNUT: {"hp": (4000, 8000, 16000)},
    PLANT_CHERRYBOMB: {"damage": (1800, 3600, 5400), "radius": (1.5, 1.75, 2.0)},
    PLANT_FUMESHROOM: {"damage": (20, 40, 60)},
    PLANT_LILYPAD: {"hp": (400, 800, 1600)},
    PLANT_SNOWPEA: {"damage": (20, 40, 60)},
}

# Plant Food (能量豆, PvZ2 signature item): falls from the sky, click to store,
# then click a plant to unleash its super effect.
PLANT_FOOD_MAX = 3
PLANT_FOOD_INTERVAL = (20000, 32000)  # ms between sky drops (min, max)
PLANT_FOOD_LIFETIME = 14000  # ms a dropped vial stays on the lawn
FOOD_BOOST_SHOOT_S = 1.8     # peashooter machine-gun duration
FOOD_FUME_DAMAGE = 300       # fume-shroom row sweep
FOOD_SUN_BURST = 6           # sunflower sun pellets

# Sun
SUN_FALL_INTERVAL = 7000  # ms
SUN_FALL_COUNT = 3
SUN_LIFETIME = 14000  # ms — longer dwell so a busy moment never wastes sun
SUN_VALUE = 25
SUN_FALL_Y = -40
SUN_COLLECT_RADIUS = 24  # forgiving click radius (original PvZ is generous too)

# Wave config: (wave_num, zombie_count, zombie_types, delay_before)
WAVES = [
    (1, 3, [ZOMBIE_BASIC], 8000),
    (2, 5, [ZOMBIE_BASIC, ZOMBIE_BASIC], 6000),
    (3, 6, [ZOMBIE_BASIC, ZOMBIE_CONEHEAD], 5000),
    (4, 8, [ZOMBIE_BASIC, ZOMBIE_CONEHEAD, ZOMBIE_FLAG], 4500),
    (5, 10, [ZOMBIE_BASIC, ZOMBIE_CONEHEAD, ZOMBIE_BUCKETHEAD], 4000),
    (6, 12, [ZOMBIE_CONEHEAD, ZOMBIE_BUCKETHEAD, ZOMBIE_FLAG], 3500),
    (7, 15, [ZOMBIE_BUCKETHEAD, ZOMBIE_FLAG, ZOMBIE_CONEHEAD], 3000),
    (8, 18, [ZOMBIE_BUCKETHEAD, ZOMBIE_CONEHEAD, ZOMBIE_FLAG, ZOMBIE_BASIC], 2500),
    (9, 20, [ZOMBIE_BUCKETHEAD, ZOMBIE_FLAG, ZOMBIE_CONEHEAD, ZOMBIE_BASIC], 2000),
    (10, 25, [ZOMBIE_BUCKETHEAD, ZOMBIE_CONEHEAD, ZOMBIE_FLAG, ZOMBIE_BASIC], 1500),
]

# Difficulty scaling
WAVE_ZOMBIE_SPACING_BASE = 4000  # ms between zombies in a wave
WAVE_ZOMBIE_SPACING_MIN = 800

# Lawnmower (one per row, left edge of lawn — the last-resort mower)
LAWNMOWER_W = 42
LAWNMOWER_H = 50
LAWNMOWER_X = GRID_X - LAWNMOWER_W - 5
LAWNMOWER_SPEED = 520  # px/s when activated

# House — on the LEFT of the lawn in the PvZ layout (zombies walk right→left).
# When a zombie passes the mower slot with no mower left, it reaches the house
# and starts eating it.
HOUSE_LEFT_WALL = LAWNMOWER_X - 8  # visible zombie body must pass mower before defeat
HOUSE_HP = 1000  # higher so eating feels like the PvZ "brains eaten" delay
HOUSE_EAT_DPS = 300  # per second per zombie at the door (~3.3s for one zombie)

# UI Bar — top of screen, like original PvZ. Cards keep their native art ratio
# (49x69) so they are NOT squashed; bar height leaves room below for the lawn.
UI_BAR_Y = 0
UI_BAR_H = 76
SEED_BAR_X = 10
SEED_BAR_W = SCREEN_WIDTH - 20
# Sun jar (embedded in seed bar, left side)
SUN_JAR_X = SEED_BAR_X + 8
SUN_JAR_Y = UI_BAR_Y + 3
SUN_JAR_W = 48
SUN_JAR_H = 70
# Seed card layout — native PvZ card art is 49x69
SEED_CARD_W = 49
SEED_CARD_H = 69
SEED_CARD_GAP = 8
# Reserve room for both the 48px sun icon and a 62px numeric counter.
SEED_CARD_START_X = SUN_JAR_X + SUN_JAR_W + 70

# Tooltips / messages
TOOLTIP_FONT_SIZE = 18
MSG_FONT_SIZE = 28

# Sounds (we'll use simple beeps if no audio files)
SOUND_PLANT = "plant"
SOUND_SHOOT = "shoot"
SOUND_SUN_COLLECT = "sun"
SOUND_ZOMBIE_DIE = "zombie_die"
SOUND_LOSE = "lose"
SOUND_WIN = "win"