import asyncio
import json
import logging
import traceback
from dataclasses import replace
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

# Load .env from the kwami-ai-lk root directory (2 levels up from here if we are in agent/agent/main.py)
# Adjust path: kwami-ai-lk/agent/agent/main.py -> kwami-ai-lk/.env
load_dotenv(Path(__file__).parent.parent.parent / ".env")

from livekit import rtc
from livekit.agents import (
    AgentServer,
    AgentSession,
    JobContext,
    JobProcess,
    cli,
    room_io,
)
from livekit.plugins import silero

from .config import KwamiConfig, KwamiVoiceConfig
from .core import KwamiAgent
from .factories import llm as llm_factory
from .factories import stt as stt_factory
from .factories import tts as tts_factory
from .factories import realtime as realtime_factory
from .memory import create_memory, KwamiMemory

# Don't call logging.basicConfig() - LiveKit agents sets up JSON logging
logger = logging.getLogger("kwami-agent")

server = AgentServer()


def prewarm(proc: JobProcess):
    """Prewarm the VAD model for faster startup."""
    proc.userdata["vad"] = silero.VAD.load()


server.setup_fnc = prewarm


@server.rtc_session(agent_name="kwami-agent")
async def entrypoint(ctx: JobContext):
    """Main entry point for Kwami agent sessions."""
    logger.info(f"🚀 Kwami session starting in room: {ctx.room.name}")

    # Log participants for debugging and extract user identity
    logger.info(f"📋 Room has {len(ctx.room.remote_participants)} remote participants")
    user_identity = None
    for pid, p in ctx.room.remote_participants.items():
        logger.info(f"  - {p.identity} (connected: {p.is_connected})")
        # Get the first non-agent participant as the user identity
        if not p.identity.startswith("agent"):
            user_identity = p.identity
            logger.info(f"👤 User identity: {user_identity}")

    # Get prewarmed VAD
    vad = ctx.proc.userdata["vad"]
    
    # 1. Start with default configuration initially
    # This ensures we connect to the room quickly.
    config = KwamiConfig()
    
    # create default components
    initial_agent = _create_agent_from_config(config, vad)
    session = AgentSession()
    
    # Track current agent manually since AgentSession doesn't expose it
    # Also store user_identity for memory fallback
    agent_state = {"current_agent": initial_agent, "user_identity": user_identity}
    
    # 2. Setup data handler for config updates
    # Only ONE handler is needed if it handles both "config" (initial) and "config_update"
    def handle_data(data: rtc.DataPacket):
        try:
            payload = data.data.decode("utf-8")
            message = json.loads(payload)
            msg_type = message.get("type")
            
            logger.info(f"📨 Received data message: {msg_type}")
            
            if msg_type == "config":
                # Initial setup or full reconfiguration
                asyncio.create_task(
                    _handle_full_config(session, agent_state, message, vad)
                )
            elif msg_type == "config_update":
                # Partial update
                asyncio.create_task(
                    _handle_config_update(session, agent_state, message, vad)
                )
            elif msg_type == "tool_result":
                # Handle tool result from client
                current_agent = agent_state.get("current_agent")
                if current_agent and hasattr(current_agent, "handle_tool_result"):
                    # Execute in background or directly? The handle_tool_result just resolves a future, 
                    # so it's fast.
                    current_agent.handle_tool_result(
                        message.get("toolCallId"),
                        message.get("result"),
                        message.get("error")
                    )
                
        except Exception as e:
            logger.error(f"Error handling data message: {e}")

    ctx.room.on("data_received", handle_data)

    # 3. Start the session
    await session.start(
        agent=initial_agent,
        room=ctx.room,
        room_options=room_io.RoomOptions(
            audio_input=True,
            audio_output=True,
        ),
    )
    
    logger.info(f"✅ Kwami session started for room: {ctx.room.name}")


def _create_agent_from_config(config: KwamiConfig, vad, memory=None, skip_greeting: bool = False) -> KwamiAgent:
    """Helper to create a KwamiAgent instance from a config object.
    
    Args:
        config: The Kwami configuration
        vad: Voice Activity Detection instance
        memory: Optional memory instance
        skip_greeting: If True, skip the initial greeting (used for reconfigurations)
    """
    voice_config = config.voice
    
    if voice_config.pipeline_type == "realtime":
        logger.info(f"Using realtime pipeline: {voice_config.realtime_provider}/{voice_config.realtime_model}")
        realtime_model = realtime_factory.create_realtime_model(voice_config)
        return KwamiAgent(config, vad=vad, memory=memory, llm=realtime_model, skip_greeting=skip_greeting)
    else:
        logger.info(
            f"Using standard pipeline: "
            f"STT={voice_config.stt_provider}/{voice_config.stt_model}, "
            f"LLM={voice_config.llm_provider}/{voice_config.llm_model}, "
            f"TTS={voice_config.tts_provider}/{voice_config.tts_model}"
        )
        stt = stt_factory.create_stt(voice_config)
        llm = llm_factory.create_llm(voice_config)
        tts = tts_factory.create_tts(voice_config)
        return KwamiAgent(config, vad=vad, memory=memory, stt=stt, llm=llm, tts=tts, skip_greeting=skip_greeting)


