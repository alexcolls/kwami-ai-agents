"""Factory functions for creating agent pipeline components.

Supports multiple providers based on available API keys:
- STT: Deepgram, OpenAI Whisper, AssemblyAI, Google Cloud, ElevenLabs
- LLM: OpenAI, Google Gemini, Anthropic, Groq, DeepSeek, Mistral, Cerebras, Ollama
- TTS: Cartesia, ElevenLabs, OpenAI, Deepgram, Google Cloud
"""

from livekit.plugins import (
    cartesia,
    deepgram,
    openai,
    silero,
    google,
    elevenlabs,
    assemblyai,
)

from config import KwamiVoiceConfig


# =============================================================================
# Speech-to-Text (STT) Factory
# =============================================================================

def create_stt(config: KwamiVoiceConfig):
    """Create STT instance based on configuration.
    
    Supported providers:
    - deepgram: Deepgram Nova models (nova-3, nova-2, etc.)
    - openai: OpenAI Whisper models
    - assemblyai: AssemblyAI models
    - google: Google Cloud Speech-to-Text
    - elevenlabs: ElevenLabs Scribe
    """
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
    
    elif provider == "assemblyai":
        return assemblyai.STT(
            word_boost=config.stt_word_boost or [],
        )
    
    elif provider == "google":
        return google.STT(
            model=config.stt_model or "chirp",
            languages=[config.stt_language or "en-US"],
        )
    
    elif provider == "elevenlabs":
        return elevenlabs.STT(
            model=config.stt_model or "scribe_v1",
            language=config.stt_language or "en",
        )
    
    # Default to Deepgram
    return deepgram.STT(
        model="nova-2",
        language="en",
    )


# =============================================================================
# Large Language Model (LLM) Factory
# =============================================================================

def create_llm(config: KwamiVoiceConfig):
    """Create LLM instance based on configuration.
    
    Supported providers:
    - openai: GPT-4o, GPT-4, GPT-3.5, o1 models
    - google: Gemini models (2.0, 1.5 Pro, 1.5 Flash)
    - anthropic: Claude models (via OpenAI-compatible endpoint)
    - groq: Llama, Mixtral models (via OpenAI-compatible endpoint)
    - deepseek: DeepSeek Chat, Reasoner
    - mistral: Mistral Large, Medium, Small
    - cerebras: Llama models on Cerebras hardware
    - ollama: Local models
    """
    provider = config.llm_provider.lower()
    
    if provider == "openai":
        return openai.LLM(
            model=config.llm_model or "gpt-4o-mini",
            temperature=config.llm_temperature,
        )
    
    elif provider == "google":
        return google.LLM(
            model=config.llm_model or "gemini-2.0-flash",
            temperature=config.llm_temperature,
        )
    
    elif provider == "anthropic":
        # Anthropic via OpenAI-compatible API
        return openai.LLM.with_anthropic(
            model=config.llm_model or "claude-3-5-sonnet-latest",
            temperature=config.llm_temperature,
        )
    
    elif provider == "groq":
        # Groq via OpenAI-compatible API
        return openai.LLM.with_groq(
            model=config.llm_model or "llama-3.1-70b-versatile",
            temperature=config.llm_temperature,
        )
    
    elif provider == "deepseek":
        # DeepSeek via OpenAI-compatible API
        return openai.LLM.with_deepseek(
            model=config.llm_model or "deepseek-chat",
            temperature=config.llm_temperature,
        )
    
    elif provider == "mistral":
        # Mistral via OpenAI-compatible API  
        return openai.LLM.with_x_ai(
            model=config.llm_model or "mistral-large-latest",
            temperature=config.llm_temperature,
            base_url="https://api.mistral.ai/v1",
        )
    
    elif provider == "cerebras":
        # Cerebras via OpenAI-compatible API
        return openai.LLM.with_cerebras(
            model=config.llm_model or "llama3.1-70b",
            temperature=config.llm_temperature,
        )
    
    elif provider == "ollama":
        # Ollama local models
        return openai.LLM.with_ollama(
            model=config.llm_model or "llama3.2",
            temperature=config.llm_temperature,
        )
    
    # Default to OpenAI
    return openai.LLM(
        model="gpt-4o-mini",
        temperature=0.7,
    )


# =============================================================================
# Text-to-Speech (TTS) Factory
# =============================================================================

def create_tts(config: KwamiVoiceConfig):
    """Create TTS instance based on configuration.
    
    Supported providers:
    - cartesia: Sonic models with wide voice selection
    - elevenlabs: Turbo, Multilingual, Flash models
    - openai: TTS-1, TTS-1-HD, GPT-4o-mini-TTS
    - deepgram: Aura voices
    - google: Studio and Neural2 voices
    """
    provider = config.tts_provider.lower()
    
    if provider == "cartesia":
        return cartesia.TTS(
            model=config.tts_model or "sonic-2",
            voice=config.tts_voice or "79a125e8-cd45-4c13-8a67-188112f4dd22",
            speed=config.tts_speed,
            encoding="pcm_s16le",
        )
    
    elif provider == "elevenlabs":
        return elevenlabs.TTS(
            model=config.tts_model or "eleven_turbo_v2_5",
            voice=config.tts_voice or "21m00Tcm4TlvDq8ikWAM",  # Rachel
        )
    
    elif provider == "openai":
        return openai.TTS(
            model=config.tts_model or "tts-1",
            voice=config.tts_voice or "alloy",
            speed=config.tts_speed,
        )
    
    elif provider == "deepgram":
        return deepgram.TTS(
            model=config.tts_model or "aura-asteria-en",
        )
    
    elif provider == "google":
        return google.TTS(
            voice=config.tts_voice or "en-US-Studio-O",
            speaking_rate=config.tts_speed,
        )
    
    # Default to Cartesia
    return cartesia.TTS(
        model="sonic-2",
        voice="79a125e8-cd45-4c13-8a67-188112f4dd22",
    )


# =============================================================================
# Voice Activity Detection (VAD) Factory
# =============================================================================

def create_vad(config: KwamiVoiceConfig):
    """Create VAD instance based on configuration.
    
    Currently only Silero VAD is supported as it's the most reliable
    for real-time voice detection.
    """
    return silero.VAD.load(
        min_speech_duration=config.vad_min_speech_duration,
        min_silence_duration=config.vad_min_silence_duration,
    )


# =============================================================================
# Realtime Model Factory
# =============================================================================

def create_realtime_model(config: KwamiVoiceConfig):
    """Create Realtime model instance for ultra-low latency.
    
    Supported providers:
    - openai: GPT-4o Realtime
    - google: Gemini 2.0 Flash Live
    """
    provider = config.realtime_provider.lower() if config.realtime_provider else "openai"
    
    if provider == "openai":
        return openai.realtime.RealtimeModel(
            model=config.realtime_model or "gpt-4o-realtime-preview",
            voice=config.realtime_voice or "alloy",
            temperature=config.llm_temperature,
            modalities=config.realtime_modalities or ["text", "audio"],
            turn_detection=openai.realtime.ServerVadOptions(
                threshold=config.vad_threshold,
                prefix_padding_ms=300,
                silence_duration_ms=int(config.vad_min_silence_duration * 1000),
            ),
        )
    
    elif provider == "google":
        return google.beta.realtime.RealtimeModel(
            model=config.realtime_model or "gemini-2.0-flash-exp",
            voice=config.realtime_voice or "Puck",
            temperature=config.llm_temperature,
        )
    
    # Default to OpenAI Realtime
    return openai.realtime.RealtimeModel(
        model="gpt-4o-realtime-preview",
        voice="alloy",
    )
