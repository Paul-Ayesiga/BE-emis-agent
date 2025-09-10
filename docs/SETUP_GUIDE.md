# MAS Setup Guide

This guide provides detailed step-by-step instructions for setting up and running the MAS (Multi-Agent System) for EMIS.

## 📋 Prerequisites

### System Requirements

- **Operating System**: macOS, Linux, or Windows 10+
- **Python**: Version 3.13+ (check with `python --version`)
- **Memory**: Minimum 8GB RAM (16GB recommended)
- **Storage**: At least 2GB free space
- **Network**: Internet connection for API calls and package downloads

### Required Accounts and API Keys

1. **Google AI Studio Account**
   - Visit [Google AI Studio](https://makersuite.google.com/app/apikey)
   - Create an account and generate an API key
   - Keep this key secure - you'll need it for configuration

2. **Tavily Search (Optional)**
   - Visit [Tavily](https://tavily.com/) 
   - Sign up for an account
   - Get your API key from the dashboard

3. **LangChain (Optional - for tracing)**
   - Visit [LangSmith](https://smith.langchain.com/)
   - Create an account and get your API key

### Development Tools

- **Git**: For cloning the repository
- **UV Package Manager** (recommended) or pip
- **Code Editor**: VS Code, PyCharm, or your preferred editor

## 🚀 Installation Process

### Step 1: Clone the Repository

```bash
# Clone the repository
git clone <repository-url>
cd MAS

# Verify you're in the correct directory
ls -la
# You should see: main.py, streaming_api.py, my_mcp_server.py, pyproject.toml
```

### Step 2: Install Python and Package Manager

#### Install UV Package Manager (Recommended)

```bash
# On macOS and Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# On Windows (PowerShell)
powershell -c "irm https://astral.sh/uv/install.sh | iex"

# Restart your terminal and verify installation
uv --version
```

#### Alternative: Use pip (if UV is not available)

```bash
# Ensure you have Python 3.13+
python --version

# Upgrade pip to latest version
python -m pip install --upgrade pip
```

### Step 3: Set Up Virtual Environment

#### Using UV

```bash
# Create and activate virtual environment with dependencies
uv sync

# Activate the virtual environment
# On macOS/Linux:
source .venv/bin/activate

# On Windows:
.venv\Scripts\activate

# Verify activation (you should see (.venv) in your prompt)
which python  # Should point to .venv/bin/python
```

#### Using pip

```bash
# Create virtual environment
python -m venv .venv

# Activate virtual environment
# On macOS/Linux:
source .venv/bin/activate

# On Windows:
.venv\Scripts\activate

# Install dependencies
pip install -e .
```

### Step 4: Environment Configuration

Create a `.env` file in the project root directory:

```bash
# Create the .env file
touch .env  # On Windows: New-Item .env -ItemType File
```

Edit the `.env` file with your preferred text editor and add:

```env
# Required: Google Gemini API Key
GOOGLE_API_KEY=your_google_api_key_here

# Optional: Enhanced search capabilities
TAVILY_API_KEY=your_tavily_api_key_here

# Optional: LangChain tracing and monitoring
LANGCHAIN_API_KEY=your_langchain_api_key_here
LANGCHAIN_TRACING_V2=true
LANGCHAIN_PROJECT=emis-agent

# Optional: Logging configuration
LOG_LEVEL=INFO
PYTHONPATH=.
```

**Important**: Replace `your_google_api_key_here` with your actual Google API key.

### Step 5: Verify Installation

```bash
# Check Python version
python --version
# Should show Python 3.13 or higher

# Check installed packages
pip list | grep -E "(langraph|fastapi|google|mcp)"

# Verify environment variables
python -c "import os; print('GOOGLE_API_KEY:', 'SET' if os.getenv('GOOGLE_API_KEY') else 'NOT SET')"
```

## 🔧 Backend Setup (Optional)

If you have an existing EMIS backend API:

### Step 6: Prepare Your Backend API

1. Ensure your backend API is running on `http://localhost:8080`
2. Verify OpenAPI documentation is available at `http://localhost:8080/v3/api-docs`

```bash
# Test backend connectivity
curl http://localhost:8080/health
curl http://localhost:8080/v3/api-docs
```

If you don't have a backend API, the system will work with limited functionality using only the built-in tools.

## 🏃‍♂️ Running the System

### Step 7: Start the FastMCP Server

Open a new terminal window and run:

```bash
# Navigate to project directory
cd MAS

# Activate virtual environment
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Start the MCP server
python my_mcp_server.py
```

You should see output like:
```
INFO:     Started server process [12345]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000
```

Keep this terminal running.

### Step 8: Start the Streaming API Server

Open another terminal window and run:

```bash
# Navigate to project directory
cd MAS

# Activate virtual environment
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Start the streaming API server
python streaming_api.py
```

Alternatively, use uvicorn directly:

```bash
uvicorn streaming_api:app --host 0.0.0.0 --port 8001 --reload
```

You should see output like:
```
INFO:     Started server process [12346]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8001
```

### Step 9: Test the CLI Interface (Optional)

In a third terminal:

```bash
# Navigate to project directory
cd MAS

# Activate virtual environment
source .venv/bin/activate

# Start the CLI interface
python main.py
```

This will start an interactive chat session with the agent.

## ✅ Verification

### Test the API Endpoints

1. **Health Check**:
   ```bash
   curl http://localhost:8001/health
   ```
   Expected response:
   ```json
   {"status": "healthy", "agent_initialized": true}
   ```

2. **API Documentation**:
   - Open `http://localhost:8001/docs` in your browser
   - You should see the FastAPI interactive documentation

3. **Test Chat Endpoint**:
   ```bash
   curl -X POST "http://localhost:8001/chat/stream" \
        -H "Content-Type: application/json" \
        -d '{"message": "Hello, can you help me?", "session_id": "test-123"}'
   ```

### Test the Agent

1. **CLI Test**:
   ```bash
   python main.py
   # Try asking: "What can you help me with?"
   ```

2. **Web Interface Test** (if you have a frontend):
   - Navigate to your frontend application
   - Try starting a conversation
   - Verify streaming responses work

## 🐛 Troubleshooting

### Common Issues and Solutions

#### Issue 1: Import Errors

**Error**: `ModuleNotFoundError: No module named 'langraph'`

**Solution**:
```bash
# Reinstall dependencies
pip install -e .
# or with uv
uv sync
```

#### Issue 2: API Key Not Found

**Error**: `GOOGLE_API_KEY environment variable not set`

**Solutions**:
1. Verify `.env` file exists and contains the API key
2. Check the API key format (no quotes needed in .env)
3. Restart the application after adding the key

```bash
# Check if .env file exists
ls -la .env

# Check if key is loaded
python -c "from dotenv import load_dotenv; load_dotenv(); import os; print(os.getenv('GOOGLE_API_KEY')[:10] + '...' if os.getenv('GOOGLE_API_KEY') else 'NOT FOUND')"
```

#### Issue 3: Port Already in Use

**Error**: `Address already in use`

**Solutions**:
```bash
# Find process using the port
lsof -i :8000  # or :8001

# Kill the process
kill -9 <PID>

# Or use different ports
uvicorn streaming_api:app --port 8002
python my_mcp_server.py --port 8003
```

#### Issue 4: FastMCP Connection Failed

**Error**: `Connection failed to MCP server`

**Solutions**:
1. Ensure the MCP server is running on the correct port
2. Check if the backend API is accessible
3. Verify network connectivity

```bash
# Test MCP server directly
curl http://localhost:8000/mcp

# Check if backend is running
curl http://localhost:8080/health
```

#### Issue 5: Memory Issues

**Error**: System running out of memory

**Solutions**:
1. Close unnecessary applications
2. Increase virtual memory/swap
3. Consider using a smaller model or reducing concurrent sessions

```bash
# Check memory usage
free -h  # Linux
vm_stat  # macOS
```

### Debug Mode

Enable detailed logging:

```bash
# Set debug environment variables
export LOG_LEVEL=DEBUG
export PYTHONPATH="${PYTHONPATH}:."

# Run with debug output
python streaming_api.py
```

### Getting Help

If you're still experiencing issues:

1. Check the main [README.md](../README.md) for additional troubleshooting
2. Review the [parallel tools documentation](langgraph_parallel_tools.md)
3. Check the application logs for specific error messages
4. Create an issue with:
   - Your operating system
   - Python version
   - Complete error message
   - Steps you've already tried

## 🔧 Advanced Configuration

### Development Environment

For development work, install additional tools:

```bash
# Install development dependencies
uv sync --group dev

# Install pre-commit hooks
pre-commit install

# Run code quality checks
black .
ruff check .
mypy .
```

### Production Deployment

For production deployment:

1. **Use a production WSGI server**:
   ```bash
   # Install gunicorn
   pip install gunicorn

   # Run with multiple workers
   gunicorn streaming_api:app -w 4 -k uvicorn.workers.UvicornWorker
   ```

2. **Set up reverse proxy** (nginx, Apache, etc.)
3. **Configure SSL certificates**
4. **Set up monitoring and logging**
5. **Use environment-specific configuration**

### Docker Setup (Optional)

Create a `Dockerfile`:

```dockerfile
FROM python:3.13-slim

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN pip install uv && uv sync --frozen

COPY . .

EXPOSE 8001

CMD ["python", "streaming_api.py"]
```

Build and run:
```bash
docker build -t mas-agent .
docker run -p 8001:8001 --env-file .env mas-agent
```

## 🎯 Next Steps

After successful setup:

1. **Explore the API**: Use the interactive docs at `http://localhost:8001/docs`
2. **Test Different Queries**: Try various types of questions and tasks
3. **Integrate with Frontend**: Connect your web application to the streaming API
4. **Customize Tools**: Add your own tools and modify the agent behavior
5. **Monitor Performance**: Set up logging and monitoring for production use

## 📚 Additional Resources

- [Main README](../README.md) - Project overview and features
- [LangGraph Documentation](https://langchain-ai.github.io/langgraph/)
- [FastMCP Documentation](https://github.com/chrishayuk/fastmcp)
- [Google AI Studio](https://makersuite.google.com/)
- [FastAPI Documentation](https://fastapi.tiangolo.com/)

---

**Congratulations! 🎉** Your MAS system should now be up and running. If you encounter any issues, refer to the troubleshooting section or reach out for support.