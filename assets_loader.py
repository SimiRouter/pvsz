"""Load and cache PvZ sprite assets.

Supports two formats:
1. Static images (PNG with alpha or RGB) — load as-is.
2. Sprite sheets with PvZ magenta colorkey (255, 0, 255) — auto-cut into frames
   and store each frame as ``key_frame{i}``.
"""

import math
import os
import pygame

import fade_cache

ASSET_DIR = os.path.join(os.path.dirname(__file__), "assets")

_cache = {}
_loaded = False

# PvZ sprite sheets use (255, 0, 255) magenta as background placeholder for transparency.
COLOKKEY = pygame.Color(255, 0, 255)

# Plant sheets have 6 frames; bundled zombie sheets have 7 frames in a 360px strip.
_SHEET_PATTERNS = {
    # filename in ui/ : (frame_w, frame_h, n_frames, key_prefix)
    "p_PeaShooter_idle.png":       (84, 84, 6, "anim_peashooter_idle"),
    "p_PeaShooter_attack.png":     (84, 84, 6, "anim_peashooter_attack"),
    "p_SnowpeaShooter_idle.png":   (84, 84, 6, "anim_snowpea_idle"),
    "p_SnowpeaShooter_attack.png": (84, 84, 6, "anim_snowpea_attack"),
    "p_SunFlower_idle.png":        (84, 84, 6, "anim_sunflower_idle"),
    "p_SunFlower_glow.png":        (84, 84, 6, "anim_sunflower_glow"),
    "p_Wallnut_idle.png":          (84, 84, 6, "anim_wallnut_idle"),
    "p_Wallnut_cracked.png":       (84, 84, 6, "anim_wallnut_cracked"),
    "p_Wallnut_verycracked.png":   (84, 84, 6, "anim_wallnut_verycracked"),
    "z_AZombie.png":               (52, 58, 7, "anim_zombie_a_idle"),
    "z_AZombie_eating.png":        (52, 58, 7, "anim_zombie_a_eat"),
    "z_AZombie_dying.png":         (52, 58, 7, "anim_zombie_a_die"),
    "z_BZombie.png":               (52, 58, 7, "anim_zombie_b_idle"),
    "z_BZombie_eating.png":        (52, 58, 7, "anim_zombie_b_eat"),
    "z_BZombie_dying.png":         (52, 58, 7, "anim_zombie_b_die"),
}


def to_display_format(img):
    """Re-encode a loaded surface in the display's own pixel format.

    ``pygame.image.load`` hands back a surface in whatever format the PNG uses,
    and a blit whose source format differs from the display's falls off the fast
    path into a per-pixel conversion — every frame, for the life of the sprite.
    The full-screen lawn background is the worst case because it is blitted once
    per frame and nothing else in the frame can be drawn until it lands:
    measured 0.55 ms as-loaded against 0.13 ms converted, so the missing
    ``convert()`` was costing ~0.4 ms of a 16.67 ms budget on its own.

    Per-pixel alpha needs ``convert_alpha``; a colour-keyed or fully opaque
    surface needs plain ``convert``, which keeps the key and is the cheaper
    blit. No display yet (headless tooling) is not an error here — the surface
    still works, just slower, so it is returned untouched.
    """
    if img is None:
        return None
    try:
        if img.get_flags() & pygame.SRCALPHA:
            return img.convert_alpha()
        return img.convert()
    except pygame.error:
        return img


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
    # The alpha test above needs the *source* format, so this runs before the
    # display-format conversion below rather than after it.
    corner = img.get_at((0, 0))
    if corner.a > 240 and corner.r > 90 and corner.b > 90 \
            and corner.g < min(corner.r, corner.b):
        img = _apply_colorkey(img, bg_color=corner)
    return to_display_format(img)


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
            for x in range(w):
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
    actual_n = (sheet_w + frame_w - 1) // frame_w
    actual_n = min(actual_n, n_frames)
    for i in range(actual_n):
        rect = pygame.Rect(i * frame_w, 0, min(frame_w, sheet_w - i * frame_w), frame_h)
        frame = img.subsurface(rect).copy()
        _cache[f"{key_prefix}_{i}"] = frame
    _cache[key_prefix + "_count"] = actual_n
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
    scaled = upscale(base, (w, h))
    scaled = _strip_white_box(scaled)
    _cache[cache_key] = scaled
    return scaled


