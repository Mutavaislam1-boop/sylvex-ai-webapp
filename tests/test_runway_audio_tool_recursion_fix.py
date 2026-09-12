"""_runway_audio_tool() used to call itself unconditionally with no base
case (services/audio_router.py), guaranteeing a RecursionError on every
single Runway voice/audio call before any network request was even built -
this backs every Runway audio tool (text_to_speech, sound_effect,
speech_to_speech, voice_dubbing, voice_isolation), so the bug took down
all Runway audio functionality, not just one catalog model."""
import services.audio_router as audio_router


def test_runway_audio_tool_does_not_recurse_and_defaults_to_text_to_speech():
    assert audio_router._runway_audio_tool({}) == "text_to_speech"
    assert audio_router._runway_audio_tool({"voice_options": {}}) == "text_to_speech"


def test_runway_audio_tool_honors_an_explicit_valid_tool():
    for tool in audio_router.RUNWAY_AUDIO_TOOLS:
        assert audio_router._runway_audio_tool({"voice_options": {"runway_tool": tool}}) == tool
        assert audio_router._runway_audio_tool({"voice_options": {"runwayTool": tool}}) == tool


def test_runway_audio_tool_falls_back_to_default_for_an_unknown_tool():
    assert audio_router._runway_audio_tool({"voice_options": {"runway_tool": "not_a_real_tool"}}) == "text_to_speech"
