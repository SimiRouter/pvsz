"""Procedurally synthesized sound effects (no external audio files).

Each sound is generated as a short PCM buffer at import/init time and played
through pygame.mixer.Sound. If the mixer is unavailable (e.g. headless CI)
all calls degrade silently.
"""

import math
import struct
import time
import pygame

SAMPLE_RATE = 22050
CHANNELS = 1

_sounds = {}
_ok = False
# Minimum gap between two plays of the same sound (seconds). Rapid-fire events
# (pea hits, shots) would otherwise retrigger the same Sound object every few
# frames, cutting itself and crackling.
_MIN_GAP = {
    "shoot": 0.055, "zombie_hit": 0.05, "eat": 0.09, "sun": 0.05,
    "plant": 0.03, "zombie_die": 0.06, "click": 0.03,
}
_last_play = {}


def _pcm(samples):
    """Encode samples for the mixer channel count (mono/stereo safe)."""
    raw = bytearray()
    for s in samples:
        packed = struct.pack("<h", int(max(-1.0, min(1.0, s)) * 32000))
        raw.extend(packed * CHANNELS)
    return bytes(raw)


def _gen(freq_start, freq_end, dur, vol=0.5, wave="sine", noise=0.0):
    """Synthesize a tone sweep into a 16-bit mono PCM bytes object."""
    n = int(SAMPLE_RATE * dur)
    samples = []
    for i in range(n):
        t = i / SAMPLE_RATE
        prog = i / max(1, n - 1)
        # exponential frequency glide start→end
        f = freq_start * (freq_end / freq_start) ** prog
        if wave == "square":
            val = 0.6 if math.sin(2 * math.pi * f * t) >= 0 else -0.6
        elif wave == "saw":
            ph = (f * t) % 1.0
            val = 2 * ph - 1
        else:
            val = math.sin(2 * math.pi * f * t)
        if noise > 0:
            import random
            val += random.uniform(-noise, noise)
        # envelope: quick attack, exponential decay
        env = min(1.0, prog * 20) * math.exp(-2.5 * prog)
        s = max(-1.0, min(1.0, val * env * vol))
        samples.append(s)
    return _pcm(samples)


def _buzz(dur, vol=0.6, noise=0.3, freq=120):
    n = int(SAMPLE_RATE * dur)
    import random
    random.seed(7)
    samples = []
    for i in range(n):
        t = i / SAMPLE_RATE
        prog = i / max(1, n - 1)
        carrier = math.sin(2 * math.pi * freq * (1 + prog) * t)
        val = carrier + random.uniform(-noise, noise)
        env = math.exp(-3.0 * prog)
        s = max(-1.0, min(1.0, val * env * vol))
        samples.append(s)
    return _pcm(samples)


def _chord(freqs, dur, vol=0.4):
    n = int(SAMPLE_RATE * dur)
    samples = []
    for i in range(n):
        t = i / SAMPLE_RATE
        prog = i / max(1, n - 1)
        val = 0.0
        for f in freqs:
            val += math.sin(2 * math.pi * f * t)
        val /= len(freqs)
        env = min(1.0, prog * 12) * math.exp(-2.0 * prog)
        s = max(-1.0, min(1.0, val * env * vol))
        samples.append(s)
    return _pcm(samples)


def init():
    """Initialize the mixer and build sound buffers matching its actual format."""
    global _ok, _sounds, SAMPLE_RATE, CHANNELS
    if _ok:
        return
    try:
        if pygame.mixer.get_init() is None:
            pygame.mixer.init(frequency=SAMPLE_RATE, size=-16, channels=1, buffer=512)
        actual = pygame.mixer.get_init()
        if actual:
            SAMPLE_RATE = actual[0]
            CHANNELS = actual[2]
        def make(name, data):
            try:
                _sounds[name] = pygame.mixer.Sound(buffer=data)
            except Exception:
                _sounds[name] = None
        make("plant", _gen(200, 90, 0.12, vol=0.5, wave="square"))
        make("shoot", _gen(700, 300, 0.07, vol=0.28, wave="square"))
        make("sun", _gen(1300, 1800, 0.16, vol=0.35) )
        make("sun_land", _gen(500, 700, 0.06, vol=0.2))
        make("zombie_die", _gen(160, 45, 0.35, vol=0.5, wave="saw", noise=0.15))
        make("zombie_hit", _gen(220, 160, 0.05, vol=0.2, wave="square"))
        make("explode", _buzz(0.6, vol=0.65, noise=0.45, freq=90))
        make("wave", _gen(320, 640, 0.5, vol=0.5, wave="saw") + _gen(480, 960, 0.45, vol=0.4, wave="saw"))
        make("bigwave", _chord([392, 494, 587], 0.7, vol=0.5))
        make("lose", _chord([220, 175, 147, 110], 1.6, vol=0.5))
        make("win", _chord([523, 659, 784, 1047], 0.9, vol=0.45))
        make("eat", _gen(140, 90, 0.08, vol=0.3, wave="square"))
        # UI & feedback extras
        make("click", _gen(950, 700, 0.045, vol=0.22, wave="square"))
        make("error", _gen(220, 150, 0.09, vol=0.22, wave="square"))
        make("shovel", _gen(320, 110, 0.12, vol=0.35, wave="square", noise=0.2))
        make("mow", _buzz(0.55, vol=0.5, noise=0.5, freq=65))
        make("food", _chord([660, 880, 1100], 0.22, vol=0.35))
        make("upgrade", _chord([523, 784], 0.3, vol=0.4))
        make("steal", _gen(520, 140, 0.4, vol=0.4, wave="saw"))
        make("groan", _gen(110, 55, 0.9, vol=0.3, wave="saw", noise=0.25))
        _ok = True
    except Exception:
        _ok = False


def play(name, volume=1.0):
    """Play a sound by name if audio is available (throttled per sound)."""
    if not _ok:
        return
    gap = _MIN_GAP.get(name)
    if gap is not None:
        now = time.monotonic()
        if now - _last_play.get(name, 0.0) < gap:
            return
        _last_play[name] = now
    snd = _sounds.get(name)
    if snd is not None:
        try:
            snd.set_volume(max(0.0, min(1.0, volume)))
            snd.play()
        except Exception:
            pass
