# Kwami AI Agents

LiveKit Cloud agents for Kwami AI voice interactions.

## Quick Start

```bash
# Copy and configure environment
cp .env.sample .env
# Edit .env with your credentials

# Install dependencies
make install

# Run agent locally for development
make dev
```

## Project Structure

```
kwami-ai-agents/
├── agent/                # LiveKit Cloud agent (pg agent)
│   ├── agent/            # Agent module
│   │   ├── main.py       # Entry point
│   │   ├── core.py       # Core agent logic
│   │   ├── config.py     # Kwami configuration
│   │   ├── memory.py     # Zep Cloud memory integration
│   │   ├── tools.py      # Agent tools
│   │   ├── client_tools.py # Client-side tools
│   │   └── factories/    # STT/LLM/TTS/VAD factories
│   ├── livekit.toml      # LiveKit Cloud config
│   ├── pyproject.toml
│   └── Dockerfile
├── .env                  # Agent credentials
├── Makefile
└── README.md
```

## Multiple Agents (Future)

The structure supports multiple agents for different apps or tasks:

```
kwami-ai-agents/
├── agents/
│   ├── pg/               # Playground agent
│   ├── assistant/        # General assistant
│   └── support/          # Customer support agent
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

## Commands

| Command | Description |
|---------|-------------|
| `make install` | Install agent dependencies |
| `make dev` | Run agent locally for testing |
| `make deploy` | Deploy agent to LiveKit Cloud |
| `make lint` | Run linter |
| `make format` | Format code |

## Deployment

Deploy the agent to LiveKit Cloud:

```bash
# Configure your LiveKit Cloud project
cd agent
lk agent config

# Deploy to LiveKit Cloud
lk agent deploy

# Or use make
make deploy
```

LiveKit Cloud handles scaling, lifecycle, and hosting automatically.

## Environment Variables

Create a `.env` file in the project root:

```env
# LiveKit (required)
LIVEKIT_URL=wss://your-project.livekit.cloud
LIVEKIT_API_KEY=your-api-key
LIVEKIT_API_SECRET=your-api-secret

# AI Providers (required)
OPENAI_API_KEY=your-openai-key
DEEPGRAM_API_KEY=your-deepgram-key
CARTESIA_API_KEY=your-cartesia-key

# Memory - Zep Cloud (optional, enables persistent memory)
ZEP_API_KEY=your-zep-api-key
```

## Related Repositories

- **[kwami-ai-api](https://github.com/alexcolls/kwami-ai-api)** - Token endpoint and memory API
- **[kwami-ai](https://github.com/alexcolls/kwami-ai)** - TypeScript SDK
- **[kwami-ai-pg](https://github.com/alexcolls/kwami-ai-pg)** - Playground Vue app

## License

Apache 2.0
