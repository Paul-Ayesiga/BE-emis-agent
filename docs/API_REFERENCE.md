# MAS API Reference

Complete API documentation for the MAS (Multi-Agent System) streaming agent.

## 🌐 Base URL

```
http://localhost:8001
```

For production deployments, replace with your actual domain.

## 📋 Overview

The MAS API provides a RESTful interface with Server-Sent Events (SSE) streaming capabilities for real-time AI agent interactions. The API is built with FastAPI and supports concurrent multi-user sessions with persistent memory.

### Key Features

- **Streaming Responses**: Real-time token-by-token responses via SSE
- **Session Management**: Persistent conversations with checkpointing
- **Human-in-the-Loop**: Built-in escalation for human assistance
- **Tool Integration**: Seamless integration with OpenAPI tools via FastMCP
- **Error Recovery**: Robust error handling with graceful degradation

## 🔐 Authentication & Configuration

### Environment Setup

The API requires the following environment variables:

```env
GOOGLE_API_KEY=your_google_gemini_key
TAVILY_API_KEY=your_tavily_key_optional
LANGCHAIN_API_KEY=your_langchain_key_optional
```

### CORS Configuration

The API includes CORS middleware configured for:
- `http://localhost:3000` (React dev server)
- `http://localhost:5173` (Vite dev server)

For production, update the CORS origins in `streaming_api.py`.

## 📡 Endpoints

### Health Check

Check if the agent is initialized and ready to handle requests.

**GET** `/health`

#### Response

```json
{
  "status": "healthy",
  "agent_initialized": true
}
```

#### Status Codes

- `200 OK`: Agent is healthy and initialized
- `503 Service Unavailable`: Agent not initialized or unhealthy

#### Example

```bash
curl -X GET "http://localhost:8001/health"
```

---

### Start Streaming Chat

Initiate a new conversation or continue an existing session with real-time streaming responses.

**POST** `/chat/stream`

#### Request Body

```json
{
  "message": "string",
  "session_id": "string" // optional
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `message` | string | Yes | User's message or query |
| `session_id` | string | No | Existing session ID for continuation |

#### Response

Server-Sent Events (SSE) stream with the following chunk types:

```json
{
  "type": "thinking|tool_call|response|completed|error|human_input_needed",
  "content": "string",
  "session_id": "string",
  "timestamp": "string" // ISO 8601 format
}
```

#### Chunk Types

| Type | Description | Example Content |
|------|-------------|-----------------|
| `thinking` | Agent reasoning process | "Analyzing the user's request for school information..." |
| `tool_call` | Tool execution status | "Calling search_schools with parameters..." |
| `response` | Streaming response tokens | "I found 5 schools matching your criteria..." |
| `completed` | Task completion | "Task completed successfully" |
| `error` | Error information | "Error: Unable to connect to database" |
| `human_input_needed` | Human assistance required | "I need clarification: Which type of schools?" |

#### Status Codes

- `200 OK`: Stream started successfully
- `400 Bad Request`: Invalid request format
- `503 Service Unavailable`: Agent not initialized

#### Example Request

```bash
curl -X POST "http://localhost:8001/chat/stream" \
  -H "Content-Type: application/json" \
  -H "Accept: text/event-stream" \
  -d '{
    "message": "Find all high schools in New York with more than 500 students",
    "session_id": "session-123"
  }'
```

#### Example Response Stream

```
data: {"type": "thinking", "content": "I need to search for high schools in New York with enrollment over 500 students.", "session_id": "session-123", "timestamp": "2024-01-01T12:00:00Z"}

data: {"type": "tool_call", "content": "Searching schools database with filters: location=New York, type=high_school, min_capacity=500", "session_id": "session-123", "timestamp": "2024-01-01T12:00:01Z"}

data: {"type": "response", "content": "I found 23 high schools in New York with enrollment over 500 students. Here are the top results:\n\n1. **Brooklyn Technical High School**\n   - Enrollment: 5,900 students\n   - Location: Brooklyn, NY", "session_id": "session-123", "timestamp": "2024-01-01T12:00:02Z"}

