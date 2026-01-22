"""
Kwami Agent - LiveKit Cloud Agent

Entry point for the Kwami AI agent deployed to LiveKit Cloud.
Run locally with: uv run python agent.py dev
Deploy with: lk agent deploy

Supports:
- Standard pipeline: STT → LLM → TTS
- Realtime pipeline: OpenAI Realtime / Google Gemini Live
- Mid-conversation voice/LLM switching via data channel or function tools
"""

import asyncio
import json
import logging
from pathlib import Path
from typing import Any, Optional

from dotenv import load_dotenv

# Load .env from the kwami-ai-lk root directory
load_dotenv(Path(__file__).parent.parent / ".env")

from livekit import rtc
from livekit.agents import (
    Agent,
    AgentServer,
    AgentSession,
    JobContext,
    JobProcess,
    RunContext,
    cli,
    room_io,
)
from livekit.agents.llm import function_tool
from livekit.plugins import silero, cartesia, deepgram, openai, google, elevenlabs

from config import KwamiConfig, KwamiVoiceConfig
from plugins import create_llm, create_stt, create_tts, create_realtime_model

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("kwami-agent")

server = AgentServer()


def prewarm(proc: JobProcess):
    """Prewarm the VAD model for faster startup."""
    proc.userdata["vad"] = silero.VAD.load()


server.setup_fnc = prewarm


