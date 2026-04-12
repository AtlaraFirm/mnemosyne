---
tags:
- ask
- body
- bot
- cache
- check
- cli
- contributors
- copyright
- developer
- guide
- https
- import
- markdown-it
- markdown-it-container
- markdown-it-deflist
- markdown-it-texmath
- mnemosyne
- path
- plantitle
- provided
- pytest
- qdrant
- readme
- software
- splitmix64
- telegram
- tui
- vigna
---

# CLI Guide

## Overview
The CLI lets you interact with your Obsidian vault using natural language and commands.

## Commands
- `ask <question>`: Ask questions about your notes
- `search <keywords>`: Search notes by keyword
- `new <title>`: Create a new note
- `edit <note>`: Edit an existing note
- `related <note>`: Find related notes

## Examples
```sh
python -m mnemosyne.frontends.cli ask "What are my project goals?"
python -m mnemosyne.frontends.cli search "meeting notes"
```

## Help
Run `python -m mnemosyne.frontends.cli --help` for all options.