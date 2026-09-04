"""Load and cache PvZ sprite assets.

Supports two formats:
1. Static images (PNG with alpha or RGB) — load as-is.
2. Sprite sheets with PvZ magenta colorkey (255, 0, 255) — auto-cut into frames
   and store each frame as ``key_frame{i}``.
"""

import math
import os
import pygame

ASSET_DIR = os.path.join(os.path.dirname(__file__), "assets")

_cache = {}
_loaded = False

# PvZ sprite sheets use (255, 0, 255) magenta as background placeholder for transparency.
COLOKKEY = pygame.Color(255, 0, 255)

# 6-frame plant/zombie animation sheets are 504x84 (84 tall) for plants, 360x58 for zombies.
_SHEET_PATTERNS = {
    # filename in ui/ : (frame_w, frame_h, n_frames, key_prefix)
    "p_PeaShooter_idle.png":       (84, 84, 6, "anim_peashooter_idle"),
    "p_PeaShooter_attack.png":     (84, 84, 6, "anim_peashooter_attack"),
    "p_SunFlower_idle.png":        (84, 84, 6, "anim_sunflower_idle"),
    "p_SunFlower_glow.png":        (84, 84, 6, "anim_sunflower_glow"),
    "p_Wallnut_idle.png":          (84, 84, 6, "anim_wallnut_idle"),
    "p_Wallnut_cracked.png":       (84, 84, 6, "anim_wallnut_cracked"),
    "p_Wallnut_verycracked.png":   (84, 84, 6, "anim_wallnut_verycracked"),
    "z_AZombie.png":               (60, 58, 6, "anim_zombie_a_idle"),
    "z_AZombie_eating.png":        (60, 58, 6, "anim_zombie_a_eat"),
    "z_AZombie_dying.png":         (60, 58, 6, "anim_zombie_a_die"),
    "z_BZombie.png":               (60, 58, 6, "anim_zombie_b_idle"),
    "z_BZombie_eating.png":        (60, 58, 6, "anim_zombie_b_eat"),
    "z_BZombie_dying.png":         (60, 58, 6, "anim_zombie_b_die"),
}


def _load_raw(name, sub="ui"):
    """Load a PNG and apply colorkey if it has magenta background."""
    path = os.path.join(ASSET_DIR, sub, name)
    if not os.path.exists(path):
        return None
    try:
        img = pygame.image.load(path)
    except Exception:
        return None
    # Some standalone UI sprites use the same muted-purple matte as sheets.
    # Auto-clean only when the corner is opaque and purple-dominant.
    corner = img.get_at((0, 0))
    if corner.a > 240 and corner.r > 90 and corner.b > 90 \
            and corner.g < min(corner.r, corner.b):
        img = _apply_colorkey(img, bg_color=corner)
    return img


def _apply_colorkey_legacy(img):
    """Strip PvZ sprite-sheet magenta background, returning an RGBA surface.

    PvZ editor PNGs encode the alpha placeholder as (255, 0, 255). However
    anti-aliased edges get PNG-compressed to mauve tones like (153, 94, 153),
    so a strict equality check leaves a 1-2 pixel purple border. Solution:
    walk every pixel and force alpha=0 for any magenta-ish color.
    """
    if img is None:
        return None
    if img.get_size()[0] == 0:
        return None
    try:
        if img.get_alpha() is None:
            img = img.convert()
        else:
            img = img.convert_alpha()
    except pygame.error:
        # No video display yet — keep the original surface; it still works,
        # just slightly slower to blit.
        pass
    w, h = img.get_size()
    # Use a per-pixel loop — only runs once per sheet (cached result).
    out = pygame.Surface((w, h), pygame.SRCALPHA, 32)
    out.blit(img, (0, 0))
    # Treat any pixel where R high, G low, B high as transparent.
    pixel_access = out.lock() if hasattr(out, "lock") else None
    try:
        for y in range(h):
            row_start = y * w * 4
            for x in range(w):
                off = row_start + x * 4
                if pixel_access is not None:
                    r, g, b, a = pixel_access[x]
                else:
                    r, g, b, a = out.get_at((x, y))
                if r > 180 and g < 100 and b > 180:
                    if pixel_access is not None:
                        pixel_access[x] = (0, 0, 0, 0)
                    else:
                        out.set_at((x, y), (0, 0, 0, 0))
    finally:
        if pixel_access is not None:
            out.unlock()
    return out