class KwamiAgent(Agent):
    """Dynamic AI agent configured by the Kwami frontend library.
    
    This agent adapts its behavior based on configuration received from
    the Kwami frontend, including:
    - Persona (name, personality, traits, conversation style)
    - Voice pipeline (STT, LLM, TTS providers and models)
    - Tools (function calling capabilities)
    - Mid-conversation voice/LLM switching
    """

    def __init__(self, config: Optional[KwamiConfig] = None, vad=None):
        self.kwami_config = config or KwamiConfig()
        self._vad = vad  # Store VAD for agent switching
        
        # Track current voice config for switching
        self._current_voice_config = self.kwami_config.voice

        instructions = self._build_system_prompt()
        super().__init__(instructions=instructions)

    def _build_system_prompt(self) -> str:
        """Build the system prompt from persona configuration."""
        persona = self.kwami_config.persona

        prompt_parts = []

        # Base personality
        if persona.system_prompt:
            prompt_parts.append(persona.system_prompt)
        else:
            prompt_parts.append(f"You are {persona.name}, {persona.personality}.")

        # Traits
        if persona.traits:
            prompt_parts.append(f"\nKey traits: {', '.join(persona.traits)}")

        # Conversation style
        if persona.conversation_style:
            prompt_parts.append(f"\nConversation style: {persona.conversation_style}")

        # Response length guidance
        length_guide = {
            "short": "Keep responses brief and concise (1-2 sentences).",
            "medium": "Provide balanced responses with enough detail (2-4 sentences).",
            "long": "Give comprehensive, detailed responses when appropriate.",
        }
        if persona.response_length in length_guide:
            prompt_parts.append(f"\n{length_guide[persona.response_length]}")

        # Emotional tone guidance
        tone_guide = {
            "neutral": "Maintain a balanced, objective tone.",
            "warm": "Express warmth and friendliness in your interactions.",
            "enthusiastic": "Show enthusiasm and energy in your responses.",
            "calm": "Maintain a calm, soothing demeanor.",
        }
        if persona.emotional_tone in tone_guide:
            prompt_parts.append(f"\n{tone_guide[persona.emotional_tone]}")

        # Voice interaction guidance
        prompt_parts.append("\n\nYou are interacting via voice. Keep responses concise and conversational.")
        prompt_parts.append("Do not use emojis, asterisks, markdown, or other special characters.")
        prompt_parts.append("Speak naturally as if having a real conversation.")
        
        # Voice switching capability
        prompt_parts.append("\nYou can change your voice or the AI model being used if the user requests it.")

        return "\n".join(prompt_parts)

    async def on_enter(self) -> None:
        """Called when the agent joins the room."""
        logger.info(
            f"🤖 Kwami agent '{self.kwami_config.kwami_name}' "
            f"({self.kwami_config.kwami_id}) entered room"
        )

        # Greet the user when the agent joins
        # Use allow_interruptions=False so client has time to calibrate AEC
        self.session.generate_reply(
            instructions="Greet the user warmly and introduce yourself briefly.",
            allow_interruptions=False
        )

    async def on_user_turn_completed(self, turn_ctx: Any, new_message: Any) -> None:
        """Called when user finishes speaking."""
        # This can be used to track conversation state
        pass

    # =========================================================================
    # Voice/LLM Configuration Update Methods
    # =========================================================================
    
    async def update_voice_config(self, voice_config: dict) -> None:
        """Update voice pipeline configuration mid-conversation.
        
        This method is called when the frontend sends a config_update message
        or when a function tool requests a voice change.
        """
        try:
            # Update TTS if voice/provider changed
            if self.session.tts is not None:
                tts_updates = {}
                if "tts_voice" in voice_config:
                    tts_updates["voice"] = voice_config["tts_voice"]
                if "tts_speed" in voice_config:
                    tts_updates["speed"] = voice_config["tts_speed"]
                if "tts_model" in voice_config:
                    tts_updates["model"] = voice_config["tts_model"]
                
                if tts_updates:
                    self.session.tts.update_options(**tts_updates)
                    logger.info(f"🔊 Updated TTS options: {tts_updates}")
            
            # Update STT if language/model changed
            if self.session.stt is not None:
                stt_updates = {}
                if "stt_language" in voice_config:
                    stt_updates["language"] = voice_config["stt_language"]
                if "stt_model" in voice_config:
                    stt_updates["model"] = voice_config["stt_model"]
                
                if stt_updates:
                    self.session.stt.update_options(**stt_updates)
                    logger.info(f"🎤 Updated STT options: {stt_updates}")
            
            # For LLM provider changes, we need to create a new agent
            # because LLM instances can't be updated mid-session
            if "llm_provider" in voice_config or "llm_model" in voice_config:
                logger.info(f"🧠 LLM change requested - will apply on next interaction")
                # Store for potential agent switch
                self._current_voice_config.llm_provider = voice_config.get(
                    "llm_provider", self._current_voice_config.llm_provider
                )
                self._current_voice_config.llm_model = voice_config.get(
                    "llm_model", self._current_voice_config.llm_model
                )
                self._current_voice_config.llm_temperature = voice_config.get(
                    "llm_temperature", self._current_voice_config.llm_temperature
                )
                
        except Exception as e:
            logger.error(f"Failed to update voice config: {e}")

    # =========================================================================
    # Function Tools for Voice/LLM Switching
    # =========================================================================

    @function_tool
    async def get_kwami_info(self, context: RunContext) -> dict[str, Any]:
        """Get information about this Kwami instance."""
        return {
            "kwami_id": self.kwami_config.kwami_id,
            "kwami_name": self.kwami_config.kwami_name,
            "persona": {
                "name": self.kwami_config.persona.name,
                "personality": self.kwami_config.persona.personality,
            },
        }

    @function_tool
    async def get_current_time(self, context: RunContext) -> str:
        """Get the current time. Useful when the user asks what time it is."""
        from datetime import datetime
        return datetime.now().strftime("%I:%M %p on %A, %B %d, %Y")
    
    @function_tool
    async def change_voice(self, context: RunContext, voice_name: str) -> str:
        """Change the TTS voice. Available voices depend on the current TTS provider.
        
        Args:
            voice_name: The name or ID of the voice to switch to.
                       For Cartesia: Use voice names like 'British Lady', 'California Girl', etc.
                       For ElevenLabs: Use voice names like 'Rachel', 'Josh', 'Bella', etc.
                       For OpenAI: Use 'alloy', 'echo', 'nova', 'shimmer', 'onyx', 'fable'.
        """
        try:
            if self.session.tts is not None:
                # Map common voice names to IDs for Cartesia
                cartesia_voice_map = {
                    "british lady": "79a125e8-cd45-4c13-8a67-188112f4dd22",
                    "sophia": "79a125e8-cd45-4c13-8a67-188112f4dd22",
                    "california girl": "c2ac25f9-ecc4-4f56-9095-651354df60c0",
                    "reading lady": "b7d50908-b17c-442d-ad8d-810c63997ed9",
                    "newsman": "a167e0f3-df7e-4d52-a9c3-f949145efdab",
                    "blake": "a167e0f3-df7e-4d52-a9c3-f949145efdab",
                    "commercial man": "63ff761f-c1e8-414b-b969-d1833d1c870c",
                    "friendly sidekick": "421b3369-f63f-4b03-8980-37a44df1d4e8",
                }
                
                # Check if it's a known name and convert to ID
                voice_id = cartesia_voice_map.get(voice_name.lower(), voice_name)
                
                self.session.tts.update_options(voice=voice_id)
                logger.info(f"🔊 Voice changed to: {voice_name}")
                return f"Voice changed to {voice_name}. I'm now speaking with a different voice!"
            return "Unable to change voice - TTS not available"
        except Exception as e:
            logger.error(f"Failed to change voice: {e}")
            return f"Sorry, I couldn't change the voice: {str(e)}"

    @function_tool
    async def change_speaking_speed(self, context: RunContext, speed: float) -> str:
        """Change the speaking speed. 
        
        Args:
            speed: Speed multiplier between 0.5 (slow) and 2.0 (fast). 
                   1.0 is normal speed.
        """
        try:
            speed = max(0.5, min(2.0, speed))  # Clamp to valid range
            if self.session.tts is not None:
                self.session.tts.update_options(speed=speed)
                logger.info(f"🔊 Speaking speed changed to: {speed}")
                
                if speed < 0.8:
                    return f"Speed set to {speed}. I'll speak more slowly now."
                elif speed > 1.2:
                    return f"Speed set to {speed}. I'll speak faster now."
                else:
                    return f"Speed set to {speed}. Speaking at normal pace."
            return "Unable to change speed - TTS not available"
        except Exception as e:
            logger.error(f"Failed to change speed: {e}")
            return f"Sorry, I couldn't change the speed: {str(e)}"

    @function_tool
    async def change_language(self, context: RunContext, language: str) -> str:
        """Change the conversation language for both speech recognition and synthesis.
        
        Args:
            language: Language code like 'en' (English), 'es' (Spanish), 'fr' (French),
                     'de' (German), 'it' (Italian), 'pt' (Portuguese), 'ja' (Japanese),
                     'ko' (Korean), 'zh' (Chinese).
        """
        try:
            language = language.lower().strip()
            
            # Update STT language
            if self.session.stt is not None:
                self.session.stt.update_options(language=language)
                logger.info(f"🎤 STT language changed to: {language}")
            
            # Update TTS language if supported
            if self.session.tts is not None:
                try:
                    self.session.tts.update_options(language=language)
                    logger.info(f"🔊 TTS language changed to: {language}")
                except Exception:
                    pass  # Not all TTS providers support language parameter
            
            greetings = {
                "en": "Language changed to English. How can I help you?",
                "es": "Idioma cambiado a español. ¿Cómo puedo ayudarte?",
                "fr": "Langue changée en français. Comment puis-je vous aider?",
                "de": "Sprache auf Deutsch geändert. Wie kann ich Ihnen helfen?",
                "it": "Lingua cambiata in italiano. Come posso aiutarti?",
                "pt": "Idioma alterado para português. Como posso ajudá-lo?",
                "ja": "言語が日本語に変更されました。何かお手伝いできますか?",
                "ko": "언어가 한국어로 변경되었습니다. 무엇을 도와드릴까요?",
                "zh": "语言已更改为中文。我能帮你什么?",
            }
            
            return greetings.get(language, f"Language changed to {language}.")
        except Exception as e:
            logger.error(f"Failed to change language: {e}")
            return f"Sorry, I couldn't change the language: {str(e)}"
    
    @function_tool
    async def get_current_voice_settings(self, context: RunContext) -> dict[str, Any]:
        """Get the current voice pipeline settings."""
        return {
            "tts_provider": self._current_voice_config.tts_provider,
            "tts_model": self._current_voice_config.tts_model,
            "tts_voice": self._current_voice_config.tts_voice,
            "tts_speed": self._current_voice_config.tts_speed,
            "stt_provider": self._current_voice_config.stt_provider,
            "stt_model": self._current_voice_config.stt_model,
            "stt_language": self._current_voice_config.stt_language,
            "llm_provider": self._current_voice_config.llm_provider,
            "llm_model": self._current_voice_config.llm_model,
            "llm_temperature": self._current_voice_config.llm_temperature,
        }