def _median(values):
    ordered = sorted(values)
    return ordered[len(ordered) // 2]


def upscale(img, size):
    """Scale a surface to `size`, keeping pixel-art edges crisp.

    The bundled sheets are tiny — a zombie body is 27x44 source pixels — and
    they are drawn at ~96 px tall, a 2.2x blow-up. A single ``smoothscale``
    from 44 px smears every outline into mush. ``scale2x`` is an edge-directed
    2x filter (EPX) that doubles the sprite while keeping silhouettes sharp, so
    pre-doubling once or twice and letting smoothscale finish the fractional
    remainder keeps the art legible at lawn size.
    """
    tw, th = int(size[0]), int(size[1])
    if tw < 1 or th < 1 or img.get_width() < 1 or img.get_height() < 1:
        return pygame.transform.smoothscale(img, (max(1, tw), max(1, th)))
    if tw <= img.get_width() and th <= img.get_height():
        return pygame.transform.smoothscale(img, (tw, th))
    out = img
    try:
        for _ in range(2):
            if out.get_width() * 2 <= tw and out.get_height() * 2 <= th:
                out = pygame.transform.scale2x(out)
            else:
                break
    except (pygame.error, ValueError):
        out = img
    return pygame.transform.smoothscale(out, (tw, th))


# ---------------------------------------------------------------- shadows
_shadow_cache = {}


def shadow(w, h):
    """Elliptical contact shadow: dense centre fading to a soft rim."""
    key = (int(w), int(h))
    img = _shadow_cache.get(key)
    if img is not None:
        return img
    w, h = max(2, int(w)), max(2, int(h))
    img = pygame.Surface((w, h), pygame.SRCALPHA)
    cx, cy = w / 2.0, h / 2.0
    steps = 6
    for i in range(steps, 0, -1):
        k = i / float(steps)
        rw, rh = max(1, int(cx * k)), max(1, int(cy * k))
        alpha = int(26 + 70 * (1.0 - k) ** 1.5)
        pygame.draw.ellipse(img, (12, 26, 10, alpha),
                            (cx - rw, cy - rh, rw * 2, rh * 2))
    _shadow_cache[key] = img
    return img


def _faded(img, alpha):
    """A copy of ``img`` stamped with surface-level ``alpha``.

    ``set_alpha`` on a *shared* cached surface is a mutation, not a blit
    parameter: the surface keeps the alpha for every later blit, so two
    consumers of one cache key clobber each other (the old code set the
    shadow cache to 118 for walking zombies and 70 for dying ones — every
    shadow in between rendered at whichever alpha was set last).

    Delegates to :mod:`fade_cache`, which memoizes the stamped copies per
    (sprite, quantized alpha): 30 walking zombies re-fading the same shadow
    every frame used to mint 30 copies a frame.
    """
    return fade_cache.faded(img, alpha)


def blit_shadow(screen, cx, cy, w, h=None, alpha=150):
    """Draw a cached contact shadow centred on (cx, cy)."""
    img = shadow(w, h if h is not None else max(3, w // 3))
    if alpha < 255:
        img = _faded(img, alpha)
    screen.blit(img, img.get_rect(center=(int(cx), int(cy))))


# ------------------------------------------------------- zombie headgear
_gear_cache = {}


def _shade(color, k):
    return (max(0, min(255, int(color[0] * k))),
            max(0, min(255, int(color[1] * k))),
            max(0, min(255, int(color[2] * k))))


def cone_sprite(w, h):
    """Traffic-cone hat: shaded cone body, white reflective band, dark rim."""
    key = ("cone", int(w), int(h))
    img = _gear_cache.get(key)
    if img is None:
        w, h = max(8, int(w)), max(8, int(h))
        img = pygame.Surface((w, h), pygame.SRCALPHA)
        base = (232, 118, 30)
        # cone body as a stack of shrinking horizontal bands — cheap gradient
        for y in range(h):
            t = y / float(h - 1)
            half = int((w / 2.0) * (0.10 + 0.90 * t))
            col = _shade(base, 0.72 + 0.42 * (1.0 - t) * (1.0 - abs(t - 0.45) * 0.4))
            if 0.42 < t < 0.58:
                col = (245, 245, 240)
            pygame.draw.line(img, col, (w // 2 - half, y), (w // 2 + half, y))
        # left highlight / right shadow for volume
        for y in range(h):
            t = y / float(h - 1)
            half = int((w / 2.0) * (0.10 + 0.90 * t))
            if half < 2:
                continue
            img.set_at((w // 2 - half, y), _shade(base, 0.55))
            img.set_at((w // 2 - half + 1, y), _shade(base, 0.95))
            img.set_at((w // 2 + half - 1, y), _shade(base, 0.50))
        # base flange + dark outline
        pygame.draw.rect(img, _shade(base, 0.80), (1, h - 4, w - 2, 4))
        pygame.draw.line(img, (90, 40, 8), (w // 2, 0), (1, h - 1), 1)
        pygame.draw.line(img, (90, 40, 8), (w // 2, 0), (w - 2, h - 1), 1)
        pygame.draw.rect(img, (90, 40, 8), (0, h - 2, w, 2))
        _gear_cache[key] = img
    return img


def bucket_sprite(w, h):
    """Metal bucket: brushed gradient, rim highlight, riveted bands."""
    key = ("bucket", int(w), int(h))
    img = _gear_cache.get(key)
    if img is None:
        w, h = max(10, int(w)), max(10, int(h))
        img = pygame.Surface((w, h), pygame.SRCALPHA)
        for y in range(h):
            t = y / float(h - 1)
            k = 0.70 + 0.55 * math.sin(min(1.0, t) * math.pi) * 0.5 + 0.20 * (1 - t)
            pygame.draw.line(img, _shade((168, 176, 186), k), (0, y), (w - 1, y))
        # vertical brushed-metal streaks
        for x in range(0, w, 3):
            k = 0.86 + 0.20 * ((x * 37) % 7) / 6.0
            pygame.draw.line(img, _shade((150, 158, 168), k), (x, 2), (x, h - 3), 1)
        # rolled rim
        pygame.draw.ellipse(img, (206, 214, 222), (-2, -3, w + 4, 9))
        pygame.draw.ellipse(img, (120, 128, 136), (-2, -3, w + 4, 9), 2)
        # bottom lip
        pygame.draw.rect(img, (100, 108, 116), (0, h - 4, w, 4))
        # outline
        pygame.draw.line(img, (78, 84, 92), (0, 2), (0, h - 1), 2)
        pygame.draw.line(img, (78, 84, 92), (w - 1, 2), (w - 1, h - 1), 2)
        _gear_cache[key] = img
    return img


def flag_sprite(w, h):
    """Red pennant on a wooden pole, waving with a stitched edge."""
    key = ("flag", int(w), int(h))
    img = _gear_cache.get(key)
    if img is None:
        w, h = max(12, int(w)), max(12, int(h))
        img = pygame.Surface((w, h), pygame.SRCALPHA)
        pole_x = 3
        pygame.draw.rect(img, (120, 82, 40), (pole_x - 2, 0, 4, h))
        pygame.draw.rect(img, (168, 122, 66), (pole_x - 2, 0, 2, h))
        fw, fh = w - pole_x - 2, max(8, int(h * 0.42))
        # wavy pennant: two stacked quads so it reads as cloth
        top = []
        bot = []
        for x in range(fw):
            t = x / float(max(1, fw - 1))
            wave = math.sin(t * 2.6) * (fh * 0.10)
            top.append((pole_x + 2 + x, 2 + wave))
            bot.append((pole_x + 2 + x, 2 + fh - (fh * 0.35) * t + wave))
        pts = top + bot[::-1]
        pygame.draw.polygon(img, (198, 36, 36), pts)
        pygame.draw.polygon(img, (240, 96, 84),
                            [p for p in top] + [(p[0], p[1] + 3) for p in top[::-1]])
        pygame.draw.lines(img, (120, 18, 18), True, pts, 1)
        _gear_cache[key] = img
    return img


def newspaper_sprite(w, h):
    """Folded newspaper with visible columns of type."""
    key = ("news", int(w), int(h))
    img = _gear_cache.get(key)
    if img is None:
        w, h = max(8, int(w)), max(8, int(h))
        img = pygame.Surface((w, h), pygame.SRCALPHA)
        pygame.draw.rect(img, (238, 235, 224), (0, 0, w, h), border_radius=2)
        pygame.draw.rect(img, (176, 172, 160), (0, 0, w, h), 1, border_radius=2)
        # headline bar + two columns of text lines
        pygame.draw.rect(img, (60, 58, 54), (2, 2, max(2, w - 4), 3))
        x = 3
        col_w = max(2, (w - 7) // 2)
        for c in range(2):
            cx = x + c * (col_w + 1)
            for i in range(2, h - 2, 2):
                pygame.draw.line(img, (168, 164, 154),
                                 (cx, i), (cx + col_w - 1, i), 1)
        pygame.draw.line(img, (205, 202, 192), (w // 2, 1), (w // 2, h - 1), 1)
        _gear_cache[key] = img
    return img


def pole_sprite(w, h):
    """Vaulting pole: tapered wooden shaft with an angled crop mark."""
    key = ("pole", int(w), int(h))
    img = _gear_cache.get(key)
    if img is None:
        w, h = max(4, int(w)), max(6, int(h))
        img = pygame.Surface((w, h), pygame.SRCALPHA)
        for i in range(h):
            t = i / float(max(1, h - 1))
            x = int(1 + t * (w - 4))
            pygame.draw.line(img, (176, 122, 58), (x, i), (x + 2, i))
            img.set_at((x, i), (208, 158, 92))
            img.set_at((x + 2, i), (110, 72, 30))
        _gear_cache[key] = img
    return img


def _reference_prefix(prefix):
    """Sheet whose body size defines the scale for a whole animation group.

    A zombie must not change size when it switches from walking to eating or
    dying, so every ``anim_zombie_{a,b}_*`` sheet borrows the metrics of its
    partner ``_idle`` (walking) sheet.
    """
    if prefix.startswith("anim_zombie"):
        base = prefix.rsplit("_", 1)[0]
        if _cache.get(f"{base}_idle_0") is not None:
            return f"{base}_idle"
    return prefix


def _sheet_metrics(prefix):
    """Constant (body_h, centre_x, foot_y, body_w) of a sheet, in source px.

    Medians of the per-frame bounding boxes, so one outlier frame cannot drag
    the whole animation around.
    """
    cache_key = f"_bmetrics_{prefix}"
    if cache_key in _cache:
        return _cache[cache_key]
    ref = _reference_prefix(prefix)
    boxes = []
    for i in range(_cache.get(ref + "_count", 6)):
        img = frame(ref, i)
        if img is None:
            continue
        box = img.get_bounding_rect(min_alpha=16)
        if box.width > 0 and box.height > 0:
            boxes.append(box)
    if boxes:
        metrics = (_median([b.height for b in boxes]),
                   _median([b.x + b.width / 2.0 for b in boxes]),
                   _median([b.y + b.height for b in boxes]),
                   float(_median([b.width for b in boxes])))
    else:
        metrics = (45.0, 26.0, 55.0, 26.0)   # bundled zombie sheets
    _cache[cache_key] = metrics
    return metrics


def frame_body(prefix, index, target_h):
    """Return (surface, anchor_x, baseline, body_w, body_h) for a frame.

    The whole sprite slot is smoothscaled by ONE factor per sheet
    (``target_h / median body height``) and anchored on the sheet's median
    body centre and median foot line, which the caller turns into a blit
    position with ``(foot_x - anchor_x, foot_y - baseline)``.

    Fitting each frame to its own bounding box — the previous approach — made
    the drawn body change shape from frame to frame, because the walk frames'
    silhouettes differ by up to 43% in width (21..30 px): a thin frame got
    stretched horizontally 4.7x and a wide one 3.3x, so a walking zombie
    visibly pulsed while the near-uniform eating sheet looked stable.
    """
    step = index % _cache.get(prefix + "_count", 6)
    cache_key = f"_body_{prefix}_{step}_{target_h}"
    if cache_key in _cache:
        return _cache[cache_key]
    med_h, med_cx, med_foot, med_w = _sheet_metrics(prefix)
    scale = target_h / med_h if med_h > 0 else 1.0
    img = frame(prefix, step)
    if img is None:
        surf = pygame.Surface((1, 1), pygame.SRCALPHA)
        _cache[cache_key] = (surf, 0, 0, 1, 1)
        return _cache[cache_key]
    size = (max(1, int(round(img.get_width() * scale))),
            max(1, int(round(img.get_height() * scale))))
    surf = upscale(img, size)
    result = (surf,
              int(round(med_cx * scale)),
              int(round(med_foot * scale)),
              max(1, int(round(med_w * scale))),
              int(round(med_h * scale)))
    _cache[cache_key] = result
    return result


def white_silhouette(surf):
    """A white copy of ``surf`` that keeps its alpha channel.

    ``BLEND_RGBA_MAX`` against (255,255,255,0) raises every visible pixel to
    white while leaving transparent pixels transparent — so a hit flash lights
    up the zombie's actual silhouette instead of a white box around it.
    """
    out = surf.copy()
    out.fill((255, 255, 255, 0), special_flags=pygame.BLEND_RGBA_MAX)
    return out


def frame_body_flash(prefix, index, target_h):
    """Hit-flash silhouette for a zombie body frame (cached)."""
    step = index % _cache.get(prefix + "_count", 6)
    ck = f"_bodyflash_{prefix}_{step}_{target_h}"
    hit = _cache.get(ck)
    if hit is not None:
        return hit
    body = frame_body(prefix, step, target_h)
    if body is None or body[0] is None:
        return None
    out = white_silhouette(body[0])
    _cache[ck] = out
    return out


def frame_body_tinted(prefix, index, target_h, tint, alpha):
    """``frame_body`` recoloured toward ``tint`` — elite-variant skins.

    Every non-boss zombie in this build shares one walk sheet, so the AI
    zombies would otherwise be indistinguishable from a plain zombie until you
    read their gear. A hue wash over the body gives each variant an identity
    you can read at a glance mid-wave.

    Pass a *light* tint (values near 255) and alpha 255: the multiply keeps
    the sprite's luminance and only rotates its hue. A dark tint crushes the
    shading to mud.
    """
    step = index % _cache.get(prefix + "_count", 6)
    ck = f"_bodytint_{prefix}_{step}_{target_h}_{tint}_{alpha}"
    hit = _cache.get(ck)
    if hit is not None:
        return hit
    body = frame_body(prefix, step, target_h)
    if body is None or body[0] is None:
        return None
    surf, anchor_x, baseline, bw, bh = body
    out = surf.copy()
    # BLEND_RGBA_MULT multiplies every channel including alpha, so the tint
    # lands only on pixels that were already visible and the sprite keeps its
    # own shading. A plain blit of a filled overlay would paint the sprite's
    # transparent padding solid — which is exactly what it looked like.
    out.fill((*tint, alpha), special_flags=pygame.BLEND_RGBA_MULT)
    result = (out, anchor_x, baseline, bw, bh)
    _cache[ck] = result
    return result


def frame_body_tinted_flash(prefix, index, target_h, tint, alpha):
    """Hit-flash silhouette for a tinted body frame (cached)."""
    step = index % _cache.get(prefix + "_count", 6)
    ck = f"_bodytintflash_{prefix}_{step}_{target_h}_{tint}_{alpha}"
    hit = _cache.get(ck)
    if hit is not None:
        return hit
    body = frame_body_tinted(prefix, step, target_h, tint, alpha)
    if body is None or body[0] is None:
        return None
    out = white_silhouette(body[0])
    _cache[ck] = out
    return out


def tinted_frame(prefix, index, w, h, tint, alpha):
    """Cached dark-tinted scaled frame (used by the boss)."""
    ck = f"_tint_{prefix}_{index % _cache.get(prefix + '_count', 6)}_{w}x{h}_{tint}_{alpha}"
    hit = _cache.get(ck)
    if hit is not None:
        return hit
    big = scaled_frame(prefix, index, w, h)
    if big is None:
        return None
    big = big.copy()
    overlay = pygame.Surface(big.get_size(), pygame.SRCALPHA)
    overlay.fill((*tint, alpha))
    big.blit(overlay, (0, 0))
    _cache[ck] = big
    return big


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
    count = _cache.get(prefix + "_count", 6)
    return _cache.get(f"{prefix}_{index % count}")


def scaled_frame(prefix, index, w, h):
    """Get an animation frame pre-scaled to (w, h), cached per size."""
    count = _cache.get(prefix + "_count", 6)
    ck = f"_fscale_{prefix}_{index % count}_{w}x{h}"
    if ck in _cache:
        return _cache[ck]
    f = frame(prefix, index)
    if f is None:
        return None
    s = upscale(f, (w, h))
    _cache[ck] = s
    return s


def anim_frames(prefix):
    """Return list of all 6 frames for a given prefix."""
    count = _cache.get(prefix + "_count", 6)
    return [_cache[f"{prefix}_{i}"] for i in range(count) if f"{prefix}_{i}" in _cache]


def preload(prefixes, target_h, tints=()):
    """Build every cached variant of ``prefixes`` up front.

    The body cache is keyed per (sheet, frame, height), so the first time a
    zombie plays its death animation mid-wave the engine does a scale2x plus a
    smoothscale for each cell it has not drawn yet. With a big horde that lands
    as a visible hitch exactly when something interesting is happening.
    Measured on a 34-zombie AI-level horde: 222 body surfaces were minted
    across 85 separate frames of the run, the worst frame minting 36 of them at
    once and costing 13.1 ms against a 4.1 ms average. Warming the same set
    during the level transition cuts that to 16 surfaces across 14 frames with
    no frame above the average — the work is moved, not removed, so the mean is
    unchanged; what disappears is the spike.

    ``tints`` warms the recoloured elite skins and their hit-flash
    silhouettes, which are the most expensive variants because each one copies
    and multiplies a whole body frame.
    """
    for prefix in prefixes:
        if prefix + "_count" not in _cache:
            continue                      # sheet never loaded — nothing to do
        for step in range(_cache[prefix + "_count"]):
            frame_body(prefix, step, target_h)
            # Plain zombies flash white on every hit too, and that silhouette
            # is minted on demand exactly like the tinted ones. Warming only
            # the tinted variants left an untinted flash to be built mid-wave,
            # which is the same hitch by a different name.
            frame_body_flash(prefix, step, target_h)
            for tint in tints:
                frame_body_tinted(prefix, step, target_h, *tint)
                frame_body_tinted_flash(prefix, step, target_h, *tint)


def preload_rotations(key, w, h, steps=None):
    """Build every quantized rotation of ``key`` at size ``(w, h)``.

    ``rotated`` quantizes to 24 steps of 15 degrees, so a spinning sprite walks
    the same 24-entry set once per revolution and mints one entry the first time
    it reaches each. Because the spin is slow, those land as a steady drip of
    single allocations spread across the sprite's whole lifetime rather than one
    obvious hitch — measured as thirteen separate mid-run allocations on a sun,
    one every ~23 frames. Each is individually cheap; together they are pure
    garbage-collector pressure that warming at load time removes entirely.

    Defaults to the full 24-step revolution, which is the only value that
    actually covers a continuously spinning sprite.
    """
    for step in range(24 if steps is None else steps):
        rotated(key, w, h, step)


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


def _strip_photo_backdrop(img, tol=18):
    """Remove the photo backdrop baked into the bundled wiki icons.

    ``assets/plants/cherrybomb.png`` & co. are squircle photos of the plant on
    grass / underwater, so they blit as a solid green box. Region-grow inwards
    from the border and clear every pixel within `tol` of the pixel it was
    reached through: a smooth photo gradient is eaten, the plant's own outline
    stops the fill. Bails out (returns the icon untouched) if the fill escapes
    into the plant, which would punch holes in it.
    """
    src = img.convert_alpha()
    out = src.copy()
    w, h = out.get_size()
    seen = bytearray(w * h)
    from collections import deque
    queue = deque()
    for x in range(w):
        queue.append((x, 0, x, 0))
        queue.append((x, h - 1, x, h - 1))
    for y in range(h):
        queue.append((0, y, 0, y))
        queue.append((w - 1, y, w - 1, y))
    budget = int(w * h * 0.7)
    cleared = 0
    while queue:
        x, y, rx, ry = queue.popleft()
        idx = y * w + x
        if seen[idx]:
            continue
        seen[idx] = 1
        ref = src.get_at((rx, ry))
        cur = src.get_at((x, y))
        if cur.a != 0:
            if max(abs(cur.r - ref.r), abs(cur.g - ref.g), abs(cur.b - ref.b)) > tol:
                continue
            out.set_at((x, y), (0, 0, 0, 0))
            cleared += 1
            if cleared > budget:
                return img
        for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            if 0 <= nx < w and 0 <= ny < h and not seen[ny * w + nx]:
                queue.append((nx, ny, x, y))
    return out


def _cursor_sheet(plant_type):
    """Clean sprite sheet backing a cursor icon, if the plant has one."""
    return {
        PLANT_PEASHOOTER: "anim_peashooter_idle",
        PLANT_SNOWPEA: "anim_peashooter_idle",   # caller tints it cyan
        PLANT_SUNFLOWER: "anim_sunflower_idle",
        PLANT_WALLNUT: "anim_wallnut_idle",
    }.get(plant_type)


def cursor_icon(plant_type, size):
    """Backdrop-free plant icon for the cursor ghost and the cell preview.

    Uses a clean sprite-sheet frame when the plant has one, otherwise the wiki
    icon with its photo backdrop flood-filled away. Blitting the raw wiki icon
    under the mouse painted an opaque green box over whatever it covered — a
    sun the player was reaching for simply vanished behind it.
    """
    cache_key = f"_cursor_{plant_type}_{size}"
    if cache_key in _cache:
        return _cache[cache_key]
    img = None
    prefix = _cursor_sheet(plant_type)
    if prefix:
        f = frame(prefix, 0)
        if f is not None:
            bounds = f.get_bounding_rect(min_alpha=16)
            if bounds.width > 0 and bounds.height > 0:
                img = f.subsurface(bounds).copy()
    if img is None:
        base = plant_icon(plant_type)
        if base is None:
            return None
        img = _strip_photo_backdrop(base)
    w, h = img.get_size()
    k = min(size / float(w), size / float(h))
    img = pygame.transform.smoothscale(
        img, (max(1, int(w * k)), max(1, int(h * k))))
    _cache[cache_key] = img
    return img


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
