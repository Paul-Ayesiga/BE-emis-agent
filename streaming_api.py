from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import json
import asyncio
from typing import AsyncGenerator
import uuid
from main import EMISAgent
from langgraph.types import Command
from langgraph.errors import GraphInterrupt
import os
import time

app = FastAPI(title="EMIS Streaming Agent API")

# Add CORS middleware for React frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],  # React dev servers
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global agent instance
agent = None

class ChatRequest(BaseModel):
    message: str
    session_id: str = None

class ResumeRequest(BaseModel):
    session_id: str
    human_response: str

class StreamChunk(BaseModel):
    type: str  # "thinking", "tool_call", "response", "completed", "error", "human_input_needed"
    content: str
    session_id: str
    timestamp: str

@app.on_event("startup")
async def startup_event():
    global agent
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError("GOOGLE_API_KEY environment variable not set")
    agent = EMISAgent(api_key)
    await agent.initialize()

async def generate_stream(message: str, session_id: str) -> AsyncGenerator[str, None]:
    """Generate streaming response for the chat message"""
    try:
        # Initial state
        initial_state = {
            "messages": [],
            "task_plan": None,
            "current_step": 0,
            "max_iterations": 10,
            "iterations_used": 0,
            "task_completed": False,
            "pending_data": {}
        }
        
        # Add user message
        from langchain_core.messages import HumanMessage
        initial_state["messages"] = [HumanMessage(content=message)]
        
        # Stream initial thinking message
        yield f"data: {json.dumps({'type': 'thinking', 'content': '🧠 **Processing your request...**', 'session_id': session_id})}\n\n"
        await asyncio.sleep(0.1)
        
        # Track response state
        response_started = False
        config = {"thread_id": session_id}
        
        try:
            # Run the agent with streaming updates
            async for chunk in agent.graph.astream(
                initial_state, 
                config=config
            ):
                node_name = list(chunk.keys())[0]
                node_output = chunk[node_name]
                
                if node_name == "tools":
                    # Tool execution
                    if "messages" in node_output:
                        for msg in node_output["messages"]:
                            if hasattr(msg, 'content') and msg.content:
                                # Extract tool name if possible
                                tool_name = "Unknown"
                                if hasattr(msg, 'name'):
                                    tool_name = msg.name
                                elif "CallToolResult" in str(msg.content):
                                    # Try to extract tool name from content
                                    content_str = str(msg.content)
                                    if "function_name" in content_str:
                                        try:
                                            start = content_str.find('"function_name": "') + 17
                                            end = content_str.find('"', start)
                                            if start > 16 and end > start:
                                                tool_name = content_str[start:end]
                                        except:
                                            pass
                                
                                tool_info = f"🔧 **Executing:** {tool_name}"
                                yield f"data: {json.dumps({'type': 'tool_call', 'content': tool_info, 'session_id': session_id})}\n\n"
                                await asyncio.sleep(0.1)
                
                elif node_name == "planner":
                    # AI response
                    if "messages" in node_output:
                        for msg in node_output["messages"]:
                            if hasattr(msg, 'content') and msg.content:
                                # If this is the first response content, clear thinking
                                if not response_started:
                                    response_started = True
                                    yield f"data: {json.dumps({'type': 'clear_thinking', 'content': '', 'session_id': session_id})}\n\n"
                                
                                # Check if message has tool calls (means it's not final response)
                                has_tool_calls = hasattr(msg, 'tool_calls') and msg.tool_calls
                                
                                if not has_tool_calls:
                                    # This is a final response - stream it word by word
                                    words = msg.content.split(' ')
                                    for i, word in enumerate(words):
                                        if i == 0:
                                            content = word
                                        else:
                                            content = f" {word}"
                                        
                                        yield f"data: {json.dumps({'type': 'response', 'content': content, 'session_id': session_id})}\n\n"
                                        await asyncio.sleep(0.05)  # Streaming delay
                                else:
                                    # This message has tool calls, just indicate planning
                                    yield f"data: {json.dumps({'type': 'thinking', 'content': '🤔 **Planning next steps...**', 'session_id': session_id})}\n\n"
                            
                            # Check if task is completed
                            if node_output.get("task_completed", False):
                                yield f"data: {json.dumps({'type': 'completed', 'content': '', 'session_id': session_id})}\n\n"
                                yield f"data: {json.dumps({'type': 'end', 'content': '', 'session_id': session_id})}\n\n"
                                return
            
            # End stream if we get here without task completion
            yield f"data: {json.dumps({'type': 'end', 'content': '', 'session_id': session_id})}\n\n"
            
        except GraphInterrupt as interrupt:
            # Handle human-in-the-loop interrupt
            if interrupt.interrupts:
                interrupt_data = interrupt.interrupts[0].value
                query = interrupt_data.get("query", "Human input needed")
                
                yield f"data: {json.dumps({'type': 'human_input_needed', 'content': query, 'session_id': session_id})}\n\n"
                # Don't end the stream - client will handle resumption
                return
            else:
                yield f"data: {json.dumps({'type': 'error', 'content': 'Unknown interrupt occurred', 'session_id': session_id})}\n\n"
                yield f"data: {json.dumps({'type': 'end', 'content': '', 'session_id': session_id})}\n\n"
        
    except Exception as e:
        error_msg = f"❌ **Error:** {str(e)}"
        yield f"data: {json.dumps({'type': 'error', 'content': error_msg, 'session_id': session_id})}\n\n"
        yield f"data: {json.dumps({'type': 'end', 'content': '', 'session_id': session_id})}\n\n"

