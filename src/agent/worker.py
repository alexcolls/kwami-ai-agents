"""
Kwami Agent Worker - LiveKit Agent Server

This is the entry point for running the Kwami agent as a worker process.
It connects to LiveKit and handles incoming session requests.
"""

import logging

from livekit.agents import AgentServer, AgentSession, JobContext, room_io

from kwami_lk.agent.config import KwamiConfig
from kwami_lk.agent.kwami_agent import KwamiAgent
from kwami_lk.agent.plugins import create_llm, create_stt, create_tts, create_vad

logger = logging.getLogger("kwami-agent")
logger.setLevel(logging.INFO)

# Create the agent server
server = AgentServer()


@server.rtc_session()
async def kwami_session(ctx: JobContext):
    """
    Main entry point for Kwami agent sessions.

    Each Kwami instance from the frontend creates a new session with
    its own configuration.
    """
    logger.info(f"🚀 Kwami session starting in room: {ctx.room.name}")

    # Default configuration - will be updated when frontend sends config
    config = KwamiConfig()

    # Create the agent
    agent = KwamiAgent(config)

    # Create the session with voice pipeline components
    session = AgentSession(
        stt=create_stt(config.voice),
        llm=create_llm(config.voice),
        tts=create_tts(config.voice),
        vad=create_vad(config.voice),
    )

    # Start the session
    await session.start(
        agent=agent,
        room=ctx.room,
        room_options=room_io.RoomOptions(
            audio_input=True,
            audio_output=True,
            noise_cancellation=(
                room_io.NoiseFilter.BVC if config.voice.noise_cancellation else None
            ),
        ),
    )

    logger.info(f"✅ Kwami session started for room: {ctx.room.name}")


def run():
    """Run the agent server."""
    server.run()


if __name__ == "__main__":
    run()
