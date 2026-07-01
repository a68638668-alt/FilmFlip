from settings import get_data_file
import json

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
        place = str(item.get("place", "")).strip()
        scanner = str(item.get("scanner", "")).strip()

        if not name:
            continue

        presets.append({
            "name": name,
            "camera": camera,
            "film": film,
            "lab": lab,
            "place": place,
            "scanner": scanner,
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
        place = str(item.get("place", "")).strip()
        scanner = str(item.get("scanner", "")).strip()

        if not name:
            continue

        # memo는 촬영마다 달라질 수 있는 값이라 프리셋에 저장하지 않는다.
        cleaned.append({
            "name": name,
            "camera": camera,
            "film": film,
            "lab": lab,
            "place": place,
            "scanner": scanner,
        })

    PRESET_FILE.write_text(
        json.dumps(cleaned, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
