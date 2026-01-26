# Kwami AI LiveKit

LiveKit token endpoint and cloud agent for Kwami AI.

## Quick Start

```bash
# Copy and configure environment
cp .env.sample .env
# Edit .env with your credentials

# Run API server (token endpoint)
make api-install
make api

# Run agent locally (in another terminal)
make agent-install
make agent
```

## Project Structure

```
kwami-ai-lk/
├── api/                  # Token endpoint API (deploy anywhere)
│   ├── main.py           # FastAPI entry point
│   ├── config.py         # Settings
│   ├── token_utils.py    # Token generation
│   ├── routes/           # API endpoints
│   ├── pyproject.toml
│   └── Dockerfile
├── agent/                # LiveKit Cloud agent
│   ├── agent.py          # Agent entry point
│   ├── config.py         # Kwami configuration
│   ├── plugins.py        # STT/LLM/TTS factories
│   ├── memory.py         # Zep Cloud memory integration
│   ├── pyproject.toml
│   └── livekit.toml      # LiveKit Cloud config
├── .env                  # Shared credentials
├── Makefile
└── README.md
```

## Persistent Memory

Each Kwami agent can have independent, persistent memory powered by [Zep Cloud](https://www.getzep.com/). This enables:

- **Conversation history** - Remember all past conversations
- **Fact extraction** - Automatically extract and store facts about users
- **Temporal knowledge graphs** - Track how facts change over time
- **Sub-200ms retrieval** - Fast context retrieval for real-time voice

### Setup

1. Create a Zep Cloud account at https://www.getzep.com/
2. Get your API key from the dashboard
3. Add `ZEP_API_KEY` to your `.env` file

### How it works

- Each Kwami uses its `kwami_id` as a unique user identifier in Zep
- Conversations are automatically tracked and stored
- Memory context is injected into the system prompt
- The agent can use `remember_fact` and `recall_memories` tools

### Configuration

Memory can be configured in `config.py`:

```python
@dataclass
class KwamiMemoryConfig:
    enabled: bool = True                    # Enable/disable memory
    api_key: str = ""                       # Zep API key (or ZEP_API_KEY env var)
    user_id: str = ""                       # Override user ID
    session_id: str = ""                    # Override session ID
    auto_inject_context: bool = True        # Inject memory into system prompt
    max_context_messages: int = 10          # Recent messages in context
    include_facts: bool = True              # Include extracted facts
    include_entities: bool = True           # Include entities
    min_fact_relevance: float = 0.5         # Minimum fact relevance score
```

## Commands

| Command | Description |
|---------|-------------|
| `make api-install` | Install API dependencies |
| `make api` | Run token API locally (http://localhost:8080) |
| `make agent-install` | Install agent dependencies |
| `make agent` | Run agent locally for testing |
| `make agent-deploy` | Deploy agent to LiveKit Cloud |
| `make lint` | Run linter on both projects |
| `make format` | Format code in both projects |

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `GET /` | GET | API info |
| `GET /health` | GET | Health check |
| `POST /token` | POST | Generate LiveKit token |
| `GET /token` | GET | Generate token (simple) |
| `GET /docs` | GET | OpenAPI documentation |

### Token Request

```bash
curl -X POST http://localhost:8080/token \
  -H "Content-Type: application/json" \
  -d '{
    "room_name": "my-room",
    "participant_name": "user-123"
  }'
```

## Deployment

### API (Token Endpoint)

Deploy the `api/` folder to any hosting provider:

```bash
# Docker
make docker-build
make docker-up

# Or deploy to Railway, Fly.io, Render, etc.
```

### Agent (LiveKit Cloud)

Deploy the agent to LiveKit Cloud:

```bash
cd agent

# Configure your LiveKit Cloud project
lk agent config

# Deploy to LiveKit Cloud
lk agent deploy
```

LiveKit Cloud handles scaling, lifecycle, and hosting automatically.

## Environment Variables

Create a `.env` file in the project root:

```env
# LiveKit (required)
LIVEKIT_URL=wss://your-project.livekit.cloud
LIVEKIT_API_KEY=your-api-key
LIVEKIT_API_SECRET=your-api-secret

# AI Providers (required for agent)
OPENAI_API_KEY=your-openai-key
DEEPGRAM_API_KEY=your-deepgram-key
CARTESIA_API_KEY=your-cartesia-key

# Memory - Zep Cloud (optional, enables persistent memory)
ZEP_API_KEY=your-zep-api-key

# API Config (optional)
APP_ENV=development
DEBUG=true
API_PORT=8080
CORS_ORIGINS=http://localhost:3000,http://localhost:5173
```

## License

Apache 2.0
