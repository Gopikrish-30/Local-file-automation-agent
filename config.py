import os
import pathlib
from dotenv import load_dotenv

load_dotenv()

# ── Telegram ────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
ALLOWED_USER_IDS: list[int] = [
    int(uid.strip())
    for uid in os.getenv("ALLOWED_USER_IDS", "").split(",")
    if uid.strip().isdigit()
]

# ── OpenRouter LLM ──────────────────────────────────────────
OPENROUTER_API_KEY: str = os.getenv("OPENROUTER_API_KEY", "")
LLM_MODEL: str = "meta-llama/llama-3.3-70b-instruct:free"
OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"

# ── File-system safety ──────────────────────────────────────
# Root anchors – the agent will resolve *relative* paths under USER_HOME.
USER_HOME: pathlib.Path = pathlib.Path.home()

# Directories the bot is NEVER allowed to touch (case-insensitive on Windows).
BLOCKED_DIRS: set[str] = {
    "windows", "program files", "program files (x86)",
    "programdata", "$recycle.bin", "system volume information",
    "recovery", "boot", "perflogs",
}

# Extensions the bot will NEVER delete / overwrite.
PROTECTED_EXTENSIONS: set[str] = {".sys", ".dll", ".exe", ".bat", ".cmd", ".ps1", ".reg"}

# Maximum depth for recursive searches (to avoid runaway scans).
MAX_SEARCH_DEPTH: int = 6

# Maximum files to list at once.
MAX_LIST_FILES: int = 60

# Maximum file size (bytes) the bot will send via Telegram (50 MB TG limit).
MAX_SEND_SIZE: int = 49 * 1024 * 1024
