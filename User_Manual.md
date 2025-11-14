# Lybic GUI Agent - User Manual

Complete guide to using the Lybic GUI Agent for AI-powered task automation.

## Table of Contents

- [Getting Started](#getting-started)
- [Quick Start](#quick-start)
- [Usage Guide](#usage-guide)
- [Configuration](#configuration)
- [Request Parameters](#request-parameters)
- [API Examples](#api-examples)
- [Architecture Design](#architecture-design)
- [Development Guide](#development-guide)
- [Project Information](#project-information)
- [Best Practice Example](#best-practice-example)

---

## Getting Started

### What is Lybic GUI Agent?

Lybic GUI Agent is a minimal administrative agent that provides RESTful APIs for AI-powered task automation using the UI-TARS model. It enables you to:

- Automate UI tasks in cloud sandbox environments
- Execute complex workflows with natural language instructions
- Manage async tasks with persistent context
- Stream real-time execution progress

### Prerequisites

Before you begin, ensure you have:

- **Python 3.10+** installed
- **Docker** (recommended for production)
- **Lybic Platform Account** - Get your API credentials from [Lybic](https://lybic.cn)
- **Doubao API Key** - Obtain from [Volcengine ARK Platform](https://console.volcengine.com/ark)

### Key Concepts

- **Sandbox** - Isolated cloud environment where tasks execute
- **Task** - A unit of work with instructions and context
- **Context** - Conversation history that persists across requests
- **Stream Mode** - Real-time task execution with SSE
- **Async Mode** - Background task execution with status polling

---

## Quick Start

### 1. Installation

#### Option A: Using Python (Development)

```bash
# Clone repository
git clone git@github.com:lybic/mini-agent.git
cd mini-agent

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# Install dependencies
pip install uv
uv sync

# Configure environment
cp src/.env.example src/.env
# Edit src/.env with your credentials
```

#### Option B: Using Docker (Recommended)

```bash
# Build the image
docker build -t lybic-guiagent .

# Run the container
docker run -p 5000:5000 lybic-guiagent
```

### 2. Starting the Server

```bash
# Method 1: Direct Python execution
python -m src.main

# Method 2: Using installed script
lybic-guiagent

# Server starts at http://localhost:5000
```

### 3. Verify Installation

```bash
# Health check
curl http://localhost:5000/api/health

# Expected response:
# {"status": "ok"}
```

---

## Usage Guide

### Workflow Overview

```
1. Create Sandbox (optional)
   ↓
2. Submit Task / Stream Execution
   ↓
3. Monitor Progress (async mode)
   ↓
4. Retrieve Results
   ↓
5. Continue Context (optional)
```

### Basic Usage Pattern

#### Streaming Mode (Real-time)

```bash
curl -X POST http://localhost:5000/api/agent/run \
  -H "Content-Type: application/json" \
  -d '{
    "instruction": "Open notepad and type Hello World",
    "sandbox_id": "box-123",
    "authentication": {
      "api_key": "sk-your-key",
      "org_id": "your-org-id"
    },
    "ark_apikey": "your-ark-key"
  }'
```

#### Async Mode (Background)

```bash
# Step 1: Submit task
TASK_ID=$(curl -X POST http://localhost:5000/api/agent/task/submit \
  -H "Content-Type: application/json" \
  -d '{
    "instruction": "Search for Python tutorials on Google",
    "sandbox_id": "box-123",
    "authentication": {
      "api_key": "sk-your-key",
      "org_id": "your-org-id"
    },
    "ark_apikey": "your-ark-key"
  }' | jq -r '.task_id')

# Step 2: Poll status
curl http://localhost:5000/api/agent/task/status/$TASK_ID
```

### Creating Sandboxes

```bash
curl -X POST http://localhost:5000/api/sandbox/create \
  -H "Content-Type: application/json" \
  -d '{
    "name": "my-sandbox",
    "shape": "beijing-2c-4g-cpu",
    "maxLifeSeconds": 3600,
    "authentication": {
      "api_key": "sk-your-key",
      "org_id": "your-org-id"
    }
  }'

# Response includes sandbox_id for subsequent requests
```

### Context Continuation

```bash
# First request
curl -X POST http://localhost:5000/api/agent/task/submit \
  -d '{
    "instruction": "Open browser and go to wikipedia.org",
    "sandbox_id": "BOX-123",
    "authentication": {...},
    "ark_apikey": "..."
  }' | jq -r '.task_id'

# Continue conversation with same context
curl -X POST http://localhost:5000/api/agent/run \
  -d '{
    "instruction": "Now search for Artificial Intelligence",
    "sandbox_id": "BOX-123",
    "continue_context": true,
    "task_id": "previous-task-id",
    "authentication": {...},
    "ark_apikey": "..."
  }'
```

### Cancelling Tasks

```bash
# Cancel specific task
curl -X POST http://localhost:5000/api/agent/cancel \
  -d '{
    "task_id": "task-id-to-cancel",
    "authentication": {...}
  }'

# Cancel all active tasks
curl -X POST http://localhost:5000/api/agent/cancel \
  -d '{
    "authentication": {...}
  }'
```

---

## Configuration

### Environment Variables

Create `src/.env` file with the following configuration:

```bash
# ==================== Logging ====================
# Options: DEBUG, INFO, WARNING, ERROR, CRITICAL
LOG_LEVEL=INFO

# ==================== Lybic Platform ====================
# Your Lybic API credentials
LYBIC_API_KEY=sk-your-lybic-api-key
LYBIC_ORG_ID=your-lybic-org-id
LYBIC_API_ENDPOINT=https://api.lybic.cn

# ==================== LLM Configuration ====================
# Doubao/ARK API key for UI-TARS model
ARK_API_KEY=your-ark-api-key

# ==================== Storage Configuration ====================
# Backend type: 'memory' (default) or 'postgres'
TASK_STORAGE_BACKEND=memory

# PostgreSQL connection (only if using postgres)
# POSTGRES_CONNECTION_STRING=postgresql://user:password@host:port/database
```

### Storage Backends

#### Memory Storage (Default)

- **Use Case**: Development, testing, single-instance deployments
- **Pros**: No external dependencies, fast
- **Cons**: Data lost on restart, not suitable for distributed systems

```bash
TASK_STORAGE_BACKEND=memory
```

#### PostgreSQL Storage

- **Use Case**: Production, distributed systems, data persistence
- **Pros**: Persistent, scalable, multi-instance support
- **Cons**: Requires PostgreSQL setup

```bash
TASK_STORAGE_BACKEND=postgres
POSTGRES_CONNECTION_STRING=postgresql://postgres:password@localhost:5432/agent_tasks
```

### Model Configuration

The agent uses Doubao's UI-TARS model by default:

- **Model Name**: `doubao-1-5-ui-tars-250428`
- **API Endpoint**: `https://ark.cn-beijing.volces.com/api/v3`
- **Thinking Type**: `disabled` (optimized for UI tasks)
- **System Prompt**: Defined in `src/prompts.py`

---

## Request Parameters

### `RunAgentRequest` (Streaming Execution)

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `instruction` | string | ✅ | - | Natural language task instruction |
| `sandbox_id` | string | ❌ | null | Lybic sandbox ID (created if omitted) |
| `user_system_prompt` | string | ❌ | null | Custom system prompt override |
| `continue_context` | boolean | ❌ | false | Continue from previous task context |
| `task_id` | string | ❌ | null | Task ID for context continuation |
| `authentication` | object | ❌ | null | Lybic credentials (overrides env vars) |
| `ark_apikey` | string | ❌ | null | ARK API key (overrides env var) |

### `SubmitTaskRequest` (Async Execution)

All parameters from `RunAgentRequest` plus:

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `max_steps` | integer | ❌ | 50 | Maximum execution steps |

### `CreateSandboxRequest`

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `name` | string | ❌ | - | Sandbox name |
| `shape` | string | ❌ | beijing-2c-4g-cpu | Sandbox specifications |
| `maxLifeSeconds` | integer | ❌ | 3600 | Sandbox lifetime (max 86400) |
| `projectId` | string | ❌ | null | Lybic project ID |
| `authentication` | object | ❌ | null | Lybic credentials |

### `CancelRequest`

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `task_id` | string | ❌ | null | Specific task to cancel (or all if null) |
| `authentication` | object | ❌ | null | Lybic credentials |

### `LybicAuthentication` Object

```json
{
  "api_key": "sk-your-api-key",
  "org_id": "your-org-id",
  "api_endpoint": "https://api.lybic.cn"  // optional
}
```

---

## API Examples

### Example 1: Simple Task Execution

```bash
curl -X POST http://localhost:5000/api/agent/run \
  -H "Content-Type: application/json" \
  -d '{
    "instruction": "Open calculator and compute 123 * 456",
    "sandbox_id": "sbx-abc123",
    "authentication": {
      "api_key": "sk-lybic-key",
      "org_id": "org-123"
    },
    "ark_apikey": "ark-api-key"
  }'
```

**Response** (Server-Sent Events stream):

```
data: {"type": "thinking", "content": "Planning to open calculator..."}

data: {"type": "action", "content": "Opening calculator application"}

data: {"type": "result", "content": "Result: 56088"}

data: {"type": "finished", "output": "Calculation completed: 56088"}
```

### Example 2: Async Task with Status Polling

```bash
# Submit task
curl -X POST http://localhost:5000/api/agent/task/submit \
  -H "Content-Type: application/json" \
  -d '{
    "instruction": "Create a text file named report.txt with content: Meeting notes",
    "sandbox_id": "box-abc123",
    "max_steps": 50,
    "authentication": {
      "api_key": "sk-lybic-key",
      "org_id": "org-123"
    },
    "ark_apikey": "ark-api-key"
  }'
```

**Response:**

```json
{
  "success": true,
  "task_id": "550e8400-e29b-41d4-a716-446655440000",
  "message": "Task submitted successfully"
}
```

**Poll status:**

```bash
curl http://localhost:5000/api/agent/task/status/550e8400-e29b-41d4-a716-446655440000
```

**Status Response:**

```json
{
  "task_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "finished",
  "query": "Create a text file named report.txt with content: Meeting notes",
  "finished_output": "File report.txt created successfully",
  "llm_context": {...},
  "sandbox_info": {
    "sandbox_id": "box-abc123"
  }
}
```

### Example 3: Creating and Using Sandbox

```bash
# Step 1: Create sandbox
SANDBOX_RESPONSE=$(curl -X POST http://localhost:5000/api/sandbox/create \
  -H "Content-Type: application/json" \
  -d '{
    "name": "automation-env",
    "shape": "beijing-2c-4g-cpu",
    "maxLifeSeconds": 7200,
    "authentication": {
      "api_key": "sk-lybic-key",
      "org_id": "org-123"
    }
  }')

SANDBOX_ID=$(echo $SANDBOX_RESPONSE | jq -r '.sandbox_id')

# Step 2: Use sandbox for task
curl -X POST http://localhost:5000/api/agent/run \
  -H "Content-Type: application/json" \
  -d '{
    "instruction": "Open browser and navigate to github.com",
    "sandbox_id": "$SANDBOX_ID",
    "authentication": {
      "api_key": "sk-lybic-key",
      "org_id": "org-123"
    },
    "ark_apikey": "ark-api-key"
  }'
```

### Example 4: Context Continuation

```bash
# First conversation turn
TASK_RESPONSE=$(curl -X POST http://localhost:5000/api/agent/task/submit \
  -H "Content-Type: application/json" \
  -d '{
    "instruction": "Open notepad",
    "sandbox_id": "box-abc123",
    "authentication": {
      "api_key": "sk-lybic-key",
      "org_id": "org-123"
    },
    "ark_apikey": "ark-api-key"
  }')

TASK_ID=$(echo $TASK_RESPONSE | jq -r '.task_id')

# Wait for completion
sleep 10

# Continue conversation
curl -X POST http://localhost:5000/api/agent/run \
  -H "Content-Type: application/json" \
  -d '{
    "instruction": "Type \"Hello, World!\" in the notepad",
    "sandbox_id": "sbx-abc123",
    "continue_context": true,
    "task_id": "$TASK_ID",
    "authentication": {
      "api_key": "sk-lybic-key",
      "org_id": "org-123"
    },
    "ark_apikey": "ark-api-key"
  }'
```

### Example 5: Python Client

```python
import requests
import json

class LybicAgentClient:
    def __init__(self, base_url="http://localhost:5000"):
        self.base_url = base_url
        
    def run_task(self, instruction, sandbox_id, auth, ark_key):
        """Stream task execution"""
        url = f"{self.base_url}/api/agent/run"
        payload = {
            "instruction": instruction,
            "sandbox_id": sandbox_id,
            "authentication": auth,
            "ark_apikey": ark_key
        }
        
        response = requests.post(url, json=payload, stream=True)
        
        for line in response.iter_lines():
            if line:
                decoded_line = line.decode('utf-8')
                if decoded_line.startswith('data: '):
                    data = json.loads(decoded_line[6:])
                    yield data
    
    def submit_task(self, instruction, sandbox_id, auth, ark_key):
        """Submit async task"""
        url = f"{self.base_url}/api/agent/task/submit"
        payload = {
            "instruction": instruction,
            "sandbox_id": sandbox_id,
            "authentication": auth,
            "ark_apikey": ark_key
        }
        
        response = requests.post(url, json=payload)
        return response.json()
    
    def get_status(self, task_id):
        """Get task status"""
        url = f"{self.base_url}/api/agent/task/status/{task_id}"
        response = requests.get(url)
        return response.json()

# Usage
client = LybicAgentClient()

auth = {
    "api_key": "sk-lybic-key",
    "org_id": "org-123"
}

# Stream execution
for event in client.run_task(
    "Open calculator",
    "box-123",
    auth,
    "ark-key"
):
    print(event)

# Async execution
result = client.submit_task(
    "Create file test.txt",
    "box-123",
    auth,
    "ark-key"
)
task_id = result['task_id']

# Poll status
status = client.get_status(task_id)
print(status)
```

---

## Architecture Design

### System Overview

```
┌─────────────────────────────────────────────────────────────┐
│                         Client Layer                         │
│  (Web UI / API Clients / CLI Tools / External Systems)      │
└──────────────────────────┬──────────────────────────────────┘
                           │ REST API / SSE
┌──────────────────────────▼──────────────────────────────────┐
│                      FastAPI Server                          │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  API Endpoints (main.py)                               │ │
│  │  /api/agent/run, /api/agent/task/submit, ...          │ │
│  └────────────────────────────────────────────────────────┘ │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│                     Agent Orchestration                      │
│  ┌────────────────┐  ┌────────────────┐  ┌──────────────┐  │
│  │   Planner      │  │  Chat Client   │  │   Storage    │  │
│  │  (LangGraph)   │  │  (UI-TARS)     │  │  (Memory/PG) │  │
│  └────────────────┘  └────────────────┘  └──────────────┘  │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│                    External Services                         │
│  ┌────────────────┐  ┌────────────────┐  ┌──────────────┐  │
│  │ Lybic Sandbox  │  │  Doubao ARK    │  │  PostgreSQL  │  │
│  │   (Runtime)    │  │   (UI-TARS)    │  │  (Optional)  │  │
│  └────────────────┘  └────────────────┘  └──────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

### Component Details

#### 1. FastAPI Server (`src/main.py`)

**Responsibilities:**
- HTTP request handling
- SSE streaming
- Task lifecycle management
- Authentication/authorization
- Error handling

**Key Features:**
- Async/await for high concurrency
- Thread-safe task tracking with `asyncio.Lock`
- Automatic context persistence every 5 steps
- Graceful task cancellation

#### 2. Planner (`src/planner.py`)

**Responsibilities:**
- Task execution orchestration
- LangGraph state machine management
- Tool invocation
- Step-by-step execution

**Execution Flow:**

```
1. Initialize with sandbox_id and model_client
2. Setup LangGraph workflow
3. Execute task steps iteratively
4. Yield progress updates
5. Handle errors and cancellations
6. Return final result
```

#### 3. Chat Client (`src/chat.py`)

**Responsibilities:**
- LLM API communication
- Message history management
- Context serialization/deserialization
- System prompt injection

**Features:**
- Async OpenAI client wrapper
- Context persistence support
- Streaming response handling
- Session management

#### 4. Storage Layer (`src/storage/`)

**Implementations:**

**Memory Storage:**
```python
class MemoryTaskStorage:
    def __init__(self):
        self.tasks = {}  # In-memory dictionary
    
    async def save_task(self, task_data):
        self.tasks[task_data.task_id] = task_data
    
    async def get_task(self, task_id):
        return self.tasks.get(task_id)
```

**PostgreSQL Storage:**
```python
class PostgresTaskStorage:
    def __init__(self, connection_string):
        self.pool = asyncpg.create_pool(connection_string)
    
    async def save_task(self, task_data):
        await self.pool.execute(
            "INSERT INTO tasks (...) VALUES (...)"
        )
```

### Execution Flow

#### Streaming Mode

```
1. Client sends POST /api/agent/run
   ↓
2. Server creates/validates sandbox
   ↓
3. Initialize model client and planner
   ↓
4. Setup SSE stream connection
   ↓
5. Execute planner.run_task()
   ↓
6. Stream events to client:
   - Thinking steps
   - Actions taken
   - Observations
   - Results
   ↓
7. Save context every 5 steps
   ↓
8. Finalize task and close stream
```

#### Async Mode

```
1. Client sends POST /api/agent/task/submit
   ↓
2. Server generates task_id
   ↓
3. Create task in storage (status: pending)
   ↓
4. Return task_id immediately
   ↓
5. Background: Execute task
   ↓
6. Update storage with progress
   ↓
7. Client polls GET /api/agent/task/status/{task_id}
   ↓
8. Return current status and results
```

### Context Management

Context persistence enables conversation continuity:

```python
# Save context
context = model_client.get_context_for_persistence()
await task_storage.save_llm_context(task_id, context)

# Restore context
task_data = await task_storage.get_task(task_id)
if task_data.llm_context:
    model_client.restore_context_from_persistence(
        task_data.llm_context
    )
```

**Context includes:**
- System prompt
- Conversation history
- User messages
- Assistant responses
- Tool calls and results

### Concurrency Model

```python
# Thread-safe task tracking
active_tasks = {}
active_tasks_lock = asyncio.Lock()

async def track_task(task_id, planner):
    async with active_tasks_lock:
        active_tasks[task_id] = planner

async def remove_task(task_id):
    async with active_tasks_lock:
        active_tasks.pop(task_id, None)
```

**Features:**
- Multiple concurrent tasks
- Safe task cancellation
- No race conditions
- Efficient resource cleanup

---

## Development Guide

### Project Structure

```
mini-agent/
├── src/
│   ├── main.py           # FastAPI application entry
│   ├── chat.py           # LLM client wrapper
│   ├── planner.py        # Agent execution logic
│   ├── dto.py            # Request/response models
│   ├── prompts.py        # System prompts
│   ├── storage/
│   │   ├── __init__.py   # Storage factory
│   │   ├── memory.py     # In-memory storage
│   │   └── postgres.py   # PostgreSQL storage
│   └── store/            # Additional utilities
├── playground/           # Vue.js frontend
│   ├── src/
│   ├── package.json
│   └── vite.config.ts
├── Dockerfile            # Container build
├── pyproject.toml        # Python dependencies
└── uv.lock               # Locked dependencies
```

### Setting Up Development Environment

```bash
# 1. Clone and setup
git clone git@github.com:lybic/mini-agent.git
cd mini-agent

# 2. Backend setup
python -m venv .venv
source .venv/bin/activate
pip install uv
uv sync

# 3. Frontend setup
cd playground
npm install

# 4. Configure environment
cp src/.env.example src/.env
# Edit src/.env with your credentials

# 5. Start development servers
# Terminal 1: Backend
python -m src.main

# Terminal 2: Frontend
cd playground && npm run dev
```

### Running Tests

```bash
# Backend tests (if available)
pytest

# Frontend tests
cd playground
npm run test

# Type checking
npm run type-check

# Linting
npm run lint
```

### Adding New Endpoints

```python
# In src/main.py

@app.post('/api/custom/endpoint')
async def custom_endpoint(req: CustomRequest):
    """Custom endpoint description"""
    try:
        # Your logic here
        return JSONResponse({
            'success': True,
            'data': result
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
```

### Extending Storage Backends

```python
# Create src/storage/custom.py

from .base import TaskStorage, TaskData

class CustomStorage(TaskStorage):
    async def save_task(self, task_data: TaskData):
        # Implementation
        pass
    
    async def get_task(self, task_id: str) -> TaskData:
        # Implementation
        pass

# Register in src/storage/__init__.py
```

### Debugging

```bash
# Enable debug logging
export LOG_LEVEL=DEBUG

# Run with debugger
python -m debugpy --listen 5678 -m src.main

# View logs
tail -f logs/agent.log
```

### Code Style

```bash
# Backend (Python)
black src/
isort src/
flake8 src/

# Frontend (TypeScript)
cd playground
npm run format
npm run lint
```

---

## Project Information

### Technology Stack

**Backend:**
- **FastAPI** 0.115+ - Modern web framework
- **LangGraph** 1.0.3+ - Agent orchestration
- **OpenAI** - LLM client library
- **Lybic SDK** 0.8+ - Sandbox management
- **asyncpg** - PostgreSQL async driver
- **Uvicorn** - ASGI server

**Frontend:**
- **Vue.js 3** - Progressive framework
- **TypeScript** - Type-safe JavaScript
- **Vite** - Build tool
- **Pinia** - State management
- **@lybic/ui** - UI components

**Infrastructure:**
- **Docker** - Containerization
- **PostgreSQL** - Optional persistence
- **Volcengine ARK** - LLM provider

### System Requirements

**Development:**
- Python 3.10+
- Node.js 22+
- 2GB RAM minimum
- 1GB disk space

**Production:**
- 2+ CPU cores
- 4GB+ RAM
- PostgreSQL 12+ (optional)
- Docker 20+ (recommended)

### Performance Characteristics

- **Concurrent Tasks**: 10-100 depending on resources
- **Context Save Interval**: Every 5 steps
- **Max Task Lifetime**: Configurable (default 50 steps)
- **SSE Latency**: <100ms typically
- **Sandbox Creation**: 1-3 seconds

### Limitations

- Single LLM model (UI-TARS) currently supported
- No built-in authentication (use reverse proxy)
- Memory storage not suitable for production
- Chinese system prompts by default

### Version History

- **0.1.0** (Current) - Initial release with core features

---

## Best Practice Example

This example demonstrates production-ready deployment with Docker and PostgreSQL.

### Complete Production Setup

#### 1. Docker Compose Configuration

Create `docker-compose.yml`:

```yaml
version: '3.8'

services:
  postgres:
    image: postgres:15-alpine
    container_name: lybic-postgres
    environment:
      POSTGRES_DB: agent_tasks
      POSTGRES_USER: agent_user
      POSTGRES_PASSWORD: secure_password_here
    volumes:
      - postgres_data:/var/lib/postgresql/data
    ports:
      - "5432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U agent_user"]
      interval: 10s
      timeout: 5s
      retries: 5
    networks:
      - lybic-network

  agent:
    build: .
    container_name: lybic-agent
    ports:
      - "5000:5000"
    environment:
      # Logging
      LOG_LEVEL: INFO
      
      # Storage configuration
      TASK_STORAGE_BACKEND: postgres
      POSTGRES_CONNECTION_STRING: postgresql://agent_user:secure_password_here@postgres:5432/agent_tasks
      
      # Optional: Default credentials (can be overridden per request)
      # LYBIC_API_KEY: sk-your-default-key
      # LYBIC_ORG_ID: your-default-org
      # ARK_API_KEY: your-default-ark-key
    depends_on:
      postgres:
        condition: service_healthy
    networks:
      - lybic-network
    restart: unless-stopped

volumes:
  postgres_data:

networks:
  lybic-network:
    driver: bridge
```

#### 2. Initialize Database

Create `init_db.sql`:

```sql
-- Create tasks table
CREATE TABLE IF NOT EXISTS tasks (
    task_id VARCHAR(255) PRIMARY KEY,
    status VARCHAR(50) NOT NULL,
    query TEXT NOT NULL,
    max_steps INTEGER DEFAULT 50,
    finished_output TEXT,
    final_state TEXT,
    llm_context JSONB,
    sandbox_info JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes
CREATE INDEX idx_tasks_status ON tasks(status);
CREATE INDEX idx_tasks_created_at ON tasks(created_at);

-- Create update trigger
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_tasks_updated_at 
    BEFORE UPDATE ON tasks
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();
```

#### 3. Start Services

```bash
# Start all services
docker-compose up -d

# Check logs
docker-compose logs -f agent

# Verify health
curl http://localhost:5000/api/health
```

#### 4. Client Example with API Keys in Requests

**Python Client:**

```python
import requests
import json
from typing import Generator, Dict

class ProductionLybicClient:
    def __init__(
        self,
        base_url: str = "http://localhost:5000",
        lybic_api_key: str = None,
        lybic_org_id: str = None,
        ark_api_key: str = None
    ):
        self.base_url = base_url
        self.lybic_auth = {
            "api_key": lybic_api_key,
            "org_id": lybic_org_id
        } if lybic_api_key and lybic_org_id else None
        self.ark_api_key = ark_api_key
    
    def create_sandbox(
        self,
        name: str = "production-sandbox",
        shape: str = "beijing-2c-4g-cpu",
        max_life_seconds: int = 7200
    ) -> Dict:
        """Create a new sandbox"""
        url = f"{self.base_url}/api/sandbox/create"
        payload = {
            "name": name,
            "shape": shape,
            "maxLifeSeconds": max_life_seconds,
            "authentication": self.lybic_auth
        }
        
        response = requests.post(url, json=payload)
        response.raise_for_status()
        return response.json()
    
    def run_task_stream(
        self,
        instruction: str,
        sandbox_id: str,
        continue_context: bool = False,
        task_id: str = None
    ) -> Generator[Dict, None, None]:
        """Stream task execution with real-time updates"""
        url = f"{self.base_url}/api/agent/run"
        payload = {
            "instruction": instruction,
            "sandbox_id": sandbox_id,
            "continue_context": continue_context,
            "authentication": self.lybic_auth,
            "ark_apikey": self.ark_api_key
        }
        
        if task_id:
            payload["task_id"] = task_id
        
        response = requests.post(url, json=payload, stream=True)
        response.raise_for_status()
        
        for line in response.iter_lines():
            if line:
                decoded_line = line.decode('utf-8')
                if decoded_line.startswith('data: '):
                    try:
                        data = json.loads(decoded_line[6:])
                        yield data
                    except json.JSONDecodeError:
                        continue
    
    def submit_task_async(
        self,
        instruction: str,
        sandbox_id: str,
        max_steps: int = 50
    ) -> Dict:
        """Submit task for async execution"""
        url = f"{self.base_url}/api/agent/task/submit"
        payload = {
            "instruction": instruction,
            "sandbox_id": sandbox_id,
            "max_steps": max_steps,
            "authentication": self.lybic_auth,
            "ark_apikey": self.ark_api_key
        }
        
        response = requests.post(url, json=payload)
        response.raise_for_status()
        return response.json()
    
    def get_task_status(self, task_id: str) -> Dict:
        """Get task status and results"""
        url = f"{self.base_url}/api/agent/task/status/{task_id}"
        response = requests.get(url)
        response.raise_for_status()
        return response.json()
    
    def cancel_task(self, task_id: str = None):
        """Cancel specific task or all tasks"""
        url = f"{self.base_url}/api/agent/cancel"
        payload = {"authentication": self.lybic_auth}
        
        if task_id:
            payload["task_id"] = task_id
        
        response = requests.post(url, json=payload)
        response.raise_for_status()
        return response.json()


# Usage Example
def main():
    # Initialize client with credentials
    client = ProductionLybicClient(
        base_url="http://localhost:5000",
        lybic_api_key="sk-your-lybic-api-key",
        lybic_org_id="your-lybic-org-id",
        ark_api_key="your-ark-api-key"
    )
    
    # Step 1: Create sandbox
    print("Creating sandbox...")
    sandbox_result = client.create_sandbox(
        name="automation-workspace",
        max_life_seconds=7200
    )
    sandbox_id = sandbox_result['sandbox_id']
    print(f"Sandbox created: {sandbox_id}")
    
    # Step 2: Execute task with streaming
    print("\nExecuting task (streaming)...")
    instruction = "Open browser and search for 'Python best practices'"
    
    for event in client.run_task_stream(instruction, sandbox_id):
        event_type = event.get('type', 'unknown')
        content = event.get('content', '')
        print(f"[{event_type}] {content}")
        
        if event_type == 'finished':
            print(f"\nTask completed: {event.get('output')}")
            break
    
    # Step 3: Continue conversation (context continuation)
    print("\nContinuing conversation...")
    follow_up = "Now click on the first result"
    
    task_result = client.submit_task_async(follow_up, sandbox_id)
    task_id = task_result['task_id']
    print(f"Follow-up task submitted: {task_id}")
    
    # Step 4: Poll for completion
    import time
    while True:
        status = client.get_task_status(task_id)
        print(f"Status: {status['status']}")
        
        if status['status'] in ['finished', 'error', 'cancelled']:
            print(f"Final output: {status.get('finished_output')}")
            break
        
        time.sleep(2)
    
    print("\nAll tasks completed!")


if __name__ == "__main__":
    main()
```

#### 5. cURL Examples

```bash
# Set credentials
LYBIC_API_KEY="sk-your-lybic-api-key"
LYBIC_ORG_ID="your-lybic-org-id"
ARK_API_KEY="your-ark-api-key"

# Create sandbox
SANDBOX_RESPONSE=$(curl -s -X POST http://localhost:5000/api/sandbox/create \
  -H "Content-Type: application/json" \
  -d '{
    "name": "production-sandbox",
    "shape": "beijing-2c-4g-cpu",
    "maxLifeSeconds": 7200,
    "authentication": {
      "api_key": "$LYBIC_API_KEY",
      "org_id": "$LYBIC_ORG_ID"
    }
  }')

SANDBOX_ID=$(echo $SANDBOX_RESPONSE | jq -r '.sandbox_id')
echo "Sandbox ID: $SANDBOX_ID"

# Execute task with streaming
curl -X POST http://localhost:5000/api/agent/run \
  -H "Content-Type: application/json" \
  -d '{
    "instruction": "Open calculator and compute 2+2",
    "sandbox_id": "$SANDBOX_ID",
    "authentication": {
      "api_key": "$LYBIC_API_KEY",
      "org_id": "$LYBIC_ORG_ID"
    },
    "ark_apikey": "$ARK_API_KEY"
  }'

# Submit async task
TASK_RESPONSE=$(curl -s -X POST http://localhost:5000/api/agent/task/submit \
  -H "Content-Type: application/json" \
  -d '{
    "instruction": "Create a file named test.txt",
    "sandbox_id": "$SANDBOX_ID",
    "max_steps": 30,
    "authentication": {
      "api_key": "$LYBIC_API_KEY",
      "org_id": "$LYBIC_ORG_ID"
    },
    "ark_apikey": "$ARK_API_KEY"
  }')

TASK_ID=$(echo $TASK_RESPONSE | jq -r '.task_id')
echo "Task ID: $TASK_ID"

# Poll status
while true; do
  STATUS=$(curl -s http://localhost:5000/api/agent/task/status/$TASK_ID)
  TASK_STATUS=$(echo $STATUS | jq -r '.status')
  echo "Status: $TASK_STATUS"
  
  if [ "$TASK_STATUS" = "finished" ] || [ "$TASK_STATUS" = "error" ]; then
    echo $STATUS | jq '.'
    break
  fi
  
  sleep 2
done
```

#### 6. Monitoring and Maintenance

```bash
# View logs
docker-compose logs -f agent
docker-compose logs -f postgres

# Database health
docker-compose exec postgres psql -U agent_user -d agent_tasks -c "SELECT COUNT(*) FROM tasks;"

# Backup database
docker-compose exec postgres pg_dump -U agent_user agent_tasks > backup.sql

# Restart services
docker-compose restart agent

# Stop services
docker-compose down

# Clean up (including data)
docker-compose down -v
```

#### 7. Production Checklist

- ✅ Use PostgreSQL for persistence
- ✅ Pass API keys in requests (not environment variables)
- ✅ Implement proper error handling
- ✅ Set up database backups
- ✅ Monitor disk usage (logs, database)
- ✅ Configure resource limits in docker-compose
- ✅ Use HTTPS reverse proxy (nginx/caddy)
- ✅ Implement rate limiting
- ✅ Set up log rotation
- ✅ Monitor task execution metrics
- Add an authorization verification middleware before the apiserver.(Optional)

### Benefits of This Approach

1. **Security**: API keys not stored in environment variables
2. **Scalability**: PostgreSQL supports multiple agent instances
3. **Reliability**: Data persists across restarts
4. **Flexibility**: Different credentials per request
5. **Maintainability**: Easy to backup and monitor
6. **Production-ready**: Proper health checks and restarts

---

## Troubleshooting

### Common Issues

**Problem**: Connection refused to Lybic API
```bash
# Solution: Check credentials and network
curl https://api.lybic.cn/health
# Verify LYBIC_API_KEY and LYBIC_ORG_ID
```

**Problem**: PostgreSQL connection fails
```bash
# Solution: Check connection string
docker-compose exec postgres psql -U agent_user -d agent_tasks
# Verify POSTGRES_CONNECTION_STRING
```

**Problem**: Task stuck in 'running' state
```bash
# Solution: Cancel and retry
curl -X POST http://localhost:5000/api/agent/cancel \
  -d '{"task_id": "stuck-task-id"}'
```

**Problem**: High memory usage
```bash
# Solution: Limit concurrent tasks
# Add to docker-compose.yml:
    deploy:
      resources:
        limits:
          memory: 2G
```

---

## Additional Resources

- [Lybic Platform Documentation](https://lybic.ai/docs)
- [Doubao UI-TARS Model](https://www.volcengine.com/docs/82379/1263279)
- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [LangGraph Documentation](https://langchain-ai.github.io/langgraph/)

---

**Last Updated**: 14/11/2025 18:09 GMT +8
**Version**: 0.1.0
