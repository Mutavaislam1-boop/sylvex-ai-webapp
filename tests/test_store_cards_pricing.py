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

def _examples():
    """EXAMPLES defaults in store-cards.js: key -> (cost, model)."""
    found = re.findall(r"\{ key: '(\w+)', cost: (\d+), model: '([\w.-]+)'", SOURCE)
    return {key: (int(cost), model) for key, cost, model in found}


def test_example_defaults_match_the_live_cheapest_selection(monkeypatch):
    # The Mini App overrides these with the catalog's live examples; the
    # defaults (also used by the Website) must equal what the server picks.
    monkeypatch.setitem(main._STORE_EXAMPLES_CACHE, "value", None)
    live = main.store_generation_examples()
    defaults = _examples()
    assert set(defaults) == set(live) == {"photo", "video", "music", "voice", "text"}
    for key, (cost, model) in defaults.items():
        assert (cost, model) == (live[key]["credits"], live[key]["model"]), key


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