async def generate_stream_resume(human_command: Command, session_id: str) -> AsyncGenerator[str, None]:
    """Generate streaming response after human input"""
    try:
        config = {"thread_id": session_id}
        
        yield f"data: {json.dumps({'type': 'thinking', 'content': '🧠 **Processing your response...**', 'session_id': session_id})}\n\n"
        await asyncio.sleep(0.1)
        
        response_started = False
        
        try:
            # Resume execution with human command
            async for chunk in agent.graph.astream(human_command, config=config):
                node_name = list(chunk.keys())[0]
                node_output = chunk[node_name]
                
                if node_name == "tools":
                    # Tool execution
                    if "messages" in node_output:
                        for msg in node_output["messages"]:
                            if hasattr(msg, 'content') and msg.content:
                                tool_name = "Unknown"
                                if hasattr(msg, 'name'):
                                    tool_name = msg.name
                                
                                tool_info = f"🔧 **Executing:** {tool_name}"
                                yield f"data: {json.dumps({'type': 'tool_call', 'content': tool_info, 'session_id': session_id})}\n\n"
                                await asyncio.sleep(0.1)
                
                elif node_name == "planner":
                    # AI response
                    if "messages" in node_output:
                        for msg in node_output["messages"]:
                            if hasattr(msg, 'content') and msg.content:
                                if not response_started:
                                    response_started = True
                                    yield f"data: {json.dumps({'type': 'clear_thinking', 'content': '', 'session_id': session_id})}\n\n"
                                
                                has_tool_calls = hasattr(msg, 'tool_calls') and msg.tool_calls
                                
                                if not has_tool_calls:
                                    # Stream final response
                                    words = msg.content.split(' ')
                                    for i, word in enumerate(words):
                                        if i == 0:
                                            content = word
                                        else:
                                            content = f" {word}"
                                        
                                        yield f"data: {json.dumps({'type': 'response', 'content': content, 'session_id': session_id})}\n\n"
                                        await asyncio.sleep(0.05)
                                else:
                                    yield f"data: {json.dumps({'type': 'thinking', 'content': '🤔 **Planning next steps...**', 'session_id': session_id})}\n\n"
                            
                            if node_output.get("task_completed", False):
                                yield f"data: {json.dumps({'type': 'completed', 'content': '', 'session_id': session_id})}\n\n"
                                yield f"data: {json.dumps({'type': 'end', 'content': '', 'session_id': session_id})}\n\n"
                                return
            
            yield f"data: {json.dumps({'type': 'end', 'content': '', 'session_id': session_id})}\n\n"
            
        except GraphInterrupt as interrupt:
            # Another human input needed
            if interrupt.interrupts:
                interrupt_data = interrupt.interrupts[0].value
                query = interrupt_data.get("query", "Human input needed")
                
                yield f"data: {json.dumps({'type': 'human_input_needed', 'content': query, 'session_id': session_id})}\n\n"
                return
                
    except Exception as e:
        error_msg = f"❌ **Error:** {str(e)}"
        yield f"data: {json.dumps({'type': 'error', 'content': error_msg, 'session_id': session_id})}\n\n"
        yield f"data: {json.dumps({'type': 'end', 'content': '', 'session_id': session_id})}\n\n"

@app.post("/chat/stream")
async def stream_chat(request: ChatRequest):
    """Stream chat responses to React frontend"""
    if not agent:
        raise HTTPException(status_code=500, detail="Agent not initialized")
    
    session_id = request.session_id or str(uuid.uuid4())
    
    return StreamingResponse(
        generate_stream(request.message, session_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Content-Type": "text/event-stream",
        }
    )

@app.post("/chat/resume")
async def resume_chat(request: ResumeRequest):
    """Resume conversation after human input"""
    if not agent:
        raise HTTPException(status_code=500, detail="Agent not initialized")
    
    # Resume with human response
    human_command = Command(resume={"data": request.human_response})
    
    return StreamingResponse(
        generate_stream_resume(human_command, request.session_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Content-Type": "text/event-stream",
        }
    )

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "agent_ready": agent is not None}

@app.get("/session/{session_id}/state")
async def get_session_state(session_id: str):
    """Get current state of a session"""
    if not agent:
        raise HTTPException(status_code=500, detail="Agent not initialized")
    
    try:
        config = {"thread_id": session_id}
        snapshot = agent.graph.get_state(config)
        
        return {
            "session_id": session_id,
            "next_nodes": list(snapshot.next) if snapshot.next else [],
            "has_interrupts": len(snapshot.interrupts) > 0 if snapshot.interrupts else False,
            "interrupt_data": snapshot.interrupts[0].value if snapshot.interrupts else None
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting session state: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)