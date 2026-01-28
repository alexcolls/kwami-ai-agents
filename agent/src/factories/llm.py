from livekit.plugins import openai

try:
    from livekit.plugins import google
except ImportError:
    google = None  # type: ignore

from ..config import KwamiVoiceConfig


def create_llm(config: KwamiVoiceConfig):
    """Create LLM instance based on configuration."""
    provider = config.llm_provider.lower()
    
    if provider == "openai":
        return openai.LLM(
            model=config.llm_model or "gpt-4o-mini",
            temperature=config.llm_temperature,
        )
    
    elif provider == "google" and google is not None:
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