def _apply_colorkey(img, bg_color=None, tolerance=34):
    """Remove muted-purple matte by flood-filling edge-connected pixels."""
    if img is None or img.get_width() == 0 or img.get_height() == 0:
        return None
    try:
        out = img.convert_alpha()
    except pygame.error:
        out = img.copy()
    w, h = out.get_size()
    key = pygame.Color(*(bg_color or out.get_at((0, 0))))

    def is_matte(pixel):
        if pixel.a == 0:
            return True
        return (abs(pixel.r - key.r) <= tolerance
                and abs(pixel.g - key.g) <= tolerance
                and abs(pixel.b - key.b) <= tolerance)

    from collections import deque
    queue = deque()
    seen = bytearray(w * h)
    for x in range(w):
        queue.append((x, 0)); queue.append((x, h - 1))
    for y in range(h):
        queue.append((0, y)); queue.append((w - 1, y))
    while queue:
        x, y = queue.popleft()
        idx = y * w + x
        if seen[idx]:
            continue
        seen[idx] = 1
        pixel = out.get_at((x, y))
        if not is_matte(pixel):
            continue
        out.set_at((x, y), (0, 0, 0, 0))
        if x > 0: queue.append((x - 1, y))
        if x + 1 < w: queue.append((x + 1, y))
        if y > 0: queue.append((x, y - 1))
        if y + 1 < h: queue.append((x, y + 1))
    return out


def _slice_sheet(name, sub, frame_w, frame_h, n_frames, key_prefix):
    """Load a pre-cleaned sprite sheet, cut it into frames, and cache them."""
    img = _load_raw(name, sub)
    if img is None:
        return
    # _load_raw() already removes an opaque purple matte. Repeating the
    # flood-fill here doubled cold-start work without changing pixels.
    sheet_w, sheet_h = img.get_size()
    actual_n = sheet_w // frame_w
    actual_n = min(actual_n, n_frames)
    for i in range(actual_n):
        rect = pygame.Rect(i * frame_w, 0, frame_w, frame_h)
        frame = img.subsurface(rect).copy()
        _cache[f"{key_prefix}_{i}"] = frame
    # also cache full sheet for fallback
    _cache[key_prefix + "_sheet"] = img


def _make_lily_pad_icon(size):
    """Procedural lily pad sprite (96px): green pad, notch, veins, highlight."""
    pad = pygame.Surface((size, size), pygame.SRCALPHA)
    s = size / 96.0
    # base pad
    pygame.draw.ellipse(pad, (36, 122, 52), (4 * s, 18 * s, 88 * s, 62 * s))
    pygame.draw.ellipse(pad, (52, 150, 66), (10 * s, 22 * s, 76 * s, 52 * s))
    pygame.draw.ellipse(pad, (66, 172, 78), (18 * s, 28 * s, 60 * s, 40 * s))
    # radial veins
    cx, cy = 48 * s, 48 * s
    for ang in (-150, -110, -70, -30, 10, 150, 170):
        a = math.radians(ang)
        pygame.draw.line(pad, (44, 138, 58),
                         (cx, cy),
                         (cx + 34 * s * math.cos(a), cy + 26 * s * math.sin(a)), 2)
    # the signature wedge notch, cut out of the pad towards the upper right
    notch = pygame.Surface((size, size), pygame.SRCALPHA)
    pygame.draw.polygon(notch, (255, 255, 255, 255), [
        (cx, cy), (86 * s, 24 * s), (92 * s, 40 * s)])
    pad.blit(notch, (0, 0), special_flags=pygame.BLEND_RGBA_SUB)
    # rim + water glint
    pygame.draw.ellipse(pad, (26, 96, 40), (4 * s, 18 * s, 88 * s, 62 * s), 2)
    pygame.draw.ellipse(pad, (150, 210, 255, 90), (14 * s, 60 * s, 60 * s, 12 * s))
    return pad


