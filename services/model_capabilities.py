"""Central Model Capability System — Phase 1 (Batch 1) of the Pro Studio
master remediation plan.

This module is the intended single source of truth for model capability and
pricing data across Pro Studio. Per the approved plan
(/root/.claude/plans/splendid-moseying-starlight.md) migration is strictly
additive: nothing existing (IMAGE_MODEL_FEATURES, SEEDREAM_MODEL_CAPABILITIES,
VIDEO_MODEL_CONFIG, KLING_COST_MATRIX, etc.) is deleted or modified by this
module. Instead, the owning modules (main.py, services/video_router.py) call
the register_*() functions below, passing in their existing dicts, so this
module has zero import dependency on either of them and can be imported
freely from both without any circular-import risk.

Batch 1 scope: schema + registry + one behavior-preserving repoint (image
Character/Object/seed gating). No video consumer is repointed to read this
module yet, and none of this module's video data is enforced or gated on
anywhere. See the plan file for the full roadmap and the constraints this
implementation follows (additive-only migration, text-conditioning vs.
visual-reference separation for Character/Object, Batch-1-only scope).
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional


class MediaCategory(str, Enum):
    IMAGE = "image"
    VIDEO = "video"
    MUSIC = "music"
    VOICE = "voice"
    TEXT = "text"


class VisualReferenceMode(str, Enum):
    """Whether — and how — a model accepts an actual reference IMAGE for a
    character/object. This is deliberately a separate axis from whether the
    model can be told about a character/object in the text prompt
    (CharacterCapability.text_conditioning below): a model can be
    UNSUPPORTED here while still fully supporting the character/object
    through prompt text, which is how every video model works today via
    services.character_prompts.build_character_prompt() /
    _build_video_visual_prompt()'s has_character branch — that behavior must
    never be modeled as "unsupported" or regressed."""

    REAL_MULTI_IMAGE = "real_multi_image"
    DEGRADED_SINGLE_IMAGE = "degraded_single_image"
    PROVIDER_NATIVE_ASSET = "provider_native_asset"
    UNSUPPORTED = "unsupported"


@dataclass(frozen=True)
class ReferenceLimits:
    max_count: int = 0
    accepts_inline_base64: bool = True
    accepts_url: bool = True
    param_name: str = ""
    visual_mode: VisualReferenceMode = VisualReferenceMode.UNSUPPORTED


@dataclass(frozen=True)
class CharacterCapability:
    # Two independent axes - do not conflate them (see VisualReferenceMode
    # docstring above for why this split exists).
    text_conditioning: bool = True
    visual_reference: ReferenceLimits = field(default_factory=ReferenceLimits)


@dataclass(frozen=True)
class PricingTier:
    axes: tuple = ()
    table: dict = field(default_factory=dict)
    # True = data kept for audit trail; no code path can select this tier
    # (e.g. Kling's dead "voice_control" tier - see register_video_models()).
    unreachable: bool = False


@dataclass(frozen=True)
class ModelCapability:
    id: str
    category: MediaCategory
    provider: str
    label: str = ""

    start_frame: bool = False
    end_frame: bool = False
    video_input: bool = False        # usable as the base clip in Video Edit mode
    motion_reference: bool = False   # usable as the driving clip in Motion Control mode
    audio_input: bool = False
    audio_reference: bool = False

    character: CharacterCapability = field(default_factory=CharacterCapability)
    object: CharacterCapability = field(default_factory=CharacterCapability)

    seed: bool = False
    negative_prompt: bool = False
    sound_toggle: bool = False
    native_audio: bool = False

    durations: tuple = ()
    resolutions: tuple = ()
    ratios: tuple = ()
    qualities: tuple = ()
    output_counts: tuple = (1,)
    modes: tuple = ()

    avatar: bool = False

    pricing: dict = field(default_factory=dict)
    extra: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        data = asdict(self)
        data["category"] = self.category.value
        data["character"]["visual_reference"]["visual_mode"] = self.character.visual_reference.visual_mode.value
        data["object"]["visual_reference"]["visual_mode"] = self.object.visual_reference.visual_mode.value
        for tier in data.get("pricing", {}).values():
            tier["axes"] = list(tier.get("axes") or ())
        data["durations"] = list(self.durations)
        data["resolutions"] = list(self.resolutions)
        data["ratios"] = list(self.ratios)
        data["qualities"] = list(self.qualities)
        data["output_counts"] = list(self.output_counts)
        data["modes"] = list(self.modes)
        return data


# The registry populated by register_image_models()/register_video_models().
# Owning modules call those at import time; nothing in this module populates
# it on its own, so importing this module has no side effects.
MODEL_CAPABILITIES: dict = {}


def get_capability(model_id: str) -> Optional[ModelCapability]:
    return MODEL_CAPABILITIES.get((model_id or "").strip())


def serialize_capabilities() -> dict:
    return {model_id: cap.to_dict() for model_id, cap in MODEL_CAPABILITIES.items()}


# ---------------------------------------------------------------------------
# Image registration
# ---------------------------------------------------------------------------

def _image_character_capability(supports_visual_reference: bool, seedream: Optional[dict]) -> CharacterCapability:
    if seedream:
        limits = ReferenceLimits(
            max_count=int(seedream.get("max_references") or 0),
            accepts_inline_base64=bool(seedream.get("allow_inline_base64", True)),
            accepts_url=True,
            param_name=str(seedream.get("reference_param") or ""),
            visual_mode=VisualReferenceMode.REAL_MULTI_IMAGE if supports_visual_reference else VisualReferenceMode.UNSUPPORTED,
        )
    elif supports_visual_reference:
        # No published per-model reference-count limit exists for these
        # providers today (unlike Seedream) - default to a single reference
        # image, the historically safe assumption for non-Seedream image
        # character/object support in this codebase.
        limits = ReferenceLimits(max_count=1, visual_mode=VisualReferenceMode.REAL_MULTI_IMAGE)
    else:
        limits = ReferenceLimits(visual_mode=VisualReferenceMode.UNSUPPORTED)
    # Every image model accepts a text prompt describing the character/object
    # by name - this axis is trivially true for image generation (it is a
    # text-to-image system) and is not the fact under audit here; the visual
    # axis above is what IMAGE_MODEL_FEATURES actually gates today.
    return CharacterCapability(text_conditioning=True, visual_reference=limits)


def register_image_models(image_model_features: dict, seedream_model_capabilities: Optional[dict] = None) -> None:
    """Populate MODEL_CAPABILITIES for every image model in
    main.py's IMAGE_MODEL_FEATURES, folding in SEEDREAM_MODEL_CAPABILITIES's
    per-model reference limits where present. Passed in by main.py - this
    module never imports main.py itself (see module docstring)."""
    seedream_model_capabilities = seedream_model_capabilities or {}
    for model_id, features in image_model_features.items():
        seedream = seedream_model_capabilities.get(model_id)
        character_supported = bool(features.get("character"))
        object_supported = bool(features.get("object"))
        MODEL_CAPABILITIES[model_id] = ModelCapability(
            id=model_id,
            category=MediaCategory.IMAGE,
            provider="",
            character=_image_character_capability(character_supported, seedream if character_supported else None),
            object=_image_character_capability(object_supported, seedream if object_supported else None),
            seed=bool(features.get("seed")),
        )


def image_character_object_seed(model_id: str) -> dict:
    """Behavior-preserving replacement for main.py's image_model_features()
    body, reading from the new registry instead of IMAGE_MODEL_FEATURES
    directly. Kept here (rather than duplicated in main.py) so the parity
    test and the real call site exercise the exact same code path."""
    cap = get_capability(model_id)
    if not cap or cap.category != MediaCategory.IMAGE:
        return {"character": False, "object": False, "seed": False}
    return {
        "character": cap.character.visual_reference.visual_mode != VisualReferenceMode.UNSUPPORTED,
        "object": cap.object.visual_reference.visual_mode != VisualReferenceMode.UNSUPPORTED,
        "seed": cap.seed,
    }


# ---------------------------------------------------------------------------
# Video registration
# ---------------------------------------------------------------------------

# First-pass values only: no existing structure declares per-model visual
# character/object reference behavior for video (that fact does not exist
# anywhere in the codebase yet - see the plan's Schema section). These are
# the models this effort has concrete evidence for so far; every other video
# model defaults to VisualReferenceMode.UNSUPPORTED pending the dedicated
# per-provider audit the plan schedules for Batch 2 (roadmap step 2). This
# is safe for Batch 1: nothing reads/enforces this field for video yet.
_VIDEO_PROVIDER_NATIVE_ASSET_MODELS = {
    "heygen_v3_video_agent", "heygen_avatar_iv", "heygen_avatar_v",
    "heygen_avatar_iii", "heygen_image_video", "heygen_cinematic_avatar",
    "kling_o3_omni",
}

# Kling's dead "voice_control" pricing tier: no VIDEO_MODEL_CONFIG entry ever
# sets voice_control=True and nothing routes to it. Kept, not deleted, not
# made reachable (verifying real Kling API support is out of reach here) -
# see PricingTier.unreachable.
_UNREACHABLE_PRICING_TIERS = {
    ("kling_2_6", "voice_control"),
}


def _video_character_capability(model_id: str) -> CharacterCapability:
    if model_id in _VIDEO_PROVIDER_NATIVE_ASSET_MODELS:
        visual_mode = VisualReferenceMode.PROVIDER_NATIVE_ASSET
        limits = ReferenceLimits(max_count=1, visual_mode=visual_mode)
    else:
        limits = ReferenceLimits(visual_mode=VisualReferenceMode.UNSUPPORTED)
    # Confirmed via services/character_prompts.py + video_router.py's
    # _build_video_visual_prompt(): has_character folds the character into
    # the prompt text (build_character_prompt/OPERATION_PROMPTS) for every
    # video model uniformly, regardless of that model's visual-reference
    # support. This must stay True for all video models.
    return CharacterCapability(text_conditioning=True, visual_reference=limits)


def _video_pricing(model_id: str, kling_cost_matrix: dict) -> dict:
    tiers = kling_cost_matrix.get(model_id)
    if not tiers:
        # Non-Kling video pricing lives in estimate_video_generation_cost's
        # own inline table, not a standalone dict - folding it in is
        # deferred (see plan's "explicitly out of scope" list: this is
        # request-building/pricing-unification work, not this phase's).
        return {}
    pricing = {}
    for variant, table in tiers.items():
        pricing[variant] = PricingTier(
            axes=("resolution", "duration"),
            table=table,
            unreachable=(model_id, variant) in _UNREACHABLE_PRICING_TIERS,
        )
    return pricing


def register_video_models(video_model_config: dict, kling_cost_matrix: Optional[dict] = None) -> None:
    """Populate MODEL_CAPABILITIES for every video model in
    services/video_router.py's VIDEO_MODEL_CONFIG, folding in
    KLING_COST_MATRIX pricing where present. Passed in by main.py - this
    module never imports services.video_router itself (see module
    docstring)."""
    kling_cost_matrix = kling_cost_matrix or {}
    for model_id, config in video_model_config.items():
        modes = tuple(config.get("modes") or ())
        MODEL_CAPABILITIES[model_id] = ModelCapability(
            id=model_id,
            category=MediaCategory.VIDEO,
            provider=str(config.get("provider") or ""),
            start_frame=bool(config.get("start_image")),
            end_frame=bool(config.get("end_image")),
            video_input=bool(config.get("video_edit")),
            motion_reference=bool(config.get("motion_control")),
            # Only kling_lip_sync declares lip_sync today; lip sync is the
            # one existing video mode that requires an audio track as input.
            audio_input=bool(config.get("lip_sync")),
            character=_video_character_capability(model_id),
            object=_video_character_capability(model_id),
            # _build_video_payload passes opts.get("seed") through
            # unconditionally for every model today (no per-model gating
            # exists yet) - transcribed as-is, not audited per-provider.
            seed=True,
            sound_toggle=bool(config.get("sound")),
            native_audio=bool(config.get("native_audio")),
            durations=tuple(config.get("durations") or ()),
            resolutions=tuple(config.get("resolutions") or ()),
            ratios=tuple(config.get("ratios") or ()),
            modes=modes,
            avatar=bool(config.get("avatar")),
            pricing=_video_pricing(model_id, kling_cost_matrix),
        )
