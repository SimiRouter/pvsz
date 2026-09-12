"""Memoized alpha variants of shared cached sprites.

``fx.faded`` / ``particles._faded`` / ``assets_loader._faded`` all used to do
a fresh ``surface.copy() + set_alpha`` on *every* blit: walking zombies
re-copied their contact shadow 30x/frame and the particle system re-copied
dot/puff sprites 70x/frame (profiled steady state). The copies are pure
waste — the (base sprite, alpha) pair repeats every frame.

This module keys a weak map off the base sprite (so variants die with it)
and quantizes alpha onto a 1/32 ladder: at 60 fps a fade crosses one step
every ~2 frames, which is visually indistinguishable from continuous alpha
but caps variants per sprite at 32.

Only pygame is imported — safe to pull in from fx, particles and
assets_loader without any import cycle.
"""
import weakref

_variants = weakref.WeakKeyDictionary()


def faded(surface, alpha):
    """Return ``surface`` stamped with surface-level ``alpha`` (0-255).

    Safe to blit repeatedly: the returned surface is a private cached copy
    that nobody may mutate — shared cached sprites must never get
    ``set_alpha`` called on them directly (two consumers would clobber each
    other's alpha).
    """
    a = int(max(0, min(255, alpha)))
    if a >= 255:
        return surface
    # 1/32 ladder: 1..11 -> 8, 12..19 -> 16, ... 244..251 -> 248.
    # Snapping the bottom step to 8 keeps the ladder monotone; 0 stays 0
    # (callers use it for fully-invisible sprites).
    q = (a + 4) // 8 * 8
    if q >= 255:
        return surface
    if a and q < 8:
        q = 8
    variants = _variants.get(surface)
    if variants is None:
        variants = _variants[surface] = {}
    out = variants.get(q)
    if out is None:
        out = variants[q] = surface.copy()
        out.set_alpha(q)
    return out
