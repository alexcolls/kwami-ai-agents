.PHONY: help install dev deploy lint format clean

help:
	@echo "Kwami AI Agents - Development Commands"
	@echo ""
	@echo "Agent Commands:"
	@echo "  make install       - Install agent dependencies"
	@echo "  make dev           - Run agent locally (dev mode)"
	@echo "  make deploy        - Deploy agent to LiveKit Cloud"
	@echo ""
	@echo "Code Quality:"
	@echo "  make lint          - Run linter"
	@echo "  make format        - Format code"
	@echo ""
	@echo "Cleanup:"
	@echo "  make clean         - Remove caches and virtual envs"

# =============================================================================
# Agent
# =============================================================================

install:
	cd agent && uv sync

dev:
	cd agent && uv run python -m agent.main dev

create:
	cd agent && lk agent create .

deploy:
	cd agent && lk agent deploy

# =============================================================================
# Code Quality
# =============================================================================

lint:
	cd agent && uv run ruff check .

format:
	cd agent && uv run ruff format . && uv run ruff check --fix .

# =============================================================================
# Cleanup
# =============================================================================

clean:
	rm -rf agent/.venv agent/__pycache__ agent/**/__pycache__
	rm -rf .pytest_cache .ruff_cache
