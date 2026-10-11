"""The Store cards (webapp/js/store-cards.js) show how many of each example a
balance covers. Those per-example costs must come from the SYLVEX price
engine, and the credit cards that continue to checkout must map to packs
SHOP_ITEMS actually sells at the same price. This keeps the frontend
constants from drifting away from the backend."""
import json
import re
from pathlib import Path

import main

ROOT = Path(__file__).resolve().parent.parent
SOURCE = (ROOT / "webapp" / "js" / "store-cards.js").read_text(encoding="utf-8")
LANGUAGE = (ROOT / "webapp" / "js" / "language.js").read_text(encoding="utf-8")

EXAMPLE_PAYLOADS = {
    "photo": {"mode": "image", "image_options": {"count": 1}},
    "video": {"mode": "video", "video_options": {"duration": 5, "resolution": "720p"}},
    "music": {"mode": "music", "music_options": {}},
    "voice": {"mode": "voice", "prompt": "x" * 1000, "voice_options": {}},
}


def _examples():
    found = re.findall(r"\{ key: '(\w+)', cost: (null|\d+), model: '([\w.-]+)' \}", SOURCE)
    return {key: (None if cost == "null" else int(cost), model) for key, cost, model in found}


def test_example_costs_match_the_price_engine():
    examples = _examples()
    assert set(examples) == {"photo", "video", "music", "voice", "text"}
    for key, payload in EXAMPLE_PAYLOADS.items():
        cost, model = examples[key]
        request = json.loads(json.dumps(payload))
        request["model"] = model
        options_key = {"photo": "image_options", "video": "video_options", "music": "music_options", "voice": "voice_options"}[key]
        request[options_key]["model"] = model
        request.setdefault("prompt", "x")
        estimate = main.calculate_generation_price(request)
        assert estimate.get("pricing_available", True), key
        assert estimate["credits"] == cost, (key, model, estimate["credits"])


def test_text_example_is_usage_billed():
    cost, model = _examples()["text"]
    assert cost is None
    estimate = main.calculate_generation_price({"mode": "text", "model": model, "prompt": "x"})
    assert estimate["billing"] == "usage"


def test_checkout_cards_map_to_existing_packs_at_the_same_price():
    mapping = dict(re.findall(r"(\d+): '(pack_\d+)'", SOURCE.split("LEGACY_PACK_IDS = ", 1)[1].split(";", 1)[0]))
    assert mapping, "LEGACY_PACK_IDS not found"
    for usd, pack_id in mapping.items():
        item = main.SHOP_ITEMS[pack_id]
        assert item["kind"] == "credits"
        assert item["usd"] == float(usd)
        assert item["credits"] == int(usd) * 100


def test_mini_app_has_english_and_russian_store_strings():
    keys = set(re.findall(r"^    (store_\w+):", SOURCE, flags=re.M))
    assert keys
    for lang in ("en", "ru"):
        block = LANGUAGE.split(f"Object.assign(I18N.{lang}, {{\n    store_period_month", 1)[1].split("});", 1)[0]
        present = {"store_period_month"} | set(re.findall(r"^    (store_\w+):", block, flags=re.M))
        assert keys <= present, (lang, sorted(keys - present))
