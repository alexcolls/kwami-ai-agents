"""Pytest configuration for Kwami agent tests."""

import sys
from pathlib import Path
from unittest.mock import MagicMock

# Mock livekit modules BEFORE any imports to avoid dependency issues
# This must happen before adding the agent dir to path
mock_modules = [
    "livekit",
    "livekit.agents",
    "livekit.agents.inference",
    "livekit.plugins",
    "livekit.plugins.openai",
    "livekit.plugins.deepgram",
    "livekit.plugins.cartesia",
    "livekit.plugins.elevenlabs",
    "livekit.plugins.google",
    "livekit.plugins.silero",
    "livekit.plugins.anthropic",
    "zep_cloud",
    "zep_cloud.client",
    "zep_cloud.types",
]

for mod in mock_modules:
    if mod not in sys.modules:
        sys.modules[mod] = MagicMock()

# Create a mock Agent class that can be used as a base class
mock_agent = MagicMock()
mock_agent.__class_getitem__ = lambda cls, x: cls
sys.modules["livekit.agents"].Agent = type("Agent", (), {})

# Add the agent directory to the path so 'src' can be imported
agent_dir = Path(__file__).parent.parent
sys.path.insert(0, str(agent_dir))