def init():
    """Initialize asset cache. Call once after pygame.display.set_mode()."""
    global _loaded
    if _loaded:
        return

    # ---- Animation sprite sheets (magenta colorkey) ----
    for filename, (fw, fh, n, prefix) in _SHEET_PATTERNS.items():
        _slice_sheet(filename, "ui", fw, fh, n, prefix)

    # ---- Lawn background (full PvZ yard with house, fence, sidewalk) ----
    img = _load_raw("g_DayBackground.png")
    if img:
        _cache["bg_day_full"] = img
    img = _load_raw("g_NightBackground.png")
    if img:
        _cache["bg_night_full"] = img
    img = _load_raw("nbg.png")
    if img:
        _cache["bg_night_alt"] = img  # alternate night artwork; not a pool scene
    img = _load_raw("frontyard.png")
    if img:
        _cache["bg_fallback"] = img

    # ---- Plant icons (96x96 from wiki) ----
    for name, key in [
        ("peashooter.png", "plant_peashooter"),
        ("sunflower.png", "plant_sunflower"),
        ("wallnut.png", "plant_wallnut"),
        ("cherrybomb.png", "plant_cherrybomb"),
        ("fumeshroom.png", "plant_fumeshroom"),
        ("lily_pad.png", "ui_lily_pad"),
    ]:
        img = _load_raw(name, "plants")
        if img is not None:
            _cache[key] = img

    # lily_pad.png is not bundled — synthesize the icon so seed cards,
    # ghosts and the in-game pad all share one decent sprite.
    if "ui_lily_pad" not in _cache:
        _cache["ui_lily_pad"] = _make_lily_pad_icon(96)

    # ---- Zombie icons (96x96 from wiki) — fallback if sprite sheet missing ----
    for name, key in [
        ("basic.png", "zombie_basic"),
        ("conehead.png", "zombie_conehead"),
        ("flag.png", "zombie_flag"),
        ("buckethead.png", "zombie_buckethead"),
    ]:
        img = _load_raw(name, "zombies")
        if img is not None:
            _cache[key] = img

    # ---- UI misc ----
    for name, key in [
        ("sun.png", "ui_sun"),
        ("lawnmower.png", "ui_lawnmower"),
        ("shovel_gh.png", "ui_shovel"),
        ("v_Pea.png", "ui_pea"),
        ("v_Sun.png", "ui_sun_small"),
        ("v_Snowpea.png", "ui_snowpea"),
        ("StartKey.png", "ui_startkey"),
        ("g_GameOverScreen.png", "ui_gameover"),
        ("p_EmptyPlant.png", "ui_plant_empty"),
        ("p_SelectedPlant.png", "ui_plant_selected"),
        ("c_PeaShooterCard.png", "card_peashooter"),
        ("c_SunFlowerCard.png", "card_sunflower"),
        ("c_WallnutCard.png", "card_wallnut"),
        ("c_SunCard.png", "card_sun"),
        ("c_KernelPultCard.png", "card_kernelpult"),
        ("c_SnowpeaShooterCard.png", "card_snowpea"),
        ("c_SelectedCard.png", "card_selected"),
        ("c_InactiveCard.png", "card_inactive"),
    ]:
        img = _load_raw(name)
        if img is not None:
            _cache[key] = img

    # Menu backgrounds (1400x600 RGBA)
    for name, key in [
        ("m_DayMenu.png", "menu_day"),
        ("m_NightMenu.png", "menu_night"),
    ]:
        img = _load_raw(name)
        if img is not None:
            _cache[key] = img

    _loaded = True


def get(key):
    """Get cached asset by key. Returns None if missing."""
    return _cache.get(key)


def has(key):
    return key in _cache


def _strip_white_box(img, threshold=240):
    """Make fully-opaque white/near-white pixels transparent.

    A few bundled sprites (peashooter_sprite, sunflower_sprite, walnut_sprite)
    ship with a flat white corner instead of an alpha channel. They otherwise
    look like solid white squares when used as the cursor ghost icon.
    """
    try:
        out = img.convert_alpha()
    except pygame.error:
        return img
    w, h = out.get_size()
    # Quick corner check — only rewrite when all four corners are opaque white.
    for cx, cy in ((0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)):
        p = out.get_at((cx, cy))
        if not (p.a > 240 and p.r > threshold and p.g > threshold and p.b > threshold):
            return img
    out.lock()
    try:
        for y in range(h):
            for x in range(w):
                p = out.get_at((x, y))
                if p.a > 240 and p.r > threshold and p.g > threshold and p.b > threshold:
                    out.set_at((x, y), (255, 255, 255, 0))
    finally:
        out.unlock()
    return out


def scale(key, w, h):
    """Return a scaled copy of asset, cached."""
    cache_key = f"_scaled_{key}_{w}x{h}"
    if cache_key in _cache:
        return _cache[cache_key]
    base = get(key)
    if base is None:
        return None
    scaled = pygame.transform.smoothscale(base, (w, h))
    scaled = _strip_white_box(scaled)
    _cache[cache_key] = scaled
    return scaled


