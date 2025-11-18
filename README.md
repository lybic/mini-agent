# Lybic GUI Agent

A minimal administrative Lybic agent instance that provides RESTful APIs for AI-powered task automation using the UI-TARS model.

[![License](https://img.shields.io/badge/license-apache-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/fastapi-0.115+-green.svg)](https://fastapi.tiangolo.com/)

## 🌟 Features

- **RESTful API** - FastAPI-based server with comprehensive REST endpoints
- **UI-TARS Model** - Powered by Doubao's UI-TARS model for intelligent task automation
- **Streaming Execution** - Real-time task execution with Server-Sent Events (SSE)
- **Task Management** - Async task submission, status tracking, and cancellation
- **Context Persistence** - Conversation continuity with PostgreSQL or in-memory storage
- **Sandbox Integration** - Seamless Lybic sandbox creation and management
- **Web Playground** - Vue.js + TypeScript testing interface

## 📦 Architecture

```
lybic-guiagent/
├── src/                    # Backend API server
│   ├── main.py            # FastAPI application & endpoints
│   ├── chat.py            # AsyncChatModelClient wrapper
│   ├── planner.py         # LangGraph-based agent planner
│   ├── dto.py             # Data transfer objects
│   ├── prompts.py         # System prompts for UI-TARS
│   ├── storage/           # Task persistence backends
│   └── store/             # Storage utilities
├── playground/            # Vue.js frontend for testing
├── Dockerfile             # Multi-stage container build
└── pyproject.toml         # Python project configuration
```

### Core Components

- **Backend API Server** - FastAPI-based Python server with agent orchestration
- **Frontend Playground** - Vue.js + TypeScript interface for testing
- **Agent Core** - LangGraph-based planner with OpenAI/Doubao API integration
- **Storage Layer** - In-memory or PostgreSQL persistence for task contexts

## 🚀 Quick Start

### Prerequisites

- Python 3.10+
- Docker (optional, for containerized deployment)
- Node.js 20+ (for frontend development)

### Installation

#### 1. Using Python Virtual Environment

```bash
# Clone the repository
git clone git@github.com:lybic/mini-agent.git
cd mini-agent

# Create and activate virtual environment
uv install virtualenv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies with uv
pip install uv
uv sync

# Configure environment variables
cp src/.env.example src/.env
# Edit src/.env with your API keys
```

#### 2. Using Docker

```bash
# Build the image
docker build -t lybic-guiagent .

# Run the container
docker run -p 5000:5000 \
  -e ARK_API_KEY=your-ark-api-key \
  -e LYBIC_API_KEY=your-lybic-api-key \
  -e LYBIC_ORG_ID=your-lybic-org-id \
  lybic-guiagent
```

### Running the Server

```bash
# Start the API server
python -m src.main

# Or use the installed script
lybic-guiagent

# Server will be available at http://localhost:5000
```

### Testing with Playground

```bash
# Navigate to playground directory
cd playground/

# Install dependencies
npm install

# Start development server
npm run dev

# Access at http://localhost:5173
```

## 📚 API Endpoints

### Core Endpoints

- **`GET /api/health`** - Health check endpoint
- **`POST /api/agent/run`** - Stream agent execution with SSE
- **`POST /api/agent/task/submit`** - Submit async task and get task_id
- **`GET /api/agent/task/status/{task_id}`** - Query task status and results
- **`POST /api/agent/cancel`** - Cancel running tasks
- **`POST /api/sandbox/create`** - Create Lybic sandbox for task execution

### Quick API Example

```bash
# Health check
curl http://localhost:5000/api/health

# Stream agent execution
curl -X POST http://localhost:5000/api/agent/run \
  -H "Content-Type: application/json" \
  -d '{
    "instruction": "Open a browser and navigate to google.com",
    "sandbox_id": "your-sandbox-id",
    "authentication": {
      "api_key": "your-lybic-api-key",
      "org_id": "your-lybic-org-id"
    },
    "ark_apikey": "your-ark-api-key"
  }'
```

## ⚙️ Configuration

### Environment Variables

Create a `src/.env` file with the following variables:

```bash
# Logging
LOG_LEVEL=INFO

# Lybic Platform Credentials
LYBIC_API_KEY=sk-your-lybic-api-key
LYBIC_ORG_ID=your-lybic-org-id
LYBIC_API_ENDPOINT=https://api.lybic.cn

# Doubao LLM API Key
ARK_API_KEY=your-ark-api-key
ARK_API_ENDPOINT=https://ark.cn-beijing.volces.com/api/v3

# Task Storage Configuration
TASK_STORAGE_BACKEND=memory  # or 'postgres'

# PostgreSQL (only if TASK_STORAGE_BACKEND=postgres)
POSTGRES_CONNECTION_STRING=postgresql://user:password@localhost:5432/agent_tasks
```

### Model Configuration

- **Model**: `doubao-1-5-ui-tars-250428` (Volcengine ARK API)
- **Thinking Type**: Disabled for optimal UI task performance
- **System Prompt**: Defined in `src/prompts.py`

## 🐳 Docker Deployment

### Production Deployment with PostgreSQL

```bash
# 1. Start PostgreSQL
docker run -d \
  --name postgres \
  -e POSTGRES_PASSWORD=your-password \
  -e POSTGRES_DB=agent_tasks \
  -p 5432:5432 \
  postgres:15

# 2. Build and run the agent
docker build -t lybic-guiagent .

docker run -d \
  --name lybic-agent \
  -p 5000:5000 \
  -e TASK_STORAGE_BACKEND=postgres \
  -e POSTGRES_CONNECTION_STRING=postgresql://postgres:your-password@postgres:5432/agent_tasks \
  --link postgres:postgres \
  lybic-guiagent
```

## 📖 Documentation

For detailed documentation, see:
- **[User Manual](User_Manual.md)** - Complete guide with examples
- **[API Reference](openapi.json)** - OpenAPI specification
- **[CLAUDE.md](CLAUDE.md)** - Development guidelines

## 🛠️ Development

### Backend Development

```bash
# Install dependencies
uv sync

# Run server in development mode
python -m src.main

# The server will reload on code changes
```

### Frontend Development

```bash
cd playground/

# Install dependencies
npm install

# Development server
npm run dev

# Type checking
npm run type-check

# Linting and formatting
npm run lint
npm run format

# Build for production
npm run build
```

## 🧪 Testing

The playground serves as the primary testing interface:

1. Start backend server: `python -m src.main`
2. Start frontend: `cd playground && npm run dev`
3. Access web interface to test agent capabilities
4. Monitor agent execution via real-time streaming

## 🤝 Contributing

Contributions are welcome! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🔗 Related Projects

- [Lybic Platform](https://lybic.cn) - Cloud sandbox environment
- [UI-TARS](https://www.volcengine.com/docs/82379/1263279) - Doubao's UI task automation model

## 📞 Support

For issues and questions:
- Open an issue on GitHub
- Check existing documentation
- Review the User Manual for detailed examples

## 🎯 Roadmap

- [ ] Support for additional LLM models
- [ ] Enhanced error handling and retry mechanisms
- [ ] Web UI improvements
- [ ] API rate limiting and authentication
- [ ] Metrics and monitoring integration
