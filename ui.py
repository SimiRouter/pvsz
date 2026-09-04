"""UI elements: seed bar, tooltips, menus."""

import math

import pygame
from constants import *
import assets_loader
import fx
from fx import cached_text
import i18n
tr = i18n.tr


def _card_image_key(plant_type):
    return {
        PLANT_PEASHOOTER: "card_peashooter",
        PLANT_SUNFLOWER: "card_sunflower",
        PLANT_WALLNUT: "card_wallnut",
        # No dedicated card art exists for these plants. Never substitute a
        # different plant's card: use the procedural card with the real icon.
        PLANT_CHERRYBOMB: None,
        PLANT_FUMESHROOM: None,
        PLANT_LILYPAD: None,
        PLANT_SNOWPEA: None,
        PLANT_COBCANNON: None,
    }.get(plant_type)


_blit_fit_cache = {}


def _blit_contained(screen, image, rect, padding=0, upscale=True):
    """Aspect-fit an image inside rect and clip strictly to that container."""
    if image is None:
        return None
    inner = pygame.Rect(rect).inflate(-padding * 2, -padding * 2)
    if inner.w <= 0 or inner.h <= 0:
        return None
    iw, ih = image.get_size()
    if iw <= 0 or ih <= 0:
        return None
    scale = min(inner.w / iw, inner.h / ih)
    if not upscale:
        scale = min(1.0, scale)
    size = (max(1, int(iw * scale)), max(1, int(ih * scale)))
    # Cache the fitted surface: seed cards redraw every frame, and
    # smoothscaling the same source to the same size each frame is waste.
    key = (id(image), size)
    fitted = _blit_fit_cache.get(key)
    if fitted is None:
        fitted = pygame.transform.smoothscale(image, size) if size != (iw, ih) else image
        _blit_fit_cache[key] = fitted
    dest = fitted.get_rect(center=inner.center)
    old_clip = screen.get_clip()
    screen.set_clip(rect)
    screen.blit(fitted, dest)
    screen.set_clip(old_clip)
    return dest


def _fit_font(text, max_width, max_size=18, min_size=10):
    """Choose the largest cached CJK-capable font that fits max_width."""
    for size in range(max_size, min_size - 1, -1):
        f = i18n.font(size)
        if f.size(text)[0] <= max_width:
            return f
    return i18n.font(min_size)


def _dim_overlay(alpha):
    """Shared translucent full-screen overlay (one per alpha value, reused)."""
    key = ("_dim", alpha)
    surf = _blit_fit_cache.get(key)
    if surf is None:
        surf = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
        surf.fill((0, 0, 0, alpha))
        _blit_fit_cache[key] = surf
    return surf


