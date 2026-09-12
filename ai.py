"""Zombie intelligence: battlefield intel + an adaptive wave director.

Two cooperating pieces:

``intel``
    A module-level snapshot of the lawn, rebuilt once per frame by the game.
    It answers the two questions every AI zombie asks — "how strong is each
    row?" and "where does that row's defense start?" — in O(plants) instead of
    making each zombie scan the plant list again.

``Director``
    Reads ``intel`` and biases wave composition toward whatever the player's
    defense is *weak* against: massed peashooters get bucketheads, a thin
    back line gets diggers, a single stacked lane gets a tactician. It only
    ever nudges the scripted wave (``DIRECTOR_MAX_ADAPT``), so progression
    still reads as authored rather than random.

Both are deliberately free of pygame/entity imports so ``entities`` and
``wave`` can use them without an import cycle.
"""

import random

from constants import (
    GRID_ROWS, SCREEN_WIDTH, GRID_X, CELL_W,
    ZOMBIE_BASIC, ZOMBIE_CONEHEAD, ZOMBIE_BUCKETHEAD, ZOMBIE_FLAG,
    ZOMBIE_NEWSPAPER, ZOMBIE_POLE, ZOMBIE_BALLOON, ZOMBIE_BUNGEE,
    ZOMBIE_TACTICIAN, ZOMBIE_DIGGER, ZOMBIE_HEALER, ZOMBIE_COMMANDER,
    PLANT_PEASHOOTER, PLANT_SNOWPEA, PLANT_WALLNUT, PLANT_SUNFLOWER,
    PLANT_CHERRYBOMB, PLANT_FUMESHROOM, PLANT_LILYPAD, PLANT_COBCANNON,
    DIRECTOR_MAX_ADAPT, DIRECTOR_STACK_MIN_THREAT,
)

# Relative danger of each plant family, used to score a row's defense.
_PLANT_THREAT = {
    PLANT_PEASHOOTER: 10.0,
    PLANT_SNOWPEA: 12.0,
    PLANT_FUMESHROOM: 9.0,
    PLANT_COBCANNON: 26.0,
    PLANT_CHERRYBOMB: 16.0,     # one-shot deterrent counts as burst threat
    PLANT_WALLNUT: 6.0,         # soaks, doesn't kill
    PLANT_SUNFLOWER: 1.5,       # economy, barely defended
    PLANT_LILYPAD: 0.5,
}


class BattlefieldIntel:
    """Per-row view of the player's defense, refreshed every frame."""

    __slots__ = ("row_threat", "row_front_x", "row_plants", "total_threat",
                 "plant_count", "shooter_count", "wall_count", "economy_count",
                 "has_anti_air", "tick", "water_rows")

    def __init__(self):
        n = GRID_ROWS
        self.row_threat = [0.0] * n
        self.row_front_x = [float(SCREEN_WIDTH)] * n
        self.row_plants = [0] * n
        self.total_threat = 0.0
        self.plant_count = 0
        self.shooter_count = 0
        self.wall_count = 0
        self.economy_count = 0
        self.has_anti_air = False
        self.tick = 0
        # Rows that are open water (pool levels). Ground zombies, bungee drops
        # and lane transfers must avoid them — there is no swim state, so a
        # zombie picked onto a water row walks *on* the surface. Empty set on
        # land-only boards; the game sets it per level.
        self.water_rows = frozenset()

    def rebuild(self, plants):
        row_threat = self.row_threat
        row_front = self.row_front_x
        row_plants = self.row_plants
        for i in range(len(row_threat)):
            row_threat[i] = 0.0
            row_front[i] = float(SCREEN_WIDTH)
            row_plants[i] = 0
        total = 0.0
        count = shooters = walls = economy = 0
        anti_air = False
        for p in plants:
            if not p.alive or p.row < 0 or p.row >= len(row_threat):
                continue
            r = p.row
            t = _PLANT_THREAT.get(p.plant_type, 4.0)
            # A plant that has been chewed down is worth proportionally less
            # as a target — the AI should not commit to a lane that is already
            # about to fall on its own.
            hp_ratio = 1.0
            mh = getattr(p, "max_hp", 0)
            if mh:
                hp_ratio = max(0.15, min(1.0, p.hp / float(mh)))
            t *= 0.55 + 0.45 * hp_ratio
            row_threat[r] += t
            total += t
            count += 1
            row_plants[r] += 1
            # Front line = the plant a walking zombie meets first (largest x,
            # since zombies come in from the right). The digger surfaces just
            # past it, so this is exactly the line it has to bypass.
            if p.x > row_front[r]:
                row_front[r] = float(p.x)
            if p.plant_type in (PLANT_PEASHOOTER, PLANT_SNOWPEA,
                                PLANT_FUMESHROOM, PLANT_COBCANNON):
                shooters += 1
                anti_air = True
            elif p.plant_type == PLANT_WALLNUT:
                walls += 1
            elif p.plant_type == PLANT_SUNFLOWER:
                economy += 1
        self.total_threat = total
        # Must be assigned here: profile() bails to "default" the moment this
        # reads 0, so leaving it at its __init__ value silently disabled every
        # profile except "default" — the whole adaptive branch was dead.
        self.plant_count = count
        self.shooter_count = shooters
        self.wall_count = walls
        self.economy_count = economy
        self.has_anti_air = anti_air

    # ------------------------------------------------------------ queries
    def land_rows(self):
        """Rows a ground zombie can actually walk on (excludes open water)."""
        if not self.water_rows:
            return list(range(GRID_ROWS))
        return [r for r in range(GRID_ROWS) if r not in self.water_rows]

    def weakest_row(self):
        """Row with the least defensive threat (ties broken randomly)."""
        if not self.row_threat:
            return 0
        best = min(self.row_threat)
        picks = [i for i, t in enumerate(self.row_threat) if t <= best + 0.001]
        return random.choice(picks)

    def strongest_row(self):
        best = max(self.row_threat)
        picks = [i for i, t in enumerate(self.row_threat) if t >= best - 0.001]
        return random.choice(picks)

    def neighbor_rows(self, row):
        """Rows adjacent to ``row``, nearest first."""
        out = []
        for d in (1, -1, 2, -2, 3, -3, 4, -4):
            r = row + d
            if 0 <= r < len(self.row_threat):
                out.append(r)
        return out

    def best_transfer(self, row):
        """Cheapest adjacent-ish row worth hopping to, or None.

        Only returns a row that is meaningfully softer than the current one,
        so tacticians commit to a real flank instead of twitching every
        cooldown.
        """
        cur = self.row_threat[row] if 0 <= row < len(self.row_threat) else 0.0
        best_row, best_val = None, cur
        for r in self.neighbor_rows(row):
            if r in self.water_rows:
                continue    # a tactician cannot flank into open water
            # A hop costs travel time, so the payoff has to clear a margin
            # that grows with distance.
            if abs(r - row) == 1:
                margin = 4.0
            else:
                margin = 8.0 + 4.0 * (abs(r - row) - 1)
            val = self.row_threat[r]
            if val < best_val - margin:
                best_row, best_val = r, val
        return best_row