def frame_body(prefix, index, target_w, target_h):
    """Return a (surface, foot_x, body_h) triple for one animation frame.

    Source sprite slots are 60x58, but the visible body only occupies a
    bounding rect inside that slot. If we smoothscale the whole 60x58 to
    99x96 the head gets clipped and the foot floats relative to the ground,
    because the transparent padding around the body carries over.

    We crop the visible body from the source, smoothscale it to target_w
    keeping its aspect ratio, and pad with transparent pixels so the foot
    sits at the bottom of the returned surface.
    """
    step = index % 6
    cache_key = f"_body_{prefix}_{step}_{target_w}x{target_h}"
    if cache_key in _cache:
        return _cache[cache_key]
    img = frame(prefix, step)
    if img is None:
        surf = pygame.Surface((target_w, target_h), pygame.SRCALPHA)
        _cache[cache_key] = (surf, target_w // 2, target_h)
        return _cache[cache_key]
    bounds = img.get_bounding_rect(min_alpha=16)
    if bounds.width <= 0 or bounds.height <= 0:
        surf = pygame.Surface((target_w, target_h), pygame.SRCALPHA)
        _cache[cache_key] = (surf, target_w // 2, target_h)
        return _cache[cache_key]
    body = img.subsurface(bounds).copy()
    src_w, src_h = body.get_size()
    body_h = int(round(src_h * target_w / src_w))
    body_h = min(body_h, target_h)
    scaled = pygame.transform.smoothscale(body, (target_w, body_h))
    surf = pygame.Surface((target_w, target_h), pygame.SRCALPHA)
    surf.blit(scaled, (0, target_h - body_h))
    xs = []
    for y in range(src_h - 5, src_h):
        for x in range(src_w):
            if body.get_at((x, y)).a >= 16:
                xs.append(x + bounds.left)
    foot_x_src = (sum(xs) / len(xs)) if xs else src_w // 2
    foot_x = round(foot_x_src * target_w / img.get_width())
    _cache[cache_key] = (surf, foot_x, target_h)
    return _cache[cache_key]


def rotated(key, w, h, angle_step):
    """Return a cached scaled+rotated image for quantized angle_step."""
    step = int(angle_step) % 24
    cache_key = f"_rot_{key}_{w}x{h}_{step}"
    if cache_key in _cache:
        return _cache[cache_key]
    base = scale(key, w, h)
    if base is None:
        return None
    img = pygame.transform.rotate(base, step * 15)
    _cache[cache_key] = img
    return img


def frame(prefix, index):
    """Get animation frame by sheet prefix and frame index."""
    return _cache.get(f"{prefix}_{index % 6}")


def scaled_frame(prefix, index, w, h):
    """Get an animation frame pre-scaled to (w, h), cached per size."""
    ck = f"_fscale_{prefix}_{index % 6}_{w}x{h}"
    if ck in _cache:
        return _cache[ck]
    f = frame(prefix, index)
    if f is None:
        return None
    s = pygame.transform.smoothscale(f, (w, h))
    _cache[ck] = s
    return s


def anim_frames(prefix):
    """Return list of all 6 frames for a given prefix."""
    return [_cache[f"{prefix}_{i}"] for i in range(6) if f"{prefix}_{i}" in _cache]


def plant_icon(plant_type):
    """Static plant icon for fallback."""
    mapping = {
        PLANT_PEASHOOTER: "plant_peashooter",
        PLANT_SUNFLOWER: "plant_sunflower",
        PLANT_WALLNUT: "plant_wallnut",
        PLANT_CHERRYBOMB: "plant_cherrybomb",
        PLANT_FUMESHROOM: "plant_fumeshroom",
        PLANT_LILYPAD: "ui_lily_pad",
        PLANT_SNOWPEA: "plant_peashooter",   # fallback reuses peashooter; game tints it cyan
    }
    key = mapping.get(plant_type)
    return get(key) if key else None


def zombie_icon(zombie_type):
    """Static zombie icon for fallback."""
    mapping = {
        ZOMBIE_BASIC: "zombie_basic",
        ZOMBIE_CONEHEAD: "zombie_conehead",
        ZOMBIE_FLAG: "zombie_flag",
        ZOMBIE_BUCKETHEAD: "zombie_buckethead",
    }
    key = mapping.get(zombie_type)
    return get(key) if key else None


# late-bind constants
from constants import (
    PLANT_PEASHOOTER, PLANT_SUNFLOWER, PLANT_WALLNUT,
    PLANT_CHERRYBOMB, PLANT_FUMESHROOM, PLANT_LILYPAD,
    PLANT_SNOWPEA,
    ZOMBIE_BASIC, ZOMBIE_CONEHEAD, ZOMBIE_FLAG, ZOMBIE_BUCKETHEAD,
)