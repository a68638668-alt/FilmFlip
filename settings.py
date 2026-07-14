import json
import os
import shutil
import sys
from pathlib import Path


APP_NAME = "FilmFlip"


def get_app_data_dir() -> Path:
    """
    Return a user-writable app data directory.

    macOS:
        ~/Library/Application Support/FilmFlip

    Windows:
        %APPDATA%/FilmFlip

    Linux/other:
        ~/.filmflip
    """

    if sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
        app_dir = base / APP_NAME

    elif sys.platform.startswith("win"):
        base = os.environ.get("APPDATA")

        if base:
            app_dir = Path(base) / APP_NAME
        else:
            app_dir = Path.home() / "AppData" / "Roaming" / APP_NAME

    else:
        app_dir = Path.home() / ".filmflip"

    app_dir.mkdir(parents=True, exist_ok=True)
    return app_dir


def get_data_file(filename: str) -> Path:
    """
    Return a path inside FilmFlip's app data directory.
    """

    return get_app_data_dir() / filename


SETTINGS_FILE = get_data_file("settings.json")

DEFAULT_SETTINGS = {
    "remember_last_folder": True,
    "last_folder": "",
    "theme": "light",
    "thumbnail_size": "medium",
    "roll_base_count": 36,
    "default_sort": "reverse",
}


def _migrate_legacy_file(filename: str):
    """
    Copy an old json file that may exist beside the source/app files
    into the new app data directory, only if the new file does not exist.
    """

    new_path = get_data_file(filename)

    if new_path.exists():
        return

    legacy_path = Path(__file__).parent / filename

    if legacy_path.exists() and legacy_path != new_path:
        try:
            shutil.copy2(legacy_path, new_path)
        except Exception:
            pass


def load_settings():
    _migrate_legacy_file("settings.json")

    if not SETTINGS_FILE.exists():
        save_settings(DEFAULT_SETTINGS)
        return DEFAULT_SETTINGS.copy()

    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        data = DEFAULT_SETTINGS.copy()

    if not isinstance(data, dict):
        data = DEFAULT_SETTINGS.copy()

    for key, value in DEFAULT_SETTINGS.items():
        data.setdefault(key, value)

    return data


def save_settings(settings: dict):
    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)

    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False, indent=4)


# Migrate known FilmFlip user data files.
# Other modules can use get_data_file("filename.json") to save in the same location.
for _filename in (
    "settings.json",
    "filmflip_presets.json",
    "shooting_presets.json",
    "template_settings.json",
):
    _migrate_legacy_file(_filename)