# Module-level snapshot; the game rebuilds it once per frame and every AI
# zombie reads it. Avoids threading a reference through every spawn path.
intel = BattlefieldIntel()


def refresh_intel(plants):
    intel.rebuild(plants)
    intel.tick += 1


# --------------------------------------------------------------- director
# What each zombie is *for*, so the director can pick a counter rather than a
# random type. Keys are threat profiles; values are (type, weight).
_COUNTERS = {
    # Player stacked a lot of shooters: out-tank them.
    "shooters": [(ZOMBIE_BUCKETHEAD, 3.0), (ZOMBIE_COMMANDER, 1.6),
                 (ZOMBIE_HEALER, 1.2), (ZOMBIE_BASIC, 1.0)],
    # Player built a wall line: go over it or under it.
    "walls": [(ZOMBIE_POLE, 3.0), (ZOMBIE_DIGGER, 2.4), (ZOMBIE_BASIC, 1.0)],
    # Player is economy-heavy (few shooters): press with cheap fast bodies.
    "economy": [(ZOMBIE_BASIC, 3.0), (ZOMBIE_FLAG, 2.0), (ZOMBIE_TACTICIAN, 1.4)],
    # Player has one overloaded lane: flank it.
    "stacked": [(ZOMBIE_TACTICIAN, 3.2), (ZOMBIE_DIGGER, 1.6), (ZOMBIE_FLAG, 1.2)],
    # Generic pressure.
    "default": [(ZOMBIE_BASIC, 2.0), (ZOMBIE_CONEHEAD, 1.6),
                (ZOMBIE_FLAG, 1.0), (ZOMBIE_NEWSPAPER, 0.8)],
}

# Zombies the director is allowed to *introduce* (it never invents a type the
# current level's wave table has not unlocked yet — see Director.compose).
_AI_TYPES = (ZOMBIE_TACTICIAN, ZOMBIE_DIGGER, ZOMBIE_HEALER, ZOMBIE_COMMANDER)


def _weighted_choice(pairs):
    total = sum(w for _, w in pairs)
    if total <= 0:
        return pairs[0][0]
    r = random.uniform(0, total)
    upto = 0.0
    for item, w in pairs:
        upto += w
        if r <= upto:
            return item
    return pairs[-1][0]


