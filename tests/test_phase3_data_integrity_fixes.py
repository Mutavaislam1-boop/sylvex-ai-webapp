"""Regression tests for the Pro Studio A-Z audit's Phase 3 data-integrity fixes.

- image_reference_urls() used to concatenate [user uploads, character refs,
  object refs] with no fairness, so enough user uploads silently starved
  Character/Object out of every provider's fixed reference-count truncation
  (e.g. reference_images[:5] for OpenAI, refs[:5] for Flux.2). It now
  round-robins the three groups (matching Seedream's already-correct
  fairness pattern) so a representative from every source survives.
- The public Gallery API (/api/public/prostudio/gallery) truncated
  multi-image results to images[0] - a third instance of the same bug class
  already fixed for the chat mini-card and the Generation Info drawer.
"""
import main


def test_image_reference_urls_round_robins_instead_of_starving_character_object():
    payload = {
        "image_options": {
            "referenceImageUrls": [f"https://x.test/user{i}.png" for i in range(6)],
            "characterReferences": ["https://x.test/char1.png"],
            "objectReferences": ["https://x.test/obj1.png"],
        }
    }
    refs = main.image_reference_urls(payload)
    # 6 user uploads alone would fill any real provider's [:5] truncation
    # before Character/Object were ever read under the old naive concat.
    first_five = refs[:5]
    assert "https://x.test/char1.png" in first_five
    assert "https://x.test/obj1.png" in first_five


def test_image_reference_urls_dedupes_and_keeps_all_refs_when_room_allows():
    payload = {
        "image_options": {
            "referenceImageUrls": ["https://x.test/user1.png", "https://x.test/user1.png"],
            "characterReferences": ["https://x.test/char1.png"],
            "objectReferences": ["https://x.test/obj1.png"],
        }
    }
    refs = main.image_reference_urls(payload)
    assert refs.count("https://x.test/user1.png") == 1
    assert set(refs) == {"https://x.test/user1.png", "https://x.test/char1.png", "https://x.test/obj1.png"}
