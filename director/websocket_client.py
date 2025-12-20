import asyncio
import json
import websockets
from typing import Callable, Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)

class GameStateClient:
    """WebSocket client for receiving game state and sending commands."""

    def __init__(self, uri: str, on_state_update: Callable, on_event: Callable):
        self.uri = uri
        self.websocket: Optional[websockets.WebSocketClientProtocol] = None
        self.on_state_update = on_state_update
        self.on_event = on_event
        self.running = False

    async def connect(self):
        """Connect to WebSocket server and listen for messages."""
        self.running = True

        while self.running:
            try:
                logger.info(f"Connecting to {self.uri}...")
                async with websockets.connect(self.uri) as websocket:
                    self.websocket = websocket
                    logger.info("Connected to game server")

                    async for message in websocket:
                        try:
                            data = json.loads(message)
                            await self._handle_message(data)
                        except json.JSONDecodeError as e:
                            logger.error(f"Failed to parse message: {e}")
                        except Exception as e:
                            logger.error(f"Error handling message: {e}")

            except websockets.ConnectionClosed:
                logger.warning("Connection closed, reconnecting in 5 seconds...")
                await asyncio.sleep(5)
            except Exception as e:
                logger.error(f"Connection error: {e}")
                await asyncio.sleep(5)

    async def _handle_message(self, data: Dict[str, Any]):
        """Route incoming messages to appropriate handlers."""
        msg_type = data.get('type')

        if msg_type == 'state':
            await self.on_state_update(data)
        elif msg_type == 'event':
            await self.on_event(data)
        elif msg_type == 'command_result':
            logger.info(f"Command result: {data.get('success')} - {data.get('message')}")
        else:
            logger.warning(f"Unknown message type: {msg_type}")

    async def send_command(self, command: str, parameters: Dict[str, Any], reason: str = "") -> bool:
        """Send a command to the game server."""
        if not self.websocket or self.websocket.close_code is not None:
            logger.error("Cannot send command - not connected")
            return False

        try:
            message = {
                'type': 'command',
                'command': command,
                'parameters': parameters,
                'reason': reason
            }

            await self.websocket.send(json.dumps(message))
            logger.debug(f"Sent command: {command} with params: {parameters}")
            return True

        except Exception as e:
            logger.error(f"Failed to send command: {e}")
            return False

    def stop(self):
        """Stop the client."""
        self.running = False
