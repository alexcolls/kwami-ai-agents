"""Provider detection utilities for TTS/LLM switching."""

from typing import Optional, Tuple

# OpenAI TTS voice names
OPENAI_VOICES = {"alloy", "ash", "coral", "echo", "fable", "nova", "onyx", "sage", "shimmer"}


def detect_tts_provider_from_model(model: str) -> Optional[str]:
    """Detect TTS provider based on model name.
    
    Args:
        model: The model name/identifier.
        
    Returns:
        Provider name if detected, None otherwise.
    """
    if not model:
        return None
    
    model_lower = model.lower()
    
    if model_lower.startswith("eleven_"):
        return "elevenlabs"
    
    if model_lower.startswith("tts-") or model_lower.startswith("gpt-4o"):
        return "openai"
    
    if model_lower.startswith("sonic"):
        return "cartesia"
    
    if model_lower.startswith("aura"):
        return "deepgram"
    
    return None


def detect_tts_provider_from_voice(voice: str) -> Optional[str]:
    """Detect TTS provider based on voice ID format.
    
    Args:
        voice: The voice ID or name.
        
    Returns:
        Provider name if detected, None otherwise.
    """
    if not voice:
        return None
    
    # ElevenLabs: 20+ char alphanumeric IDs (e.g., "JBFqnCBsd6RMkjVDRZzb")
    if len(voice) >= 20 and voice.isalnum():
        return "elevenlabs"
    
    # Cartesia: UUID format (e.g., "79a125e8-cd45-4c13-8a67-188112f4dd22")
    if len(voice) == 36 and voice.count("-") == 4:
        return "cartesia"
    
    # OpenAI: Short lowercase names
    if voice.lower() in OPENAI_VOICES:
        return "openai"
    
    return None


def detect_provider_change(
    current_provider: str,
    new_model: Optional[str] = None,
    new_voice: Optional[str] = None,
) -> Tuple[str, bool]:
    """Detect if provider should change based on new model/voice.
    
    Args:
        current_provider: The current TTS provider.
        new_model: New model name (if changing).
        new_voice: New voice ID (if changing).
        
    Returns:
        Tuple of (detected_provider, has_changed).
    """
    detected_provider = current_provider
    
    # First try to detect from model (higher confidence)
    if new_model:
        model_provider = detect_tts_provider_from_model(new_model)
        if model_provider:
            detected_provider = model_provider
    
    # If model didn't change provider, try voice
    if detected_provider == current_provider and new_voice:
        voice_provider = detect_tts_provider_from_voice(new_voice)
        if voice_provider:
            detected_provider = voice_provider
    
    has_changed = detected_provider != current_provider
    return detected_provider, has_changed
