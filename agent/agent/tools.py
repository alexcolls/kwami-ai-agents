import logging
from typing import Any, Dict
from livekit.agents import RunContext, function_tool

logger = logging.getLogger("kwami-agent")


class AgentToolsMixin:
    """Mixin containing function tools for KwamiAgent."""

    @function_tool()
    async def get_kwami_info(self, context: RunContext) -> Dict[str, Any]:
        """Get information about this Kwami instance."""
        return {
            "kwami_id": self.kwami_config.kwami_id,
            "kwami_name": self.kwami_config.kwami_name,
            "persona": {
                "name": self.kwami_config.persona.name,
                "personality": self.kwami_config.persona.personality,
            },
        }

    @function_tool()
    async def get_current_time(self, context: RunContext) -> str:
        """Get the current time. Useful when the user asks what time it is."""
        from datetime import datetime
        return datetime.now().strftime("%I:%M %p on %A, %B %d, %Y")
    
    @function_tool()
    async def change_voice(self, context: RunContext, voice_name: str) -> str:
        """Change the TTS voice. Available voices depend on the current TTS provider.
        
        Args:
            voice_name: The name or ID of the voice to switch to.
                       For Cartesia: Use voice names like 'British Lady', 'California Girl', etc.
                       For ElevenLabs: Use voice names like 'Rachel', 'Josh', 'Bella', etc.
                       For OpenAI: Use 'alloy', 'echo', 'nova', 'shimmer', 'onyx', 'fable'.
        """
        try:
            # We assume self.session is available on the main class
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
                
                # Different TTS providers use different parameter names
                tts_provider = getattr(self.session.tts, "provider", "").lower()
                if tts_provider == "elevenlabs" or "elevenlabs" in type(self.session.tts).__module__:
                    self.session.tts.update_options(voice_id=voice_id)
                else:
                    self.session.tts.update_options(voice=voice_id)
                    
                logger.info(f"🔊 Voice changed to: {voice_name}")
                return f"Voice changed to {voice_name}. I'm now speaking with a different voice!"
            return "Unable to change voice - TTS not available"
        except Exception as e:
            logger.error(f"Failed to change voice: {e}")
            return f"Sorry, I couldn't change the voice: {str(e)}"

    @function_tool()
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

    @function_tool()
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
    
    @function_tool()
    async def get_current_voice_settings(self, context: RunContext) -> Dict[str, Any]:
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

    @function_tool()
    async def remember_fact(self, context: RunContext, fact: str) -> str:
        """Remember an important fact about the user for future conversations."""
        if not self._memory or not self._memory.is_initialized:
            return "Memory is not available in this session."
        
        try:
            await self._memory.add_fact(fact)
            logger.info(f"🧠 Remembered fact: {fact}")
            return f"I'll remember that: {fact}"
        except Exception as e:
            logger.error(f"Failed to remember fact: {e}")
            return "Sorry, I couldn't save that to memory."

    @function_tool()
    async def recall_memories(self, context: RunContext, topic: str) -> str:
        """Search your memory for information about a specific topic."""
        if not self._memory or not self._memory.is_initialized:
            return "Memory is not available in this session."
        
        try:
            results = await self._memory.search(topic, limit=5)
            
            if not results:
                return f"I don't have any memories about '{topic}' yet."
            
            memories = []
            for r in results:
                if r.get("content"):
                    memories.append(f"- {r['content']}")
            
            if memories:
                return f"Here's what I remember about '{topic}':\n" + "\n".join(memories)
            return f"I don't have specific memories about '{topic}'."
            
        except Exception as e:
            logger.error(f"Failed to recall memories: {e}")
            return "Sorry, I couldn't search my memory right now."

    @function_tool()
    async def get_memory_status(self, context: RunContext) -> Dict[str, Any]:
        """Get the current memory status and statistics."""
        if not self._memory:
            return {
                "enabled": False,
                "status": "Memory not configured",
            }
        
        if not self._memory.is_initialized:
            return {
                "enabled": True,
                "status": "Memory not initialized",
            }
        
        try:
            memory_context = await self._memory.get_context()
            return {
                "enabled": True,
                "status": "Active",
                "user_id": self._memory.user_id,
                "session_id": self._memory.session_id,
                "facts_count": len(memory_context.facts),
                "recent_messages_count": len(memory_context.recent_messages),
                "has_summary": memory_context.summary is not None,
            }
        except Exception as e:
            return {
                "enabled": True,
                "status": f"Error: {str(e)}",
            }
