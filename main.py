import os
import asyncio
import uuid
from typing import Dict, List, Any, Optional, Callable, Annotated, Literal
from typing_extensions import TypedDict
from dotenv import load_dotenv

from langgraph.graph import StateGraph, START, END
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, BaseMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition
from langchain_tavily import TavilySearch
from fastmcp import Client
from langchain_core.tools import StructuredTool, tool
from langgraph.types import Command, interrupt
from pydantic import BaseModel, Field, create_model
import traceback, sys
import json

# Load environment variables
load_dotenv()

class AgentState(TypedDict):
    messages: Annotated[List[BaseMessage], add_messages]
    task_plan: Optional[str]
    current_step: int
    max_iterations: int
    iterations_used: int
    task_completed: bool
    pending_data: Dict[str, Any]  # Store intermediate data between steps

@tool
def human_assistance(query: str) -> str:
    """Request assistance from a human when more information is needed."""
    try:
        print(f"🤖 Requesting human assistance: {query}")
        human_response = interrupt({"query": query})
        
        # This only executes after human provides input
        response_data = human_response.get("data", "")
        print(f"👤 Received human response: {response_data}")
        return human_response['data']
        
    except Exception as e:
        print(f"❌ Human assistance error: {e}")
        return f"Error requesting human assistance: {str(e)}"

