"""Lawn grid for planting.

The grid is drawn transparently on top of the lawn background image.
The background itself (sky, house, sidewalk, fence) is drawn separately
in Game._draw_lawn_background().
"""

import pygame
from constants import *
import assets_loader


class Grid:
    def __init__(self):
        self.rows = GRID_ROWS
        self.cols = GRID_COLS
        self.cell_w = CELL_W
        self.cell_h = CELL_H
        self.x = GRID_X
        self.y = GRID_Y
        self.selected_cell = None  # (row, col)
        self.hover_cell = None
        # pre-rendered hover/selection overlays (avoid per-frame Surface allocs)
        self._hover_overlay = pygame.Surface((self.cell_w, self.cell_h), pygame.SRCALPHA)
        self._hover_overlay.fill((255, 255, 255, 40))
        self._shovel_overlay = pygame.Surface((self.cell_w, self.cell_h), pygame.SRCALPHA)
        self._shovel_overlay.fill((255, 70, 50, 60))

    def get_cell(self, mx, my):
        if mx < self.x or my < self.y:
            return None
        col = int((mx - self.x) // self.cell_w)
        row = int((my - self.y) // self.cell_h)
        if 0 <= col < self.cols and 0 <= row < self.rows:
            return (row, col)
        return None

    def get_cell_center(self, row, col):
        cx = self.x + col * self.cell_w + self.cell_w // 2
        cy = self.y + row * self.cell_h + self.cell_h // 2
        return (cx, cy)

    def update_hover(self, mx, my):
        self.hover_cell = self.get_cell(mx, my)

    def draw(self, screen, shovel_active=False):
        # No-op: the lawn background image already shows the grass tiles.
        # Just draw hover/selection overlays.
        if self.hover_cell:
            row, col = self.hover_cell
            pos = (self.x + col * self.cell_w, self.y + row * self.cell_h)
            overlay = self._shovel_overlay if shovel_active else self._hover_overlay
            screen.blit(overlay, pos)
        if self.selected_cell:
            row, col = self.selected_cell
            rect = pygame.Rect(self.x + col * self.cell_w, self.y + row * self.cell_h,
                               self.cell_w, self.cell_h)
            pygame.draw.rect(screen, (255, 230, 0), rect, 3)

    def clear_selection(self):
        self.selected_cell = None