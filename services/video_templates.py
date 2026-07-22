import json
from pathlib import Path
from typing import List, Dict, Optional

BASE_DIR = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = BASE_DIR / "webapp" / "video-templates"


def get_all_templates() -> List[Dict]:
    templates = []

    if not TEMPLATES_DIR.exists():
        return templates

    for folder in sorted(TEMPLATES_DIR.iterdir()):
        if not folder.is_dir():
            continue

        template_file = folder / "template.json"

        if not template_file.exists():
            continue

        try:
            with open(template_file, "r", encoding="utf-8") as f:
                template = json.load(f)

            template["folder"] = folder.name

            templates.append(template)

        except Exception as e:
            print(f"Error loading template {folder.name}: {e}")

    return templates


def get_template(template_id: str) -> Optional[Dict]:
    template_file = TEMPLATES_DIR / template_id / "template.json"

    if not template_file.exists():
        return None

    with open(template_file, "r", encoding="utf-8") as f:
        return json.load(f)