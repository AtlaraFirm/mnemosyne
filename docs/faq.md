---
tags:
- body
- check
- plantitle
- qdrant
---

# FAQ & Troubleshooting

## Why is Ollama not starting?
- Make sure Docker is running.
- Check `docker-compose logs ollama` for errors.

## Qdrant connection issues?
- Ensure Qdrant is running (`docker-compose ps`).
- Check `.env` for correct Qdrant URL.

## CLI/TUI not finding vault?
- Set the correct VAULT_PATH in `.env`.
- Check file permissions.

## Telegram bot not responding?
- Double-check your bot token in `.env`.
- Make sure your server has internet access.

## Still stuck?
- See [docs/README.md](README.md) or open an issue on GitHub.