def draw_button(screen, rect, label, base_color, hover=False, font=None,
                font_size=28, selected_border=(255, 255, 0)):
    """Shared rounded button with hover glow and outlined label."""
    r = pygame.Rect(rect)
    # ---- Hover halo: expanding ring drawn BEHIND the button ----
    # Re-create a transient state object on each frame so this stays pure.
    if hover:
        # Two concentric soft rings expanding outward + fading
        for k, (delay_t, color, base_w) in enumerate([
            (0.0, selected_border, 8),   # bright outer
            (0.20, base_color, 6),       # colored inner
        ]):
            # ramp 0..1 over ~0.45s, offset by delay_t
            t = max(0.0, min(1.0, _hover_phase(delay_t)))
            if t <= 0.0:
                continue
            # alpha fades, radius grows
            alpha = int(160 * (1.0 - t))
            grow = int(2 + 18 * t)
            halo_w = base_w + grow
            halo_rect = r.inflate(grow * 2, grow)
            halo = pygame.Surface(halo_rect.size, pygame.SRCALPHA)
            pygame.draw.rect(halo, (*color, alpha), halo.get_rect(),
                             halo_w, border_radius=12)
            screen.blit(halo, halo_rect.topleft)
    if hover:
        color = tuple(min(255, c + 50) for c in base_color)
        r = r.inflate(8, 6)
        pygame.draw.rect(screen, color, r, border_radius=10)
        pygame.draw.rect(screen, selected_border, r, 3, border_radius=10)
    else:
        pygame.draw.rect(screen, base_color, r, border_radius=10)
        pygame.draw.rect(screen, (0, 0, 0), r, 3, border_radius=10)
    if font is None:
        # cached render: menus redraw every frame, font.render x5 is waste
        t = cached_text(label, font_size, COLOR_WHITE, outline=(0, 0, 0))
        screen.blit(t, t.get_rect(center=r.center))
        return
    t = font.render(label, True, COLOR_WHITE)
    for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
        outline = font.render(label, True, (0, 0, 0))
        screen.blit(outline, (r.centerx - t.get_width() // 2 + dx,
                              r.centery - t.get_height() // 2 + dy))
    screen.blit(t, (r.centerx - t.get_width() // 2,
                    r.centery - t.get_height() // 2))


# Persistent phase tracker for hover halo (read by draw_button).
# Stored at module level so multiple callers share the same ramp state.
import time as _time
_hover_phase_state = {"last_hover": 0.0, "phase": 0.0}


def _hover_phase(delay_t=0.0):
    """Return 0..1 ramp since the last hover state flip; subtract delay_t offset."""
    now = _time.time()
    last = _hover_phase_state["last_hover"]
    # Reset phase if it has been > 1.0s since last hover (i.e. button is idle)
    if now - last > 0.6:
        return 0.0
    return max(0.0, min(1.0, (now - last) - delay_t))


def pulse_hover():
    """Call when a menu button transitions to hovered (mouse entered / focused)."""
    _hover_phase_state["last_hover"] = _time.time()


class SeedButton:
    def __init__(self, plant_type, x, y, w, h):
        self.plant_type = plant_type
        self.x = x
        self.y = y
        self.w = w
        self.h = h
        self.info = PLANT_INFO[plant_type]
        self.selected = False
        self.can_afford = True
        self.cooldown_remaining = 0  # ms remaining
        self.cooldown_max = 0
        self._prev_cooldown = 0.0
        self.ready_flash = 0.0   # golden pulse when the card finishes cooling
        self._dim_red = None    # cached "cannot afford" overlay
        self._dim_black = None  # cached cooldown overlay (blitted as subslice)

    def update(self, sun, plant_cooldowns, dt=0.0):
        self.can_afford = sun >= self.info["cost"]
        # plant_cooldowns is stored in seconds (matches PLANT_INFO["cooldown"] units)
        if self.plant_type in plant_cooldowns:
            self.cooldown_remaining = plant_cooldowns[self.plant_type]
            self.cooldown_max = self.info["cooldown"]
        else:
            self.cooldown_remaining = 0
            self.cooldown_max = self.info["cooldown"]
        # finished cooling this frame → flash like the original seed bank
        if self._prev_cooldown > 0 and self.cooldown_remaining <= 0:
            self.ready_flash = 0.7
        self._prev_cooldown = self.cooldown_remaining
        if self.ready_flash > 0:
            self.ready_flash = max(0.0, self.ready_flash - dt)

    def _dim_surfaces(self):
        if self._dim_red is None:
            self._dim_red = pygame.Surface((self.w, self.h), pygame.SRCALPHA)
            self._dim_red.fill((80, 30, 30, 130))
            self._dim_black = pygame.Surface((self.w, self.h), pygame.SRCALPHA)
            self._dim_black.fill((0, 0, 0, 200))
        return self._dim_red, self._dim_black

    def tooltip_lines(self):
        """Hover info: name, cost, cooldown, one-line description."""
        desc = tr(PLANT_DESC.get(self.plant_type, ""))
        lines = [i18n.plant_name(self.plant_type),
                 f"{tr('Cost')}: {self.info['cost']}   {tr('Cooldown')}: {self.info['cooldown']}{tr('s')}"]
        if desc:
            lines.append(desc)
        lines.append(tr("Plant again on the same plant to upgrade (max Lv3)"))
        return "\n".join(lines)

    def draw(self, screen, font):
        slot = pygame.Rect(self.x, self.y, self.w, self.h)
        old_clip = screen.get_clip()
        screen.set_clip(slot)
        # full seed packet image (preferred)
        card_key = _card_image_key(self.plant_type)
        card_img = assets_loader.get(card_key) if card_key else None

        if card_img is not None:
            _blit_contained(screen, card_img, slot)
            # desaturate/darken when cannot afford or in cooldown
            if not self.can_afford or self.cooldown_remaining > 0:
                dim_red, dim_black = self._dim_surfaces()
                if not self.can_afford:
                    screen.blit(dim_red, slot.topleft)
                else:
                    ratio = max(0.0, min(1.0, self.cooldown_remaining / self.cooldown_max)) if self.cooldown_max > 0 else 0
                    overlay_h = int(self.h * ratio)
                    if overlay_h > 0:
                        screen.blit(dim_black, (self.x, self.y + self.h - overlay_h),
                                    (0, self.h - overlay_h, self.w, overlay_h))

            # cooldown remaining seconds text
            if self.cooldown_remaining > 0:
                cd_text = fx.cached_text(f"{self.cooldown_remaining:.1f}", 16, COLOR_WHITE, outline=(0, 0, 0))
                screen.blit(cd_text, cd_text.get_rect(center=slot.center))
            screen.set_clip(old_clip)
            # selection border stays INSIDE the card slot; golden pulse right
            # after the card finishes cooling (original seed-bank behavior)
            border = (35, 25, 15)
            if self.selected:
                border = (255, 255, 150)
            elif self.ready_flash > 0 and self.can_afford:
                pulse = abs(math.sin(self.ready_flash * 14))
                border = (255, int(190 + 60 * pulse), int(40 + 60 * pulse))
            pygame.draw.rect(screen, border, slot, 3 if (self.selected or
                             (self.ready_flash > 0 and self.can_afford)) else 1,
                             border_radius=5)
            return

        # fallback procedural card (when dedicated art is missing)
        base_color = (70, 70, 75) if self.can_afford else (100, 50, 50)
        if self.selected:
            base_color = (90, 90, 95)
        pygame.draw.rect(screen, base_color, slot, border_radius=6)

        icon_size = min(36, self.w - 8, self.h - 24)
        ix = self.x + (self.w - icon_size) // 2
        iy = self.y + 4
        self._draw_icon(screen, ix, iy, icon_size)

        cost_str = str(self.info["cost"])
        cost_color = COLOR_YELLOW if self.can_afford else COLOR_RED
        ct = fx.cached_text(cost_str, 15, cost_color, outline=(0, 0, 0))
        screen.blit(ct, (self.x + self.w - ct.get_width() - 3, self.y + self.h - ct.get_height() - 2))

        if self.cooldown_remaining > 0:
            ratio = max(0.0, min(1.0, self.cooldown_remaining / self.cooldown_max)) if self.cooldown_max > 0 else 0
            overlay_h = int(self.h * ratio)
            pygame.draw.rect(screen, (0, 0, 0, 180),
                             (self.x, self.y + self.h - overlay_h, self.w, overlay_h), border_radius=6)
            cd_text = fx.cached_text(f"{self.cooldown_remaining:.1f}", 14, COLOR_WHITE, outline=(0, 0, 0))
            screen.blit(cd_text, cd_text.get_rect(center=slot.center))
        screen.set_clip(old_clip)
        pygame.draw.rect(screen, (255, 255, 150) if self.selected else COLOR_WHITE,
                         slot, 3 if self.selected else 2, border_radius=6)

    def _draw_icon(self, screen, x, y, size):
        # try to use real plant sprite (96x96 source)
        img = assets_loader.plant_icon(self.plant_type)
        if img is not None:
            scaled = pygame.transform.smoothscale(img, (size, size))
            screen.blit(scaled, (x, y))
            return
        # fallback drawings
        if self.plant_type == PLANT_PEASHOOTER:
            pygame.draw.ellipse(screen, (0, 140, 0), (x, y + 6, size, size - 6))
            pygame.draw.circle(screen, (40, 170, 40), (x + size // 2, y + size // 2), size // 3)
        elif self.plant_type == PLANT_SUNFLOWER:
            pygame.draw.circle(screen, COLOR_YELLOW, (x + size // 2, y + size // 2), size // 2)
            pygame.draw.circle(screen, COLOR_ORANGE, (x + size // 2, y + size // 2), size // 2, 2)
        elif self.plant_type == PLANT_WALLNUT:
            pygame.draw.ellipse(screen, (150, 110, 50), (x, y + 4, size, size - 4))
        elif self.plant_type == PLANT_CHERRYBOMB:
            pygame.draw.circle(screen, (200, 20, 20), (x + size // 2, y + size // 2), size // 2)
        elif self.plant_type == PLANT_FUMESHROOM:
            pygame.draw.ellipse(screen, (70, 0, 110), (x, y + 6, size, size - 6))
        elif self.plant_type == PLANT_SNOWPEA:
            # peashooter body in cool blues
            pygame.draw.ellipse(screen, (50, 120, 170), (x, y + 6, size, size - 6))
            pygame.draw.circle(screen, (140, 220, 255), (x + size // 2, y + size // 2), size // 3)
        elif self.plant_type == PLANT_LILYPAD:
            # water
            pygame.draw.ellipse(screen, (70, 140, 220), (x, y + size - 10, size, 8))
            # pad
            pygame.draw.ellipse(screen, (40, 150, 60), (x, y + 2, size, size - 10))
            pygame.draw.ellipse(screen, (90, 200, 110), (x + size // 4, y + size // 4, size // 2, size // 2 - 6))
            # notch
            pygame.draw.polygon(screen, (40, 150, 60), [
                (x + size - 4, y + size // 2),
                (x + size - 4, y + size // 2 - 8),
                (x + size + 2, y + size // 2 - 8),
            ])

    def contains(self, mx, my):
        return self.x <= mx <= self.x + self.w and self.y <= my <= self.y + self.h


class Tooltip:
    def __init__(self):
        self.visible = False
        self.text = ""
        self.x = 0
        self.y = 0
        self._lines = None  # rendered cache for the current text
        self._line_w = 0

    def show(self, text, x, y):
        if text != self.text:
            self._lines = None
        self.visible = True
        self.text = text
        self.x = x
        self.y = y

    def hide(self):
        self.visible = False

    def update(self, dt):
        pass  # tooltip visibility is controlled manually

    def _render_lines(self, font):
        if self._lines is None:
            lines = self.text.split("\n")
            self._lines = [font.render(line, True, COLOR_WHITE) for line in lines]
            self._line_w = max(l.get_width() for l in self._lines) if self._lines else 0
        return self._lines

    def draw(self, screen, font):
        if not self.visible or not self.text:
            return
        lines = self._render_lines(font)
        tw = self._line_w + 20
        th = len(lines) * 22 + 12
        # clamp to screen
        self.x = max(5, min(self.x, SCREEN_WIDTH - tw - 5))
        self.y = max(UI_BAR_H + 5, min(self.y, SCREEN_HEIGHT - th - 5))
        pygame.draw.rect(screen, (30, 30, 30, 230), (self.x, self.y, tw, th), border_radius=6)
        pygame.draw.rect(screen, COLOR_WHITE, (self.x, self.y, tw, th), 1, border_radius=6)
        for i, line in enumerate(lines):
            screen.blit(line, (self.x + 10, self.y + 6 + i * 22))


class Message:
    def __init__(self):
        self.text = ""
        self.timer = 0
        self.duration = 0
        self._surf = None
        self._surf_font_size = 0

    def show(self, text, duration=2000):
        self.text = text
        # Call sites pass milliseconds; update() receives seconds.
        self.duration = max(0.0, duration / 1000.0)
        self.timer = 0
        self._surf = None

    def update(self, dt):
        if self.duration > 0:
            self.timer += dt
            if self.timer >= self.duration:
                self.text = ""
                self.duration = 0
                self._surf = None

    def draw(self, screen, font):
        if not self.text:
            return
        if self._surf is None:
            t = font.render(self.text, True, COLOR_WHITE)
            max_w = SCREEN_WIDTH - 40
            if t.get_width() > max_w:
                f = _fit_font(self.text, max_w, 20, 10)
                t = f.render(self.text, True, COLOR_WHITE)
            self._surf = t  # rendered once per message
        t = self._surf
        y = UI_BAR_H + 8
        bg = pygame.Rect(SCREEN_WIDTH // 2 - t.get_width() // 2 - 10,
                         y, t.get_width() + 20, t.get_height() + 10)
        pygame.draw.rect(screen, (0, 0, 0, 180), bg, border_radius=6)
        screen.blit(t, (SCREEN_WIDTH // 2 - t.get_width() // 2, y + 5))


class MenuScreen:
    def __init__(self):
        self.title_font = i18n.font(72)
        self.font = i18n.font(32)
        self.small_font = i18n.font(24)
        self.btn_font = i18n.font(36)
        # Visible buttons
        bw, bh = 280, 60
        cx = SCREEN_WIDTH // 2
        self.btn_start = pygame.Rect(0, 0, bw, bh)
        self.btn_start.center = (cx, 390)
        self.btn_help = pygame.Rect(0, 0, bw, bh)
        self.btn_help.center = (cx, 470)
        self.btn_quit = pygame.Rect(0, 0, bw, bh)
        self.btn_quit.center = (cx, 550)
        self.lang_btn = pygame.Rect(SCREEN_WIDTH - 118, 16, 100, 40)
        self._hover = None
        self.show_help = False

    def handle_mouse(self, mx, my):
        if self.lang_btn.collidepoint(mx, my):
            return "lang"
        if self.btn_start.collidepoint(mx, my):
            return "start"
        if self.btn_help.collidepoint(mx, my):
            return "help"
        if self.btn_quit.collidepoint(mx, my):
            return "quit"
        return None

    def update_hover(self, mx, my):
        prev = self._hover
        self._hover = None
        if self.lang_btn.collidepoint(mx, my):
            self._hover = "lang"
        elif self.btn_start.collidepoint(mx, my):
            self._hover = "start"
        elif self.btn_help.collidepoint(mx, my):
            self._hover = "help"
        elif self.btn_quit.collidepoint(mx, my):
            self._hover = "quit"
        if self._hover and self._hover != prev:
            pulse_hover()

    def draw(self, screen):
        import assets_loader
        bg = assets_loader.get("bg_day_full")
        if bg:
            screen.blit(bg, (0, 0))
            screen.blit(_dim_overlay(110), (0, 0))
        else:
            screen.fill((50, 100, 50))
        title = cached_text("PLANTS VS ZOMBIES", 72, (255, 230, 0), outline=(0, 0, 0))
        screen.blit(title, (SCREEN_WIDTH // 2 - title.get_width() // 2, 80))
        sub = self.font.render(tr("Python Edition"), True, COLOR_WHITE)
        screen.blit(sub, (SCREEN_WIDTH // 2 - sub.get_width() // 2, 170))
        instr = self.small_font.render(tr("Click a seed packet, then click the lawn to plant"), True, COLOR_WHITE)
        screen.blit(instr, (SCREEN_WIDTH // 2 - instr.get_width() // 2, 220))
        instr2 = self.small_font.render(tr("Click falling suns to collect them"), True, COLOR_WHITE)
        screen.blit(instr2, (SCREEN_WIDTH // 2 - instr2.get_width() // 2, 250))
        # Buttons
        self._draw_btn(screen, self.btn_start, tr("Start Game"), "start", (60, 130, 60))
        self._draw_btn(screen, self.btn_help, tr("How to Play"), "help", (60, 90, 130))
        self._draw_btn(screen, self.btn_quit, tr("Quit"), "quit", (130, 60, 60))
        # language toggle button (top-right)
        lang = "中文" if not i18n.is_zh() else "EN"
        lrect = self.lang_btn
        pygame.draw.rect(screen, (100, 100, 115) if self._hover == "lang" else (70, 70, 80),
                         lrect, border_radius=8)
        pygame.draw.rect(screen, (200, 200, 200), lrect, 2, border_radius=8)
        lt = self.small_font.render(lang, True, COLOR_WHITE)
        screen.blit(lt, (lrect.centerx - lt.get_width() // 2, lrect.centery - lt.get_height() // 2))

        if self.show_help:
            panel = pygame.Rect(SCREEN_WIDTH // 2 - 360, 258, 720, 118)
            pygame.draw.rect(screen, (20, 25, 22, 225), panel, border_radius=10)
            pygame.draw.rect(screen, (220, 220, 180), panel, 2, border_radius=10)
            lines = [
                tr("Click a seed packet, then click the lawn to plant"),
                tr("Click falling suns to collect them"),
                tr("Collect falling plant food, then click a plant to feed it"),
                "P: " + tr("PAUSED") + "   F: " + tr("Speed x2") + "   M: " + tr("Sound OFF") + "   F11: Fullscreen",
            ]
            for i, line in enumerate(lines):
                f = _fit_font(line, panel.w - 24, 18, 11)
                txt = f.render(line, True, COLOR_WHITE)
                screen.blit(txt, txt.get_rect(center=(panel.centerx, panel.y + 18 + i * 26)))

    def _draw_btn(self, screen, rect, label, key, base_color):
        draw_button(screen, rect, label, base_color, self._hover == key, font_size=36)


class GameOverScreen:
    """Defeat screen with Retry / Main Menu buttons (click or Enter)."""

    def __init__(self):
        self.font = i18n.font(48)
        self.small_font = i18n.font(28)
        bw, bh = 280, 58
        cx = SCREEN_WIDTH // 2
        self.btn_retry = pygame.Rect(0, 0, bw, bh); self.btn_retry.center = (cx, 380)
        self.btn_menu = pygame.Rect(0, 0, bw, bh); self.btn_menu.center = (cx, 460)
        self._hover = None

    def update_hover(self, mx, my):
        prev = self._hover
        self._hover = None
        if self.btn_retry.collidepoint(mx, my):
            self._hover = "retry"
        elif self.btn_menu.collidepoint(mx, my):
            self._hover = "menu"
        if self._hover and self._hover != prev:
            pulse_hover()

    def handle_mouse(self, mx, my):
        self.update_hover(mx, my)
        return self._hover

    def draw(self, screen, wave_num, survival=False):
        screen.blit(_dim_overlay(180), (0, 0))
        if survival:
            if i18n.is_zh():
                text = self.font.render(f"你坚持了 {max(0, wave_num - 1)} 波！", True, COLOR_WHITE)
            else:
                text = self.font.render(f"You survived {max(0, wave_num - 1)} waves!", True, COLOR_WHITE)
        else:
            text = self.font.render(tr("Game Over!"), True, COLOR_RED)
        screen.blit(text, (SCREEN_WIDTH // 2 - text.get_width() // 2, 170))
        if not survival:
            # the iconic line from the original defeat screen
            brains = self.small_font.render(tr("The zombies ate your brains!"), True, (235, 60, 50))
            screen.blit(brains, (SCREEN_WIDTH // 2 - brains.get_width() // 2, 260))
        draw_button(screen, self.btn_retry, tr("Retry"), (60, 130, 60), self._hover == "retry")
        draw_button(screen, self.btn_menu, tr("Main Menu"), (130, 60, 60), self._hover == "menu")
        sub = cached_text(tr("Click to return to menu"), 28, (200, 200, 200), outline=(0, 0, 0))
        screen.blit(sub, (SCREEN_WIDTH // 2 - sub.get_width() // 2, 540))


class LevelCompleteScreen:
    """Victory screen with Next Level / Back to Map buttons (click or Enter)."""

    def __init__(self):
        self.font = i18n.font(48)
        self.small_font = i18n.font(28)
        bw, bh = 280, 58
        cx = SCREEN_WIDTH // 2
        self.btn_next = pygame.Rect(0, 0, bw, bh); self.btn_next.center = (cx, 380)
        self.btn_map = pygame.Rect(0, 0, bw, bh); self.btn_map.center = (cx, 460)
        self._hover = None

    def update_hover(self, mx, my):
        prev = self._hover
        self._hover = None
        if self.btn_next.collidepoint(mx, my):
            self._hover = "next"
        elif self.btn_map.collidepoint(mx, my):
            self._hover = "map"
        if self._hover and self._hover != prev:
            pulse_hover()

    def handle_mouse(self, mx, my):
        self.update_hover(mx, my)
        return self._hover

    def draw(self, screen):
        screen.blit(_dim_overlay(180), (0, 0))
        text = self.font.render(tr("Victory! You saved the house!"), True, (120, 255, 120))
        screen.blit(text, (SCREEN_WIDTH // 2 - text.get_width() // 2, 200))
        draw_button(screen, self.btn_next, tr("Next Level"), (60, 130, 60), self._hover == "next")
        draw_button(screen, self.btn_map, tr("Back to Map"), (60, 90, 130), self._hover == "map")
        sub = cached_text(tr("Click to play again"), 28, (200, 200, 200), outline=(0, 0, 0))
        screen.blit(sub, (SCREEN_WIDTH // 2 - sub.get_width() // 2, 540))


class PauseScreen:
    """Pause overlay with clickable Resume / Restart / Main Menu buttons."""

    def __init__(self):
        self.font = i18n.font(48)
        self.small_font = i18n.font(28)
        bw, bh = 280, 58
        cx = SCREEN_WIDTH // 2
        self.btn_resume = pygame.Rect(0, 0, bw, bh); self.btn_resume.center = (cx, 300)
        self.btn_restart = pygame.Rect(0, 0, bw, bh); self.btn_restart.center = (cx, 380)
        self.btn_menu = pygame.Rect(0, 0, bw, bh); self.btn_menu.center = (cx, 460)
        self._hover = None

    def update_hover(self, mx, my):
        prev = self._hover
        self._hover = None
        for name, rect in (("resume", self.btn_resume), ("restart", self.btn_restart),
                           ("menu", self.btn_menu)):
            if rect.collidepoint(mx, my):
                self._hover = name
        if self._hover and self._hover != prev:
            pulse_hover()

    def handle_mouse(self, mx, my):
        self.update_hover(mx, my)
        return self._hover

    def draw(self, screen):
        screen.blit(_dim_overlay(150), (0, 0))
        text = self.font.render(tr("PAUSED"), True, COLOR_WHITE)
        screen.blit(text, (SCREEN_WIDTH // 2 - text.get_width() // 2, 170))
        draw_button(screen, self.btn_resume, tr("Resume"), (60, 130, 60), self._hover == "resume")
        draw_button(screen, self.btn_restart, tr("Restart"), (60, 90, 130), self._hover == "restart")
        draw_button(screen, self.btn_menu, tr("Main Menu"), (130, 60, 60), self._hover == "menu")
        sub = self.small_font.render("P: " + tr("Resume") + "   Esc: " + tr("Main Menu"), True, (170, 170, 170))
        screen.blit(sub, (SCREEN_WIDTH // 2 - sub.get_width() // 2, 540))


# ============================================================
# Mode Select Screen
# ============================================================
class ModeButton:
    def __init__(self, mode_id, label, desc, x, y, w, h):
        self.mode_id = mode_id
        self.label = label
        self.desc = desc
        self.x = x
        self.y = y
        self.w = w
        self.h = h
        self.hover = False

    def contains(self, mx, my):
        return self.x <= mx <= self.x + self.w and self.y <= my <= self.y + self.h

    def draw(self, screen, font):
        color = (80, 120, 80) if self.hover else (60, 90, 60)
        pygame.draw.rect(screen, color, (self.x, self.y, self.w, self.h), border_radius=10)
        pygame.draw.rect(screen, COLOR_WHITE, (self.x, self.y, self.w, self.h), 2, border_radius=10)
        # label
        lt = font.render(tr(self.label), True, COLOR_WHITE)
        screen.blit(lt, (self.x + self.w // 2 - lt.get_width() // 2, self.y + 12))
        # desc
        dt = i18n.font(20).render(tr(self.desc), True, (180, 180, 180))
        screen.blit(dt, (self.x + self.w // 2 - dt.get_width() // 2, self.y + 48))


class ModeSelectScreen:
    def __init__(self):
        self.title_font = i18n.font(56)
        self.font = i18n.font(28)
        self.buttons = []
        bw = 280
        bh = 120
        spacing = 30
        total_w = bw * 2 + spacing
        start_x = (SCREEN_WIDTH - total_w) // 2
        y = 200

        self.buttons.append(ModeButton(MODE_ADVENTURE, "Adventure", "16 levels, 5 worlds", start_x, y, bw, bh))
        self.buttons.append(ModeButton(MODE_SURVIVAL, "Survival", "Endless waves", start_x + bw + spacing, y, bw, bh))

    def handle_mouse(self, mx, my, activate=True):
        """Update hover state; return mode id only when activate=True."""
        hit = None
        for btn in self.buttons:
            btn.hover = btn.contains(mx, my)
            if btn.hover:
                hit = btn.mode_id
        return hit if activate else None

    def draw(self, screen):
        import assets_loader
        bg = assets_loader.get("bg_day_full")
        if bg:
            screen.blit(bg, (0, 0))
            screen.blit(_dim_overlay(80), (0, 0))
        else:
            screen.fill((40, 80, 40))
        title = self.title_font.render(tr("Select Game Mode"), True, COLOR_WHITE)
        screen.blit(title, (SCREEN_WIDTH // 2 - title.get_width() // 2, 80))
        for btn in self.buttons:
            btn.draw(screen, self.font)
        back = cached_text(tr("Click to go back"), 28, (210, 210, 210), outline=(0, 0, 0))
        screen.blit(back, (SCREEN_WIDTH // 2 - back.get_width() // 2, SCREEN_HEIGHT - 50))


# ============================================================
# Level Select Screen
# ============================================================
class LevelCard:
    def __init__(self, level, x, y, w, h, unlocked):
        self.level = level
        self.x = x
        self.y = y
        self.w = w
        self.h = h
        self.unlocked = unlocked
        self.hover = False
        self._texts = None  # rendered label cache (cards redraw every frame)

    def contains(self, mx, my):
        return self.x <= mx <= self.x + self.w and self.y <= my <= self.y + self.h

    def _render_texts(self):
        if self._texts is None:
            lv = self.level
            texts = {}
            name_text = i18n.fmt_level_name(str(lv.get("name") or lv.get("id", "")))
            name_font = _fit_font(name_text, self.w - 18, 18, 10)
            texts["name"] = name_font.render(name_text, True, COLOR_WHITE)
            if "plants" in lv and "waves" in lv:
                pl_txt = f"{len(lv['plants'])} {tr('plants')}"
                wv_txt = f"{len(lv['waves'])} {tr('waves')}"
                meta_font = _fit_font(pl_txt + "  " + wv_txt, self.w - 16, 14, 9)
                texts["meta"] = meta_font.render(pl_txt + "  " + wv_txt, True, (205, 205, 205))
            elif "desc" in lv:
                desc = tr(lv["desc"])
                desc_font = _fit_font(desc, self.w - 16, 14, 9)
                texts["desc"] = desc_font.render(desc, True, (205, 205, 205))
                endless = tr("Endless waves")
                texts["endless"] = _fit_font(endless, self.w - 16, 14, 9).render(
                    endless, True, (255, 210, 110))
            self._texts = texts
        return self._texts

    def draw(self, screen, font):
        rect = pygame.Rect(self.x, self.y, self.w, self.h)
        old_clip = screen.get_clip()
        screen.set_clip(rect)
        if not self.unlocked:
            pygame.draw.rect(screen, (50, 40, 40), rect, border_radius=8)
            pygame.draw.rect(screen, (80, 60, 60), rect, 2, border_radius=8)
            lock_text = tr("LOCKED")
            lock_font = _fit_font(lock_text, self.w - 12, 22, 11)
            lock = lock_font.render(lock_text, True, (180, 140, 140))
            screen.blit(lock, lock.get_rect(center=rect.center))
            screen.set_clip(old_clip)
            return

        color = (78, 105, 72) if self.hover else (50, 72, 50)
        pygame.draw.rect(screen, color, rect, border_radius=8)
        pygame.draw.rect(screen, (255, 230, 120) if self.hover else COLOR_WHITE,
                         rect, 3 if self.hover else 2, border_radius=8)

        texts = self._render_texts()
        lv = self.level
        screen.blit(texts["name"], (self.x + 8, self.y + 7))

        if "meta" in texts:
            meta = texts["meta"]
            screen.blit(meta, (self.x + 8, self.y + self.h - meta.get_height() - 6))
            badge_color = self._world_color(lv.get("world", 1))
            badge = pygame.Rect(self.x + self.w - 28, self.y + 6, 22, 22)
            pygame.draw.rect(screen, badge_color, badge, border_radius=4)
            wn = cached_text(str(lv["world"]), 14, COLOR_WHITE, outline=(0, 0, 0))
            screen.blit(wn, wn.get_rect(center=badge.center))
        elif "desc" in texts:
            screen.blit(texts["desc"], (self.x + 8, self.y + 34))
            et = texts["endless"]
            screen.blit(et, (self.x + 8, self.y + self.h - et.get_height() - 6))
        screen.set_clip(old_clip)

    def _world_color(self, world):
        colors = {
            1: (200, 200, 50),   # Day - yellow
            2: (100, 80, 160),   # Night - purple
            3: (50, 120, 200),   # Pool - blue
            4: (140, 160, 180),  # Fog - gray
            5: (180, 100, 60),   # Roof - orange
        }
        return colors.get(world, (100, 100, 100))


class LevelSelectScreen:
    def __init__(self):
        self.title_font = i18n.font(44)
        self.font = i18n.font(24)
        self.cards = []
        self.world_labels = ["Day", "Night", "Pool", "Fog", "Roof"]
        self.title = "Adventure Mode"
        self.show_world_labels = True

    def set_items(self, items, title, unlocked_ids=None):
        """Build cards that always fit inside the 1400x600 logical canvas."""
        self.cards = []
        self.title = title
        self.show_world_labels = any("world" in item for item in items)

        if self.show_world_labels:
            # Five horizontal world rows. Each world's 3-4 levels stay together.
            # This fixes the old 3-column layout where 16 cards created six rows
            # and the last cards were outside the 600px window.
            cw, ch = 255, 76
            gap_x, gap_y = 12, 14
            start_x, start_y = 120, 82
            world_counts = {}
            for item in items:
                world = item.get("world", 1)
                col = world_counts.get(world, 0)
                world_counts[world] = col + 1
                cx = start_x + col * (cw + gap_x)
                cy = start_y + (world - 1) * (ch + gap_y)
                unlocked = unlocked_ids is None or item["id"] in unlocked_ids
                self.cards.append(LevelCard(item, cx, cy, cw, ch, unlocked))
        else:
            # Survival: five modes fit in one centered row.
            cw, ch = 225, 104
            gap = 16
            total = len(items) * cw + max(0, len(items) - 1) * gap
            start_x = (SCREEN_WIDTH - total) // 2
            for i, item in enumerate(items):
                unlocked = unlocked_ids is None or item["id"] in unlocked_ids
                self.cards.append(LevelCard(item, start_x + i * (cw + gap), 210,
                                            cw, ch, unlocked))

    def handle_mouse(self, mx, my, activate=True):
        hit = None
        prev_hover = any(c.hover for c in self.cards)
        for card in self.cards:
            was_hover = card.hover
            card.hover = card.contains(mx, my) and card.unlocked
            if card.hover and not was_hover:
                pulse_hover()
            if card.hover:
                hit = card.level["id"]
        return hit if activate else None

    def draw(self, screen):
        import assets_loader
        bg = assets_loader.get("bg_day_full")
        if bg:
            screen.blit(bg, (0, 0))
            screen.blit(_dim_overlay(100), (0, 0))
        else:
            screen.fill((30, 60, 30))
        title = self.title_font.render(self.title, True, COLOR_WHITE)
        screen.blit(title, (SCREEN_WIDTH // 2 - title.get_width() // 2, 20))

        if self.show_world_labels:
            y_base = 82
            for w in range(5):
                label = self.font.render(tr(self.world_labels[w]), True, (240, 220, 120))
                screen.blit(label, (18, y_base + w * 90 + (76 - label.get_height()) // 2))

        for card in self.cards:
            card.draw(screen, self.font)

        back = cached_text(tr("Click card to select  |  Backspace to return"), 24,
                           (235, 235, 235), outline=(0, 0, 0))
        screen.blit(back, (SCREEN_WIDTH // 2 - back.get_width() // 2, SCREEN_HEIGHT - 40))


# ============================================================
# Seed Select Screen (PvZ: pick your plant loadout before a level)
# ============================================================
class SeedSelectScreen:
    """Choose which seed cards to bring into an adventure level.

    Pool layout: left column = the level's available plants; clicking toggles
    a plant into the "pack" (right column). Confirm with the Start button.
    """

    def __init__(self):
        self.title_font = i18n.font(48)
        self.font = i18n.font(24)
        self.big_font = i18n.font(30)
        self.available = []      # plant types shown in the pool
        self.picked = []         # plant types currently in the pack
        self.title = ""
        self.level_name = ""
        self.card_w = 132
        self.card_h = 144
        self.gap = 14
        self._hover = None
        # buttons
        self.start_btn = pygame.Rect(0, 0, 220, 64)
        self.start_btn.bottomright = (SCREEN_WIDTH - 30, SCREEN_HEIGHT - 30)
        self.back_btn = pygame.Rect(0, 0, 160, 50)
        self.back_btn.bottomleft = (30, SCREEN_HEIGHT - 30)

    def set_level(self, level):
        """Configure for an adventure level dict."""
        self.title = "Choose your plants"
        self.level_name = level["name"]
        self.available = list(level["plants"])
        # default pack = everything available (level-limited roster)
        self.picked = list(level["plants"])

    def handle_mouse(self, mx, my, activate=True):
        """Update hover; return action only for an activating click."""
        self._hover = None
        if self.start_btn.collidepoint(mx, my):
            self._hover = "start"
            return "start" if activate else None
        if self.back_btn.collidepoint(mx, my):
            self._hover = "back"
            return "back" if activate else None
        for ptype, r in self._card_rects().items():
            if r.collidepoint(mx, my):
                self._hover = ("seed", ptype)
                return ("toggle", ptype) if activate else None
        return None

    def _card_rects(self):
        count = max(1, len(self.available))
        total = count * self.card_w + (count - 1) * self.gap
        x0 = (SCREEN_WIDTH - total) // 2
        y0 = 176
        return {ptype: pygame.Rect(x0 + i * (self.card_w + self.gap), y0,
                                   self.card_w, self.card_h)
                for i, ptype in enumerate(self.available)}

    def draw(self, screen):
        import assets_loader
        bg = assets_loader.get("bg_day_full")
        if bg:
            screen.blit(bg, (0, 0))
        screen.blit(_dim_overlay(150), (0, 0))

        title = self.title_font.render(tr(self.title), True, (255, 230, 0))
        screen.blit(title, (SCREEN_WIDTH // 2 - title.get_width() // 2, 60))
        sub = self.big_font.render(i18n.fmt_level_name(self.level_name), True, COLOR_WHITE)
        screen.blit(sub, (SCREEN_WIDTH // 2 - sub.get_width() // 2, 110))

        # label — aligned to the card row so it never overlaps a card
        rects = self._card_rects()
        row_x0 = min(r.x for r in rects.values()) if rects else 90
        lab = self.font.render(tr("Available plants — click to include in your pack:"),
                               True, (205, 205, 205))
        screen.blit(lab, (row_x0, 148))
        for ptype, r in rects.items():
            in_pack = ptype in self.picked
            hovered = self._hover == ("seed", ptype)
            slot = pygame.Surface((r.w, r.h), pygame.SRCALPHA)
            slot.fill((68, 76, 72, 240) if hovered else
                      ((58, 64, 62, 235) if in_pack else (42, 44, 45, 225)))
            screen.blit(slot, r.topleft)
            pygame.draw.rect(screen,
                             (255, 245, 150) if hovered else
                             ((255, 225, 80) if in_pack else (150, 150, 150)),
                             r, 3 if (in_pack or hovered) else 2, border_radius=8)

            image_rect = pygame.Rect(r.x + 10, r.y + 8, r.w - 20, 86)
            key = _card_image_key(ptype)
            img = assets_loader.get(key) if key else assets_loader.plant_icon(ptype)
            _blit_contained(screen, img, image_rect, padding=2)

            status = tr("IN PACK") if in_pack else tr("off")
            status_font = _fit_font(status, r.w - 12, 15, 10)
            stxt = status_font.render(status, True,
                                      (255, 230, 70) if in_pack else (170, 170, 170))
            screen.blit(stxt, stxt.get_rect(center=(r.centerx, r.y + 101)))

            info = PLANT_INFO[ptype]
            name = i18n.plant_name(ptype)
            name_font = _fit_font(name, r.w - 12, 16, 10)
            nm = name_font.render(name, True, COLOR_WHITE)
            screen.blit(nm, nm.get_rect(center=(r.centerx, r.y + 119)))
            cost = i18n.font(13).render(str(info["cost"]), True, COLOR_YELLOW)
            screen.blit(cost, cost.get_rect(center=(r.centerx, r.y + 136)))

        # compact pack summary: native-ratio mini cards, fully inside panel
        py = 392
        pk_text = f"{tr('Your pack')} ({len(self.picked)}/{len(self.available)})"
        pk = self.big_font.render(pk_text, True, COLOR_WHITE)
        screen.blit(pk, (90, py - 38))
        for i, ptype in enumerate(self.picked):
            x = 90 + i * (SEED_CARD_W + 10)
            r = pygame.Rect(x, py, SEED_CARD_W, SEED_CARD_H)
            pygame.draw.rect(screen, (45, 50, 48), r, border_radius=5)
            img_key = _card_image_key(ptype)
            img = assets_loader.get(img_key) if img_key else assets_loader.plant_icon(ptype)
            _blit_contained(screen, img, r, padding=2)
            pygame.draw.rect(screen, COLOR_WHITE, r, 1, border_radius=5)

        # start button
        hover = self._hover == "start"
        col = (80, 170, 80) if hover else (60, 130, 60)
        pygame.draw.rect(screen, col, self.start_btn, border_radius=10)
        pygame.draw.rect(screen, (0, 0, 0), self.start_btn, 3, border_radius=10)
        st = self.big_font.render(tr("Start!"), True, COLOR_WHITE)
        screen.blit(st, (self.start_btn.centerx - st.get_width() // 2,
                         self.start_btn.centery - st.get_height() // 2))
        # back
        bh_over = self._hover == "back"
        bcol = (140, 90, 60) if bh_over else (110, 70, 50)
        pygame.draw.rect(screen, bcol, self.back_btn, border_radius=8)
        bt = self.font.render(tr("Back"), True, COLOR_WHITE)
        screen.blit(bt, (self.back_btn.centerx - bt.get_width() // 2,
                         self.back_btn.centery - bt.get_height() // 2))
        hint = self.font.render(tr("1-6 keys pick seeds in-game · Space skips the wait between waves"),
                                True, (160, 160, 160))
        screen.blit(hint, (SCREEN_WIDTH // 2 - hint.get_width() // 2, 24))
        hint2 = cached_text(tr("Collect falling plant food, then click a plant to feed it"),
                            22, (150, 235, 150), outline=(0, 0, 0))
        screen.blit(hint2, (SCREEN_WIDTH // 2 - hint2.get_width() // 2, 560))


# ============================================================
# Survival Complete Screen
# ============================================================
class SurvivalCompleteScreen:
    def __init__(self):
        self.font = i18n.font(48)
        self.small_font = i18n.font(28)
        bw, bh = 280, 58
        cx = SCREEN_WIDTH // 2
        self.btn_retry = pygame.Rect(0, 0, bw, bh); self.btn_retry.center = (cx, 380)
        self.btn_menu = pygame.Rect(0, 0, bw, bh); self.btn_menu.center = (cx, 460)
        self._hover = None

    def update_hover(self, mx, my):
        prev = self._hover
        self._hover = None
        if self.btn_retry.collidepoint(mx, my):
            self._hover = "retry"
        elif self.btn_menu.collidepoint(mx, my):
            self._hover = "menu"
        if self._hover and self._hover != prev:
            pulse_hover()

    def handle_mouse(self, mx, my):
        self.update_hover(mx, my)
        return self._hover

    def draw(self, screen, waves):
        screen.blit(_dim_overlay(180), (0, 0))
        if i18n.is_zh():
            text = self.font.render(f"坚持了 {waves} 波！", True, COLOR_WHITE)
        else:
            text = self.font.render(f"Survived {waves} waves!", True, COLOR_WHITE)
        screen.blit(text, (SCREEN_WIDTH // 2 - text.get_width() // 2, 200))
        draw_button(screen, self.btn_retry, tr("Retry"), (60, 130, 60), self._hover == "retry")
        draw_button(screen, self.btn_menu, tr("Main Menu"), (130, 60, 60), self._hover == "menu")
        sub = self.small_font.render(tr("Click to return to menu"), True, (170, 170, 170))
        screen.blit(sub, (SCREEN_WIDTH // 2 - sub.get_width() // 2, 540))