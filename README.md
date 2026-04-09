# Mnemosyne

A local-first Obsidian vault assistant with CLI, TUI, and Telegram bot interfaces. All AI runs locally via Ollama. No cloud, no accounts, no lock-in.

## Features
- Natural language Q&A over your vault
- Keyword and semantic search
- Note creation and editing
- Related note discovery
- TUI chat interface
- Telegram bot integration

## Quickstart
1. Clone this repo
2. Copy `.env.example` to `.env` and edit paths
3. Run `docker-compose up` to start Ollama and Qdrant
4. Run `python -m mnemosyne.frontends.cli --help`

## License
MIT
