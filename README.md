# 🤖 Telegram File Management AI Agent

A Python-powered AI agent that lets you manage your local files from Telegram using natural language. Powered by **Groq** (qwen/qwen3-32b).

## Architecture

```
Telegram (Phone)
        ↓
Telegram Bot API
        ↓
Python Agent (bot.py – running on your laptop)
        ↓
Groq LLM (intent parsing only – llm_planner.py)
        ↓
Local File/System Executor (file_ops.py)
        ↓
Result sent back to Telegram
```

## Files

| File | Purpose |
|------|---------|
| `bot.py` | Main entry point – Telegram bot handlers |
| `llm_planner.py` | Sends user text to Groq LLM, returns structured action plan |
| `file_ops.py` | All file system operations (list, send, search, delete, etc.) |
| `config.py` | Configuration & safety settings |
| `.env` | Your API keys (never commit this!) |

## Setup

### 1. Install Python dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure `.env`

Open `.env` and fill in your keys:

```env
TELEGRAM_BOT_TOKEN=your_telegram_bot_token_here
GROQ_API_KEY=your_groq_api_key_here
ALLOWED_USER_IDS=123456789
```

**How to get your Telegram user ID:**
- Start the bot and send `/myid` — it will reply with your numeric ID.
- Add that ID to `ALLOWED_USER_IDS` in `.env` and restart the bot.
- You can add multiple IDs separated by commas: `123,456,789`

### 3. Run the bot

```bash
python bot.py
```

## Usage

### Slash Commands (fast, no LLM call)

| Command | Example |
|---------|---------|
| `/list <path>` | `/list Desktop` |
| `/send <path>` | `/send Pictures/photo.jpg` |
| `/search <name>` | `/search resume.pdf` |
| `/delete <path>` | `/delete Desktop/test.txt` |
| `/create <path>` | `/create Desktop/Projects` |
| `/organize <path>` | `/organize Downloads` |
| `/health` | System CPU/RAM/uptime |
| `/disk` | Disk space usage |
| `/tree <path>` | `/tree Desktop` |
| `/info <path>` | `/info Documents/report.pdf` |
| `/myid` | Show your Telegram user ID |

### Natural Language (LLM-powered)

Just type in plain English:

- "Show me what's on my Desktop"
- "Send me image.png from Pictures"
- "Find all PDF files"
- "Delete the test folder from Desktop"
- "Create a folder called Projects on Desktop"
- "Organize my Downloads folder"
- "How much disk space do I have?"
- "Check system health"
- "Move report.pdf from Desktop to Documents"
- "Copy the data folder from Desktop to Documents"
- "Rename old.txt to new.txt on Desktop"

## Safety Features

- **User whitelist** – Only allowed Telegram user IDs can use the bot
- **Blocked directories** – System folders (Windows, Program Files, etc.) are untouchable
- **Protected extensions** – `.exe`, `.dll`, `.sys`, `.bat` etc. cannot be deleted
- **File size limit** – Won't send files larger than 49 MB (Telegram limit)
- **Search depth limit** – Recursive searches are capped to avoid runaway scans

## Supported File Operations

| Operation | What it does |
|-----------|-------------|
| **List** | Shows files & folders with sizes |
| **Send** | Sends files via Telegram (images as photos, videos as videos, etc.) |
| **Search** | Recursive file search by name pattern |
| **Delete** | Delete files or folders (with safety checks) |
| **Create** | Create folders or text files |
| **Rename** | Rename files or folders |
| **Move** | Move files/folders to another directory |
| **Copy** | Copy files or folders |
| **Info** | Detailed metadata (size, dates, etc.) |
| **Organize** | Auto-sort files into category sub-folders |
| **Tree** | Visual tree view of directory structure |
| **Disk Usage** | Storage info for all drives |
| **System Health** | CPU, RAM, swap, uptime |
