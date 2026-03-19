# Telegram AI Chat Bot (aiogram)

Telegram bot that replies when mentioned or when users reply to the bot. It sends the full reply chain as context to an OpenAI-compatible API and supports group allow-listing, private chat toggle, and rate limits via config.

## Features

- Reply triggers: @mention or replying to the bot in groups; all messages in DMs (optional)
- Context: entire reply chain up to `context.max_reply_chain`
- OpenAI-compatible API endpoint (supports `/v1` or full `/chat/completions` URLs)
- Group allow-listing with `allow_all_groups` and `allowed_group_ids`
- Per-user and per-chat rate limiting
- Typing indicator while the AI response is generated

## Requirements

- Python 3.10+
- A Telegram bot token (from BotFather)
- An OpenAI-compatible API key and base URL

## Quick start (local)

1. Create and activate a venv:

```bash
python -m venv .venv
source .venv/bin/activate
```

2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Create your config:

```bash
cp config.example.yaml config.yaml
```

4. Edit `config.yaml` with your bot token and AI API settings.

5. Run the bot:

```bash
python main.py
```

## Docker

1. Copy config:

```bash
cp config.example.yaml config.yaml
```

2. Build the image:

```bash
docker build -t telegram-ai-bot .
```

3. Run the container:

```bash
docker run --rm -v "$(pwd)/config.yaml:/app/config.yaml" telegram-ai-bot
```

## Docker Compose

1. Copy config:

```bash
cp config.example.yaml config.yaml
```

2. Start the service:

```bash
docker compose up -d --build
```

## Configuration

All settings live in `config.yaml`.

### Telegram

- `telegram.bot_token`: Telegram bot token
- `telegram.allow_private_chats`: allow responding in DMs
- `telegram.allow_all_groups`: respond in all groups
- `telegram.allowed_group_ids`: list of group IDs to allow if `allow_all_groups` is false

### AI API

- `ai.base_url`: API base URL (e.g. `https://api.openai.com`, `https://api.groq.com/openai/v1`)
- `ai.api_key`: API key
- `ai.model`: model name
- `ai.temperature`: sampling temperature
- `ai.max_tokens`: response max tokens
- `ai.timeout_seconds`: request timeout
- `ai.system_prompt`: system message
- `ai.error_reply`: reply shown if the AI request fails

### Rate limits

- `rate_limits.per_user_per_minute`: per-user limit (0 disables)
- `rate_limits.per_chat_per_minute`: per-chat limit (0 disables)
- `rate_limits.exceeded_message`: reply when limit is exceeded

### Context

- `context.max_reply_chain`: number of messages to include from reply chain

## License

GPL-3.0. See `LICENSE`.

