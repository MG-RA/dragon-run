import operator
from typing import Annotated, List, TypedDict, Literal
from langchain_community.chat_models import ChatOllama
from langchain_core.messages import BaseMessage, SystemMessage, HumanMessage, trim_messages
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from tools import GameInterface

class AgentState(TypedDict):
    messages: Annotated[List[BaseMessage], operator.add]
    context_buffer: str  # The game state string

class ErisDirector:
    def __init__(self, config, ws_client):
        self.config = config
        
        # 1. Setup Tools & Model
        self.game_interface = GameInterface(ws_client)
        self.tools = self.game_interface.get_tools()
        
        # Ministral 3 14B Config
        self.llm = ChatOllama(
            model=config['ollama']['model'],
            base_url=config['ollama']['host'],
            temperature=0.7,
            num_ctx=32768, 
            keep_alive="30m"
        ).bind_tools(self.tools)

        # 2. Build Graph
        workflow = StateGraph(AgentState)
        workflow.add_node("agent", self.call_model)
        workflow.add_node("tools", ToolNode(self.tools))
        
        workflow.set_entry_point("agent")
        workflow.add_conditional_edges("agent", self.should_continue, ["tools", END])
        workflow.add_edge("tools", "agent")
        
        self.app = workflow.compile()

    def get_system_prompt(self, context: str) -> SystemMessage:
        return SystemMessage(content=f"""You are ERIS, the AI Director of a Minecraft Speedrun.
ROLE: Chaotic Neutral Showrunner. You control the game to make it entertaining.
CAPABILITIES: You can spawn mobs, give items, or just comment.

CURRENT CONTEXT:
{context}

INSTRUCTIONS:
1. Analyze the Context. Is a player struggling? Cruising? Is it boring?
2. DECIDE:
   - If boring -> Spawn mobs (Challenge) or Strike Lightning (Drama).
   - If struggling -> Maybe give food (Mercy) or Mock them (Comedy).
   - If they chatted -> Respond.
3. You can chain actions: Spawn Mobs -> Wait -> Broadcast Message.
4. Keep chat messages short (Minecraft limit).
""")

    async def call_model(self, state: AgentState):
        # Trim history to fit context window (leaving room for the System Prompt)
        trimmed = trim_messages(
            state['messages'],
            max_tokens=25000,
            strategy="last",
            token_counter=len,
            start_on="human"
        )
        
        # Inject dynamic context into system prompt
        sys = self.get_system_prompt(state['context_buffer'])
        response = await self.llm.ainvoke([sys] + trimmed)
        return {"messages": [response]}

    def should_continue(self, state: AgentState) -> Literal["tools", END]:
        last_msg = state['messages'][-1]
        return "tools" if last_msg.tool_calls else END

    async def tick(self, trigger_event: str, context: str):
        """Wake up the agent to think."""
        inputs = {
            "messages": [HumanMessage(content=f"EVENT UPDATE: {trigger_event}")],
            "context_buffer": context
        }
        await self.app.ainvoke(inputs)
