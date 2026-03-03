"""
bot.py – Telegram Bot + AI File Agent
=======================================
Run:  python bot.py

Flow:
  1. User sends a message (natural language OR /command)
  2. LLM parses intent → {action, args, summary}
  3. file_ops executes the action locally
  4. Result is sent back to Telegram
"""

from __future__ import annotations

import logging
import pathlib
import html

from telegram import Update, BotCommand
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
from telegram.constants import ParseMode

import config
import file_ops
import llm_planner

# ── Logging ──────────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("telebot")


# ════════════════════════════════════════════════════════════════
#  Auth guard
# ════════════════════════════════════════════════════════════════

def _is_authorized(update: Update) -> bool:
    if not config.ALLOWED_USER_IDS:
        return True  # no whitelist → everyone allowed
    return update.effective_user.id in config.ALLOWED_USER_IDS


async def _deny(update: Update) -> None:
    uid = update.effective_user.id
    logger.warning(f"Unauthorized access attempt by user {uid}")
    await update.message.reply_text(
        f"🚫 Unauthorized. Your user ID is `{uid}`.\n"
        "Ask the bot owner to add it to ALLOWED_USER_IDS.",
        parse_mode=ParseMode.MARKDOWN,
    )


# ════════════════════════════════════════════════════════════════
#  /start and /help
# ════════════════════════════════════════════════════════════════

HELP_TEXT = """
🤖 **File Management AI Agent**

Just type your request in plain English! Examples:

• `list Desktop`
• `show me what's in Downloads`
• `send image.png from Pictures`
• `search resume.pdf`
• `delete test.txt from Desktop`
• `create folder Projects on Desktop`
• `create file notes.txt on Desktop`
• `organize Downloads`
• `rename old.txt to new.txt on Desktop`
• `move report.pdf from Desktop to Documents`
• `copy data.xlsx from Desktop to Documents`
• `info about Desktop`
• `tree Desktop`
• `disk usage`
• `system health`

**Quick commands:**
/list <path> – List directory
/send <path> – Send a file
/search <name> – Search files
/delete <path> – Delete file/folder
/create <path> – Create folder
/organize <path> – Organize directory
/health – System health
/disk – Disk usage
/tree <path> – Tree view
/info <path> – File info
/myid – Show your Telegram user ID
/help – This help message
"""


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_authorized(update):
        return await _deny(update)
    await update.message.reply_text(
        f"👋 Hello **{update.effective_user.first_name}**!\n" + HELP_TEXT,
        parse_mode=ParseMode.MARKDOWN,
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_authorized(update):
        return await _deny(update)
    await update.message.reply_text(HELP_TEXT, parse_mode=ParseMode.MARKDOWN)


async def cmd_myid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"Your Telegram user ID: `{update.effective_user.id}`", parse_mode=ParseMode.MARKDOWN)


# ════════════════════════════════════════════════════════════════
#  Quick slash-commands (bypass LLM for speed)
# ════════════════════════════════════════════════════════════════

