"""TTS (Text-to-Speech) Factory Module.

Provides comprehensive TTS creation with:
- Voice ID validation per provider
- API key validation
- Detailed error handling
- Provider-specific voice constants
- Caching support
"""

import logging
import os
from functools import lru_cache
from typing import Optional

from livekit.agents import inference
from livekit.plugins import cartesia, openai, deepgram

try:
    from livekit.plugins import elevenlabs
except ImportError:
    elevenlabs = None  # type: ignore

try:
    from livekit.plugins import google
except ImportError:
    google = None  # type: ignore

from ..config import KwamiVoiceConfig

logger = logging.getLogger("kwami-agent")


# =============================================================================
# Voice ID Constants
# =============================================================================

class OpenAIVoices:
    """OpenAI TTS voice IDs. Note: ballad/verse are Realtime-only."""
    ALLOY = "alloy"       # Neutral
    ASH = "ash"           # Male
    CORAL = "coral"       # Female
    ECHO = "echo"         # Male
    FABLE = "fable"       # Neutral
    NOVA = "nova"         # Female
    ONYX = "onyx"         # Male
    SAGE = "sage"         # Female
    SHIMMER = "shimmer"   # Female
    
    ALL = {ALLOY, ASH, CORAL, ECHO, FABLE, NOVA, ONYX, SAGE, SHIMMER}
    DEFAULT = NOVA


class ElevenLabsVoices:
    """ElevenLabs voice IDs (premade voices)."""
    RACHEL = "21m00Tcm4TlvDq8ikWAM"
    DOMI = "AZnzlk1XvdvUeBnXmlld"
    BELLA = "EXAVITQu4vr4xnSDxMaL"
    ELLI = "MF3mGyEYCl7XYWbV9V6O"
    JOSH = "TxGEqnHWrfWFTfGW9XjX"
    ARNOLD = "VR6AewLTigWG4xSOukaG"
    ADAM = "pNInz6obpgDQGcFmaJgB"
    SAM = "yoZ06aMxZJJ28mfd3POQ"
    DANIEL = "onwK4e9ZLuTAKqWW03F9"
    CHARLOTTE = "XB0fDUnXU5powFXDhCwa"
    LILY = "pFZP5JQG7iQjIQuC4Bku"
    CALLUM = "N2lVS1w4EtoT3dr4eOWO"
    CHARLIE = "IKne3meq5aSn9XLyUdCD"
    GEORGE = "JBFqnCBsd6RMkjVDRZzb"
    LIAM = "TX3LPaxmHKxFdv7VOQHJ"
    WILL = "bIHbv24MWmeRgasZH58o"
    JESSICA = "cgSgspJ2msm6clMCkdW9"
    ERIC = "cjVigY5qzO86Huf0OWal"
    CHRIS = "iP95p4xoKVk53GoZ742B"
    BRIAN = "nPczCjzI2devNBz1zQrb"
    
    ALL = {RACHEL, DOMI, BELLA, ELLI, JOSH, ARNOLD, ADAM, SAM, DANIEL,
           CHARLOTTE, LILY, CALLUM, CHARLIE, GEORGE, LIAM, WILL,
           JESSICA, ERIC, CHRIS, BRIAN}
    DEFAULT = RACHEL


class CartesiaVoices:
    """Cartesia voice IDs (UUID format)."""
    # English - Female
    BRITISH_LADY = "79a125e8-cd45-4c13-8a67-188112f4dd22"
    JACQUELINE = "9626c31c-bec5-4cca-baa8-f8ba9e84c8bc"
    CALIFORNIA_GIRL = "c2ac25f9-ecc4-4f56-9095-651354df60c0"
    READING_LADY = "b7d50908-b17c-442d-ad8d-810c63997ed9"
    SARAH = "00a77add-48d5-4ef6-8157-71e5437b282d"
    MIDWESTERN_WOMAN = "ed81fd13-2016-4a49-8fe3-c0d2761695fc"
    MARIA = "5619d38c-cf51-4d8e-9575-48f61a280413"
    COMMERCIAL_LADY = "f146dcec-e481-45be-8ad2-96e1e40e7f32"
    # English - Male
    NEWSMAN = "a167e0f3-df7e-4d52-a9c3-f949145efdab"
    COMMERCIAL_MAN = "63ff761f-c1e8-414b-b969-d1833d1c870c"
    FRIENDLY_SIDEKICK = "421b3369-f63f-4b03-8980-37a44df1d4e8"
    SOUTHERN_MAN = "638efaaa-4d0c-442e-b701-3fae16aad012"
    WISE_MAN = "fb26447f-308b-471e-8b00-8e9f04284eb5"
    BRITISH_NARRATOR = "2ee87190-8f84-4925-97da-e52547f9462c"
    
    DEFAULT = BRITISH_LADY