async def _handle_full_config(session: AgentSession, agent_state: dict, message: dict, vad):
    """Handle the 'config' message which sets the entire identity/pipeline."""
    try:
        logger.info("📥 Processing full configuration...")
        
        # 1. Parse into KwamiConfig
        new_config = KwamiConfig()
        
        # ... (Parsing logic similar to original but robust) ...
        # Apply frontend voice config
        voice_data = message.get("voice", {})
        
        # TTS
        tts_data = voice_data.get("tts", {})
        if tts_data.get("provider"): new_config.voice.tts_provider = tts_data["provider"]
        if tts_data.get("model"): new_config.voice.tts_model = tts_data["model"]
        if tts_data.get("voice"): new_config.voice.tts_voice = tts_data["voice"]
        if tts_data.get("speed"): new_config.voice.tts_speed = tts_data["speed"]
        
        # LLM
        llm_data = voice_data.get("llm", {})
        if llm_data.get("provider"): new_config.voice.llm_provider = llm_data["provider"]
        if llm_data.get("model"): new_config.voice.llm_model = llm_data["model"]
        if llm_data.get("temperature"): new_config.voice.llm_temperature = llm_data["temperature"]
        if llm_data.get("maxTokens"): new_config.voice.llm_max_tokens = llm_data["maxTokens"]
        
        # STT
        stt_data = voice_data.get("stt", {})
        if stt_data.get("provider"): new_config.voice.stt_provider = stt_data["provider"]
        if stt_data.get("model"): new_config.voice.stt_model = stt_data["model"]
        if stt_data.get("language"): new_config.voice.stt_language = stt_data["language"]
        
        # Kwami details
        # Use kwamiId from message, or fall back to user_identity (participant name)
        kwami_id = message.get("kwamiId") or agent_state.get("user_identity")
        if kwami_id: 
            new_config.kwami_id = kwami_id
            logger.info(f"👤 Using kwami_id for memory: {kwami_id}")
        if message.get("kwamiName"): new_config.kwami_name = message["kwamiName"]
        
        # Persona
        persona_data = message.get("persona", {})
        if persona_data.get("name"): new_config.persona.name = persona_data["name"]
        if persona_data.get("personality"): new_config.persona.personality = persona_data["personality"]
        if persona_data.get("systemPrompt"): new_config.persona.system_prompt = persona_data["systemPrompt"]
        if persona_data.get("traits"): new_config.persona.traits = persona_data["traits"]
        
        # 2. Initialize Memory (Important Fix!)
        memory = None
        if new_config.memory.enabled or message.get("memory", {}).get("enabled"):
             # Update memory config if present in message
            mem_data = message.get("memory", {})
            if mem_data.get("enabled") is not None:
                 new_config.memory.enabled = mem_data["enabled"]
            
            if new_config.memory.enabled:
                if not new_config.memory.user_id and new_config.kwami_id:
                    new_config.memory.user_id = f"kwami_{new_config.kwami_id}"
                
                memory = await create_memory(
                    config=new_config.memory,
                    kwami_id=new_config.kwami_id or "default",
                    kwami_name=new_config.kwami_name,
                )
        
        # 3. Create NEW Agent with this config (skip greeting since this is a reconfiguration)
        new_agent = _create_agent_from_config(new_config, vad, memory, skip_greeting=True)
        
        # 4. Switch to new agent
        session.update_agent(new_agent)
        agent_state["current_agent"] = new_agent
        logger.info(f"✅ Reconfigured agent: {new_config.voice.llm_provider}/{new_config.voice.tts_provider}")

    except Exception as e:
        logger.error(f"Failed to process full config: {e}")
        traceback.print_exc()


