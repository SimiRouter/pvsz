"""Level definitions for Adventure and Survival modes."""

from constants import *

# ============================================================
# Background types
# ============================================================
BG_DAY = "day"
BG_NIGHT = "night"
BG_POOL = "pool"
BG_FOG = "fog"
BG_ROOF = "roof"

# ============================================================
# Adventure Mode: 5 worlds, 16 levels total (including 5-4 boss)
# ============================================================
ADVENTURE_LEVELS = [
    # --- World 1: Day ---
    {
        "id": "1-1", "name": "Level 1-1", "world": 1, "bg": BG_DAY,
        "plants": [PLANT_PEASHOOTER, PLANT_SUNFLOWER, PLANT_WALLNUT],
        "waves": [
            (3, [ZOMBIE_BASIC], 8000),
            (5, [ZOMBIE_BASIC, ZOMBIE_BASIC], 6000),
        ],
        "start_sun": 150, "special": None,
    },
    {
        "id": "1-2", "name": "Level 1-2", "world": 1, "bg": BG_DAY,
        "plants": [PLANT_PEASHOOTER, PLANT_SUNFLOWER, PLANT_WALLNUT, PLANT_CHERRYBOMB],
        "waves": [
            (4, [ZOMBIE_BASIC], 7000),
            (6, [ZOMBIE_BASIC, ZOMBIE_CONEHEAD], 5500),
            (8, [ZOMBIE_BASIC, ZOMBIE_CONEHEAD, ZOMBIE_FLAG], 4500),
        ],
        "start_sun": 150, "special": None,
    },
    {
        "id": "1-3", "name": "Level 1-3", "world": 1, "bg": BG_DAY,
        "plants": [PLANT_PEASHOOTER, PLANT_SUNFLOWER, PLANT_WALLNUT, PLANT_CHERRYBOMB, PLANT_FUMESHROOM],
        "waves": [
            (5, [ZOMBIE_BASIC], 6000),
            (8, [ZOMBIE_BASIC, ZOMBIE_CONEHEAD], 5000),
            (10, [ZOMBIE_BASIC, ZOMBIE_CONEHEAD, ZOMBIE_FLAG], 4000),
            (12, [ZOMBIE_CONEHEAD, ZOMBIE_BUCKETHEAD, ZOMBIE_FLAG], 3500),
        ],
        "start_sun": 150, "special": None,
    },

    # --- World 2: Night (mushroom levels) ---
    {
        "id": "2-1", "name": "Level 2-1", "world": 2, "bg": BG_NIGHT,
        "plants": [PLANT_FUMESHROOM, PLANT_SUNFLOWER, PLANT_WALLNUT],
        "waves": [
            (3, [ZOMBIE_BASIC], 9000),
            (5, [ZOMBIE_BASIC, ZOMBIE_BASIC], 7000),
        ],
        "start_sun": 250, "special": "night",
    },
    {
        "id": "2-2", "name": "Level 2-2", "world": 2, "bg": BG_NIGHT,
        "plants": [PLANT_FUMESHROOM, PLANT_SUNFLOWER, PLANT_WALLNUT, PLANT_PEASHOOTER],
        "waves": [
            (4, [ZOMBIE_BASIC], 8000),
            (6, [ZOMBIE_BASIC, ZOMBIE_CONEHEAD], 6000),
            (8, [ZOMBIE_BASIC, ZOMBIE_CONEHEAD, ZOMBIE_FLAG], 5000),
        ],
        "start_sun": 250, "special": "night",
    },
    {
        "id": "2-3", "name": "Level 2-3", "world": 2, "bg": BG_NIGHT,
        "plants": [PLANT_FUMESHROOM, PLANT_SUNFLOWER, PLANT_WALLNUT, PLANT_CHERRYBOMB, PLANT_PEASHOOTER],
        "waves": [
            (5, [ZOMBIE_BASIC], 7000),
            (8, [ZOMBIE_BASIC, ZOMBIE_CONEHEAD], 5500),
            (10, [ZOMBIE_BASIC, ZOMBIE_CONEHEAD, ZOMBIE_FLAG], 4500),
            (12, [ZOMBIE_CONEHEAD, ZOMBIE_BUCKETHEAD, ZOMBIE_FLAG], 3500),
        ],
        "start_sun": 250, "special": "night",
    },

    # --- World 3: Pool (lily pad levels) ---
    {
        "id": "3-1", "name": "Level 3-1", "world": 3, "bg": BG_POOL,
        "plants": [PLANT_LILYPAD, PLANT_PEASHOOTER, PLANT_SUNFLOWER, PLANT_WALLNUT, PLANT_FUMESHROOM],
        "waves": [
            (3, [ZOMBIE_BASIC], 9000),
            (5, [ZOMBIE_BASIC, ZOMBIE_BASIC], 7000),
        ],
        "start_sun": 200, "special": "pool",
    },
    {
        "id": "3-2", "name": "Level 3-2", "world": 3, "bg": BG_POOL,
        "plants": [PLANT_LILYPAD, PLANT_PEASHOOTER, PLANT_SUNFLOWER, PLANT_WALLNUT, PLANT_CHERRYBOMB, PLANT_FUMESHROOM],
        "waves": [
            (4, [ZOMBIE_BASIC], 8000),
            (6, [ZOMBIE_BASIC, ZOMBIE_CONEHEAD], 6000),
            (8, [ZOMBIE_BASIC, ZOMBIE_CONEHEAD, ZOMBIE_FLAG], 5000),
        ],
        "start_sun": 200, "special": "pool",
    },
    {
        "id": "3-3", "name": "Level 3-3", "world": 3, "bg": BG_POOL,
        "plants": [PLANT_LILYPAD, PLANT_PEASHOOTER, PLANT_SUNFLOWER, PLANT_WALLNUT, PLANT_CHERRYBOMB, PLANT_FUMESHROOM],
        "waves": [
            (5, [ZOMBIE_BASIC], 7000),
            (8, [ZOMBIE_BASIC, ZOMBIE_CONEHEAD], 5500),
            (10, [ZOMBIE_BASIC, ZOMBIE_CONEHEAD, ZOMBIE_FLAG], 4500),
            (12, [ZOMBIE_CONEHEAD, ZOMBIE_BUCKETHEAD, ZOMBIE_FLAG], 3500),
        ],
        "start_sun": 200, "special": "pool",
    },

    # --- World 4: Fog ---
    {
        "id": "4-1", "name": "Level 4-1", "world": 4, "bg": BG_FOG,
        "plants": [PLANT_PEASHOOTER, PLANT_SUNFLOWER, PLANT_WALLNUT, PLANT_FUMESHROOM],
        "waves": [
            (3, [ZOMBIE_BASIC], 9000),
            (5, [ZOMBIE_BASIC, ZOMBIE_BASIC], 7000),
        ],
        "start_sun": 150, "special": "fog",
    },
    {
        "id": "4-2", "name": "Level 4-2", "world": 4, "bg": BG_FOG,
        "plants": [PLANT_PEASHOOTER, PLANT_SUNFLOWER, PLANT_WALLNUT, PLANT_CHERRYBOMB, PLANT_FUMESHROOM],
        "waves": [
            (4, [ZOMBIE_BASIC], 8000),
            (6, [ZOMBIE_BASIC, ZOMBIE_CONEHEAD], 6000),
            (8, [ZOMBIE_BASIC, ZOMBIE_CONEHEAD, ZOMBIE_FLAG], 5000),
        ],
        "start_sun": 150, "special": "fog",
    },
    {
        "id": "4-3", "name": "Level 4-3", "world": 4, "bg": BG_FOG,
        "plants": [PLANT_PEASHOOTER, PLANT_SUNFLOWER, PLANT_WALLNUT, PLANT_CHERRYBOMB, PLANT_FUMESHROOM],
        "waves": [
            (5, [ZOMBIE_BASIC], 7000),
            (8, [ZOMBIE_BASIC, ZOMBIE_CONEHEAD], 5500),
            (10, [ZOMBIE_BASIC, ZOMBIE_CONEHEAD, ZOMBIE_FLAG], 4500),
            (12, [ZOMBIE_CONEHEAD, ZOMBIE_BUCKETHEAD, ZOMBIE_BALLOON, ZOMBIE_FLAG], 3500),
        ],
        "start_sun": 150, "special": "fog",
    },

    # --- World 5: Roof ---
    {
        "id": "5-1", "name": "Level 5-1", "world": 5, "bg": BG_ROOF,
        "plants": [PLANT_PEASHOOTER, PLANT_SUNFLOWER, PLANT_WALLNUT],
        "waves": [
            (3, [ZOMBIE_BASIC], 9000),
            (5, [ZOMBIE_BASIC, ZOMBIE_BASIC], 7000),
        ],
        "start_sun": 150, "special": "roof",
    },
    {
        "id": "5-2", "name": "Level 5-2", "world": 5, "bg": BG_ROOF,
        "plants": [PLANT_PEASHOOTER, PLANT_SUNFLOWER, PLANT_WALLNUT, PLANT_CHERRYBOMB],
        "waves": [
            (4, [ZOMBIE_BASIC], 8000),
            (6, [ZOMBIE_BASIC, ZOMBIE_CONEHEAD], 6000),
            (8, [ZOMBIE_BASIC, ZOMBIE_CONEHEAD, ZOMBIE_FLAG], 5000),
        ],
        "start_sun": 150, "special": "roof",
    },
    {
        "id": "5-3", "name": "Level 5-3", "world": 5, "bg": BG_ROOF,
        "plants": [PLANT_PEASHOOTER, PLANT_SUNFLOWER, PLANT_WALLNUT, PLANT_CHERRYBOMB, PLANT_FUMESHROOM],
        "waves": [
            (5, [ZOMBIE_BASIC], 7000),
            (8, [ZOMBIE_BASIC, ZOMBIE_CONEHEAD], 5500),
            (10, [ZOMBIE_BASIC, ZOMBIE_NEWSPAPER, ZOMBIE_FLAG], 4500),
            (12, [ZOMBIE_CONEHEAD, ZOMBIE_BUCKETHEAD, ZOMBIE_NEWSPAPER, ZOMBIE_BALLOON], 3500),
        ],
        "start_sun": 150, "special": "roof",
    },
    {
        "id": "5-4", "name": "BOSS: The Zomboss", "world": 5, "bg": BG_ROOF,
        "plants": [PLANT_PEASHOOTER, PLANT_SUNFLOWER, PLANT_WALLNUT, PLANT_CHERRYBOMB, PLANT_FUMESHROOM],
        "waves": [
            (4, [ZOMBIE_BASIC], 6000),
            (6, [ZOMBIE_BASIC, ZOMBIE_NEWSPAPER], 5000),
            (8, [ZOMBIE_BASIC, ZOMBIE_CONEHEAD, ZOMBIE_POLE, ZOMBIE_BALLOON], 4000),
            (1, [ZOMBIE_BOSS], 2500),
        ],
        "start_sun": 300, "special": "roof",
    },
]

# ============================================================
# Survival Mode: 5 environments, endless waves
# ============================================================
SURVIVAL_MODES = [
    {"id": "surv_day", "name": "Day", "bg": BG_DAY, "desc": "Classic day lawn"},
    {"id": "surv_night", "name": "Night", "bg": BG_NIGHT, "desc": "Dark with mushrooms"},
    {"id": "surv_pool", "name": "Pool", "bg": BG_POOL, "desc": "Water with lily pads"},
    {"id": "surv_fog", "name": "Fog", "bg": BG_FOG, "desc": "Thick fog rolls in"},
    {"id": "surv_roof", "name": "Roof", "bg": BG_ROOF, "desc": "On the roof"},
]

# All plants available in survival
SURVIVAL_PLANTS = [PLANT_PEASHOOTER, PLANT_SUNFLOWER, PLANT_WALLNUT, PLANT_CHERRYBOMB, PLANT_FUMESHROOM, PLANT_LILYPAD]

# Pool rows (bottom 2 rows are water)
POOL_WATER_ROWS = [3, 4]
# Roof uses the same safe playable origin as the lawn; its visual identity is
# provided by the full terracotta tile surface, avoiding overlap with the 76px UI.
ROOF_GRID_Y = GRID_Y