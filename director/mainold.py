import json
from ollama import Client
from ollama import ChatResponse

client = Client(host='http://localhost:11434',)
# Configuration
MODEL = "ministral-3:14b"

class DragonRunOverlord:
    def __init__(self):
        self.messages = [
            {"role": "system", "content": (
                "You are the Dragon Run Overlord. Your job is to manage a hardcore Minecraft "
                "roguelike ecosystem. You have tools to interact with the PaperMC Plugin, "
                "the Stats API. Always use a tool if a task requires "
                "external action. If multiple steps are needed, do them one by one."
            )}
        ]


    def get_top_aura_players(self, limit: int = 5):
        """Queries the PostgreSQL database via the Stats API for leaderboards."""
        # This would call your actual API endpoint
        return [{"player": "Player1", "aura": 5000}, {"player": "Player2", "aura": 4200}]

    def run(self, user_prompt: str):
        self.messages.append({"role": "user", "content": user_prompt})
        
        # Tool mapping
        available_tools = {
            "get_top_aura_players": self.get_top_aura_players,
        }

        # Main agent loop
        while True:
            response = client.chat(
                model=MODEL,
                messages=self.messages,
                tools=[
                    self.get_top_aura_players
                ]
            )

            # Check if the LLM wants to use a tool
            if response.get('message', {}).get('tool_calls'):
                for tool in response['message']['tool_calls']:
                    function_name = tool['function']['name']
                    args = tool['function']['arguments']
                    
                    # Execute tool
                    tool_func = available_tools.get(function_name)
                    result = tool_func(**args) # type: ignore
                    
                    # Add tool result to conversation context
                    self.messages.append(response['message'])
                    self.messages.append({
                        'role': 'tool',
                        'content': json.dumps(result),
                        'name': function_name
                    })
                # Continue loop to let the model process results
                continue
            
            # Final response
            return response['message']['content']

# Usage Example
if __name__ == "__main__":
    overlord = DragonRunOverlord()
    # Complex task requiring multiple tools
    goal = "hello this is for testing"
    print(f"Overlord: {overlord.run(goal)}")