async def _handle_config_update(session: AgentSession, agent_state: dict, message: dict, vad):
    """Handle partial updates (voice, llm, persona)."""
    update_type = message.get("updateType")
    config_payload = message.get("config", {})
    
    current_agent: KwamiAgent = agent_state.get("current_agent")
    if not isinstance(current_agent, KwamiAgent):
        return

    try:
        if update_type == "voice":
            await _update_voice(session, agent_state, current_agent, config_payload, vad)
        elif update_type == "llm":
            await _update_llm(session, agent_state, current_agent, config_payload, vad)
        elif update_type == "persona":
            _update_persona(current_agent, config_payload)
            
    except Exception as e:
        logger.error(f"Error updating {update_type}: {e}")
        traceback.print_exc()


async def _update_voice(session, agent_state, agent, config, vad):
    """Update voice/TTS configuration, switching providers if needed."""
    current_provider = agent.kwami_config.voice.tts_provider
    new_provider = config.get("tts_provider") or current_provider
    new_model = config.get("tts_model")
    new_voice = config.get("tts_voice")
    
    # Detect if we need a provider switch based on model name or voice ID format
    # ElevenLabs models start with "eleven_", OpenAI models are "tts-1", etc.
    if new_model:
        if new_model.startswith("eleven_") and new_provider != "elevenlabs":
            new_provider = "elevenlabs"
            logger.info(f"Auto-detected ElevenLabs provider from model: {new_model}")
        elif new_model.startswith("tts-") or new_model.startswith("gpt-4o") and new_provider != "openai":
            new_provider = "openai"
            logger.info(f"Auto-detected OpenAI provider from model: {new_model}")
        elif new_model.startswith("sonic") and new_provider != "cartesia":
            new_provider = "cartesia"
            logger.info(f"Auto-detected Cartesia provider from model: {new_model}")
        elif new_model.startswith("aura") and new_provider != "deepgram":
            new_provider = "deepgram"
            logger.info(f"Auto-detected Deepgram provider from model: {new_model}")
    
    # Also detect provider from voice ID format if model didn't give us enough info
    if new_voice and new_provider == current_provider:
        # ElevenLabs: 20+ char alphanumeric IDs (e.g., "JBFqnCBsd6RMkjVDRZzb")
        if len(new_voice) >= 20 and new_voice.isalnum() and new_provider != "elevenlabs":
            new_provider = "elevenlabs"
            logger.info(f"Auto-detected ElevenLabs provider from voice ID format: {new_voice}")
        # Cartesia: UUID format (e.g., "79a125e8-cd45-4c13-8a67-188112f4dd22")
        elif len(new_voice) == 36 and new_voice.count("-") == 4 and new_provider != "cartesia":
            new_provider = "cartesia"
            logger.info(f"Auto-detected Cartesia provider from voice ID format: {new_voice}")
        # OpenAI: Short lowercase names (alloy, ash, coral, echo, fable, nova, onyx, sage, shimmer)
        elif new_voice in {"alloy", "ash", "coral", "echo", "fable", "nova", "onyx", "sage", "shimmer"} and new_provider != "openai":
            new_provider = "openai"
            logger.info(f"Auto-detected OpenAI provider from voice name: {new_voice}")
    
    # Check if provider actually changed
    provider_changed = new_provider != current_provider
    
    # ElevenLabs doesn't support speed updates via update_options, requires agent recreation
    # Only trigger if speed actually changed from current value
    is_elevenlabs = current_provider == "elevenlabs"
    current_speed = agent.kwami_config.voice.tts_speed or 1.0
    new_speed = config.get("tts_speed")
    speed_actually_changed = new_speed is not None and float(new_speed) != float(current_speed)
    speed_changed = speed_actually_changed and is_elevenlabs
    
    if provider_changed or speed_changed:
        reason = "provider change" if provider_changed else "speed change (ElevenLabs)"
        logger.info(f"🔄 Switching TTS: {current_provider} → {new_provider} ({reason})")
        # Full agent switch needed for provider change
        new_voice_config = replace(agent.kwami_config.voice)
        new_voice_config.tts_provider = new_provider
        if new_model: new_voice_config.tts_model = new_model
        if new_voice: new_voice_config.tts_voice = new_voice
        if config.get("tts_speed"): new_voice_config.tts_speed = config["tts_speed"]
        
        new_config = replace(agent.kwami_config)
        new_config.voice = new_voice_config
        
        new_agent = _create_agent_from_config(new_config, vad, agent._memory, skip_greeting=True)
        session.update_agent(new_agent)
        agent_state["current_agent"] = new_agent
        logger.info(f"✅ Switched to {new_provider} TTS")
    else:
        # Same provider - just update options if supported
        if hasattr(agent, "tts") and agent.tts:
            updates = {}
            # Detect TTS provider
            tts_provider = getattr(agent.tts, "provider", "").lower()
            is_elevenlabs = tts_provider == "elevenlabs" or "elevenlabs" in type(agent.tts).__module__
            
            if new_voice:
                # Different TTS providers use different parameter names for voice
                if is_elevenlabs:
                    updates["voice_id"] = new_voice
                else:
                    updates["voice"] = new_voice
            
            # ElevenLabs doesn't support speed in update_options - requires agent recreation
            if config.get("tts_speed") and not is_elevenlabs:
                updates["speed"] = config["tts_speed"]
            
            if updates and hasattr(agent.tts, "update_options"):
                try:
                    agent.tts.update_options(**updates)
                    # Update stored config to reflect new values
                    if new_voice:
                        agent.kwami_config.voice.tts_voice = new_voice
                    if config.get("tts_speed"):
                        agent.kwami_config.voice.tts_speed = config["tts_speed"]
                    logger.info(f"Updated TTS options: {updates}")
                except Exception as e:
                    logger.warning(f"Failed to update TTS options: {e}, recreating agent")
                    # If update fails, recreate the agent
                    new_voice_config = replace(agent.kwami_config.voice)
                    if new_voice: new_voice_config.tts_voice = new_voice
                    if config.get("tts_speed"): new_voice_config.tts_speed = config["tts_speed"]
                    new_config = replace(agent.kwami_config)
                    new_config.voice = new_voice_config
                    new_agent = _create_agent_from_config(new_config, vad, agent._memory, skip_greeting=True)
                    session.update_agent(new_agent)
                    agent_state["current_agent"] = new_agent
            
        # Handle STT updates
        stt_provider_changed = config.get("stt_provider") and config["stt_provider"] != agent.kwami_config.voice.stt_provider
        stt_model_changed = config.get("stt_model") and config["stt_model"] != agent.kwami_config.voice.stt_model
        
        if stt_provider_changed or stt_model_changed:
            # STT provider/model change requires agent recreation
            logger.info(f"🔄 Switching STT: {agent.kwami_config.voice.stt_provider} → {config.get('stt_provider', agent.kwami_config.voice.stt_provider)}")
            new_voice_config = replace(agent.kwami_config.voice)
            if config.get("stt_provider"): new_voice_config.stt_provider = config["stt_provider"]
            if config.get("stt_model"): new_voice_config.stt_model = config["stt_model"]
            if config.get("stt_language"): new_voice_config.stt_language = config["stt_language"]
            new_config = replace(agent.kwami_config)
            new_config.voice = new_voice_config
            new_agent = _create_agent_from_config(new_config, vad, agent._memory, skip_greeting=True)
            session.update_agent(new_agent)
            agent_state["current_agent"] = new_agent
            logger.info(f"✅ Switched to {new_voice_config.stt_provider} STT")
        elif hasattr(agent, "stt") and agent.stt:
            # Just update STT options (language only)
            updates = {}
            if config.get("stt_language"): updates["language"] = config["stt_language"]
            if updates and hasattr(agent.stt, "update_options"):
                agent.stt.update_options(**updates)
                logger.info(f"Updated STT options: {updates}")


