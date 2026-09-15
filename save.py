"""Save / load game progress (unlocked levels, records, settings).

Stored as JSON in the same folder as this module (portable, no hidden paths).
"""

import json
import os

SAVE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "save.json")


class SaveData:
    def __init__(self):
        self.completed_levels = []   # list of level ids like "1-1" (in finish order)
        self.survival_best = {}       # survival_id -> waves survived
        self.settings = {
            "mute": False,
        }

    # ---------- persistence ----------
    SCHEMA_VERSION = 1

    def to_dict(self):
        return {
            "schema_version": self.SCHEMA_VERSION,
            "completed_levels": self.completed_levels,
            "survival_best": self.survival_best,
            "settings": self.settings,
        }

    @classmethod
    def load(cls):
        data = cls()
        if not os.path.exists(SAVE_PATH):
            return data
        try:
            with open(SAVE_PATH, "r", encoding="utf-8") as f:
                raw = json.load(f)
            raw = cls._migrate(raw)
            data.completed_levels = list(raw.get("completed_levels", []))
            data.survival_best = dict(raw.get("survival_best", {}))
            data.settings.update(raw.get("settings", {}))
        except Exception:
            # Preserve the broken file for diagnosis; start fresh safely.
            try:
                os.replace(SAVE_PATH, SAVE_PATH + ".corrupt")
            except OSError:
                pass
        return data

    @classmethod
    def _migrate(cls, raw):
        """Forward-migrate a raw dict read from disk into the current schema.

        Legacy saves (pre-schema_version) used the same three keys as v1, so
        the v0 → v1 path is effectively a no-op pass-through — but the version
        bump is what lets future changes branch safely on `d["schema_version"]`.
        """
        if not isinstance(raw, dict):
            return {"schema_version": cls.SCHEMA_VERSION}
        if raw.get("schema_version", 0) < cls.SCHEMA_VERSION:
            raw = dict(raw)
            raw["schema_version"] = cls.SCHEMA_VERSION
        return raw

    @classmethod
    def from_dict(cls, d):
        """Construct a SaveData from an arbitrary dict, applying migrations.

        Useful for tests and for callers that already hold the parsed JSON.
        Unknown keys are ignored; missing keys take defaults.
        """
        data = cls()
        if not isinstance(d, dict):
            return data
        d = cls._migrate(d)
        data.completed_levels = list(d.get("completed_levels", []))
        data.survival_best = dict(d.get("survival_best", {}))
        data.settings.update(d.get("settings", {}))
        return data

    def save(self):
        tmp = SAVE_PATH + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, SAVE_PATH)
        except Exception:
            try:
                if os.path.exists(tmp):
                    os.remove(tmp)
            except OSError:
                pass

    # ---------- progress helpers ----------
    def is_completed(self, level_id):
        return level_id in self.completed_levels

    def complete_level(self, level_id):
        if level_id not in self.completed_levels:
            self.completed_levels.append(level_id)
            self.save()

    def record_survival(self, survival_id, waves):
        """Store best waves for a survival environment. Returns True if it's a new record."""
        prev = self.survival_best.get(survival_id, 0)
        if waves > prev:
            self.survival_best[survival_id] = waves
            self.save()
            return True
        return False

    def survival_record(self, survival_id):
        return self.survival_best.get(survival_id, 0)


def derive_unlocked(completed_ids):
    """Given a list of completed adventure level ids (in any order), return the
    set of currently unlocked level ids.

    Rule (PvZ-like): only the first level is open at the start. Completing a
    level unlocks the *next* level in the adventure list. All earlier worlds'
    cleared levels stay unlocked.
    """
    from levels import ADVENTURE_LEVELS

    unlocked = set()
    completed = set(completed_ids)
    for i, lv in enumerate(ADVENTURE_LEVELS):
        if i == 0:
            unlocked.add(lv["id"])
            continue
        prev = ADVENTURE_LEVELS[i - 1]
        if prev["id"] in completed:
            unlocked.add(lv["id"])
    # every completed level is always re-playable
    unlocked |= completed
    return unlocked
