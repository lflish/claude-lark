# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Lark (Feishu/飞书) bot that integrates Claude AI capabilities through the [claude-agent-http](https://github.com/lflish/claude-agent-http) backend service. The bot receives messages via Lark's WebSocket connection, processes them asynchronously, and responds with AI-generated content.

## Architecture

The system consists of two main components:

1. **claude-bot** (this repository): Handles Lark message events via WebSocket and manages message routing
2. **claude-agent-http**: External backend service that provides Claude API access and session management

Key architecture patterns:
- **Immediate response pattern**: Messages are queued immediately to return HTTP 200 to Lark, preventing duplicate message delivery
- **Asynchronous processing**: Background worker thread processes messages from a queue
- **Session persistence**: Message IDs are mapped to Claude session IDs for multi-turn conversations
- **Context threading**: Uses Lark's `root_id` and `parent_id` fields to maintain conversation context in message threads

## Development Commands

### Local Development (Python)
```bash
# Install dependencies
pip install -r requirements.txt

# Run directly (ensure CLAUDE_AGENT_URL is accessible)
export APP_ID=cli_xxxxx
export APP_SECRET=xxxxx
export CLAUDE_AGENT_URL=http://localhost:8000
python main.py

# Test the claude-agent-http client
python handle.py
```

### Docker Development
```bash
# Build Docker image
./build.sh
# or: docker build -t claude-bot:latest .

# Run standalone container
./run.sh

# Use Docker Compose (includes claude-agent-http backend)
docker-compose up -d
docker-compose logs -f claude-bot
docker-compose down
```

### Common Docker Commands
```bash
# View logs
docker logs -f claude-bot

# Restart service
docker restart claude-bot

# Stop and remove
docker stop claude-bot && docker rm claude-bot
```

## Core Components

### main.py
The main bot application with three critical functions:

- **`do_p2_im_message_receive_v1(data)`**: Event handler that immediately queues incoming messages and returns (prevents Lark timeout/retry)
- **`process_single_message(data)`**: Core message processing logic that:
  - Filters group messages (only responds to @mentions)
  - Extracts user ID from sender
  - Resolves session context using `root_id` > `parent_id` > new session
  - Calls Claude Agent HTTP backend
  - Saves session mappings for all message IDs involved
- **`process_message_worker()`**: Background thread that processes queued messages

Message flow:
1. Lark sends message → `do_p2_im_message_receive_v1()` → queue + immediate 200 OK
2. Worker thread → dequeue → `process_single_message()` → Claude API → reply
3. Session mappings saved: `message_id`, `root_id`, `reply_message_id` → `session_id`

### handle.py
HTTP client wrapper for claude-agent-http backend:

- **`ClaudeAgentClient`**: HTTP client class with methods for session lifecycle (`create_session`, `get_session`, `resume_session`, `close_session`, `chat`, `chat_stream`)
- **Session mapping storage**: Uses optimized structure with automatic LRU eviction (max 1000 sessions) persisted to JSON file
  - **Storage format v2.0**: Stores only `root_id` + last 3 messages per session (reduces storage by ~70%)
  - **Memory cache**: Message ID → Session ID mapping cached in memory for fast lookup
  - **Auto-migration**: Old storage format automatically migrated on first load with backup
- **Key functions**:
  - `ask_claude_sync()`: Main entry point for synchronous chat
  - `get_session_id()`: Retrieve session by Lark message ID (uses memory cache)
  - `save_session_mapping(message_id, session_id, is_root=False)`: Persist message mapping
    - `is_root=True`: Marks message as conversation root (永久保留)
    - `is_root=False`: Adds to recent messages (sliding window, max 3)
  - `get_or_create_session()`: Get existing or create new session with validation (deprecated)

Session storage: Configured via `LOCAL_SESSION_DIR` in .env (host path, default: `~/.claude-lark`), mounted to `/data/claude-lark` in container.

**Storage Structure** (v2.0):
```json
{
  "version": "2.0",
  "sessions": {
    "session_id": {
      "root_id": "om_root_message",
      "recent": ["om_msg_1", "om_msg_2", "om_msg_3"]
    }
  }
}
```

## Configuration

Environment variables (see `env.example`):

**Required:**
- `APP_ID`: Lark application ID
- `APP_SECRET`: Lark application secret
- `CLAUDE_AGENT_URL`: Backend service URL (default: `http://localhost:8000`)

**Optional:**
- `CLAUDE_AGENT_TIMEOUT`: Request timeout in seconds (default: 300, recommend 300-600 for complex tasks)
- `LOCAL_SESSION_DIR`: Host machine path for session storage (default: `~/.claude-lark`)
- `ANTHROPIC_API_KEY`: Only needed if running claude-agent-http via docker-compose
- Note: Container internal path is fixed at `/data/claude-lark`

## Message Context & Threading

The bot maintains conversation context through Lark's message threading:

1. **root_id**: The first message in a reply chain (highest priority for session lookup)
2. **parent_id**: The direct parent message (fallback if no root_id)
3. **message_id**: Current message ID (always saved to session mapping)

All three IDs are mapped to the same `session_id` to ensure consistent context regardless of where users reply in the thread.

## Lark API Integration

Uses `lark-oapi` SDK with WebSocket mode (long connection):
- Event subscription: `im.message.receive_v1`
- Required permissions: `im:message`, `im:message.group_at_msg`, `im:message.p2p_msg`
- Reply method: Always uses `reply()` API for message quoting

Group chat behavior: Only responds when bot is @mentioned (checks `mentions[].id.app_id` against `lark.APP_ID`)

## Session Management

Session lifecycle:
1. New message arrives → check `root_id`/`parent_id` for existing session
2. If found: reuse session (maintains context)
3. If not found: create new session via `client.create_session(user_id)`
4. After response: save message mappings:
   - `root_id` → marked as conversation root (永久保留)
   - Current `message_id` → added to recent messages (sliding window)
   - Bot reply `message_id` → added to recent messages
5. **Storage optimization**: Each session stores:
   - 1 `root_id` (永久保留，用于查找对话线程)
   - Up to 3 recent message IDs (滑动窗口，自动移除最旧的)
6. LRU eviction: Old sessions automatically closed when exceeding 1000 sessions

**Storage efficiency**: Compared to old format (all message IDs), new format reduces storage by ~70%:
- Old: 10-message conversation = 10 mappings stored
- New: 10-message conversation = 4 mappings stored (1 root + 3 recent)

Session validation: Backend sessions are validated via `get_session()` before reuse.

## Error Handling

- **Retry mechanism**: Message sending retries up to 3 times with exponential backoff
- **Health check**: On startup, validates claude-agent-http backend connectivity
- **Queue processing**: Worker thread continues on exceptions without crashing
- **Session recovery**: Invalid sessions are auto-deleted and recreated

## Dependencies

- `lark-oapi>=1.4.8`: Lark Open Platform SDK
- `requests>=2.31.0`: HTTP client for backend communication
