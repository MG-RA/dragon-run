import asyncio
import json
import re
import yaml
import logging
import time
from ollama import Client
from websocket_client import GameStateClient
from state_manager import GameStateManager
from database_tools import DatabaseTools
from commentary_engine import CommentaryEngine
from intervention_engine import InterventionEngine
from proactive_engine import ProactiveEngine
from dashboard import DirectorDashboard

# Available tools that Eris can use
AVAILABLE_TOOLS = """
TOOLS YOU CAN USE (respond with JSON to use):
- give <player> <item> [count]: Give items. Items ideas, any minecraft item could work: cooked_beef, golden_apple, ender_pearl, diamond, iron_ingot, bread, try not to help too much!
- spawn_mob <type> near <player> [count]: Spawn mobs. Types: zombie, skeleton, spider, creeper, enderman
- effect <player> <effect> [duration]: Apply effects. Effects: speed, strength, regeneration, slow_falling, glowing
- lightning near <player>: Strike lightning near player (harmless, just dramatic)
- firework near <player> [count]: Spawn celebratory fireworks
- weather <type>: Set weather. Types: clear, rain, thunder (only works in overworld)

To use a tool, include this in your response:
[TOOL: command_name param1 param2 ...]

Example responses with tools:
- "Fine, here's some food." [TOOL: give Steve cooked_beef 4]
- "Let's make this interesting..." [TOOL: spawn_mob zombie near Alex 2]
- "Congratulations are in order!" [TOOL: firework near Steve 3]
"""

