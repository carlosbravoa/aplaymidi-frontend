"""
Configuration management for RetroMIDI.
Stores settings in ~/.config/retromidi/config.json
"""

import json
import os
import shutil
from pathlib import Path
from importlib import resources


CONFIG_DIR = Path.home() / ".config" / "retromidi"
CONFIG_FILE = CONFIG_DIR / "config.json"

DEFAULTS = {
    "port": "20:0",
    "last_dir": "",
    "shuffle": False,
    "recurse": False,
}


class Config:
    def __init__(self):
        self._data = dict(DEFAULTS)
        self._install_bundled_assets()
        self._load()

    def _install_bundled_assets(self):
        """Copy bundled all_notes_off.mid to config dir if not already there."""
        dest = CONFIG_DIR / "all_notes_off.mid"
        if dest.exists():
            return
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        try:
            # Python 3.9+ path
            ref = resources.files("retromidi").joinpath("all_notes_off.mid")
            with resources.as_file(ref) as src:
                shutil.copy2(src, dest)
        except Exception:
            pass  # Non-fatal: user can set path manually in settings

    def _load(self):
        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE, "r") as f:
                    loaded = json.load(f)
                self._data.update(loaded)
            except (json.JSONDecodeError, IOError):
                pass  # Use defaults on corruption

    def save(self):
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_FILE, "w") as f:
            json.dump(self._data, f, indent=2)

    def get(self, key, default=None):
        return self._data.get(key, default)

    def set(self, key, value):
        self._data[key] = value
