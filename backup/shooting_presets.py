from settings import get_data_file
import json
from pathlib import Path

PRESET_FILE = get_data_file("shooting_presets.json")


def load_shooting_presets():
    if not PRESET_FILE.exists():
        save_shooting_presets([])
        return []

    try:
        data = json.loads(PRESET_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []

    if not isinstance(data, list):
        return []

    presets = []

    for item in data:
        if not isinstance(item, dict):
            continue

        name = str(item.get("name", "")).strip()
        camera = str(item.get("camera", "")).strip()
        film = str(item.get("film", "")).strip()
        lab = str(item.get("lab", "")).strip()

        if not name:
            continue

        presets.append({
            "name": name,
            "camera": camera,
            "film": film,
            "lab": lab,
        })

    return presets


def save_shooting_presets(presets):
    cleaned = []

    for item in presets:
        if not isinstance(item, dict):
            continue

        name = str(item.get("name", "")).strip()
        camera = str(item.get("camera", "")).strip()
        film = str(item.get("film", "")).strip()
        lab = str(item.get("lab", "")).strip()

        if not name:
            continue

        cleaned.append({
            "name": name,
            "camera": camera,
            "film": film,
            "lab": lab,
        })

    PRESET_FILE.write_text(
        json.dumps(cleaned, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