class DeepgramVoices:
    """Deepgram Aura voice IDs."""
    # Female
    ASTERIA = "asteria"
    LUNA = "luna"
    STELLA = "stella"
    ATHENA = "athena"
    HERA = "hera"
    # Male
    ORION = "orion"
    ARCAS = "arcas"
    PERSEUS = "perseus"
    ANGUS = "angus"
    ORPHEUS = "orpheus"
    HELIOS = "helios"
    ZEUS = "zeus"
    
    ALL = {ASTERIA, LUNA, STELLA, ATHENA, HERA, ORION, ARCAS, 
           PERSEUS, ANGUS, ORPHEUS, HELIOS, ZEUS}
    DEFAULT = ASTERIA


class GoogleVoices:
    """Google Cloud TTS voice IDs."""
    STUDIO_O = "en-US-Studio-O"      # Female
    STUDIO_Q = "en-US-Studio-Q"      # Male
    NEURAL2_A = "en-US-Neural2-A"    # Male
    NEURAL2_C = "en-US-Neural2-C"    # Female
    NEURAL2_D = "en-US-Neural2-D"    # Male
    NEURAL2_E = "en-US-Neural2-E"    # Female
    NEURAL2_F = "en-US-Neural2-F"    # Female
    NEURAL2_G = "en-US-Neural2-G"    # Female
    NEURAL2_H = "en-US-Neural2-H"    # Female
    NEURAL2_I = "en-US-Neural2-I"    # Male
    NEURAL2_J = "en-US-Neural2-J"    # Male
    
    DEFAULT = STUDIO_O


# =============================================================================
# API Key Validation
# =============================================================================

def _check_api_key(provider: str) -> bool:
    """Check if the required API key is set for a provider."""
    key_map = {
        "openai": ["OPENAI_API_KEY"],
        "elevenlabs": ["ELEVEN_API_KEY", "ELEVENLABS_API_KEY"],  # Accept both variants
        "cartesia": ["CARTESIA_API_KEY"],
        "deepgram": ["DEEPGRAM_API_KEY"],
        "google": ["GOOGLE_APPLICATION_CREDENTIALS"],
    }
    env_vars = key_map.get(provider, [])
    if not env_vars:
        return True  # Unknown provider, assume OK
    
    # Check if any of the valid env vars are set
    for env_var in env_vars:
        if os.getenv(env_var):
            return True
    
    logger.warning(f"⚠️ {' or '.join(env_vars)} not set for {provider} TTS")
    return False


# =============================================================================
# TTS Factory
# =============================================================================

def create_tts(config: KwamiVoiceConfig):
    """Create TTS instance based on configuration.
    
    Args:
        config: Voice configuration with provider, model, voice, speed settings.
        
    Returns:
        TTS instance for the specified provider.
        
    Raises:
        ValueError: If provider is invalid and no fallback available.
    """
    provider = config.tts_provider.lower()
    
    logger.info(
        f"🔊 Creating TTS: provider={provider}, "
        f"model={config.tts_model}, voice={config.tts_voice}"
    )
    
    # Check API key (warning only, don't block)
    _check_api_key(provider)
    
    try:
        if provider == "openai":
            return _create_openai_tts(config)
        
        elif provider == "elevenlabs":
            return _create_elevenlabs_tts(config)
        
        elif provider == "cartesia":
            return _create_cartesia_tts(config)
        
        elif provider == "deepgram":
            return _create_deepgram_tts(config)
        
        elif provider == "google":
            return _create_google_tts(config)
        
        else:
            logger.warning(f"Unknown TTS provider '{provider}', falling back to OpenAI")
            return _create_openai_tts(config)
            
    except Exception as e:
        logger.error(f"Failed to create {provider} TTS: {e}, falling back to OpenAI")
        return _create_openai_tts(config)


# =============================================================================
# Provider-Specific Factories
# =============================================================================

OPENAI_TTS_MODELS = {"tts-1", "tts-1-hd", "gpt-4o-mini-tts"}

