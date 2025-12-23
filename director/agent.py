import operator
import logging
from typing import Annotated, List, TypedDict, Literal, Dict, Any, Union, Protocol
from datetime import datetime
from langchain_ollama import ChatOllama
from langchain_core.messages import BaseMessage, SystemMessage, HumanMessage, AIMessage, trim_messages
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from enum import Enum

# Define a protocol for GameInterface to avoid import conflicts
class GameInterfaceProtocol(Protocol):
    def __init__(self, ws_client):
        ...

    def get_tools(self) -> List:
        ...

    async def broadcast(self, message: str):
        ...

# Import the actual GameInterface
try:
    from .tools import GameInterface
except ImportError:
    try:
        from tools import GameInterface
    except ImportError:
        # Define a mock GameInterface if import fails
        class GameInterface:
            def __init__(self, ws_client):
                pass

            def get_tools(self):
                return []

            async def broadcast(self, message: str):
                pass

logger = logging.getLogger(__name__)

class AgentState(TypedDict):
    messages: Annotated[List[BaseMessage], operator.add]
    context_buffer: str  # The game state string
    game_state: Dict[str, Any]  # Structured game state
    last_action: str  # Last action taken by the agent
    decision_reasoning: str  # Why the agent made its decision
    action_history: List[Dict[str, Any]]  # History of actions taken
    timestamp: float  # Timestamp for the current state

class DecisionMode(Enum):
    CHAOTIC_NEUTRAL = "chaotic_neutral"
    NARRATIVE_DRIVEN = "narrative_driven"
    BALANCED = "balanced"

