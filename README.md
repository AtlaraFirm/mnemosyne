---
tags:
- body
- mnemosyne
- plantitle
- tui
---

# Mnemosyne

A local-first Obsidian vault assistant with CLI, TUI, and Telegram bot interfaces. All AI runs locally via Ollama. No cloud, no accounts, no lock-in.

---

## Table of Contents
- [Features](#features)
- [Installation](#installation)
- [Configuration](#configuration)
- [Usage](#usage)
  - [CLI](#cli)
  - [TUI](#tui)
  - [Telegram Bot](#telegram-bot)
- [Troubleshooting & FAQ](#troubleshooting--faq)
- [Architecture](#architecture)
- [Contributing](#contributing)
- [License](#license)

---

## Features
- Natural language Q&A over your vault
- Keyword and semantic search
- Note creation and editing
- Related note discovery
- TUI chat interface
- Telegram bot integration
- Local AI (Ollama) and vector search (Qdrant)

## Installation

### Prerequisites
- Python 3.9+
- Docker (for Ollama and Qdrant)
- Git

### Steps
1. Clone this repo:
   ```sh
   git clone https://github.com/your-org/mnemosyne.git
   cd mnemosyne
   ```
2. Copy `.env.example` to `.env` and edit paths as needed.
3. Start Ollama and Qdrant:
   ```sh
   docker-compose up -d
   ```
4. Install Python dependencies:
   ```sh
   pip install -e .
   ```

### Database Setup
The database schema is created automatically on first run—no manual migration is needed. If you encounter errors about missing tables, ensure you are running the latest version and have started the app at least once via the CLI or TUI.

## Configuration

- Edit `.env` to set your Obsidian vault path and other options.
- See [docs/README.md](docs/README.md) for all config options.

## Usage

### CLI
Run:
```sh
python -m mnemosyne.frontends.cli --help
```

### TUI
Run:
```sh
python -m mnemosyne.frontends.tui
```

### Telegram Bot
1. Set your Telegram bot token in `.env`.
2. Run:
   ```sh
   python -m mnemosyne.frontends.telegram
   ```

## Troubleshooting & FAQ
See [docs/faq.md](docs/faq.md) for common issues and solutions.

## Architecture
- Local-first: All AI runs on your machine
- Ollama: LLM inference
- Qdrant: Vector search
- Modular frontends: CLI, TUI, Telegram
- Extensible: Add new frontends or backends easily

## Contributing
See [docs/development.md](docs/development.md) for developer setup, code style, and contribution guidelines.

## License
MIT