async def cmd_list(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _is_authorized(update):
        return await _deny(update)
    path = " ".join(ctx.args) if ctx.args else "~"
    result = file_ops.list_directory(path)
    await _send_result(update, result)


async def cmd_send(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _is_authorized(update):
        return await _deny(update)
    if not ctx.args:
        return await update.message.reply_text("Usage: /send <file_path>")
    path = " ".join(ctx.args)
    result = file_ops.send_file(path)
    await _send_result(update, result)


async def cmd_search(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _is_authorized(update):
        return await _deny(update)
    if not ctx.args:
        return await update.message.reply_text("Usage: /search <filename>")
    pattern = " ".join(ctx.args)
    await update.message.reply_text(f"🔍 Searching for **{pattern}**… this may take a moment.", parse_mode=ParseMode.MARKDOWN)
    result = file_ops.search_files(pattern)
    await _send_result(update, result)


async def cmd_delete(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _is_authorized(update):
        return await _deny(update)
    if not ctx.args:
        return await update.message.reply_text("Usage: /delete <path>")
    path = " ".join(ctx.args)
    result = file_ops.delete_item(path)
    await _send_result(update, result)


async def cmd_create(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _is_authorized(update):
        return await _deny(update)
    if not ctx.args:
        return await update.message.reply_text("Usage: /create <folder_path>")
    path = " ".join(ctx.args)
    result = file_ops.create_item(path, is_folder=True)
    await _send_result(update, result)


async def cmd_organize(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _is_authorized(update):
        return await _deny(update)
    path = " ".join(ctx.args) if ctx.args else "Downloads"
    result = file_ops.organize_directory(path)
    await _send_result(update, result)


async def cmd_health(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _is_authorized(update):
        return await _deny(update)
    result = file_ops.system_health()
    await _send_result(update, result)


async def cmd_disk(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _is_authorized(update):
        return await _deny(update)
    result = file_ops.disk_usage()
    await _send_result(update, result)


async def cmd_tree(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _is_authorized(update):
        return await _deny(update)
    path = " ".join(ctx.args) if ctx.args else "~"
    result = file_ops.tree_view(path)
    await _send_result(update, result)


async def cmd_info(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _is_authorized(update):
        return await _deny(update)
    if not ctx.args:
        return await update.message.reply_text("Usage: /info <path>")
    path = " ".join(ctx.args)
    result = file_ops.get_file_info(path)
    await _send_result(update, result)


# ════════════════════════════════════════════════════════════════
#  Natural-language handler (LLM-powered)
# ════════════════════════════════════════════════════════════════

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_authorized(update):
        return await _deny(update)

    user_text = update.message.text.strip()
    if not user_text:
        return

    logger.info(f"User {update.effective_user.id}: {user_text}")

    # Send "thinking" indicator
    await update.message.reply_text("🧠 Thinking…")

    # Ask LLM to parse intent
    plan = llm_planner.parse_intent(user_text)
    logger.info(f"LLM plan: {plan}")

    action = plan.get("action", "error")
    args = plan.get("args", {})
    summary = plan.get("summary", "")

    # ── Chat (non-file request) ──────────────────────────────
    if action == "chat":
        return await update.message.reply_text(summary or "👋 Hey! Ask me to manage your files.")

    # ── Error ────────────────────────────────────────────────
    if action == "error":
        return await update.message.reply_text(f"⚠️ {summary}")

    # ── Execute file operation ───────────────────────────────
    func_info = file_ops.FUNCTIONS.get(action)
    if not func_info:
        return await update.message.reply_text(f"⚠️ Unknown action: `{action}`", parse_mode=ParseMode.MARKDOWN)

    # Show what we're about to do
    if summary:
        await update.message.reply_text(f"⚡ {summary}")

    try:
        result = func_info["fn"](**args)
    except TypeError as exc:
        logger.error(f"Argument mismatch for {action}: {exc}")
        result = {"success": False, "message": f"❌ Argument error: {exc}", "data": None}
    except Exception as exc:
        logger.error(f"Execution error: {exc}")
        result = {"success": False, "message": f"❌ Execution error: {exc}", "data": None}

    await _send_result(update, result)


# ════════════════════════════════════════════════════════════════
#  Result dispatcher
# ════════════════════════════════════════════════════════════════

async def _send_result(update: Update, result: dict):
    """Send the operation result back to the user. If data contains a filepath, send the file."""
    message = result.get("message", "Done.")
    data = result.get("data")

    # If there's a file to send
    if data and result.get("success"):
        fpath = pathlib.Path(data)
        if fpath.is_file():
            try:
                # Determine send method based on file type
                suffix = fpath.suffix.lower()
                image_exts = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"}
                video_exts = {".mp4", ".mkv", ".avi", ".mov", ".webm"}
                audio_exts = {".mp3", ".wav", ".ogg", ".flac", ".m4a"}

                if suffix in image_exts:
                    await update.message.reply_photo(
                        photo=open(fpath, "rb"),
                        caption=f"📤 {fpath.name}",
                    )
                elif suffix in video_exts:
                    await update.message.reply_video(
                        video=open(fpath, "rb"),
                        caption=f"📤 {fpath.name}",
                    )
                elif suffix in audio_exts:
                    await update.message.reply_audio(
                        audio=open(fpath, "rb"),
                        caption=f"📤 {fpath.name}",
                    )
                else:
                    await update.message.reply_document(
                        document=open(fpath, "rb"),
                        caption=f"📤 {fpath.name}",
                    )
                return
            except Exception as exc:
                message += f"\n\n⚠️ Could not send file: {exc}"

    # Send text result – split long messages if needed
    for chunk in _split_message(message):
        try:
            await update.message.reply_text(chunk, parse_mode=ParseMode.MARKDOWN)
        except Exception:
            # Fallback: send without markdown if parsing fails
            await update.message.reply_text(chunk)


def _split_message(text: str, max_len: int = 4000) -> list[str]:
    """Split a message into chunks that fit Telegram's 4096 char limit."""
    if len(text) <= max_len:
        return [text]
    chunks = []
    while text:
        if len(text) <= max_len:
            chunks.append(text)
            break
        # Try to split at a newline
        idx = text.rfind("\n", 0, max_len)
        if idx == -1:
            idx = max_len
        chunks.append(text[:idx])
        text = text[idx:].lstrip("\n")
    return chunks


# ════════════════════════════════════════════════════════════════
#  Main
# ════════════════════════════════════════════════════════════════

def main():
    if not config.TELEGRAM_BOT_TOKEN:
        print("❌ TELEGRAM_BOT_TOKEN not set in .env file!")
        return
    if not config.OPENROUTER_API_KEY:
        print("❌ OPENROUTER_API_KEY not set in .env file!")
        return

    print("=" * 55)
    print("  🤖 File Management AI Agent – Starting…")
    print(f"  📂 Home: {config.USER_HOME}")
    print(f"  🧠 Model: {config.LLM_MODEL}")
    if config.ALLOWED_USER_IDS:
        print(f"  🔒 Allowed users: {config.ALLOWED_USER_IDS}")
    else:
        print("  ⚠️  No user whitelist – anyone can use the bot!")
    print("=" * 55)

    app = ApplicationBuilder().token(config.TELEGRAM_BOT_TOKEN).build()

    # Commands
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("myid", cmd_myid))
    app.add_handler(CommandHandler("list", cmd_list))
    app.add_handler(CommandHandler("send", cmd_send))
    app.add_handler(CommandHandler("search", cmd_search))
    app.add_handler(CommandHandler("delete", cmd_delete))
    app.add_handler(CommandHandler("create", cmd_create))
    app.add_handler(CommandHandler("organize", cmd_organize))
    app.add_handler(CommandHandler("health", cmd_health))
    app.add_handler(CommandHandler("disk", cmd_disk))
    app.add_handler(CommandHandler("tree", cmd_tree))
    app.add_handler(CommandHandler("info", cmd_info))

    # Natural language (catch-all)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Set bot commands for Telegram menu
    import asyncio
    async def set_commands():
        await app.bot.set_my_commands([
            BotCommand("start", "Start the bot"),
            BotCommand("help", "Show help & examples"),
            BotCommand("list", "List directory contents"),
            BotCommand("send", "Send a file"),
            BotCommand("search", "Search for files"),
            BotCommand("delete", "Delete a file or folder"),
            BotCommand("create", "Create a folder"),
            BotCommand("organize", "Organize a directory"),
            BotCommand("health", "System health check"),
            BotCommand("disk", "Disk usage"),
            BotCommand("tree", "Tree view of directory"),
            BotCommand("info", "File/folder info"),
            BotCommand("myid", "Show your user ID"),
        ])

    app.post_init = lambda _app: set_commands()

    # Start polling
    print("\n✅ Bot is running! Send a message on Telegram.\n")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