class EMISAgent:
    def __init__(self, gemini_api_key: str):
        self.llm = ChatGoogleGenerativeAI(
            model="gemini-2.0-flash",
            google_api_key=gemini_api_key,
            temperature=0.1,
        )

        self.memory = InMemorySaver()
        self.client = Client("http://localhost:8000/mcp")
        self.graph = None

    async def initialize(self):
        await self.client.__aenter__()
        tools = await self.client.list_tools()
        self.graph = self._build_graph(tools)

    def _is_gemini_compatible_schema(self, schema: Dict[str, Any]) -> bool:
        """Check if schema is compatible with Gemini's strict requirements"""
        if not isinstance(schema, dict):
            return True
        
        properties = schema.get("properties", {})
        required = schema.get("required", [])
        
        for prop_name, prop_schema in properties.items():
            if isinstance(prop_schema, dict):
                prop_type = prop_schema.get("type")
                
                # Skip array types - they're problematic with Gemini
                if prop_type == "array":
                    return False
                    
        return True

    def _create_simple_pydantic_model(self, tool_name: str, schema: Dict[str, Any]) -> BaseModel:
        """Create a simple Pydantic model that works with Gemini"""
        if not schema or not schema.get("properties"):
            return create_model(f"{tool_name}Args")
        
        properties = schema.get("properties", {})
        required = schema.get("required", [])
        field_definitions = {}
        
        for prop_name, prop_schema in properties.items():
            prop_type = prop_schema.get("type", "string")
            description = prop_schema.get("description", "")
            
            # Only handle simple types
            if prop_type == "string":
                python_type = str
            elif prop_type == "integer":
                python_type = int
            elif prop_type == "number":
                python_type = float
            elif prop_type == "boolean":
                python_type = bool
            else:
                # Skip complex types
                continue
            
            if prop_name in required:
                field_definitions[prop_name] = (python_type, Field(description=description))
            else:
                field_definitions[prop_name] = (Optional[python_type], Field(default=None, description=description))
        
        return create_model(f"{tool_name}Args", **field_definitions)

    def _should_continue(self, state: AgentState) -> Literal["planner", "tools", "__end__"]:
        """Determine next step based on current state"""
        last_message = state["messages"][-1]
        
        # Check if task is completed
        if state.get("task_completed", False):
            return "__end__"
            
        # Check if we've hit iteration limit
        if state.get("iterations_used", 0) >= state.get("max_iterations", 10):
            return "__end__"
            
        # If last message is from human, go to planner
        if isinstance(last_message, HumanMessage):
            return "planner"
            
        # If AI message contains tool calls, execute them
        if hasattr(last_message, 'tool_calls') and last_message.tool_calls:
            return "tools"
                
        # Default: end if no tool calls and looks like final response
        return "__end__"

    def _build_graph(self, tools_metadata: List[Dict[str, Any]]) -> StateGraph:
        search = TavilySearch(max_results=2)
        tools = [search, human_assistance]

        for tool_meta in tools_metadata:
            name = tool_meta.name
            desc = tool_meta.description
            input_schema = tool_meta.inputSchema if hasattr(tool_meta, 'inputSchema') else {}
            
            # Skip tools with incompatible schemas
            if not self._is_gemini_compatible_schema(input_schema):
                print(f"⚠️  Skipping tool '{name}' - incompatible schema")
                continue
            
            # Create simple Pydantic model
            args_model = self._create_simple_pydantic_model(name, input_schema)

            async def async_run(tool_name=name, **kwargs):
                try:
                    print(f"🔧 Executing: {tool_name}({kwargs})")
                    result = await self.client.call_tool(tool_name, arguments=kwargs)
                    return result
                except Exception as e:
                    traceback.print_exc(file=sys.stdout)
                    return f"Error calling {tool_name}: {str(e)}"

            structured_tool = StructuredTool.from_function(
                coroutine=async_run,
                name=name,
                description=desc,
                args_schema=args_model,
            )
            
            tools.append(structured_tool)
            print(f"✅ Registered: {name}")

        llm_with_tools = self.llm.bind_tools(tools)

        def planner(state: AgentState):
            """Main planning node - decides what to do next"""
            
            system_prompt = """You are an autonomous EMIS agent. Your job is to complete tasks by thinking through them step by step and using available tools.

CORE PRINCIPLES:
1. BE AUTONOMOUS: Don't ask for permission to use tools or gather information
2. THINK MULTI-STEP: Break complex tasks into steps and execute them
3. USE CONTEXT: Remember what you've learned from previous tool calls
4. BE EFFICIENT: If you have partial information, work with it or gather what's missing
5. ALWAYS provide clear feedback when tasks are completed
6. Avoid exposing sensitive internal IDs from database in your responses
7. FORMAT ALL RESPONSES IN MARKDOWN for the React frontend for emphasis and visual representation
8. Structure your final responses in a more friendly way, if needed according to the context

9. Learn from previous steps and use that knowledge to inform your actions
10. If you encounter an error, try alternative approaches before asking for human assistance
11. Learn to chain available tools if they can provide some information in order to complete complex tasks.

HUMAN ASSISTANCE GUIDELINES:
- For learner registration, NEVER guess required fields like gender, grade, or academic year
- If missing critical information that cannot be obtained from tools, use the human_assistance tool
- Use human_assistance with clear, specific queries about what information you need
- Example: human_assistance("I need the following information to register the learner: gender (M/F), grade (1-12), and academic_year (e.g., 2024). Please provide these details.")

AVAILABLE CONTEXT:
- Task plan: {task_plan}
- Current step: {current_step}
- Pending data: {pending_data}
- Iterations used: {iterations_used}/{max_iterations}

DECISION FRAMEWORK:
- If you need data to complete a task, use tools to get it
- If you have enough information to take an action, do it
- If a previous step gave you an ID/reference, use it for the next step
- If you encounter an error, try alternative approaches
- After successful tool calls, provide clear feedback about what happened
- If missing required information that cannot be obtained through tools, use human_assistance tool

For multi-step tasks like "register a learner at Kampala International":
1. Search for school by name to get ID
2. Check what information is provided vs required for learner creation
3. If missing required fields (gender, grade, academic_year), use human_assistance tool to ask for these specific details
4. Use the school ID and provided/collected info to create the learner  
5. ALWAYS confirm completion with details

REQUIRED FIELDS FOR LEARNER REGISTRATION:
- name (from user request)
- gender (use human_assistance if not provided)
- grade (use human_assistance if not provided) 
- academic_year (use human_assistance if not provided)
- school_id (get from school search)

Execute your plan autonomously unless you genuinely cannot proceed.

COMPLETION CRITERIA:
- If you successfully complete the requested task, state completion clearly
- If you need more information from the user, use the human_assistance tool with specific questions
- If you encounter errors, try alternative approaches first""".format(
                task_plan=state.get("task_plan", "None"),
                current_step=state.get("current_step", 0),
                pending_data=state.get("pending_data", {}),
                iterations_used=state.get("iterations_used", 0),
                max_iterations=state.get("max_iterations", 10)
            )
            
            messages = [SystemMessage(content=system_prompt)] + state["messages"]
            response = llm_with_tools.invoke(messages)
            
            # Disable parallel tool calling to avoid issues with interrupts
            if hasattr(response, 'tool_calls') and response.tool_calls:
                assert len(response.tool_calls) <= 1, "Parallel tool calls not supported with interrupts"
            
            # Update iteration counter
            new_iterations = state.get("iterations_used", 0) + 1
            
            # Mark task as completed if this is a final response without tool calls
            task_completed = False
            if not (hasattr(response, 'tool_calls') and response.tool_calls):
                # This is a final response, check if it indicates completion
                content = response.content.lower()
                if any(word in content for word in ['successfully', 'completed', 'registered', 'created', 'done', 'finished']):
                    task_completed = True
                elif any(phrase in content for phrase in ['need more information', 'please provide', 'what would you like']):
                    # This is asking for more info, not completion
                    task_completed = False
                else:
                    # Default to completed for final responses
                    task_completed = True
            
            return {
                "messages": [response],
                "iterations_used": new_iterations,
                "task_completed": task_completed
            }

        # Build the graph
        graph_builder = StateGraph(AgentState)
        graph_builder.add_node("planner", planner)
        graph_builder.add_node("tools", ToolNode(tools=tools))

        # Add conditional edges
        graph_builder.add_conditional_edges("planner", self._should_continue)
        graph_builder.add_edge("tools", "planner")  # After tools, go back to planner
        graph_builder.add_edge(START, "planner")

        return graph_builder.compile(checkpointer=self.memory)

    async def stream_response(self, response_content: str):
        """Stream response character by character for better UX"""
        words = response_content.split(' ')
        for i, word in enumerate(words):
            if i == 0:
                print(f"🤖 Agent: {word}", end='', flush=True)
            else:
                print(f" {word}", end='', flush=True)
            await asyncio.sleep(0.03)  # Small delay for streaming effect
        print()  # New line at end

    async def chat(self):
        if not self.graph:
            await self.initialize()

        # Mark as CLI mode
        self._cli_mode = True

        print("🤖 Autonomous EMIS Agent - I'll handle multi-step tasks automatically!")
        print("📋 I can search for schools, create learners, and handle complex workflows.")
        print("💡 Just tell me what you want to accomplish!\n")
        
        try:
            while True:
                user_input = input("👤 You: ")
                if user_input.lower() in ["exit", "quit"]:
                    break
                    
                # Initialize state for new conversation
                initial_state = {
                    "messages": [HumanMessage(content=user_input)],
                    "task_plan": None,
                    "current_step": 0,
                    "max_iterations": 10,
                    "iterations_used": 0,
                    "task_completed": False,
                    "pending_data": {}
                }
                
                # Run the agent
                try:
                    config = {"thread_id": str(uuid.uuid4())}
                    
                    while True:
                        try:
                            final_state = await self.graph.ainvoke(initial_state, config=config)
                            
                            # Print final result if task completed
                            if final_state.get("task_completed", False):
                                last_msg = final_state["messages"][-1]
                                if isinstance(last_msg, AIMessage):
                                    await self.stream_response(last_msg.content)
                                    print("✅ **Task completed!**\n")
                            break
                            
                        except Exception as e:
                            if "interrupt" in str(e).lower():
                                # Handle human-in-the-loop interrupt
                                snapshot = self.graph.get_state(config)
                                if snapshot.next and len(snapshot.next) > 0:
                                    # Get the interrupt details
                                    interrupts = snapshot.interrupts
                                    if interrupts:
                                        interrupt_data = interrupts[0].value
                                        query = interrupt_data.get("query", "Human input needed")
                                        print(f"\n🤖 Agent: {query}")
                                        
                                        # Get human response
                                        human_response = input("👤 Your response: ")
                                        
                                        # Resume with human response
                                        human_command = Command(resume={"data": human_response})
                                        
                                        # Update state and continue
                                        updated_state = await self.graph.ainvoke(human_command, config=config)
                                        initial_state = updated_state
                                        continue
                            else:
                                raise e
                    
                except Exception as e:
                    print(f"❌ Error: {str(e)}")
                    print("Please try again.\n")
                    
        except KeyboardInterrupt:
            print("\n👋 Goodbye!")
        finally:
            try:
                await self.client.__aexit__(None, None, None)
            except:
                pass  # Ignore cleanup errors

# CLI runner
if __name__ == "__main__":
    async def main():
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            print("Set your GOOGLE_API_KEY environment variable.")
            return

        agent = EMISAgent(api_key)
        await agent.chat()

    asyncio.run(main())