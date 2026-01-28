"""Room and participant utilities for Kwami agent."""

import asyncio
from typing import TYPE_CHECKING, List, Optional

from .logging import get_logger

if TYPE_CHECKING:
    from livekit.rtc import Participant, Room

logger = get_logger("room")


async def get_other_agents(room: "Room") -> List["Participant"]:
    """Get list of other agent participants in the room.
    
    Args:
        room: The LiveKit room instance.
        
    Returns:
        List of participants that are agents.
    """
    from livekit.rtc import ParticipantKind
    
    return [
        p for p in room.remote_participants.values()
        if p.kind == ParticipantKind.AGENT
    ]


async def should_disconnect_as_duplicate(
    room: "Room",
    my_identity: str,
    check_delays: Optional[List[float]] = None,
) -> bool:
    """Check if this agent should disconnect due to another agent having priority.
    
    Note: This check is intentionally lenient. LiveKit Cloud manages agent dispatch,
    so duplicate agents are rare. We only disconnect if we clearly see another
    active agent that has priority.
    
    Args:
        room: The LiveKit room instance.
        my_identity: This agent's identity string.
        check_delays: List of delays (seconds) between checks. Defaults to [0.1].
        
    Returns:
        True if this agent should disconnect, False if it should stay.
    """
    # Single quick check - don't be too aggressive as it can prevent agents from starting
    if check_delays is None:
        check_delays = [0.1]
    
    for delay in check_delays:
        await asyncio.sleep(delay)
        
        other_agents = await get_other_agents(room)
        
        if other_agents:
            # Filter out agents that might be disconnecting (check if connected)
            active_agents = [a for a in other_agents if a.is_connected]
            
            if not active_agents:
                logger.debug("Found agents but none are actively connected, proceeding")
                return False
            
            # The agent with the "smaller" identity stays
            oldest_agent = min(active_agents, key=lambda p: p.identity)
            
            if my_identity > oldest_agent.identity:
                logger.warning(
                    f"Another active agent ({oldest_agent.identity}) has priority. "
                    f"This agent ({my_identity}) should disconnect."
                )
                return True
            else:
                logger.info(
                    f"This agent ({my_identity}) has priority over {oldest_agent.identity}"
                )
                return False
    
    return False


async def check_duplicate_before_action(
    room: Optional["Room"],
    my_identity: Optional[str],
) -> bool:
    """Quick check for duplicate agents before performing an action.
    
    Args:
        room: The LiveKit room instance.
        my_identity: This agent's identity string.
        
    Returns:
        True if this agent should abort the action, False if it's safe to proceed.
    """
    if not room:
        return False
    
    other_agents = await get_other_agents(room)
    
    if not other_agents:
        return False
    
    if not my_identity:
        my_identity = room.local_participant.identity if room.local_participant else ""
    
    oldest = min(other_agents, key=lambda p: p.identity)
    
    if my_identity > oldest.identity:
        logger.warning(f"Aborting action - another agent ({oldest.identity}) has priority")
        return True
    
    return False
