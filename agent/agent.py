"""
Kwami Agent - LiveKit Cloud Agent

Entry point for the Kwami AI agent deployed to LiveKit Cloud.
Run locally with: uv run python agent.py dev
Deploy with: lk agent deploy
"""

import logging
from pathlib import Path
from typing import Any, Optional

from dotenv import load_dotenv

# Load .env from the kwami-ai-lk root directory
load_dotenv(Path(__file__).parent.parent / ".env")

from livekit.agents import Agent, AgentServer, AgentSession, JobContext, JobProcess, RunContext, cli, room_io
from livekit.agents.llm import function_tool
from livekit.plugins import silero

from config import KwamiConfig
from plugins import create_llm, create_stt, create_tts

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("kwami-agent")

server = AgentServer()


def prewarm(proc: JobProcess):
    """Prewarm the VAD model for faster startup."""
    proc.userdata["vad"] = silero.VAD.load()


server.setup_fnc = prewarm


class KwamiAgent(Agent):
    """Dynamic AI agent configured by the Kwami frontend library."""

    def __init__(self, config: Optional[KwamiConfig] = None):
        self.kwami_config = config or KwamiConfig()

        instructions = self._build_system_prompt()
        super().__init__(instructions=instructions)

    def _build_system_prompt(self) -> str:
        """Build the system prompt from persona configuration."""
        persona = self.kwami_config.persona

        prompt_parts = []

        if persona.system_prompt:
            prompt_parts.append(persona.system_prompt)
        else:
            prompt_parts.append(f"You are {persona.name}, {persona.personality}.")

        if persona.traits:
            prompt_parts.append(f"\nKey traits: {', '.join(persona.traits)}")

        if persona.conversation_style:
            prompt_parts.append(f"\nConversation style: {persona.conversation_style}")

        length_guide = {
            "short": "Keep responses brief and concise (1-2 sentences).",
            "medium": "Provide balanced responses with enough detail (2-4 sentences).",
            "long": "Give comprehensive, detailed responses when appropriate.",
        }
        if persona.response_length in length_guide:
            prompt_parts.append(f"\n{length_guide[persona.response_length]}")

        tone_guide = {
            "neutral": "Maintain a balanced, objective tone.",
            "warm": "Express warmth and friendliness in your interactions.",
            "enthusiastic": "Show enthusiasm and energy in your responses.",
            "calm": "Maintain a calm, soothing demeanor.",
        }
        if persona.emotional_tone in tone_guide:
            prompt_parts.append(f"\n{tone_guide[persona.emotional_tone]}")

        # Add guidance for voice interactions
        prompt_parts.append("\n\nYou are interacting via voice. Keep responses concise and conversational.")
        prompt_parts.append("Do not use emojis, asterisks, markdown, or other special characters.")

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


@server.rtc_session(agent_name="kwami-agent")
async def entrypoint(ctx: JobContext):
    """Main entry point for Kwami agent sessions."""
    logger.info(f"🚀 Kwami session starting in room: {ctx.room.name}")

    config = KwamiConfig()
    agent = KwamiAgent(config)

    # Get prewarmed VAD from process userdata
    vad = ctx.proc.userdata["vad"]

    session = AgentSession(
        stt=create_stt(config.voice),
        llm=create_llm(config.voice),
        tts=create_tts(config.voice),
        vad=vad,
    )

    await session.start(
        agent=agent,
        room=ctx.room,
        room_options=room_io.RoomOptions(
            audio_input=True,
            audio_output=True,
        ),
    )

    logger.info(f"✅ Kwami session started for room: {ctx.room.name}")


if __name__ == "__main__":
    cli.run_app(server)
