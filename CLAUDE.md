# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is the **Lybic GUI Agent** - a minimal administrative Lybic agent instance that provides RESTful APIs for AI-powered task automation using the UI-TARS model. The project consists of:

- **Backend API Server** (`src/`) - FastAPI-based Python server with agent orchestration
- **Frontend Playground** (`playground/`) - Vue.js + TypeScript interface for testing
- **Agent Core** - LangGraph-based planner with OpenAI/Doubao API integration

## Common Development Commands

### Backend Development
```bash
# Setup Python environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
uv sync

# Run the API server
python -m src.main

# Alternative using the installed script
lybic-guiagent
```

### Frontend Development (playground/)
```bash
cd playground/
npm install

# Development server
npm run dev

# Build for production
npm run build

# Type checking
npm run type-check

# Linting and formatting
npm run lint
npm run format
```

### Docker Operations
```bash
# Build the Docker image
docker build -t lybic-guiagent .

# Run with Docker
docker run -p 5000:5000 lybic-guiagent
```

## Architecture

### Backend Structure (`src/`)
- `main.py` - FastAPI application with REST endpoints for agent operations
- `chat.py` - `AsyncChatModelClient` wrapper for OpenAI/Doubao API integration
- `planner.py` - Core agent planner using LangGraph for task execution
- `dto.py` - Data transfer objects for API requests/responses
- `prompts.py` - System prompts for the UI-TARS model
- `storage/` - Task persistence backends (memory or PostgreSQL)
- `store/` - Additional storage utilities

### Key API Endpoints
- `POST /api/agent/run` - Stream agent execution with Server-Sent Events
- `POST /api/agent/task/submit` - Submit async task and get task_id
- `GET /api/agent/task/status/{task_id}` - Query task status and results
- `POST /api/sandbox/create` - Create Lybic sandbox for task execution
- `POST /api/agent/cancel` - Cancel running tasks

### Agent Execution Flow
1. Client submits task instruction via API
2. System creates sandbox environment (if needed)
3. Planner initializes with UI-TARS model client
4. Agent executes steps using LangGraph state machine
5. Context is periodically saved to storage for conversation continuity
6. Results streamed back via SSE or stored for async retrieval

### Frontend Structure (`playground/`)
- Vue.js 3 + TypeScript application
- Uses `@lybic/ui` component library
- Pinia for state management
- Vite for development tooling
- Communicates with backend API via axios

## Configuration

### Environment Variables
Backend uses `.env` file (see `src/.env.example`):
- `ARK_API_KEY` - Doubao API key for UI-TARS model
- `LYBIC_API_KEY`, `LYBIC_ORG_ID` - Lybic platform credentials
- `TASK_STORAGE_BACKEND` - "memory" (default) or "postgres"
- `LOG_LEVEL` - Logging verbosity

Frontend environment (see `playground/.env.example`):
- `VITE_LYBIC_API_KEY`, `VITE_LYBIC_ORG_ID` - Lybic credentials for frontend
- `VITE_USE_HTTPS` - Enable HTTPS for LAN access

### Model Configuration
- Default model: `doubao-1-5-ui-tars-250428` via Volcengine ARK API
- System prompt defined in `prompts.py` (`DOUBAO_UI_TARS_SYSTEM_PROMPT_ZH`)
- Thinking type: disabled for optimal UI task performance

## Development Notes

### Task Context Management
- Agent contexts are automatically saved every 5 steps during execution
- Supports conversation continuation via `continue_context` parameter
- LLM conversation state persisted using `model_client.get_context_for_persistence()`

### Concurrency and Safety
- Thread-safe task management using `asyncio.Lock`
- Active tasks tracked in global `active_tasks` dictionary
- Task cancellation supported via `planner.cancelled` flag

### Storage Options
- **Memory storage** - Default, suitable for development
- **PostgreSQL storage** - For production persistence (requires connection string)

### OpenAPI Specification
- Auto-generated OpenAPI spec available at `openapi.json`
- Schema generated from FastAPI endpoints and Pydantic models

## Testing

The playground serves as the primary testing interface:
1. Start backend server (`python -m src.main`)
2. Start frontend (`cd playground && npm run dev`)
3. Access web interface to test agent capabilities
4. Monitor agent execution via real-time streaming

## Deployment

The application is containerized with multi-stage Docker builds:
- **Base stage** - Python environment setup
- **Builder stage** - Dependency installation and package building
- **Final stage** - Lean runtime image exposing port 5000

Default sandbox configuration: `beijing-2c-4g-cpu` shape with Windows OS.