async def _update_llm(session, agent_state, agent, config, vad):
    # LLM always requires agent switch
    new_config = replace(agent.kwami_config)
    new_voice = replace(new_config.voice)
    
    if config.get("provider"): new_voice.llm_provider = config["provider"]
    if config.get("model"): new_voice.llm_model = config["model"]
    if config.get("temperature"): new_voice.llm_temperature = config["temperature"]
    
    new_config.voice = new_voice
    new_agent = _create_agent_from_config(new_config, vad, agent._memory, skip_greeting=True)
    session.update_agent(new_agent)
    agent_state["current_agent"] = new_agent


def _update_persona(agent, config):
    persona = agent.kwami_config.persona
    if "name" in config: persona.name = config["name"]
    if "personality" in config: persona.personality = config["personality"]
    if "system_prompt" in config: persona.system_prompt = config["system_prompt"]
    
    # Rebuild instructions
    # Note: KwamiAgent needs to expose a way to update instructions or we set it directly if accessible
    # Agent.instructions is a property or attribute? access directly.
    # We need to trigger the rebuild method on KwamiAgent.
    # Since we kept `_build_system_prompt` on KwamiAgent, we can just call it (if made public or accessed via private).
    agent.instructions = agent._build_system_prompt()
    agent.kwami_config.persona = persona  # Ensure config is updated


if __name__ == "__main__":
    cli.run_app(server)