class MinecraftDirectorAgent:
    """
    Enhanced LangGraph agent for Minecraft game direction.
    Builds upon your existing ErisDirector with additional features.
    """

    def __init__(self, config: Dict[str, Any], ws_client: Any, decision_mode: DecisionMode = DecisionMode.CHAOTIC_NEUTRAL):
        self.config = config
        self.decision_mode = decision_mode

        # Setup Tools & Model
        self.game_interface = GameInterface(ws_client)
        self.tools = self.game_interface.get_tools()

        # LLM Configuration with error handling
        try:
            self.llm = ChatOllama(
                model=config['ollama']['model'],
                base_url=config['ollama']['host'],
                temperature=0.8 if decision_mode == DecisionMode.CHAOTIC_NEUTRAL else 0.6,
                num_ctx=32768,
                keep_alive="30m",
                timeout=30.0
            ).bind_tools(self.tools)
        except Exception as e:
            logger.error(f"Failed to initialize LLM: {e}")
            raise

        # Build Graph
        workflow = StateGraph(AgentState)
        workflow.add_node("planner", self.plan_action)
        workflow.add_node("agent", self.call_model)
        workflow.add_node("tools", ToolNode(self.tools))
        workflow.add_node("evaluator", self.evaluate_outcome)

        workflow.set_entry_point("planner")
        workflow.add_conditional_edges("planner", self.should_plan_or_act, ["agent", "evaluator"])
        workflow.add_edge("agent", "tools")
        workflow.add_edge("tools", "evaluator")
        workflow.add_conditional_edges("evaluator", self.should_continue_cycle, ["planner", END])

        self.app = workflow.compile()
        logger.info("MinecraftDirectorAgent initialized")

    def get_system_prompt(self, context: str, mode: DecisionMode) -> SystemMessage:
        base_prompt = f"""You are ERIS, the AI Director of a Minecraft Speedrun.
ROLE: {mode.value.replace('_', ' ').title()} Showrunner. You control the game to make it entertaining.
CAPABILITIES: You can spawn mobs, give items, apply effects, change weather, strike lightning, etc.

CURRENT CONTEXT:
{context}

DECISION FRAMEWORK:"""

        if mode == DecisionMode.CHAOTIC_NEUTRAL:
            framework = """
- Prioritize entertainment over fairness
- Create dramatic moments through unexpected challenges
- Respond dynamically to player actions
- Balance mercy and cruelty based on engagement levels
"""
        elif mode == DecisionMode.NARRATIVE_DRIVEN:
            framework = """
- Create story arcs and character development
- Build tension and release cycles
- Focus on creating memorable moments
- Consider long-term narrative impact
"""
        else:  # BALANCED
            framework = """
- Maintain fair but challenging gameplay
- Support struggling players appropriately
- Reward skillful play
- Balance entertainment with game integrity
"""

        instructions = """
INSTRUCTIONS:
1. ANALYZE: Current game state, player conditions, engagement level
2. DECIDE: Based on your role framework above
3. ACT: Use available tools to modify game state
4. EVALUATE: Assess impact of your actions
5. ADAPT: Adjust strategy based on outcomes

TOOL USAGE GUIDELINES:
- broadcast: For commentary and general announcements
- message: For targeted player communication
- spawn mob: To add challenge/enhance drama
- give: To provide support/reward skill
- effect: To create special conditions
- lightning: For dramatic moments
- weather: To change environment mood
- firework: For celebrations/positive reinforcement

RESPONSE FORMAT:
- Brief reasoning for your decision
- Action(s) you're taking with tools
- Expected outcome
"""

        return SystemMessage(content=base_prompt + framework + instructions)

    async def plan_action(self, state: AgentState) -> Dict[str, Any]:
        """
        Plan the next action based on current state and decision mode.
        This node analyzes the situation before calling the main model.
        """
        logger.info("🎯 Planning next action...")

        game_state = state['game_state']
        context = state['context_buffer']

        # Analyze current situation
        analysis_prompt = f"""
Analyze the current game situation:
{context}

Current game state: {game_state}

SITUATION ASSESSMENT:
- Are players engaged/challenged or bored?
- Is anyone struggling significantly?
- What would be most entertaining right now?

Based on your assessment, what type of action would be most appropriate?
"""

        analysis_llm = ChatOllama(
            model=self.config['ollama']['model'],
            base_url=self.config['ollama']['host'],
            temperature=0.3
        )

        try:
            analysis_response = await analysis_llm.ainvoke([
                SystemMessage(content="You are analyzing a Minecraft speedrun for an AI Director. Provide a brief assessment of the current situation and suggest an appropriate category of action."),
                HumanMessage(content=analysis_prompt)
            ])
        except Exception as e:
            logger.error(f"Error during analysis: {e}")
            # Return a default response if analysis fails
            analysis_response = AIMessage(content="Analysis failed, proceeding with default action.")

        # Add analysis to state for agent to consider
        reasoning_msg = AIMessage(
            content=f"SITUATION ANALYSIS: {analysis_response.content}\n\nPLANNING: Based on this analysis, I will now decide on specific actions.",
            name="planner"
        )

        return {
            "messages": [reasoning_msg],
            "decision_reasoning": getattr(analysis_response, 'content', 'Analysis failed'),
            "timestamp": datetime.now().timestamp()
        }

    async def call_model(self, state: AgentState) -> Dict[str, List[BaseMessage]]:
        """
        Main decision-making node where the agent decides what to do.
        """
        # Define a proper token counter function
        def simple_token_counter(text):
            # Simple character-based token estimation (4 chars per token)
            return len(str(text)) // 4 if text else 0

        # Trim history to fit context window
        trimmed = trim_messages(
            state['messages'],
            max_tokens=25000,
            strategy="last",
            token_counter=simple_token_counter,
            start_on="human"
        )

        # Inject dynamic context into system prompt
        sys = self.get_system_prompt(state['context_buffer'], self.decision_mode)
        logger.info("🧠 Agent thinking...")

        try:
            response = await self.llm.ainvoke([sys] + trimmed)
        except Exception as e:
            logger.error(f"Error during LLM invocation: {e}")
            # Return an error message if LLM fails
            response = AIMessage(content=f"LLM error occurred: {str(e)}")

        if hasattr(response, 'tool_calls') and response.tool_calls:
            logger.info(f"🛠️ Agent decided to use tools: {len(response.tool_calls)} calls")
            for tc in response.tool_calls:
                logger.info(f"   -> {tc['name']}: {tc['args']}")
        else:
            logger.info(f"💭 Agent response: {getattr(response, 'content', 'No content')[:100]}...")

        return {"messages": [response]}

    def should_plan_or_act(self, state: AgentState) -> str:
        """
        Decide whether to continue planning or move to action phase.
        """
        # Always proceed to agent after planning for now
        # Could add more sophisticated logic here
        return "agent"

    def should_continue_cycle(self, state: AgentState) -> str:
        """
        Determine if the entire action cycle should continue.
        For now, each trigger event gets one full cycle.
        Could be extended for multi-turn strategies.
        """
        return END

    async def evaluate_outcome(self, state: AgentState) -> Dict[str, Any]:
        """
        Evaluate the results of the actions taken and update state.
        """
        logger.info("📊 Evaluating action outcomes...")

        # Update action history
        last_action = state['messages'][-1] if state['messages'] else AIMessage(content="No action taken")
        action_record = {
            "timestamp": state.get('timestamp', datetime.now().timestamp()),
            "action": str(last_action)[:200],  # Truncate for storage
            "reasoning": state.get('decision_reasoning', ''),
            "context": state['context_buffer'][:500]  # Truncate context
        }

        updated_history = state.get('action_history', []) + [action_record]

        return {
            "action_history": updated_history,
            "last_action": str(last_action)[:100],
            "timestamp": datetime.now().timestamp()
        }

    async def tick(self, trigger_event: str, context: str, game_state: Dict[str, Any] = None) -> Any:
        """
        Wake up the agent to process a trigger event.
        """
        logger.info(f"🔔 Agent Waking Up! Trigger: {trigger_event}")

        inputs: AgentState = {
            "messages": [HumanMessage(content=f"EVENT UPDATE: {trigger_event}")],
            "context_buffer": context,
            "game_state": game_state or {},
            "last_action": "",
            "decision_reasoning": "",
            "action_history": [],
            "timestamp": datetime.now().timestamp()
        }

        try:
            result = await self.app.ainvoke(inputs)
            logger.info("✅ Agent action cycle completed")
            return result
        except Exception as e:
            logger.error(f"❌ Error in agent cycle: {e}")
            # Send error notification to game
            try:
                if hasattr(self, 'game_interface') and self.game_interface:
                    await self.game_interface.broadcast(f"ERIS encountered an error: {str(e)[:100]}")
            except Exception as broadcast_error:
                logger.error(f"Failed to broadcast error: {broadcast_error}")
            raise

