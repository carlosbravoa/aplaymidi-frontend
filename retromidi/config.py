"""
Configuration management for RetroMIDI.
Stores settings in ~/.config/retromidi/config.json
"""

import json
import os
from pathlib import Path


CONFIG_DIR = Path.home() / ".config" / "retromidi"
CONFIG_FILE = CONFIG_DIR / "config.json"

DEFAULTS = {
    "port": "20:0",
    "last_dir": "",
}


class Config:
    def __init__(self):
        self._data = dict(DEFAULTS)
        self._load()

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