def _create_openai_tts(config: KwamiVoiceConfig):
    """Create OpenAI TTS with voice and model validation."""
    voice = config.tts_voice or OpenAIVoices.DEFAULT
    model = config.tts_model or "tts-1"
    
    # Validate model - must be an OpenAI TTS model
    if model not in OPENAI_TTS_MODELS:
        logger.warning(
            f"Model '{model}' not supported by OpenAI TTS. "
            f"Using 'tts-1'. Valid: {', '.join(sorted(OPENAI_TTS_MODELS))}"
        )
        model = "tts-1"
    
    # Validate voice
    if voice not in OpenAIVoices.ALL:
        logger.warning(
            f"Voice '{voice}' not supported by OpenAI TTS. "
            f"Using '{OpenAIVoices.DEFAULT}'. "
            f"Valid: {', '.join(sorted(OpenAIVoices.ALL))}"
        )
        voice = OpenAIVoices.DEFAULT
    
    return openai.TTS(
        model=model,
        voice=voice,
        speed=config.tts_speed or 1.0,
    )


def _create_elevenlabs_tts(config: KwamiVoiceConfig):
    """Create ElevenLabs TTS using LiveKit Inference (more reliable than direct plugin)."""
    voice_id = config.tts_voice or ElevenLabsVoices.DEFAULT
    model = config.tts_model or "eleven_turbo_v2_5"
    
    # Use LiveKit Inference for ElevenLabs - more reliable than direct plugin
    # Format: "elevenlabs/model:voice_id"
    model_string = f"elevenlabs/{model}"
    
    logger.info(f"🔊 Using LiveKit Inference for ElevenLabs: {model_string}:{voice_id}")
    
    return inference.TTS(
        model=model_string,
        voice=voice_id,
    )


def _create_cartesia_tts(config: KwamiVoiceConfig):
    """Create Cartesia TTS."""
    voice = config.tts_voice or CartesiaVoices.DEFAULT
    
    # Cartesia uses UUID format voice IDs
    if voice and len(voice) < 30 and "-" not in voice:
        logger.warning(
            f"Voice '{voice}' may be invalid for Cartesia (expected UUID format). "
            f"Using default: {CartesiaVoices.DEFAULT}"
        )
        voice = CartesiaVoices.DEFAULT
    
    return cartesia.TTS(
        model=config.tts_model or "sonic-2",
        voice=voice,
        speed=config.tts_speed or 1.0,
        encoding="pcm_s16le",
    )


def _create_deepgram_tts(config: KwamiVoiceConfig):
    """Create Deepgram Aura TTS with voice validation."""
    voice = config.tts_voice or DeepgramVoices.DEFAULT
    
    if voice not in DeepgramVoices.ALL:
        logger.warning(
            f"Voice '{voice}' not in known Deepgram voices. "
            f"Using '{DeepgramVoices.DEFAULT}'. "
            f"Valid: {', '.join(sorted(DeepgramVoices.ALL))}"
        )
        voice = DeepgramVoices.DEFAULT
    
    # Deepgram model includes voice (e.g., "aura-asteria-en")
    model = config.tts_model or f"aura-{voice}-en"
    
    return deepgram.TTS(model=model)


def _create_google_tts(config: KwamiVoiceConfig):
    """Create Google Cloud TTS with fallback handling."""
    if google is None:
        logger.warning("Google TTS plugin not installed, falling back to OpenAI")
        return _create_openai_tts(config)
    
    voice = config.tts_voice or GoogleVoices.DEFAULT
    
    return google.TTS(
        voice=voice,
        speaking_rate=config.tts_speed or 1.0,
    )


# =============================================================================
# Utility Functions
# =============================================================================

def get_available_providers() -> list[str]:
    """Get list of available TTS providers based on installed plugins."""
    providers = ["openai", "deepgram", "cartesia"]
    
    if elevenlabs is not None:
        providers.append("elevenlabs")
    if google is not None:
        providers.append("google")
    
    return providers


def get_voices_for_provider(provider: str) -> list[str]:
    """Get list of valid voice IDs for a provider."""
    provider = provider.lower()
    
    if provider == "openai":
        return list(OpenAIVoices.ALL)
    elif provider == "elevenlabs":
        return list(ElevenLabsVoices.ALL)
    elif provider == "deepgram":
        return list(DeepgramVoices.ALL)
    elif provider == "cartesia":
        return [CartesiaVoices.BRITISH_LADY, CartesiaVoices.NEWSMAN]  # Just examples
    elif provider == "google":
        return [GoogleVoices.STUDIO_O, GoogleVoices.STUDIO_Q]
    
    return []


def get_default_voice(provider: str) -> str:
    """Get the default voice ID for a provider."""
    provider = provider.lower()
    
    defaults = {
        "openai": OpenAIVoices.DEFAULT,
        "elevenlabs": ElevenLabsVoices.DEFAULT,
        "cartesia": CartesiaVoices.DEFAULT,
        "deepgram": DeepgramVoices.DEFAULT,
        "google": GoogleVoices.DEFAULT,
    }
    
    return defaults.get(provider, "default")