@server.rtc_session(agent_name="kwami-agent")
async def entrypoint(ctx: JobContext):
    """Main entry point for Kwami agent sessions.
    
    Creates either a standard (STT → LLM → TTS) or realtime pipeline
    based on configuration. Supports mid-conversation voice/LLM changes.
    """
    logger.info(f"🚀 Kwami session starting in room: {ctx.room.name}")

    config = KwamiConfig()
    
    # Get prewarmed VAD from process userdata
    vad = ctx.proc.userdata["vad"]
    
    agent = KwamiAgent(config, vad=vad)
    voice_config = config.voice

    # Create session based on pipeline type
    if voice_config.pipeline_type == "realtime":
        # Realtime pipeline - ultra-low latency
        logger.info(f"Using realtime pipeline: {voice_config.realtime_provider}/{voice_config.realtime_model}")
        
        realtime_model = create_realtime_model(voice_config)
        
        session = AgentSession(
            llm=realtime_model,
            # VAD is handled by the realtime model's turn detection
        )
    else:
        # Standard pipeline - STT → LLM → TTS
        logger.info(
            f"Using standard pipeline: "
            f"STT={voice_config.stt_provider}/{voice_config.stt_model}, "
            f"LLM={voice_config.llm_provider}/{voice_config.llm_model}, "
            f"TTS={voice_config.tts_provider}/{voice_config.tts_model}"
        )
        
        session = AgentSession(
            stt=create_stt(voice_config),
            llm=create_llm(voice_config),
            tts=create_tts(voice_config),
            vad=vad,
        )

    # Start the session
    await session.start(
        agent=agent,
        room=ctx.room,
        room_options=room_io.RoomOptions(
            audio_input=True,
            audio_output=True,
        ),
    )

    logger.info(f"✅ Kwami session started for room: {ctx.room.name}")
    
    # Set up data channel listener for config updates from frontend
    @ctx.room.on("data_received")
    def on_data_received(data: rtc.DataPacket):
        """Handle data messages from the frontend for config updates."""
        try:
            message = json.loads(data.data.decode("utf-8"))
            msg_type = message.get("type")
            
            if msg_type == "config_update":
                update_type = message.get("updateType")
                update_config = message.get("config", {})
                
                logger.info(f"📨 Received {update_type} config update: {update_config}")
                
                if update_type == "voice":
                    # Handle voice configuration updates
                    asyncio.create_task(handle_voice_update(session, agent, update_config))
                elif update_type == "llm":
                    # Handle LLM configuration updates
                    asyncio.create_task(handle_llm_update(session, agent, update_config, vad))
                elif update_type == "persona":
                    # Handle persona updates
                    asyncio.create_task(handle_persona_update(agent, update_config))
                    
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse data message: {e}")
        except Exception as e:
            logger.error(f"Error handling data message: {e}")