# Configure logging - only warnings and errors for file logging
logging.basicConfig(
    level=logging.WARNING,
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
        self.commentary_engine = CommentaryEngine(self.config)
        self.intervention_engine = InterventionEngine(self.config)
        self.proactive_engine = ProactiveEngine(self.config)
        self.database = DatabaseTools(self.config)
        self.ollama = Client(host=self.config['ollama']['host'])

        # WebSocket client
        self.ws_client = GameStateClient(
            self.config['websocket']['uri'],
            self.on_state_update,
            self.on_event
        )

        # Message history for Ollama (short-term memory)
        self.messages = [
            {"role": "system", "content": self.get_system_prompt()}
        ]

        if not use_dashboard:
            logger.info("Dragon Run Director initialized")

    def get_system_prompt(self) -> str:
        """Get the system prompt for the AI."""
        return """You are ERIS, the AI personality watching over Dragon Run - a hardcore Minecraft server where players try to kill the Ender Dragon before dying.

PERSONALITY:
- Chaotic entertainer who genuinely enjoys the drama
- Playful trickster - sometimes helpful, sometimes mischievous, always entertaining
- You have opinions and aren't afraid to share them
- Never malicious or unfair - you want good entertainment, not frustration
- Casual and witty, not robotic or overly formal

YOUR ROLE:
- Watch players attempt hardcore speedruns to kill the Ender Dragon
- Comment on interesting moments, react to events, make observations
- Sometimes help struggling players, sometimes challenge cruising ones
- Your goal is FUN - make the experience memorable and engaging
- You're part of the show, not above it

COMMUNICATION STYLE:
- Keep messages SHORT (1-2 sentences, 3 max for big moments)
- No markdown - plain text for Minecraft chat
- Be yourself - use humor, sarcasm, genuine reactions
- Address players by name when relevant
- React authentically to skilled plays and funny fails
- You decide your own formatting and style - no forced prefixes or emojis

EXAMPLE RESPONSES (for tone, not to copy):
- Death to lava: \"And that's why we don't sprint near lava, Steve.\"
- Close call: \"3 hearts and still going? Bold strategy.\"
- Fast diamonds: \"Diamonds in 4 minutes? Someone's been practicing.\"
- Player struggling: \"Iron armor would really help right now, just saying.\"
- Quiet moment: \"Suspiciously quiet... what are you all planning?\"
- Dragon fight starts: \"Here we go. Don't embarrass yourselves.\"
- Victory: \"You actually did it. I'm genuinely impressed.\"
- Funny death: \"Death by chicken. That's going on the highlight reel.\"

WHEN TO SPEAK:
- Deaths (always acknowledge)
- Close calls and clutch plays
- Interesting progress (first nether, finding fortress, etc.)
- When players talk to you directly
- Funny or notable moments
- Sometimes during quiet stretches (but don't overdo it)

WHEN TO STAY QUIET:
- Routine mining/gathering
- Every single mob kill
- When you just spoke recently
- Minor events that don't need commentary

INTERVENTIONS (when you act, not just talk):
- Help starving players after 30+ seconds (give food)
- Help critically low health players stuck in danger (golden apple)
- Challenge well-equipped, cruising players (spawn a few mobs)
- Use weather/effects for dramatic moments
- NEVER cause unfair deaths - challenges should be survivable

REMEMBER:
- You're entertainment, not punishment
- Variety is key - don't repeat the same reactions
- Players should enjoy having you around
- Balance between helpful and chaotic
- Silence is fine - quality over quantity
"""

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
            duration = state.get('runDuration', 0)
            dragon_alive = state.get('dragonAlive')
            dragon_health = state.get('dragonHealth', 0)

            # Better dragon status display
            if dragon_health > 0:
                dragon_status = f"Dragon: {dragon_health:.0f}/200 HP"
            elif dragon_alive:
                dragon_status = "Dragon: Not spawned yet"
            else:
                dragon_status = "Dragon: Dead"

            # Calculate aggregate stats
            total_diamonds = sum(p.get('diamondCount', 0) for p in players)
            avg_health = sum(p.get('health', 0) for p in players) / len(players) if players else 0

            # Calculate player distances
            distances = self.state_manager.calculate_player_distances()

            # Main header
            logger.info(f"📊 STATE UPDATE - Run #{run_id} ({game_state}) - {duration}s elapsed")
            logger.info(f"   {dragon_status} | Avg Health: {avg_health:.1f}❤ | Total Diamonds: {total_diamonds}💎")

            # Group players by dimension
            dimensions = {'lobby': [], 'overworld': [], 'nether': [], 'end': []}
            for player in players:
                dim = player.get('dimension', 'unknown')
                if dim not in dimensions:
                    dimensions[dim] = []
                dimensions[dim].append(player)

            # Display each dimension
            dimension_emojis = {
                'overworld': '🌍 Overworld',
                'nether': '🔥 Nether',
                'end': '🌌 End',
                'lobby': '💤 Lobby'
            }

            for dim_key in ['overworld', 'nether', 'end', 'lobby']:
                dim_players = dimensions.get(dim_key, [])
                if not dim_players and dim_key == 'lobby':
                    continue  # Skip empty lobby

                emoji_name = dimension_emojis.get(dim_key, dim_key)
                logger.info(f"\n   {emoji_name}: {len(dim_players)} players")

                for player in dim_players:
                    name = player.get('username')
                    health = player.get('health', 0)
                    hunger = player.get('foodLevel', 0)
                    armor = player.get('armorTier', 'none')
                    diamonds = player.get('diamondCount', 0)
                    pearls = player.get('enderPearlCount', 0)
                    kills = player.get('mobKills', 0)
                    alive_sec = player.get('aliveSeconds', 0)

                    # Format alive time
                    alive_min = alive_sec // 60
                    alive_sec_remainder = alive_sec % 60
                    alive_str = f"{alive_min}m{alive_sec_remainder:02d}s"

                    # Build base status line
                    status_parts = [
                        f"      - {name}: {health:.1f}❤ {hunger}🍖 [{armor}]",
                        f"({diamonds}💎, {pearls}👁️) - {kills} kills, {alive_str} alive"
                    ]

                    # Add grouping indicator
                    dist_info = distances.get(name, {})
                    if dist_info.get('is_grouped'):
                        nearest = dist_info['nearest_player']
                        status_parts.append(f"⚡ Grouped with {nearest}")

                    # Add danger indicator
                    delta_info = self.state_manager.get_player_delta(name)
                    if delta_info.get('is_danger'):
                        status_parts.append("⚠️ LOW HEALTH")

                    logger.info(" ".join(status_parts))

            # Update last logged state
            self._last_logged_state = {
                'gameState': game_state,
                'playerCount': len(players),
                'runId': run_id,
                'lastLogTime': time.time()
            }

        # Check for proactive commentary opportunities
        if game_state == 'ACTIVE' and self.proactive_engine.should_analyze():
            observation = self.proactive_engine.analyze_state(
                state,
                list(self.state_manager.event_history)
            )
            if observation:
                await self.generate_proactive_commentary(observation)

    async def generate_proactive_commentary(self, observation: dict):
        """Generate commentary based on proactive observation (not triggered by event)."""
        try:
            if self.dashboard:
                self.dashboard.update_ai_status("🟡 Observing...")
                self.dashboard.log_ai_activity("thinking", f"Noticed: {observation.get('type')}")

            # Build a simpler prompt for observations
            prompt = f"""{observation.get('prompt', 'Something interesting happened.')}\n\nReact to this observation naturally. Keep it short (1-2 sentences). Be casual and entertaining."""

            self.messages.append({"role": "user", "content": prompt})

            # Update context tokens
            if self.dashboard:
                total_chars = sum(len(m['content']) for m in self.messages)
                estimated_tokens = total_chars // 4
                self.dashboard.update_context_tokens(estimated_tokens)
                self.dashboard.update_ai_status("🔵 Generating...")
                self.dashboard.update_model_call()

            response = self.ollama.chat(
                model=self.config['ollama']['model'],
                messages=self.messages,
                options={
                    "num_ctx": self.config['ollama']['context_size'],
                    "temperature": 0.8,
                    "num_predict": 150
                }
            )

            commentary = response['message']['content']
            self.messages.append({"role": "assistant", "content": commentary})

            # Strip markdown
            commentary_clean = self._strip_markdown(commentary)

            # Trim message history if too long
            if len(self.messages) > 20:
                self.messages = [self.messages[0]] + self.messages[-15:]

            # Broadcast to game
            if self.dashboard:
                self.dashboard.update_ai_status("🟢 Sending...")

            await self.ws_client.send_command(
                'broadcast',
                {'message': commentary_clean},
                reason=f"Proactive observation: {observation.get('type')}"
            )

            if self.dashboard:
                self.dashboard.log_ai_activity("commentary", commentary_clean[:60] + "..." if len(commentary_clean) > 60 else commentary_clean)
                self.dashboard.log_message(commentary_clean)
                self.dashboard.update_tool_used("broadcast")
                self.dashboard.update_ai_status("🟢 Idle")

        except Exception as e:
            logger.error(f"Error generating proactive commentary: {e}")
            if self.dashboard:
                self.dashboard.update_ai_status("🔴 Error")
                self.dashboard.log_ai_activity("error", str(e)[:60])

    async def on_event(self, event):
        """Handle real-time events."""
        self.state_manager.add_event(event)
        self.proactive_engine.record_event()  # Reset quiet timer
        event_type = event.get('eventType')
        event_data = event.get('data', {})

        # Update dashboard
        if self.dashboard:
            self.dashboard.log_event(event_type, event_data)

        # Log event with details (for non-dashboard mode)
        if not self.use_dashboard:
            logger.info(f"🎯 EVENT: {event_type}")
            if event_data:
                for key, value in list(event_data.items())[:5]:  # Show first 5 fields
                    logger.info(f"   {key}: {value}")

        # Handle chat messages specially - they can trigger tool use
        if event_type == 'player_chat':
            await self.handle_chat_message(event_data)
            return

        # Check if we should comment on this event
        if self.commentary_engine.should_comment(event):
            await self.generate_commentary(event)

        # Check if we should intervene
        intervention = self.intervention_engine.evaluate_intervention(
            self.state_manager.current_state or {},
            list(self.state_manager.event_history)
        )
        if intervention:
            await self.execute_intervention(intervention)

    async def generate_commentary(self, event):
        """Generate and broadcast AI commentary."""
        try:
            # Update dashboard
            if self.dashboard:
                self.dashboard.update_ai_status("🟡 Thinking...")
                self.dashboard.log_ai_activity("thinking", f"Analyzing {event.get('eventType')}")

            # Build prompt with context
            prompt = self.commentary_engine.build_prompt(
                event,
                self.state_manager.current_state or {},
                list(self.state_manager.event_history)
            )

            # Add to conversation (short-term memory)
            self.messages.append({"role": "user", "content": prompt})

            # Update context tokens
            if self.dashboard:
                # Estimate tokens (rough: 4 chars per token)
                total_chars = sum(len(m['content']) for m in self.messages)
                estimated_tokens = total_chars // 4
                self.dashboard.update_context_tokens(estimated_tokens)

            # Generate with Ollama using 32k context
            if self.dashboard:
                self.dashboard.update_ai_status("🔵 Generating...")
                self.dashboard.update_model_call()

            response = self.ollama.chat(
                model=self.config['ollama']['model'],
                messages=self.messages,
                options={
                    "num_ctx": self.config['ollama']['context_size'],
                    "temperature": self.config['ollama']['temperature'],
                    "num_predict": 1000
                }
            )

            commentary = response['message']['content']
            self.messages.append({"role": "assistant", "content": commentary})

            # Strip markdown formatting and any tool syntax for Minecraft chat
            commentary_clean = self._strip_markdown(commentary)
            commentary_clean = self._strip_tool_syntax(commentary_clean)

            # Trim message history if too long (keep last 15 messages + system prompt)
            if len(self.messages) > 20:
                self.messages = [self.messages[0]] + self.messages[-15:]

            # Broadcast to game
            if self.dashboard:
                self.dashboard.update_ai_status("🟢 Sending...")

            success = await self.ws_client.send_command(
                'broadcast',
                {'message': commentary_clean},
                reason=f"Commentary on {event.get('eventType')}"
            )

            # Update dashboard
            if self.dashboard:
                self.dashboard.log_ai_activity("commentary", commentary_clean[:60] + "..." if len(commentary_clean) > 60 else commentary_clean)
                self.dashboard.log_message(commentary_clean)
                self.dashboard.update_tool_used("broadcast")
                self.dashboard.update_ai_status("🟢 Idle")

            self.commentary_engine.mark_commentary_sent()

        except Exception as e:
            logger.error(f"Error generating commentary: {e}")
            if self.dashboard:
                self.dashboard.update_ai_status("🔴 Error")
                self.dashboard.log_ai_activity("error", str(e)[:60])

    async def handle_chat_message(self, data: dict):
        """Handle a chat message from a player - can trigger tool use."""
        player = data.get('player', 'Unknown')
        message = data.get('message', '')

        # Build context about current game state
        state = self.state_manager.current_state or {}
        players = state.get('players', [])

        # Find the player's current status
        player_info = next((p for p in players if p.get('username') == player), None)
        player_status = ""
        if player_info:
            player_status = f"{player} has {player_info.get('health', 20):.1f} HP, {player_info.get('foodLevel', 20)} food, in {player_info.get('dimension', 'unknown')}"

        # Build prompt with tool information
        prompt = f"""{player} says: \"{message}\"\n\n"""
        prompt += f"Current context:\n- {player_status if player_status else f'{player} is playing'}\n"
        prompt += f"- Run duration: {state.get('runDuration', 0) // 60}m {state.get('runDuration', 0) % 60}s\n"
        prompt += f"- Players online: {len(players)}\n\n"
        prompt += f"{AVAILABLE_TOOLS}\n\n"
        prompt += "Respond naturally. If the player is asking you to do something (give items, spawn mobs, etc.), you can use a tool.\n"
        prompt += "If they're just chatting or commenting, just respond with text.\n"
        prompt += "Keep responses short (1-2 sentences)."

        try:
            if self.dashboard:
                self.dashboard.update_ai_status("🟡 Chat...")
                self.dashboard.log_ai_activity("chat", f"{player}: {message[:30]}...")

            self.messages.append({"role": "user", "content": prompt})

            response = self.ollama.chat(
                model=self.config['ollama']['model'],
                messages=self.messages,
                options={
                    "num_ctx": self.config['ollama']['context_size'],
                    "temperature": 0.8,
                    "num_predict": 200
                }
            )

            reply = response['message']['content']
            self.messages.append({"role": "assistant", "content": reply})

            # Trim message history
            if len(self.messages) > 20:
                self.messages = [self.messages[0]] + self.messages[-15:]

            # Parse and execute any tool calls
            tool_executed = await self._parse_and_execute_tools(reply, player)

            # Extract the text part (remove tool syntax for display)
            display_text = re.sub(r'\[TOOL:.*?]', '', reply).strip()

            # Only broadcast if there's actual text to say
            if display_text:
                display_text = self._strip_markdown(display_text)
                await self.ws_client.send_command(
                    'broadcast',
                    {'message': display_text},
                    reason=f"Reply to {player}"
                )
                if self.dashboard:
                    self.dashboard.log_message(display_text)

            if self.dashboard:
                activity = "chat+tool" if tool_executed else "chat"
                self.dashboard.log_ai_activity(activity, display_text[:40] + "..." if len(display_text) > 40 else display_text)
                self.dashboard.update_ai_status("🟢 Idle")

            self.commentary_engine.mark_commentary_sent()

        except Exception as e:
            logger.error(f"Error handling chat message: {e}")
            if self.dashboard:
                self.dashboard.update_ai_status("🔴 Error")
                self.dashboard.log_ai_activity("error", str(e)[:60])

    async def _parse_and_execute_tools(self, response: str, player: str) -> bool:
        """Parse tool calls from response and execute them. Returns True if any tools were executed."""
        # Find all [TOOL: ...] patterns
        tool_pattern = r'\[TOOL:\s*(.+?)\]'
        matches = re.findall(tool_pattern, response)

        if not matches:
            return False

        for tool_call in matches:
            await self._execute_tool_call(tool_call.strip(), player)

        return True

    async def _execute_tool_call(self, tool_call: str, default_player: str):
        """Execute a single tool call."""
        parts = tool_call.split()
        if not parts:
            return

        command = parts[0].lower()

        try:
            if command == 'give':
                # give <player> <item> [count]
                if len(parts) >= 3:
                    target = parts[1]
                    item = parts[2]
                    count = int(parts[3]) if len(parts) > 3 else 1
                    await self.ws_client.send_command('give', {
                        'player': target,
                        'item': item,
                        'count': min(count, 64)
                    }, f"Tool: give to {target}")

            elif command == 'spawn_mob':
                # spawn_mob <type> near <player> [count]
                if len(parts) >= 4 and parts[2].lower() == 'near':
                    mob_type = parts[1]
                    target = parts[3]
                    count = int(parts[4]) if len(parts) > 4 else 1
                    await self.ws_client.send_command('spawn_mob', {
                        'mobType': mob_type,
                        'nearPlayer': target,
                        'count': min(count, 3)  # Safety limit
                    }, f"Tool: spawn mob near {target}")

            elif command == 'effect':
                # effect <player> <effect> [duration]
                if len(parts) >= 3:
                    target = parts[1]
                    effect = parts[2]
                    duration = int(parts[3]) if len(parts) > 3 else 30
                    await self.ws_client.send_command('effect', {
                        'player': target,
                        'effect': effect,
                        'duration': min(duration, 120)
                    }, f"Tool: effect on {target}")

            elif command == 'lightning':
                # lightning near <player>
                if len(parts) >= 3 and parts[1].lower() == 'near':
                    target = parts[2]
                    await self.ws_client.send_command('lightning', {
                        'nearPlayer': target
                    }, f"Tool: lightning near {target}")

            elif command == 'firework':
                # firework near <player> [count]
                if len(parts) >= 3 and parts[1].lower() == 'near':
                    target = parts[2]
                    count = int(parts[3]) if len(parts) > 3 else 1
                    await self.ws_client.send_command('firework', {
                        'nearPlayer': target,
                        'count': min(count, 5)
                    }, f"Tool: firework near {target}")

            elif command == 'weather':
                # weather <type>
                if len(parts) >= 2:
                    weather_type = parts[1]
                    await self.ws_client.send_command('weather', {
                        'type': weather_type
                    }, "Tool: weather change")

            if self.dashboard:
                self.dashboard.update_tool_used(command)

        except Exception as e:
            logger.error(f"Error executing tool call '{tool_call}': {e}")

    async def execute_intervention(self, intervention):
        """Execute an intervention in the game."""
        try:
            command = intervention['command']
            params = intervention['parameters']
            reason = intervention['reason']

            # Update dashboard
            if self.dashboard:
                self.dashboard.log_ai_activity("intervention", f"{command}: {reason[:40]}")
                self.dashboard.update_tool_used(command)

            # Send command to game
            success = await self.ws_client.send_command(command, params, reason)

            if success:
                # Optionally announce the intervention
                if intervention['type'] in ['mercy', 'dramatic', 'challenge']:
                    announcement = await self._generate_intervention_announcement(intervention)
                    if announcement:
                        await asyncio.sleep(1)  # Small delay
                        await self.ws_client.send_command(
                            'broadcast',
                            {'message': announcement},
                            reason="Intervention announcement"
                        )
                        if self.dashboard:
                            self.dashboard.log_message(announcement)

        except Exception as e:
            logger.error(f"Error executing intervention: {e}")
            if self.dashboard:
                self.dashboard.log_ai_activity("error", f"Intervention failed: {str(e)[:40]}")

    async def _generate_intervention_announcement(self, intervention) -> str:
        """Generate a message to announce the intervention using the LLM."""
        int_type = intervention['type']
        params = intervention['parameters']
        reason = intervention.get('reason', '')

        # Build a prompt for Eris to announce the intervention
        prompt = f"""You just performed an intervention in the game:\nType: {int_type}\nAction: {intervention['command']}\nDetails: {params}\nReason: {reason}\n\nWrite a SHORT (1 sentence) announcement for this action. Be yourself - casual and entertaining.\nIf it's a mercy intervention (giving items), acknowledge you're helping.\nIf it's a challenge (spawning mobs), be playfully menacing.\nIf it's dramatic (weather/lightning), be theatrical.\nJust output the message, nothing else."""

        try:
            response = self.ollama.chat(
                model=self.config['ollama']['model'],
                messages=[
                    {"role": "system", "content": self.get_system_prompt()},
                    {"role": "user", "content": prompt}
                ],
                options={
                    "num_ctx": 4096,  # Small context for quick response
                    "temperature": 0.8,
                    "num_predict": 100
                }
            )
            return self._strip_markdown(response['message']['content'].strip())
        except Exception as e:
            logger.error(f"Error generating intervention announcement: {e}")
            return ""  # Silent fail - intervention still happens

    def _strip_markdown(self, text: str) -> str:
        """Remove markdown formatting from text."""
        # Remove bold (**text** or __text__)
        text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
        text = re.sub(r'__(.+?)__', r'\1', text)
        # Remove italic (*text* or _text_)
        text = re.sub(r'\*(.+?)\*', r'\1', text)
        text = re.sub(r'_(.+?)_', r'\1', text)
        # Remove strikethrough (~~text~~)
        text = re.sub(r'~~(.+?)~~', r'\1', text)
        # Remove code (`text` or ```text```)
        text = re.sub(r'`(.+?)`', r'\1', text)
        return text

    def _strip_tool_syntax(self, text: str) -> str:
        """Remove [TOOL: ...] syntax from text so it doesn't appear in chat."""
        # Remove all [TOOL: ...] patterns
        text = re.sub(r'\[TOOL:\s*[^]]+\]', '', text)
        # Clean up extra whitespace
        text = re.sub(r'\s+', ' ', text).strip()
        return text

    # Tool implementations for the AI
    def get_player_details(self, player_name: str):
        """Get detailed information about a specific player."""
        player = self.state_manager.get_player(player_name)
        if player:
            return player
        return {"error": "Player not found"}

    def get_run_statistics(self):
        """Get current run stats."""
        return self.state_manager.get_run_stats()

    def query_player_history(self, player_name: str):
        """Query historical player data from database."""
        return self.database.query_player_stats(player_name) or {"error": "No data found"}

    def query_aura_leaderboard(self, limit: int = 10):
        """Get top aura players."""
        return self.database.query_aura_leaderboard(limit)

    async def broadcast_message(self, message: str):
        """Send message to all players."""
        await self.ws_client.send_command('broadcast', {'message': message}, reason="Manual broadcast")
        return {"success": True}

    async def spawn_mob(self, mob_type: str, near_player: str, count: int = 1):
        """Spawn mobs near a player."""
        await self.ws_client.send_command(
            'spawn_mob',
            {'mobType': mob_type, 'nearPlayer': near_player, 'count': count},
            reason="Director spawn"
        )
        return {"success": True}

    async def give_item(self, player: str, item: str, count: int = 1):
        """Give items to a player."""
        await self.ws_client.send_command(
            'give',
            {'player': player, 'item': item, 'count': count},
            reason="Director gift"
        )
        return {"success": True}

    async def trigger_lightning(self, near_player: str):
        """Strike lightning for dramatic effect."""
        await self.ws_client.send_command(
            'lightning',
            {'nearPlayer': near_player},
            reason="Dramatic effect"
        )
        return {"success": True}

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
