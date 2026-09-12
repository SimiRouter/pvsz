"""Plants vs Zombies - Python Edition
Cross-platform (Mac / Windows) using Pygame.

Run: python main.py
"""

import pygame
import sys
from constants import SCREEN_WIDTH, SCREEN_HEIGHT, FPS


def _viewport(window_size):
    """Return aspect-fit destination rect for the fixed logical canvas."""
    ww, wh = window_size
    scale = min(ww / SCREEN_WIDTH, wh / SCREEN_HEIGHT)
    vw = max(1, int(SCREEN_WIDTH * scale))
    vh = max(1, int(SCREEN_HEIGHT * scale))
    return pygame.Rect((ww - vw) // 2, (wh - vh) // 2, vw, vh)


def _to_logical(pos, view):
    """Map window mouse coordinates back to 1400x600 game coordinates."""
    if not view.collidepoint(pos):
        return None
    x = (pos[0] - view.x) * SCREEN_WIDTH / view.w
    y = (pos[1] - view.y) * SCREEN_HEIGHT / view.h
    return int(x), int(y)


def _map_mouse_event(event, view):
    if event.type not in (pygame.MOUSEMOTION, pygame.MOUSEBUTTONDOWN,
                          pygame.MOUSEBUTTONUP):
        return event
    pos = _to_logical(event.pos, view)
    if pos is None:
        # A release outside the aspect-fitted viewport must still reach the
        # game so an in-progress seed drag is cancelled instead of getting
        # stuck until the next click.
        if event.type == pygame.MOUSEBUTTONUP:
            attrs = event.dict.copy()
            attrs["pos"] = (-1, -1)
            return pygame.event.Event(event.type, attrs)
        return None
    attrs = event.dict.copy()
    attrs["pos"] = pos
    if event.type == pygame.MOUSEMOTION and "rel" in attrs:
        attrs["rel"] = (int(attrs["rel"][0] * SCREEN_WIDTH / view.w),
                        int(attrs["rel"][1] * SCREEN_HEIGHT / view.h))
    return pygame.event.Event(event.type, attrs)


def main():
    pygame.init()
    window = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.RESIZABLE)
    pygame.display.set_caption("Plants vs Zombies - Python Edition")
    icon = pygame.Surface((32, 32))
    icon.fill((0, 150, 0))
    pygame.display.set_icon(icon)

    # Fixed logical canvas: all gameplay/UI coordinates remain pixel-stable;
    # only the final composed frame is aspect-fitted to the real window.
    canvas = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT)).convert()

    # Import after the display exists — game.py pre-loads converted sprites.
    from game import Game

    game = Game(canvas)
    view = _viewport(window.get_size())
    fullscreen = False
    windowed_size = window.get_size()

    running = True
    # Hybrid frame pacing: sleep through most of each 16.6 ms frame, then
    # busy-spin only the last ~2 ms. Pure clock.tick() overshoots the OS sleep
    # by 1-3 ms (visible micro-stutter at 60 fps); a full busy loop would pin
    # a whole CPU core. This gets steady frames at a fraction of the cost.
    frame_ms = 1000.0 / FPS
    next_frame = pygame.time.get_ticks()
    last_frame = next_frame
    while running:
        delay = int(next_frame - pygame.time.get_ticks())
        if delay > 3:
            pygame.time.wait(delay - 2)
        while delay > 0 and pygame.time.get_ticks() < next_frame:
            pass
        if delay < -200:
            # long stall (window drag, breakpoint) — resync, don't spiral
            next_frame = pygame.time.get_ticks()
        now = pygame.time.get_ticks()
        # Clamp huge frame gaps so zombies don't jump after a stall.
        dt = min((now - last_frame) / 1000.0, 0.05)
        last_frame = now
        next_frame += frame_ms

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                # Persist an in-progress survival run's best-wave record;
                # otherwise closing the window mid-run silently loses it.
                game._record_survival_run()
                running = False
            elif event.type == pygame.VIDEORESIZE and not fullscreen:
                window = pygame.display.set_mode((max(640, event.w), max(360, event.h)),
                                                 pygame.RESIZABLE)
                view = _viewport(window.get_size())
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_F11:
                fullscreen = not fullscreen
                if fullscreen:
                    windowed_size = window.get_size()
                    window = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
                else:
                    window = pygame.display.set_mode(windowed_size, pygame.RESIZABLE)
                view = _viewport(window.get_size())
            else:
                mapped = _map_mouse_event(event, view)
                if mapped is not None:
                    game.handle_event(mapped)

        game.update(dt)
        game.draw()
        game.draw_state()

        window.fill((10, 10, 12))
        # screen shake nudges only the final blit, not game coordinates
        shake_dx, shake_dy = game.shake_offset()
        if view.size == canvas.get_size():
            window.blit(canvas, (view.x + shake_dx, view.y + shake_dy))
        else:
            fitted = pygame.transform.smoothscale(canvas, view.size)
            window.blit(fitted, (view.x + shake_dx, view.y + shake_dy))
        pygame.display.flip()

    game.restore_cursor()
    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    main()
