# Plants vs Zombies - Python Edition

A Python + Pygame implementation of Plants vs Zombies. Cross-platform: runs on **Mac** and **Windows**.

## How to Run

### Mac / Linux
```bash
cd pvsz
./run.sh
```

### Windows
```
Double-click run.bat
```

## Game Modes

### Adventure Mode (关卡模式)
- 5 worlds × 3 levels = 15 levels
- Each world has different environment and mechanics:
  - **Day** (World 1): Classic lawn
  - **Night** (World 2): Dark sky with stars and moon
  - **Pool** (World 3): Water rows with lily pads
  - **Fog** (World 4): Fog rolls in from the right
  - **Roof** (World 5): Raised grid with roof tiles
- Each level has specific plants available and custom wave configs

### Survival Mode (无限模式)
- 5 environments: Day, Night, Pool, Fog, Roof
- Endless waves with increasing difficulty
- 50-wave cycles that regenerate automatically

## Controls

### Mouse
- **Click a seed card, then click the lawn** to plant — or **drag a card onto the lawn** and drop it
- **Click suns** to collect them (they fly into the sun jar and credit on arrival)
- **Right-click** cancels the selected card / shovel
- **Hover** a seed card, plant, or zombie for an info tooltip
- **Top-bar buttons**: pause (II) and 2x fast-forward (»), next to the shovel

### Keyboard
- **1–6**: select seed cards
- **Space**: skip the wait between waves
- **P / Esc**: pause (pause screen has Resume / Restart / Main Menu buttons)
- **F**: toggle 2x fast-forward
- **M**: mute / unmute
- **D**: debug — add 100 sun
- **F11**: fullscreen
- **Enter**: confirm on pause / defeat / victory screens
- **Esc / Backspace**: go back in menus

## Plant Upgrades (植物升级)

Replant the **same plant on the same plant** to level it up — up to **Lv3**:

| Plant | Lv1 | Lv2 | Lv3 |
|-------|-----|-----|-----|
| Peashooter dmg | 20 | 40 | 60 |
| Sunflower sun | 25 | 50 | 75 |
| Wall-nut HP | 4000 | 8000 | 16000 |
| Cherry Bomb dmg | 1800 | 3600 | 5400 (blast grows) |
| Fume-shroom dmg | 20 | 40 | 60 |
| Lily Pad HP | 400 | 800 | 1600 |

Upgraded plants show gold pips above them; the target cell glows **gold** when
an upgrade is possible. Each upgrade costs the plant's base sun cost.

## Plant Food (能量豆, from PvZ2)

A green bean periodically drops from the sky. **Click it** to store (up to 3,
see the slots left of the pause button), then **click a plant** to unleash:

- **Peashooter** — machine-gun burst (~2s of rapid fire)
- **Sunflower** — bursts 6 suns
- **Wall-nut** — full repair
- **Fume-shroom** — 300 damage to every zombie in its row
- **Cherry Bomb** — detonates immediately

## More Zombies (原版天降系)

- **Balloon Zombie (气球僵尸)** — flies in over your plants *and* lawnmowers;
  155 damage pops the balloon (290 total, PvZ1 parity), then it shuffles on foot
- **Bungee Zombie (蹦极僵尸)** — drops from the sky on a cord and **steals a
  plant** (450 HP, PvZ1 parity); kill it before it reaches the lawn. Expect one
  with every huge wave in Fog/Roof and every 5th endless wave

## Survival Scaling (无限模式成长)

Endless-mode zombies get **+3% speed and +6% bite damage per wave**
(speed up to 2x, damage up to 3x) — wave 30+ is a very different fight.

## Game Feel (本版优化)

- PvZ-style wave progress bar with flag markers (bottom-right)
- Sun jar pulse + fly-to-jar sun collection animation
- Cherry bombs get a real fireball, screen shake and a brief flash
- Plants drop in with a bounce; soil poof on planting / digging
- Ghost seed packet follows the cursor while a card is selected (OS cursor hides)
- Target cell turns green/red under the cursor showing plantability
- Pause / defeat / victory screens all have clickable buttons (retry, next level, menu)
- Synthesized SFX with anti-spam throttling (no crackling in heavy fights)

## Performance notes

The renderer is allocation-free in steady state: projectile sprites, fog strips,
pool water, roof tiles, HUD text and card art are all pre-rendered and cached.
A worst-case scene (full 5×6 defense, 26 zombies, live projectiles) costs about
2–3 ms per frame against the 16.6 ms / 60 fps budget; frame pacing uses a
busy-wait clock to avoid sleep-overshoot stutter.

## Development

Headless regression tests:

```bash
SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy ./venv/bin/python tests_smoke.py
SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy ./venv/bin/python tests_ux.py
```

`tests_ux.py` also dumps state screenshots to `screenshots/ux_audit/`.

## Plants

| Plant | Cost | Role |
|-------|------|------|
| Peashooter | 100 | Shoots peas forward |
| Sunflower | 50 | Generates sun |
| Wall-nut | 50 | Blocks zombies |
| Cherry Bomb | 150 | Explodes on contact |
| Fume-shroom | 75 | Shoots purple spores |

## Zombies

| Type | HP | Speed | Reward |
|------|-----|-------|--------|
| Basic | 100 | 18 | 5 |
| Conehead | 250 | 16 | 10 |
| Flag | 150 | 20 | 15 |
| Buckethead | 500 | 14 | 20 |

## Game Elements (原版道具)

- **Lawnmower** (割草机): One per row, zombie contact = game over
- **Door** (门): Zombies eat the door before entering the house
- **Lily Pad** (睡莲): For pool levels, plants can be placed on them
- **Roof Tile** (屋顶瓦片): For roof levels
- **Fog** (雾): For fog levels, reduces visibility
- **Seed Packet** (种子卡): Shows plant icon, sun cost, and cooldown timer
- **Sun Jar** (太阳罐): Shows current sun count

## Project Structure

```
pvsz/
  main.py       # Entry point
  game.py       # Game loop & state machine (adventure + survival)
  constants.py  # All game constants
  entities.py   # Plants, zombies, projectiles, sun, lawnmower, lily pad, roof, fog, shovel
  grid.py       # Lawn grid system
  wave.py       # Zombie wave spawner
  ui.py         # Seed bar, menus (mode select, level select, pause, game over)
  levels.py     # Level definitions (15 adventure + 5 survival environments)
  run.sh        # Mac/Linux launcher
  run.bat       # Windows launcher
  venv/         # Python virtual environment
```

## Requirements

- Python 3.9+
- Pygame (auto-installed in venv)