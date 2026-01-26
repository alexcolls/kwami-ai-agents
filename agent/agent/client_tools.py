import asyncio
import json
import logging
import uuid
from typing import Any, Callable, Dict, List, Optional
from livekit.agents import function_tool, RunContext

logger = logging.getLogger("kwami-agent")


class ClientToolManager:
    """Manages dynamic tools that are executed on the client side."""

    def __init__(self, kwami_agent):
        """
        Args:
            kwami_agent: The KwamiAgent instance (needed to access the room for sending data)
        """
        self.agent = kwami_agent
        self.pending_calls: Dict[str, asyncio.Future] = {}
        self.registered_tools: List[Dict[str, Any]] = []
        self._tools: List[Any] = []

    def register_client_tools(self, tool_definitions: List[Dict[str, Any]]) -> None:
        """Register tools defined in configuration for the LLM."""
        if not tool_definitions:
            return

        for tool_def in tool_definitions:
            # Handle different formats
            func_def = tool_def.get("function", tool_def)
            tool_name = func_def.get("name")
            description = func_def.get("description", "")
            parameters = func_def.get("parameters", {})

            if not tool_name:
                continue

            logger.info(f"🛠️ Registering client tool: {tool_name}")

            # Create the tool using function_tool with raw_schema
            tool = self._create_client_tool(tool_name, description, parameters)
            self._tools.append(tool)
            self.registered_tools.append(tool_def)

    def _create_client_tool(self, tool_name: str, description: str, parameters: dict):
        """Create a function tool that forwards calls to the client."""
        # Build the raw schema for the tool
        raw_schema = {
            "type": "function",
            "name": tool_name,
            "description": description,
            "parameters": parameters if parameters else {
                "type": "object",
                "properties": {},
                "required": [],
            },
        }

        # Create the handler function that will be called when the tool is invoked
        async def tool_handler(raw_arguments: dict, context: RunContext):
            tool_call_id = str(uuid.uuid4())
            logger.info(
                f"📞 Calling client tool '{tool_name}' (id: {tool_call_id}) args: {raw_arguments}"
            )

            # Check room connection
            if not hasattr(self.agent, "room") or not self.agent.room:
                logger.error("Cannot call client tool: No room connection")
                return "Error: Agent not connected to room"

            result_future: asyncio.Future = asyncio.Future()
            self.pending_calls[tool_call_id] = result_future

            payload = {
                "type": "tool_call",
                "toolCallId": tool_call_id,
                "function": {
                    "name": tool_name,
                    "arguments": json.dumps(raw_arguments),
                },
            }

            try:
                data = json.dumps(payload).encode("utf-8")
                await self.agent.room.local_participant.publish_data(data, reliable=True)

                try:
                    result = await asyncio.wait_for(result_future, timeout=30.0)
                    return result
                except asyncio.TimeoutError:
                    return "Error: Tool execution timed out"

            except Exception as e:
                return f"Error executing tool: {str(e)}"
            finally:
                self.pending_calls.pop(tool_call_id, None)

        # Create the function tool using the raw_schema approach
        return function_tool(tool_handler, raw_schema=raw_schema)

    def handle_tool_result(
        self, tool_call_id: str, result: str, error: Optional[str] = None
    ) -> None:
        """Handle incoming tool result from client."""
        if tool_call_id in self.pending_calls:
            future = self.pending_calls[tool_call_id]
            if not future.done():
                if error:
                    future.set_result(f"Error from client: {error}")
                else:
                    future.set_result(result)

    def create_client_tools(self) -> List[Any]:
        """Return the list of registered client tools."""
        return self._tools
