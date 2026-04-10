# Developer Guide

## Architecture Overview
- **Frontends:** CLI, TUI, Telegram bot (modular)
- **Backends:** Ollama (LLM), Qdrant (vector search)
- **Core:** Handles note parsing, embeddings, and search

## Setting Up for Development
1. Fork and clone the repo
2. Install dependencies: `pip install -e .`
3. Start Ollama and Qdrant: `docker-compose up -d`
4. Run tests: `pytest`

## Code Style
- Follows PEP8
- Use type hints
- Write docstrings for public functions

## Contributing
- Open a PR with a clear description
- Add/modify tests for your changes
- Follow code review feedback