async def handle_voice_update(session: AgentSession, agent: KwamiAgent, config: dict):
    """Handle voice (TTS/STT) configuration updates mid-conversation."""
    try:
        # Update TTS options
        if session.tts is not None:
            tts_updates = {}
            if "voice" in config:
                tts_updates["voice"] = config["voice"]
            if "speed" in config:
                tts_updates["speed"] = config["speed"]
            if "model" in config:
                tts_updates["model"] = config["model"]
            
            if tts_updates:
                session.tts.update_options(**tts_updates)
                logger.info(f"🔊 Updated TTS: {tts_updates}")
        
        # Update STT options
        if session.stt is not None:
            stt_updates = {}
            if "language" in config:
                stt_updates["language"] = config["language"]
            
            if stt_updates:
                session.stt.update_options(**stt_updates)
                logger.info(f"🎤 Updated STT: {stt_updates}")
                
        # Confirm the change to the user
        if "voice" in config:
            await session.say("Voice updated!")
                
    except Exception as e:
        logger.error(f"Failed to update voice config: {e}")


async def handle_llm_update(session: AgentSession, agent: KwamiAgent, config: dict, vad):
    """Handle LLM configuration updates mid-conversation.
    
    For LLM provider changes, we need to switch to a new agent instance
    because LLM instances are created at session start.
    """
    try:
        provider = config.get("provider", agent._current_voice_config.llm_provider)
        model = config.get("model", agent._current_voice_config.llm_model)
        temperature = config.get("temperature", agent._current_voice_config.llm_temperature)
        
        logger.info(f"🧠 Switching LLM to {provider}/{model} (temp={temperature})")
        
        # Update the agent's stored config
        agent._current_voice_config.llm_provider = provider
        agent._current_voice_config.llm_model = model
        agent._current_voice_config.llm_temperature = temperature
        
        # Create new LLM instance
        new_llm = create_llm(agent._current_voice_config)
        
        # Create a new agent with updated LLM
        new_config = agent.kwami_config
        new_config.voice = agent._current_voice_config
        new_agent = KwamiAgent(new_config, vad=vad)
        
        # Transfer to new agent (preserves conversation context)
        session.update_agent(new_agent)
        
        logger.info(f"✅ LLM switched to {provider}/{model}")
        await session.say(f"Now using {model}.")
        
    except Exception as e:
        logger.error(f"Failed to update LLM config: {e}")


async def handle_persona_update(agent: KwamiAgent, config: dict):
    """Handle persona configuration updates."""
    try:
        persona = agent.kwami_config.persona
        
        if "name" in config:
            persona.name = config["name"]
        if "personality" in config:
            persona.personality = config["personality"]
        if "system_prompt" in config:
            persona.system_prompt = config["system_prompt"]
        if "traits" in config:
            persona.traits = config["traits"]
            
        # Rebuild instructions
        agent.instructions = agent._build_system_prompt()
        logger.info(f"👤 Persona updated: {persona.name}")
        
    except Exception as e:
        logger.error(f"Failed to update persona: {e}")


if __name__ == "__main__":
    cli.run_app(server)
