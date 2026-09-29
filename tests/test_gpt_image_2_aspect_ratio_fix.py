"""Regression test for the Pro Studio A-Z audit's GPT Image 2 aspect-ratio fix.

Before this fix, the composer offered 5 distinct-looking ratios for
gpt_image_2 (1:1, 4:3, 3:4, 16:9, 9:16), but normalize_openai_image_size()
only ever produces one of 3 real OpenAI sizes - 4:3 and 16:9 both collapsed
to the same 1536x1024 box, and 3:4 and 9:16 both collapsed to the same
1024x1536 box, so two pairs of visually distinct UI choices produced
byte-identical output.
"""
import main


def test_gpt_image_2_only_maps_to_three_distinct_real_sizes():
    assert main.normalize_openai_image_size("1:1", frontend_model="gpt_image_2") == "1024x1024"
    assert main.normalize_openai_image_size("3:2", frontend_model="gpt_image_2") == "1536x1024"
    assert main.normalize_openai_image_size("2:3", frontend_model="gpt_image_2") == "1024x1536"


def test_gpt_image_2_and_gpt_image_1_share_the_same_size_mapping():
    for ratio in ("1:1", "3:2", "2:3"):
        assert main.normalize_openai_image_size(ratio, frontend_model="gpt_image_1") == \
            main.normalize_openai_image_size(ratio, frontend_model="gpt_image_2")
