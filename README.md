# Kwami AI LiveKit

LiveKit token endpoint and agent server for Kwami AI.

## Quick Start

```bash
# Install dependencies
make install

# Copy and configure environment
cp env.template .env
# Edit .env with your credentials

# Run API server (token endpoint)
make api

# Run agent worker (in another terminal)
make agent
```

## Services

| Service | Command | Port | Description |
|---------|---------|------|-------------|
| API | `make api` | 8080 | Token endpoint + health checks |
| Agent | `make agent` | - | LiveKit voice agent worker |

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

## Development

```bash
# Install with dev dependencies
make dev

# Run linter
make lint

# Format code
make format

# Run tests
make test
```

## Docker

```bash
# Build images
make docker-build

# Start services
make docker-up

# Stop services
make docker-down
```

## Project Structure

```
kwami-ai-lk/
├── src/kwami_lk/
│   ├── api/           # FastAPI application
│   │   ├── main.py    # App entry point
│   │   └── routes/    # API endpoints
│   ├── agent/         # LiveKit agent
│   │   ├── kwami_agent.py
│   │   ├── config.py
│   │   ├── worker.py
│   │   └── plugins/   # STT/LLM/TTS factories
│   └── core/          # Shared utilities
│       ├── config.py  # Settings
│       └── livekit.py # Token generation
├── tests/
├── Dockerfile
├── docker-compose.yml
└── pyproject.toml
```

## Environment Variables

See `env.template` for all available options.

Required:
- `LIVEKIT_URL` - LiveKit server URL
- `LIVEKIT_API_KEY` - LiveKit API key
- `LIVEKIT_API_SECRET` - LiveKit API secret
- `OPENAI_API_KEY` - OpenAI API key (for LLM)
- `DEEPGRAM_API_KEY` - Deepgram API key (for STT)
- `CARTESIA_API_KEY` - Cartesia API key (for TTS)

## License

MIT
