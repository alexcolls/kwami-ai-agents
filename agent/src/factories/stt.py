from livekit.plugins import deepgram, openai

try:
    from livekit.plugins import assemblyai
except ImportError:
    assemblyai = None  # type: ignore

try:
    from livekit.plugins import google
except ImportError:
    google = None  # type: ignore

try:
    from livekit.plugins import elevenlabs
except ImportError:
    elevenlabs = None  # type: ignore

from ..config import KwamiVoiceConfig


def create_stt(config: KwamiVoiceConfig):
    """Create STT instance based on configuration."""
    provider = config.stt_provider.lower()
    
    if provider == "deepgram":
        return deepgram.STT(
            model=config.stt_model,
            language=config.stt_language,
            interim_results=True,
            smart_format=True,
            punctuate=True,
        )
    
    elif provider == "openai":
        return openai.STT(
            model=config.stt_model or "whisper-1",
            language=config.stt_language if config.stt_language != "multi" else None,
        )
    
    elif provider == "assemblyai" and assemblyai is not None:
        return assemblyai.STT(
            word_boost=config.stt_word_boost or [],
        )
    
    elif provider == "google" and google is not None:
        return google.STT(
            model=config.stt_model or "chirp",
            languages=[config.stt_language or "en-US"],
        )
    
    elif provider == "elevenlabs" and elevenlabs is not None:
        return elevenlabs.STT(
            model=config.stt_model or "scribe_v1",
            language=config.stt_language or "en",
        )
    
    # Default to Deepgram
    return deepgram.STT(
        model="nova-2",
        language="en",
    )
