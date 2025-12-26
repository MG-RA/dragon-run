"""WebSocket client for game server communication."""

import asyncio
import json
import logging
import uuid
from typing import Any, Callable, Dict, Optional, Tuple

import websockets
from websockets.client import WebSocketClientProtocol

logger = logging.getLogger(__name__)

# Available tools list for retry prompts
AVAILABLE_TOOLS = """
AVAILABLE TOOLS (use these exact names):
• broadcast - Send message to all players
• whisper - Private message to one player
• spawn - Spawn mobs near a player
• give - Give items to a player
• effect - Apply potion effect
• lightning - Strike lightning near player
• weather - Change weather (clear/rain/thunder)
• firework - Launch fireworks
• teleport - Teleport player (random/swap/isolate)
• sound - Play a sound
• title - Show title/subtitle on screen
• damage - Deal non-lethal damage
• heal - Heal a player
• aura - Modify player's aura
• tnt - Spawn TNT near player
• falling - Drop falling blocks
• lookat - Force player to look at position/entity
• particles - Spawn particle effects
• fakedeath - Fake death message
• protect - Divine protection (heals + resistance)
• rescue - Emergency teleport away from danger
• respawn - Override a death (rare)
"""


class GameStateClient:
    """WebSocket client for receiving game state and sending commands."""

    def __init__(
        self, uri: str, on_state_update: Callable, on_event: Callable
    ):
        self.uri = uri
        self.websocket: Optional[WebSocketClientProtocol] = None
        self.on_state_update = on_state_update
        self.on_event = on_event
        self.running = False
        # Track pending commands for result correlation
        self._pending_commands: Dict[str, asyncio.Future] = {}
        self._command_counter = 0
        # Track failed commands for retry logic
        self._failed_commands: list[Tuple[str, Dict[str, Any], str]] = []

    async def connect(self):
        """Connect to WebSocket server and listen for messages."""
        self.running = True

        while self.running:
            try:
                logger.info(f"Connecting to {self.uri}...")
                # Disable ping to avoid keepalive timeout with Java-WebSocket server
                # The connection is local and we handle reconnection anyway
                async with websockets.connect(
                    self.uri,
                    ping_interval=None,
                    ping_timeout=None,
                ) as websocket:
                    self.websocket = websocket
                    logger.info("✅ Connected to game server")

                    async for message in websocket:
                        try:
                            data = json.loads(message)
                            await self._handle_message(data)
                        except json.JSONDecodeError as e:
                            logger.error(f"Failed to parse message: {e}")
                        except Exception as e:
                            logger.error(f"Error handling message: {e}", exc_info=True)

            except websockets.ConnectionClosed:
                logger.warning("⚠️  Connection closed, reconnecting in 5 seconds...")
                await asyncio.sleep(5)
            except Exception as e:
                logger.error(f"❌ Connection error: {e}")
                await asyncio.sleep(5)

    async def _handle_message(self, data: Dict[str, Any]):
        """Route incoming messages to appropriate handlers."""
        msg_type = data.get("type")

        if msg_type == "state":
            await self.on_state_update(data)
        elif msg_type == "event":
            await self.on_event(data)
        elif msg_type == "command_result":
            success = data.get("success", False)
            message = data.get("message", "")
            command_id = data.get("command_id")

            # Resolve pending command future if exists
            if command_id and command_id in self._pending_commands:
                future = self._pending_commands.pop(command_id)
                if not future.done():
                    future.set_result({"success": success, "message": message})

            if success:
                logger.debug(f"✅ Command success: {message}")
            else:
                logger.warning(f"⚠️  Command failed: {message}")
                # Track failed commands for potential retry
                if "Unknown command" in message:
                    # Extract the command name from the error
                    self._failed_commands.append((message, data.get("original_command", {}), message))
        else:
            logger.warning(f"Unknown message type: {msg_type}")

    async def send_command(
        self, command: str, parameters: Dict[str, Any], reason: str = ""
    ) -> bool:
        """Send a command to the game server (fire and forget)."""
        if not self.websocket or self.websocket.close_code is not None:
            logger.error("❌ Cannot send command - not connected")
            return False

        try:
            message = {
                "type": "command",
                "command": command,
                "parameters": parameters,
                "reason": reason,
            }

            await self.websocket.send(json.dumps(message))
            logger.debug(f"📤 Sent command: {command} | {parameters}")
            return True

        except Exception as e:
            logger.error(f"❌ Failed to send command: {e}")
            return False

    async def send_command_with_result(
        self, command: str, parameters: Dict[str, Any], reason: str = "", timeout: float = 5.0
    ) -> Dict[str, Any]:
        """
        Send a command and wait for the result.

        Returns dict with 'success' and 'message' keys.
        On timeout, returns {'success': False, 'message': 'Timeout'}.
        """
        if not self.websocket or self.websocket.close_code is not None:
            logger.error("❌ Cannot send command - not connected")
            return {"success": False, "message": "Not connected"}

        # Generate unique command ID
        self._command_counter += 1
        command_id = f"cmd_{self._command_counter}_{uuid.uuid4().hex[:8]}"

        try:
            # Create future for this command
            loop = asyncio.get_event_loop()
            future: asyncio.Future = loop.create_future()
            self._pending_commands[command_id] = future

            message = {
                "type": "command",
                "command": command,
                "command_id": command_id,
                "parameters": parameters,
                "reason": reason,
            }

            await self.websocket.send(json.dumps(message))
            logger.debug(f"📤 Sent command (awaiting): {command} | {parameters}")

            # Wait for result with timeout
            try:
                result = await asyncio.wait_for(future, timeout=timeout)
                return result
            except asyncio.TimeoutError:
                # Clean up pending command
                self._pending_commands.pop(command_id, None)
                logger.warning(f"⏰ Command timeout: {command}")
                return {"success": False, "message": "Timeout waiting for command result"}

        except Exception as e:
            self._pending_commands.pop(command_id, None)
            logger.error(f"❌ Failed to send command: {e}")
            return {"success": False, "message": str(e)}

    def get_available_tools_prompt(self) -> str:
        """Get the available tools prompt for LLM retry."""
        return AVAILABLE_TOOLS

    def get_failed_commands(self) -> list[Tuple[str, Dict[str, Any], str]]:
        """Get list of failed commands since last check and clear the list."""
        failed = self._failed_commands.copy()
        self._failed_commands.clear()
        return failed

    def stop(self):
        """Stop the client."""
        self.running = False
        logger.info("Stopping WebSocket client...")
