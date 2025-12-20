#!/usr/bin/env python3
"""
Simple WebSocket test client for Dragon Run Director AI.
Connects to the game server and displays real-time game state updates.
"""

import asyncio
import websockets
import json
import sys
from datetime import datetime

async def connect_to_director():
    uri = "ws://localhost:8765"

    print(f"[{datetime.now().strftime('%H:%M:%S')}] Connecting to Dragon Run Director at {uri}...")

    try:
        async with websockets.connect(uri) as websocket:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Connected successfully!")
            print("=" * 80)
            print("Listening for game state updates... (Ctrl+C to quit)")
            print("=" * 80)

            async for message in websocket:
                try:
                    data = json.loads(message)
                    timestamp = datetime.now().strftime('%H:%M:%S')

                    if data.get("type") == "state":
                        # Full state update
                        print(f"\n[{timestamp}] STATE UPDATE:")
                        print(f"  Game State: {data.get('gameState')}")
                        print(f"  Run ID: {data.get('runId')}")

                        if data.get('gameState') == 'ACTIVE':
                            print(f"  Duration: {data.get('runDuration')}s")
                            print(f"  Dragon Alive: {data.get('dragonAlive')}")
                            print(f"  World: {data.get('worldName')}")
                            print(f"  Players in Hardcore: {data.get('hardcorePlayers')}")
                        elif data.get('gameState') == 'IDLE':
                            print(f"  Lobby Players: {data.get('lobbyPlayers')}")
                            print(f"  Votes: {data.get('voteCount')}/{data.get('votesRequired')}")

                        print(f"  Total Online: {data.get('totalPlayers')}")

                    elif data.get("type") == "event":
                        # Event notification
                        event_type = data.get('eventType')
                        event_data = data.get('data', {})

                        print(f"\n[{timestamp}] EVENT: {event_type.upper()}")
                        for key, value in event_data.items():
                            print(f"  {key}: {value}")

                    else:
                        # Unknown message type
                        print(f"\n[{timestamp}] UNKNOWN MESSAGE:")
                        print(f"  {json.dumps(data, indent=2)}")

                except json.JSONDecodeError:
                    print(f"\n[{timestamp}] ERROR: Invalid JSON received")
                    print(f"  Raw message: {message}")

    except websockets.exceptions.ConnectionClosed:
        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Connection closed by server")
    except ConnectionRefusedError:
        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] ERROR: Connection refused")
        print("  Make sure the Dragon Run server is running with director.enabled=true")
    except Exception as e:
        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] ERROR: {type(e).__name__}: {e}")

def main():
    try:
        asyncio.run(connect_to_director())
    except KeyboardInterrupt:
        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Disconnected")
        sys.exit(0)

if __name__ == "__main__":
    main()