data: {"type": "completed", "content": "Query completed successfully", "session_id": "session-123", "timestamp": "2024-01-01T12:00:03Z"}
```

---

### Resume Conversation

Resume a conversation that requires human input or approval.

**POST** `/chat/resume`

#### Request Body

```json
{
  "session_id": "string",
  "human_response": "string"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `session_id` | string | Yes | Session ID that needs human input |
| `human_response` | string | Yes | Human's response or decision |

#### Response

Server-Sent Events (SSE) stream (same format as `/chat/stream`)

#### Status Codes

- `200 OK`: Conversation resumed successfully
- `400 Bad Request`: Invalid session ID or missing response
- `404 Not Found`: Session not found or expired

#### Example Request

```bash
curl -X POST "http://localhost:8001/chat/resume" \
  -H "Content-Type: application/json" \
  -H "Accept: text/event-stream" \
  -d '{
    "session_id": "session-123",
    "human_response": "Yes, please proceed with sending the enrollment report to all principals"
  }'
```

---

### Get Interactive Documentation

Access the automatically generated API documentation.

**GET** `/docs`

Returns the interactive Swagger UI documentation.

**GET** `/redoc`

Returns the ReDoc-style documentation.

## 🔄 Streaming Implementation

### Client-Side Implementation

#### JavaScript (Browser)

```javascript
async function streamChat(message, sessionId = null) {
  const response = await fetch('/chat/stream', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      message: message,
      session_id: sessionId
    })
  });

  const reader = response.body.getReader();
  const decoder = new TextDecoder();

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    const chunk = decoder.decode(value);
    const lines = chunk.split('\n');
    
    for (const line of lines) {
      if (line.startsWith('data: ')) {
        const data = JSON.parse(line.slice(6));
        handleChunk(data);
      }
    }
  }
}

function handleChunk(chunk) {
  switch (chunk.type) {
    case 'thinking':
      showThinking(chunk.content);
      break;
    case 'tool_call':
      showToolExecution(chunk.content);
      break;
    case 'response':
      appendResponse(chunk.content);
      break;
    case 'human_input_needed':
      promptHumanInput(chunk.content, chunk.session_id);
      break;
    case 'completed':
      hideLoading();
      break;
    case 'error':
      showError(chunk.content);
      break;
  }
}
```

#### Python Client

```python
import httpx
import json

async def stream_chat(message: str, session_id: str = None):
    async with httpx.AsyncClient() as client:
        async with client.stream(
            'POST',
            'http://localhost:8001/chat/stream',
            json={
                'message': message,
                'session_id': session_id
            },
            headers={'Accept': 'text/event-stream'}
        ) as response:
            async for line in response.aiter_lines():
                if line.startswith('data: '):
                    data = json.loads(line[6:])
                    yield data

# Usage
async for chunk in stream_chat("Find schools in California"):
    print(f"{chunk['type']}: {chunk['content']}")
```

#### React Hook

```jsx
import { useState, useEffect } from 'react';

export function useStreamingChat() {
  const [messages, setMessages] = useState([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [currentSession, setCurrentSession] = useState(null);

  const sendMessage = async (message) => {
    setIsStreaming(true);
    
    const response = await fetch('/chat/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        message,
        session_id: currentSession
      })
    });

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let currentResponse = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      const chunk = decoder.decode(value);
      const lines = chunk.split('\n');
      
      for (const line of lines) {
        if (line.startsWith('data: ')) {
          const data = JSON.parse(line.slice(6));
          
          if (data.type === 'response') {
            currentResponse += data.content;
            setMessages(prev => [
              ...prev.slice(0, -1),
              { type: 'ai', content: currentResponse }
            ]);
          } else if (data.type === 'completed') {
            setIsStreaming(false);
            setCurrentSession(data.session_id);
          }
        }
      }
    }
  };

  return { messages, isStreaming, sendMessage };
}
```

## ⚠️ Error Handling

### Error Response Format

All errors follow a consistent format:

```json
{
  "type": "error",
  "content": "Error description",
  "session_id": "string",
  "timestamp": "2024-01-01T12:00:00Z",
  "error_code": "ERROR_CODE",
  "details": {
    "additional": "context"
  }
}
```

### Common Error Codes

| Code | Description | Resolution |
|------|-------------|------------|
| `AGENT_NOT_INITIALIZED` | Agent not ready | Wait for startup or restart service |
| `INVALID_SESSION` | Session ID not found | Start new session |
| `TOOL_EXECUTION_ERROR` | Tool call failed | Retry or check tool configuration |
| `RATE_LIMIT_EXCEEDED` | Too many requests | Wait and retry with backoff |
| `HUMAN_INPUT_TIMEOUT` | Human assistance timeout | Resume with `/chat/resume` |
| `AUTHENTICATION_ERROR` | API key issues | Check environment variables |

### Error Recovery Strategies

#### Client-Side Retry Logic

```javascript
async function streamWithRetry(message, sessionId, maxRetries = 3) {
  for (let attempt = 1; attempt <= maxRetries; attempt++) {
    try {
      await streamChat(message, sessionId);
      return; // Success
    } catch (error) {
      if (attempt === maxRetries) {
        throw error; // Final attempt failed
      }
      
      // Exponential backoff
      await new Promise(resolve => 
        setTimeout(resolve, Math.pow(2, attempt) * 1000)
      );
    }
  }
}
```

#### Server-Side Error Recovery

The server implements automatic recovery for:
- Temporary API failures
- Network timeouts
- Memory checkpointing errors
- Tool execution failures

## 📊 Rate Limiting & Performance

### Rate Limits

- **Per session**: 10 requests per minute
- **Per IP**: 100 requests per hour
- **Concurrent streams**: 5 per session

### Performance Tips

1. **Reuse Sessions**: Keep session IDs for follow-up questions
2. **Handle Chunked Responses**: Process stream chunks incrementally
3. **Implement Backoff**: Use exponential backoff for retries
4. **Cache Responses**: Cache non-sensitive responses locally
5. **Batch Requests**: Combine related questions when possible

### Monitoring Headers

The API includes performance headers:

```http
X-Response-Time: 1.234s
X-Session-Duration: 45.67s
X-Tool-Calls: 3
X-Tokens-Used: 1500
```

## 🛠️ SDKs & Libraries

### Official Python SDK

```python
from mas_client import MASClient

client = MASClient(base_url="http://localhost:8001")

# Simple chat
response = await client.chat("Find schools in Texas")

# Streaming chat
async for chunk in client.stream_chat("Analyze enrollment data"):
    print(chunk.content)

# Resume conversation
response = await client.resume_chat(
    session_id="session-123",
    human_response="Yes, proceed"
)
```

### JavaScript/TypeScript SDK

```typescript
import { MASClient } from '@mas/client';

const client = new MASClient({
  baseUrl: 'http://localhost:8001'
});

// Streaming with async iteration
const stream = client.streamChat({
  message: 'Show me school statistics',
  sessionId: 'session-123'
});

for await (const chunk of stream) {
  console.log(`${chunk.type}: ${chunk.content}`);
}
```

## 🧪 Testing

### Health Check Test

```bash
#!/bin/bash
# health_check.sh

response=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8001/health)

if [ $response = "200" ]; then
    echo "✅ API is healthy"
    exit 0
else
    echo "❌ API health check failed (HTTP $response)"
    exit 1
fi
```

### Integration Test

```python
import asyncio
import httpx

async def test_streaming_chat():
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "http://localhost:8001/chat/stream",
            json={"message": "Hello, test message"},
            headers={"Accept": "text/event-stream"}
        )
        
        assert response.status_code == 200
        
        chunks = []
        async for line in response.aiter_lines():
            if line.startswith('data: '):
                chunk = json.loads(line[6:])
                chunks.append(chunk)
                
                if chunk['type'] == 'completed':
                    break
        
        assert len(chunks) > 0
        assert any(chunk['type'] == 'response' for chunk in chunks)

# Run test
asyncio.run(test_streaming_chat())
```

## 🔧 Advanced Usage

### Custom Headers

```http
POST /chat/stream
Content-Type: application/json
X-Request-ID: unique-request-id
X-User-Context: {"role": "admin", "school_id": "123"}

{
  "message": "Show confidential data",
  "session_id": "admin-session"
}
```

### Webhook Integration

Configure webhooks for session events:

```python
# webhook_handler.py
from fastapi import FastAPI, Request

app = FastAPI()

@app.post("/webhook/session-complete")
async def handle_session_complete(request: Request):
    data = await request.json()
    session_id = data['session_id']
    duration = data['duration']
    
    # Log completion, update metrics, etc.
    print(f"Session {session_id} completed in {duration}s")
```

### Custom Tools Integration

Add custom tools to the agent:

```python
from langchain_core.tools import tool

@tool
def calculate_enrollment_growth(current: int, previous: int) -> str:
    """Calculate enrollment growth percentage."""
    growth = ((current - previous) / previous) * 100
    return f"Growth: {growth:.2f}%"

# Register with agent
agent.add_tool(calculate_enrollment_growth)
```

## 📝 Changelog

### v1.0.0 (Latest)
- Initial release with streaming chat
- Human-in-the-loop support
- Session persistence
- Tool integration via FastMCP
- Health check endpoint

## 🔮 Roadmap

### Planned Features
- File upload support
- Batch processing endpoints
- GraphQL interface
- Enhanced analytics
- Multi-language support

---

## 📞 Support

For API support:
1. Check the [troubleshooting guide](SETUP_GUIDE.md#troubleshooting)
2. Review error codes above
3. Submit issues with request/response examples
4. Include session IDs for faster debugging

**Happy building!** 🚀