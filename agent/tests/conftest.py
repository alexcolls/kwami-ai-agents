"""Pytest configuration for Kwami agent tests."""

import sys
from pathlib import Path

# Add the agent directory to the path so 'src' can be imported
agent_dir = Path(__file__).parent.parent
sys.path.insert(0, str(agent_dir))
