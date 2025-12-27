"""WebSocket client for game server communication with reliability improvements."""

import asyncio
import json
import logging
import random
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional, Tuple

import websockets
from websockets.client import WebSocketClientProtocol

from ..config import WebSocketConfig

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


@dataclass
class PendingCommand:
    """Tracks a pending command awaiting result."""
    future: asyncio.Future
    command_data: Dict[str, Any]
    created_at: float = field(default_factory=time.time)


class ReconnectBackoff:
    """Exponential backoff with jitter for reconnection."""

    def __init__(
        self,
        base_delay: float = 1.0,
        max_delay: float = 30.0,
        jitter: float = 0.1
    ):
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.jitter = jitter
        self._attempt = 0

    def next_delay(self) -> float:
        """Get next delay and increment attempt counter."""
        delay = min(self.base_delay * (2 ** self._attempt), self.max_delay)
        # Add jitter: +/- jitter%
        jitter_range = delay * self.jitter
        delay += random.uniform(-jitter_range, jitter_range)
        self._attempt += 1
        return max(0.5, delay)  # Minimum 0.5s

    def reset(self):
        """Reset on successful connection."""
        self._attempt = 0

    @property
    def attempt(self) -> int:
        """Current attempt number."""
        return self._attempt


class GameStateClient:
    """WebSocket client for receiving game state and sending commands.

    Features:
    - Heartbeat ping/pong for dead connection detection
    - Exponential backoff reconnection
    - Command queue with dedicated sender coroutine
    - Command result correlation with futures
    - Handles command_replay messages from server
    """

    def __init__(
        self,
        uri: str,
        on_state_update: Callable,
        on_event: Callable,
        config: Optional[WebSocketConfig] = None
    ):
        self.uri = uri
        self.websocket: Optional[WebSocketClientProtocol] = None
        self.on_state_update = on_state_update
        self.on_event = on_event
        self.running = False
        self._config = config or WebSocketConfig()

        # Command queue for ordered sending
        self._command_queue: asyncio.Queue[Dict[str, Any]] = asyncio.Queue()
        self._sender_task: Optional[asyncio.Task] = None

        # Track pending commands for result correlation
        self._pending_commands: Dict[str, PendingCommand] = {}
        self._command_counter = 0
        self._sequence_counter = 0

        # Track failed commands for retry logic
        self._failed_commands: list[Tuple[str, Dict[str, Any], str]] = []

        # Reconnection backoff
        self._backoff = ReconnectBackoff(
            base_delay=self._config.reconnect_base_delay,
            max_delay=self._config.reconnect_max_delay,
            jitter=self._config.reconnect_jitter
        )

    async def connect(self):
        """Connect to WebSocket server with exponential backoff reconnection."""
        self.running = True

        while self.running:
            try:
                logger.info(f"Connecting to {self.uri}... (attempt {self._backoff.attempt + 1})")

                async with websockets.connect(
                    self.uri,
                    ping_interval=self._config.ping_interval,
                    ping_timeout=self._config.ping_timeout,
                    close_timeout=5,
                ) as websocket:
                    self.websocket = websocket
                    self._backoff.reset()
                    logger.info("Connected to game server")

                    # Start command sender task
                    self._sender_task = asyncio.create_task(self._command_sender())

                    try:
                        async for message in websocket:
                            try:
                                data = json.loads(message)
                                await self._handle_message(data)
                            except json.JSONDecodeError as e:
                                logger.error(f"Failed to parse message: {e}")
                            except Exception as e:
                                logger.error(f"Error handling message: {e}", exc_info=True)
                    finally:
                        # Cancel sender task on disconnect
                        if self._sender_task:
                            self._sender_task.cancel()
                            try:
                                await self._sender_task
                            except asyncio.CancelledError:
                                pass
                            self._sender_task = None

            except websockets.ConnectionClosed as e:
                delay = self._backoff.next_delay()
                logger.warning(f"Connection closed (code={e.code}), reconnecting in {delay:.1f}s...")
                self.websocket = None
                await asyncio.sleep(delay)
            except Exception as e:
                delay = self._backoff.next_delay()
                logger.error(f"Connection error: {e}, reconnecting in {delay:.1f}s...")
                self.websocket = None
                await asyncio.sleep(delay)

    async def _command_sender(self):
        """Dedicated coroutine for sending commands - ensures ordering."""
        while self.running:
            try:
                # Wait for command with timeout to allow checking running flag
                try:
                    command_data = await asyncio.wait_for(
                        self._command_queue.get(),
                        timeout=1.0
                    )
                except asyncio.TimeoutError:
                    continue

                if self.websocket:
                    try:
                        await self.websocket.send(json.dumps(command_data))
                        logger.debug(f"Sent command: {command_data.get('command')}")
                    except Exception as e:
                        logger.error(f"Failed to send command: {e}")
                        # Connection is dead - clear websocket reference so we stop retrying
                        # The main connect() loop will handle reconnection
                        self.websocket = None
                        # Re-queue the command for retry after reconnection
                        await self._command_queue.put(command_data)
                        await asyncio.sleep(0.5)
                else:
                    # Not connected - re-queue command
                    await self._command_queue.put(command_data)
                    await asyncio.sleep(0.5)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Command sender error: {e}")
                await asyncio.sleep(0.1)

    async def _handle_message(self, data: Dict[str, Any]):
        """Route incoming messages to appropriate handlers."""
        msg_type = data.get("type")

        if msg_type == "state":
            await self.on_state_update(data)
        elif msg_type == "event":
            await self.on_event(data)
        elif msg_type == "command_result":
            await self._handle_command_result(data)
        elif msg_type == "command_replay":
            await self._handle_command_replay(data)
        else:
            logger.warning(f"Unknown message type: {msg_type}")

    async def _handle_command_result(self, data: Dict[str, Any]):
        """Handle command result from server."""
        success = data.get("success", False)
        message = data.get("message", "")
        command_id = data.get("command_id")

        # Resolve pending command future if exists
        if command_id and command_id in self._pending_commands:
            pending = self._pending_commands.pop(command_id)
            if not pending.future.done():
                pending.future.set_result({"success": success, "message": message})

        if success:
            logger.debug(f"Command success: {message}")
        else:
            logger.warning(f"Command failed: {message}")
            # Track failed commands for potential retry
            if "Unknown command" in message:
                self._failed_commands.append((message, data.get("original_command", {}), message))

    async def _handle_command_replay(self, data: Dict[str, Any]):
        """Handle replayed commands from server after reconnect."""
        command_id = data.get("command_id")
        original_timestamp = data.get("original_timestamp", 0)

        logger.info(f"Server replayed command {command_id} from {original_timestamp}")

        # If we have a pending future for this command, it will be resolved
        # when the command_result arrives after re-execution
        if command_id in self._pending_commands:
            logger.debug(f"Command {command_id} still pending, waiting for new result")
        else:
            logger.debug(f"Fire-and-forget command {command_id} being retried by server")

    async def send_command(
        self, command: str, parameters: Dict[str, Any], reason: str = ""
    ) -> bool:
        """Queue a command for sending (fire and forget).

        Commands are queued and sent by a dedicated sender coroutine,
        guaranteeing ordering and preventing concurrent sends.
        """
        # Check queue size limit
        if self._command_queue.qsize() >= self._config.command_queue_max_size:
            logger.warning("Command queue full, dropping oldest command")
            try:
                self._command_queue.get_nowait()
            except asyncio.QueueEmpty:
                pass

        self._sequence_counter += 1
        message = {
            "type": "command",
            "command": command,
            "sequence": self._sequence_counter,
            "timestamp": int(time.time() * 1000),
            "parameters": parameters,
            "reason": reason,
        }

        await self._command_queue.put(message)
        logger.debug(f"Queued command: {command} | {parameters}")
        return True

    async def send_command_with_result(
        self, command: str, parameters: Dict[str, Any], reason: str = "", timeout: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Queue a command and wait for the result.

        Returns dict with 'success' and 'message' keys.
        On timeout, returns {'success': False, 'message': 'Timeout'}.
        """
        if timeout is None:
            timeout = self._config.command_timeout

        # Check queue size limit
        if self._command_queue.qsize() >= self._config.command_queue_max_size:
            logger.warning("Command queue full, cannot send command")
            return {"success": False, "message": "Command queue full"}

        # Generate unique command ID
        self._command_counter += 1
        self._sequence_counter += 1
        command_id = f"cmd_{self._command_counter}_{uuid.uuid4().hex[:8]}"

        try:
            # Create future for this command
            loop = asyncio.get_running_loop()
            future: asyncio.Future = loop.create_future()

            message = {
                "type": "command",
                "command": command,
                "command_id": command_id,
                "sequence": self._sequence_counter,
                "timestamp": int(time.time() * 1000),
                "parameters": parameters,
                "reason": reason,
            }

            # Store pending command with its data (for potential replay)
            self._pending_commands[command_id] = PendingCommand(
                future=future,
                command_data=message
            )

            await self._command_queue.put(message)
            logger.debug(f"Queued command (awaiting): {command} | {parameters}")

            # Wait for result with timeout
            try:
                result = await asyncio.wait_for(future, timeout=timeout)
                return result
            except asyncio.TimeoutError:
                # Clean up pending command
                self._pending_commands.pop(command_id, None)
                logger.warning(f"Command timeout: {command}")
                return {"success": False, "message": "Timeout waiting for command result"}

        except Exception as e:
            self._pending_commands.pop(command_id, None)
            logger.error(f"Failed to send command: {e}")
            return {"success": False, "message": str(e)}

    def get_available_tools_prompt(self) -> str:
        """Get the available tools prompt for LLM retry."""
        return AVAILABLE_TOOLS

    def get_failed_commands(self) -> list[Tuple[str, Dict[str, Any], str]]:
        """Get list of failed commands since last check and clear the list."""
        failed = self._failed_commands.copy()
        self._failed_commands.clear()
        return failed

    def get_pending_command_count(self) -> int:
        """Get number of commands awaiting results."""
        return len(self._pending_commands)

    def get_queue_size(self) -> int:
        """Get number of commands waiting to be sent."""
        return self._command_queue.qsize()

    def stop(self):
        """Stop the client."""
        self.running = False
        logger.info("Stopping WebSocket client...")
