# Telegram Bot Guide

## Overview
The Telegram bot lets you interact with your vault from anywhere.

## Setup
1. Create a bot with @BotFather and get the token
2. Set the token in your `.env` file as `TELEGRAM_BOT_TOKEN`
3. Run:
   ```sh
   python -m mnemosyne.frontends.telegram
   ```

## Usage
- Send questions or commands to your bot
- Get answers, search, and manage notes

## Security
- Your vault never leaves your machine
- Only the bot owner can access the vault