class Director:
    """Picks zombie types that answer the player's current defense.

    ``compose`` is called when a wave starts. It returns a list of zombie
    types of the requested length, seeded from the scripted composition (so
    the level still feels authored) but with up to ``DIRECTOR_MAX_ADAPT`` of
    the slots swapped for counters.
    """

    def __init__(self, enabled=True):
        self.enabled = enabled
        self.pressure = 0.0        # 0..1 — how hard the player is being pushed
        self.last_profile = "default"
        self.adapt_strength = DIRECTOR_MAX_ADAPT
        self.history = []

    # ------------------------------------------------------------ profiling
    def profile(self, it=None):
        """Classify the player's defense into one dominant threat profile.

        Order matters, and two of these branches were previously unreachable
        or degenerate:

        * ``walls`` used to also require ``shooter_count >= 3``, so a wall
          line on its own — the exact board pole vaulters exist to punish —
          never classified as ``walls``.
        * ``economy`` tested ``economy_count >= shooter_count * 2``, which is
          ``0 >= 0`` on any board with no shooters. Every pure-wall and
          pure-mushroom board therefore fell through into ``economy`` and drew
          cheap basic zombies instead of the counter it actually needed.

        So: require a real wall line to mean ``walls``, and require the
        economy to be non-trivial before claiming the player is turtling.
        """
        it = it or intel
        if it.plant_count == 0:
            return "default"
        # One lane carrying most of the defense → flank it. The absolute floor
        # matters: sunflowers score so low that on a sun-heavy board a single
        # peashooter is >2.2x the mean of a tiny total, which would otherwise
        # read as a stacked lane and send tacticians at an empty lawn.
        if it.row_threat:
            top = max(it.row_threat)
            mean = sum(it.row_threat) / len(it.row_threat)
            if (mean > 0 and top > mean * 2.2 and it.plant_count >= 6
                    and top >= DIRECTOR_STACK_MIN_THREAT):
                return "stacked"
        # A wall line is a defining structure on its own, shooters or not.
        if it.wall_count >= 3:
            return "walls"
        if it.shooter_count >= it.plant_count * 0.55:
            return "shooters"
        # Economy-heavy and barely defended. The floor keeps a board with no
        # sunflowers at all from matching on a vacuous 0 >= 0.
        if it.economy_count >= 2 and it.economy_count >= it.shooter_count * 2:
            return "economy"
        return "default"

    # -------------------------------------------------------------- compose
    def compose(self, scripted_types, count, allowed_types, unlock_ai=False):
        """Return a list of ``count`` zombie types to spawn.

        ``scripted_types`` is the level's own pool; ``allowed_types`` is every
        type the level may legally spawn (used to keep AI zombies gated behind
        the levels that are meant to introduce them). AI zombie types are only
        mixed in when ``unlock_ai`` is set and they are in ``allowed_types``.
        """
        if not self.enabled or count <= 0:
            return [random.choice(scripted_types) for _ in range(count)] if scripted_types else []

        prof = self.profile()
        self.last_profile = prof
        self.history.append(prof)
        if len(self.history) > 24:
            del self.history[:12]

        # Blend the counter table with the scripted pool. The scripted pool is
        # the floor: it is always a legal choice and keeps levels recognisable.
        pool = [(t, 1.4) for t in set(scripted_types)]
        for t, w in _COUNTERS.get(prof, _COUNTERS["default"]):
            if t in allowed_types:
                pool.append((t, w))
        if unlock_ai:
            for t in _AI_TYPES:
                if t in allowed_types:
                    pool.append((t, self._ai_weight(t, prof)))

        n_swap = int(round(count * self.adapt_strength))
        # Always keep at least one scripted zombie so the wave still reads as
        # the authored level, even at max adaptation.
        n_swap = min(n_swap, max(0, count - 1))
        out = []
        for i in range(count):
            if i < n_swap:
                out.append(_weighted_choice(pool))
            else:
                out.append(random.choice(scripted_types) if scripted_types
                           else _weighted_choice(pool))
        random.shuffle(out)
        return out

    def _ai_weight(self, ztype, prof):
        """Per-profile appetite for each AI zombie."""
        table = {
            ZOMBIE_TACTICIAN: {"stacked": 3.2, "shooters": 1.4, "economy": 1.6,
                               "walls": 1.2, "default": 1.0},
            ZOMBIE_DIGGER: {"walls": 3.0, "stacked": 2.0, "shooters": 1.6,
                            "economy": 1.0, "default": 0.9},
            ZOMBIE_HEALER: {"shooters": 2.2, "walls": 1.4, "stacked": 1.0,
                            "economy": 0.6, "default": 0.9},
            ZOMBIE_COMMANDER: {"economy": 2.6, "default": 1.4, "shooters": 1.4,
                               "walls": 1.0, "stacked": 0.8},
        }
        return table.get(ztype, {}).get(prof, 1.0)

    # -------------------------------------------------------------- rows
    def choose_row(self):
        """Pick a spawn row: biased toward the player's weakest lane.

        Weighted rather than deterministic — a director that always sent every
        zombie to the softest row would feel scripted and unfair.
        """
        it = intel
        if not self.enabled or it.total_threat <= 0:
            return random.choice(it.land_rows())
        # Inverse-threat weighting: soft rows get picked more often, but hard
        # rows still see pressure. Water rows are never candidates for ground
        # zombies — there is no swim state, so they would walk on the surface.
        land = it.land_rows()
        weights = []
        hardest = max(it.row_threat) if it.row_threat else 0.0
        for t in it.row_threat:
            weights.append(max(0.35, (hardest + 6.0) - t))
        total = sum(weights[r] for r in land)
        r = random.uniform(0, total)
        upto = 0.0
        for i in land:
            upto += weights[i]
            if r <= upto:
                return i
        return land[-1]