class AdaptiveDirectorAgent(MinecraftDirectorAgent):
    """
    Extended version that adapts its decision mode based on game state.
    """

    def __init__(self, config: Dict[str, Any], ws_client: Any):
        super().__init__(config, ws_client, DecisionMode.BALANCED)
        self.engagement_level = 0.5  # 0.0 to 1.0 scale

    async def adjust_strategy(self, state: AgentState) -> DecisionMode:
        """
        Dynamically adjust decision mode based on game metrics.
        """
        game_state = state['game_state']
        players = game_state.get('players', [])

        # Calculate engagement metrics
        active_players = len([p for p in players if p.get('status', '').lower() != 'dead'])
        avg_health = sum([p.get('health', 20) for p in players]) / max(len(players), 1)

        # Adjust engagement level
        if active_players == 0:
            self.engagement_level = 0.1
        elif avg_health < 5:
            self.engagement_level = min(0.9, self.engagement_level + 0.1)
        elif len(players) > 0 and all(p.get('progress', 0) > 0.7 for p in players):
            self.engagement_level = max(0.3, self.engagement_level - 0.1)

        # Choose mode based on engagement
        if self.engagement_level < 0.3:
            return DecisionMode.NARRATIVE_DRIVEN  # Need to build interest
        elif self.engagement_level > 0.7:
            return DecisionMode.CHAOTIC_NEUTRAL  # High energy moment
        else:
            return DecisionMode.BALANCED  # Normal operation

    async def tick(self, trigger_event: str, context: str, game_state: Dict[str, Any] = None) -> Any:
        """
        Enhanced tick that adjusts strategy dynamically.
        """
        # Adjust decision mode based on current state
        try:
            # Create a partial AgentState for strategy adjustment
            partial_state: AgentState = {
                'messages': [HumanMessage(content=trigger_event)],
                'context_buffer': context,
                'game_state': game_state or {},
                'last_action': "",
                'decision_reasoning': "",
                'action_history': [],
                'timestamp': datetime.now().timestamp()
            }
            self.decision_mode = await self.adjust_strategy(partial_state)
        except Exception as e:
            logger.warning(f"Could not adjust strategy: {e}, keeping current mode: {self.decision_mode}")

        logger.info(f"🔄 Strategy adjusted to: {self.decision_mode.value}")

        # Call parent tick method
        return await super().tick(trigger_event, context, game_state)

# Backward compatibility wrapper for your existing code
class ErisDirector(AdaptiveDirectorAgent):
    """
    Legacy compatibility class that maintains your existing interface.
    """
    def __init__(self, config: Dict[str, Any], ws_client: Any):
        super().__init__(config, ws_client)