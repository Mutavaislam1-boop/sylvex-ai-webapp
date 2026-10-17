from datetime import datetime, timedelta, timezone

from services.account_usage import build_usage_snapshot, category_for_mode


def test_usage_snapshot_groups_real_charges_payments_and_subscriptions():
    now = datetime(2026, 10, 18, 12, tzinfo=timezone.utc)
    grouped = [
        (now.replace(hour=0), "image", "gpt-image-1.5", "openai", 12, 2),
        (now.replace(hour=0), "video", "veo-3.1", "google", 40, 1),
        ((now - timedelta(days=1)).replace(hour=0), "voice", "eleven-v3", "elevenlabs", 8, 3),
    ]
    recent = [("gen-1", "video", "veo-3.1", "google", 40, now)]
    purchases = [(1, "stripe", 500, 500, "USD", "completed", now, None)]
    subscriptions = [(2, "pro_month", "stripe", 1500, "USD", "active", now - timedelta(days=3), now + timedelta(days=27), now - timedelta(days=3))]

    result = build_usage_snapshot(grouped, recent, purchases, subscriptions, 438, "30d", now)

    assert result["summary"]["spent_credits"] == 60
    assert result["summary"]["generation_requests"] == 6
    assert result["summary"]["added_credits"] == 500
    assert result["summary"]["payment_amounts"] == {"USD": 500}
    assert result["summary"]["active_subscription"]["plan"] == "pro_month"
    assert {item["category"]: item["credits"] for item in result["categories"]} == {
        "image": 12, "video": 40, "music": 0, "voice": 8, "text": 0,
    }
    assert result["models"][0]["model"] == "veo-3.1"
    assert len(result["timeline"]) == 30
    assert result["activity"][0]["id"] == "gen-1"


def test_category_mapping_covers_every_generation_surface():
    assert category_for_mode("edit_camera") == "image"
    assert category_for_mode("video") == "video"
    assert category_for_mode("music") == "music"
    assert category_for_mode("text-to-speech") == "voice"
    assert category_for_mode("audio") == "voice"
    assert category_for_mode("assistant_chat") == "text"
