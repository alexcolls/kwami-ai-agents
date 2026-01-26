import logging
from typing import Any, Optional

from livekit.agents import Agent

from .config import KwamiConfig
from .memory import KwamiMemory
from .tools import AgentToolsMixin
from .client_tools import ClientToolManager

logger = logging.getLogger("kwami-agent")


class KwamiAgent(Agent, AgentToolsMixin):
    """Dynamic AI agent configured by the Kwami frontend library."""

    def __init__(
        self,
        config: Optional[KwamiConfig] = None,
        vad=None,
        memory: Optional[KwamiMemory] = None,
        stt=None,
        llm=None,
        tts=None,
        skip_greeting: bool = False,
    ):
        self.kwami_config = config or KwamiConfig()
        self._vad = vad  # Store VAD for agent switching
        self._memory = memory  # Zep memory instance
        self._skip_greeting = skip_greeting  # Skip greeting if this is a reconfiguration
        
        # Track current voice config for switching
        self._current_voice_config = self.kwami_config.voice
        self.room = None # Will be set in on_enter

        # Initialize client tool manager
        self.client_tools = ClientToolManager(self)
        if self.kwami_config.tools:
            self.client_tools.register_client_tools(self.kwami_config.tools)
            
        # Combine built-in tools (mixin) with client tools
        # We need to ensure the parent Agent sees both if possible
        # Currently Agent init takes no fnc_ctx, it discovers tools from 'self'
        # To add dynamic tools, we might need to manually update fnc_ctx after init
        # or combine contexts.
        
        # Let's see if we can get the context from client_tools 
        # and merge it or register.
            
        instructions = self._build_system_prompt()
        
        # MERGE TOOLS:
        # 1. Get client tools
        combined_tools = self.client_tools.create_client_tools()
        
        # 2. Add 'self' (mixin) tools via 'tools' argument? 
        # Actually Agent() will scan 'self' for tools if we don't pass 'tools'?
        # Or if we pass 'tools', it ADDS them?
        # Looking at Agent definition: tools: 'list[llm.Tool | llm.Toolset] | None' = None
        # It likely accepts additional tools. The mixin tools on 'self' are registered via logic inside Agent.__init__ probably scanning self.
        
        self._tools = combined_tools

        super().__init__(
            instructions=instructions,
            stt=stt,
            llm=llm,
            tts=tts,
            vad=vad,
            tools=self._tools,
        )
        
        # Merge mixin tools if we supplied a context


    def _build_system_prompt(self, memory_context: Optional[str] = None) -> str:
        """Build the system prompt from persona configuration and memory context."""
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

        # Memory context injection
        if memory_context:
            prompt_parts.append("\n\n## Your Memory\n")
            prompt_parts.append("You have persistent memory of past conversations with this user.")
            prompt_parts.append("Use this context to provide personalized responses:\n")
            prompt_parts.append(memory_context)

        return "\n".join(prompt_parts)

    async def _inject_memory_context(self) -> None:
        """Fetch memory context and update system prompt."""
        if not self._memory or not self._memory.is_initialized:
            return

        try:
            context = await self._memory.get_context()
            memory_text = context.to_system_prompt_addition()
            
            if memory_text:
                # Rebuild instructions with memory context using the proper async method
                new_instructions = self._build_system_prompt(memory_text)
                await self.update_instructions(new_instructions)
                logger.info("🧠 Injected memory context into system prompt")
        except Exception as e:
            logger.error(f"Failed to inject memory context: {e}")

    async def on_enter(self, room: Any = None) -> None:
        """Called when the agent joins the room."""
        # Note: In some versions/contexts room might be passed or not. 
        # Making it optional (room: Any = None) handles both cases safely.


        if room:
            # Check for other agents to prevent double sessions
            # Wait briefly for participants to sync (race condition mitigation)
            import asyncio
            from livekit.rtc import ParticipantKind
            
            await asyncio.sleep(0.5)  # Wait for participant list to sync
            
            my_identity = room.local_participant.identity if room.local_participant else ""
            other_agents = [
                p for p in room.remote_participants.values()
                if p.kind == ParticipantKind.AGENT
            ]
            
            if other_agents:
                # If there are other agents, the one with the "smaller" identity stays
                # This ensures consistent behavior - same agent always wins
                oldest_agent = min(other_agents, key=lambda p: p.identity)
                
                if my_identity > oldest_agent.identity:
                    logger.warning(
                        f"🛑 Another agent ({oldest_agent.identity}) is already in the room. "
                        f"This agent ({my_identity}) will disconnect to prevent duplication."
                    )
                    await room.disconnect()
                    return
                else:
                    logger.info(
                        f"🟢 This agent ({my_identity}) has priority over {oldest_agent.identity}"
                    )
        
        # Store room reference for client tools
        self.room = room


        logger.info(
            f"🤖 Kwami agent '{self.kwami_config.kwami_name}' "
            f"({self.kwami_config.kwami_id}) entered room"
        )

        # Inject memory context into system prompt
        await self._inject_memory_context()

        # Greet the user - but only once per session
        # Skip if this is a reconfigured agent (not the first agent in the session)
        if self._skip_greeting:
            logger.debug("Skipping greeting (agent was reconfigured)")
            return
        
        if self._memory and self._memory.is_initialized:
            self.session.generate_reply(
                instructions=(
                    "Greet the user warmly. If you have memory context about them, "
                    "acknowledge the returning user briefly. If not, introduce yourself."
                ),
                allow_interruptions=False,
            )
        else:
            self.session.generate_reply(
                instructions="Greet the user warmly and introduce yourself briefly.",
                allow_interruptions=False,
            )

    async def on_user_turn_completed(self, turn_ctx: Any, new_message: Any) -> None:
        """Called when user finishes speaking."""
        if self._memory and self._memory.is_initialized and new_message:
            try:
                content = self._extract_message_content(new_message)
                if content:
                    await self._memory.add_message("user", content)
            except Exception as e:
                logger.warning(f"Failed to add user message to memory: {e}")

    async def on_agent_turn_completed(self, turn_ctx: Any, new_message: Any) -> None:
        """Called when agent finishes responding."""
        if self._memory and self._memory.is_initialized and new_message:
            try:
                content = self._extract_message_content(new_message)
                if content:
                    await self._memory.add_message("assistant", content)
            except Exception as e:
                logger.warning(f"Failed to add agent message to memory: {e}")

    def _extract_message_content(self, message: Any) -> str:
        """Extract text content from various message formats."""
        if message is None:
            return ""
        
        # Try common content attributes
        for attr in ("content", "text", "message"):
            if hasattr(message, attr):
                value = getattr(message, attr)
                if value is not None and isinstance(value, str) and value.strip():
                    return value.strip()
        
        # If message is already a string
        if isinstance(message, str):
            return message.strip()
        
        # Last resort: stringify but filter out object representations
        text = str(message)
        if text.startswith("<") and text.endswith(">"):
            logger.debug(f"Could not extract content from message type: {type(message)}")
            return ""
        
        return text.strip()
