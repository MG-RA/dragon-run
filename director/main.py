import asyncio
import yaml
import logging
import time
from websocket_client import GameStateClient
from state_manager import GameStateManager
from database_tools import DatabaseTools
from proactive_engine import ProactiveEngine
from dashboard import DirectorDashboard
from agent import ErisDirector

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    filename='director.log'
)
logger = logging.getLogger(__name__)

class DragonRunDirector:
    """The AI Director for Dragon Run - provides commentary and interventions."""

    def __init__(self, config_path='config.yaml', use_dashboard=True):
        # Load configuration
        with open(config_path, 'r') as f:
            self.config = yaml.safe_load(f)

        # Initialize dashboard
        self.use_dashboard = use_dashboard
        self.dashboard = DirectorDashboard() if use_dashboard else None

        # Initialize components
        self.state_manager = GameStateManager()
        self.proactive_engine = ProactiveEngine(self.config)
        self.database = DatabaseTools(self.config)
        
        # WebSocket client (needed for agent initialization)
        self.ws_client = GameStateClient(
            self.config['websocket']['uri'],
            self.on_state_update,
            self.on_event
        )

        # Initialize Eris Agent
        self.agent = ErisDirector(self.config, self.ws_client)

        if not use_dashboard:
            logger.info("Dragon Run Director initialized")

    async def on_state_update(self, state):
        """Handle periodic state updates (every 5 seconds)."""
        self.state_manager.update_state(state)

        # Update dashboard
        if self.dashboard:
            self.dashboard.update_game_state(state)
            self.dashboard.update_player_state(state.get('players', []))

        # Only log state updates when something significant changes (for non-dashboard mode)
        run_id = state.get('runId')
        game_state = state.get('gameState')
        players = state.get('players', [])

        # Track previous state to detect changes
        if not hasattr(self, '_last_logged_state'):
            self._last_logged_state = {}

        # Check if we should log (state changed, player count changed, or every 30 seconds)
        should_log = (
            self._last_logged_state.get('gameState') != game_state or
            self._last_logged_state.get('playerCount') != len(players) or
            self._last_logged_state.get('runId') != run_id or
            time.time() - self._last_logged_state.get('lastLogTime', 0) > 30
        )

        if should_log and not self.use_dashboard:
            # Keep existing logging logic for console info if dashboard is off
            duration = state.get('runDuration', 0)
            logger.info(f"📊 STATE UPDATE - Run #{run_id} ({game_state}) - {duration}s elapsed")

            self._last_logged_state = {
                'gameState': game_state,
                'playerCount': len(players),
                'runId': run_id,
                'lastLogTime': time.time()
            }

    async def on_event(self, event):
        self.state_manager.add_event(event)
        
        # Trigger Logic: Only wake the AI for interesting things
        # to save compute/latency
        should_wake = False
        trigger_msg = ""
        
        etype = event.get('eventType')
        
        if etype == 'player_chat':
            should_wake = True
            trigger_msg = f"Player {event['data']['player']} said: {event['data']['message']}"
            
        elif etype == 'player_death_detailed':
            should_wake = True
            trigger_msg = f"Player {event['data']['player']} died!"
            
        elif self.proactive_engine.should_analyze(): # Timer based check
            should_wake = True
            trigger_msg = "Routine check: Look at the state and see if anything needs intervention."

        if should_wake:
            # 1. Get Memory
            context = self.state_manager.get_narrative_context()
            
            # 2. Run Agent
            # The agent handles execution internally via the ToolNode
            await self.agent.tick(trigger_msg, context)

    async def run(self):
        """Main event loop."""
        # Start dashboard if enabled
        if self.dashboard:
            self.dashboard.start()
            self.dashboard.update_ai_status("🟡 Starting...")
            self.dashboard.log_ai_activity("system", "Director initializing...")

        # Connect to database
        self.database.connect()

        if self.dashboard:
            self.dashboard.log_ai_activity("system", "Database connected")

        # Start WebSocket client
        if self.dashboard:
            self.dashboard.update_ai_status("🟡 Connecting to game...")

        await self.ws_client.connect()

        if self.dashboard:
            self.dashboard.log_ai_activity("system", "WebSocket connected")
            self.dashboard.update_ai_status("🟢 Idle")

if __name__ == "__main__":
    director = DragonRunDirector()
    try:
        asyncio.run(director.run())
    except KeyboardInterrupt:
        if director.dashboard:
            director.dashboard.stop()
    finally:
        if director.dashboard:
            director.dashboard.stop()
        director.database.close()