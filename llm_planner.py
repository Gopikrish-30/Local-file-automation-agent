"""
llm_planner.py – OpenRouter-powered intent parser
==================================================
Takes a natural-language message from the user,
asks the LLM to extract a structured action + arguments,
and returns them for execution.
"""

from __future__ import annotations

import json
import re
import time
import traceback
from openai import OpenAI

import config
import file_ops

# Maximum retries for transient API errors
MAX_RETRIES = 3
RETRY_DELAY = 2  # seconds, doubles each retry

# ── OpenRouter client (OpenAI-compatible) ────────────────────
_client: OpenAI | None = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(
            base_url=config.OPENROUTER_BASE_URL,
            api_key=config.OPENROUTER_API_KEY,
        )
    return _client


# ── System prompt ────────────────────────────────────────────
_FUNC_DESCRIPTIONS = "\n".join(
    f"  • {name}: {info['description']}  |  params: {info['parameters']}"
    for name, info in file_ops.FUNCTIONS.items()
)

SYSTEM_PROMPT = f"""\
You are a file-management AI assistant running on the user's local machine.
Your ONLY job is to parse the user's natural-language request and output a
JSON action plan.  You must NOT execute anything yourself.

Available functions:
{_FUNC_DESCRIPTIONS}

── RULES ──
1. Respond with **ONLY** valid JSON – no markdown, no explanation, no extra text.
2. The JSON must be an object with exactly these keys:
   {{
     "action": "<function_name>",
     "args": {{ ... }},          // matching the function's parameter names
     "summary": "<short 1-line description of what you understood>"
   }}
3. If the user's request is casual / greeting / not a file operation, return:
   {{
     "action": "chat",
     "args": {{}},
     "summary": "<your friendly reply>"
   }}
4. Paths can be relative (resolved from the user's home directory) or absolute.
   Common Windows folders: Desktop, Documents, Downloads, Pictures, Music, Videos.
5. When the user says "send", "give me", "show me" a file → use send_file.
6. When the user says "organize" or "clean up" → use organize_directory.
7. When the user says "health", "status", "system info" → use system_health.
8. When the user says "disk", "storage", "space" → use disk_usage.
9. When the user says "tree" or "structure" → use tree_view.
10. When the user says "info", "details", "properties" of a file → use get_file_info.
11. For "search" or "find" → use search_files.
12. For "delete" or "remove" → use delete_item.
13. For "create folder/directory" → use create_item with is_folder=true.
14. For "create file" → use create_item with is_folder=false.
15. For "rename" → use rename_item.
16. For "move" → use move_item.
17. For "copy" → use copy_item.
18. For "list", "show", "what's in" → use list_directory.
19. Do NOT wrap JSON in markdown code fences.
"""


# ── Public API ───────────────────────────────────────────────

def parse_intent(user_message: str) -> dict:
    """
    Send the user message to OpenRouter and return the parsed action plan.
    Returns dict with keys: action, args, summary.
    On failure returns action="error".
    Retries up to MAX_RETRIES times on transient API errors.
    """
    last_error = None
    for attempt in range(MAX_RETRIES):
        try:
            client = _get_client()
            response = client.chat.completions.create(
                model=config.LLM_MODEL,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_message},
                ],
                temperature=0.1,
                max_tokens=1024,
                extra_headers={
                    "HTTP-Referer": "https://github.com/telebot-agent",
                    "X-Title": "Telebot File Agent",
                },
                extra_body={
                    "provider": {
                        "data_collection": "allow",
                    },
                },
            )
            raw = response.choices[0].message.content.strip()

            # Robust JSON extraction: handle think tags, markdown fences, etc.
            plan = _extract_json(raw)

            # Validate structure
            if "action" not in plan:
                return {
                    "action": "error",
                    "args": {},
                    "summary": f"LLM returned invalid JSON (no 'action' key). Raw: {raw[:300]}",
                }
            plan.setdefault("args", {})
            plan.setdefault("summary", "")
            return plan

        except Exception as exc:
            last_error = exc
            traceback.print_exc()
            if attempt < MAX_RETRIES - 1:
                delay = RETRY_DELAY * (2 ** attempt)
                print(f"[Retry {attempt + 1}/{MAX_RETRIES}] Waiting {delay}s before retrying…")
                time.sleep(delay)
            else:
                break

    return {
        "action": "error",
        "args": {},
        "summary": f"LLM call failed after {MAX_RETRIES} attempts: {last_error}",
    }


def _strip_think_tags(text: str) -> str:
    """Remove <think>...</think> blocks that qwen3 models emit."""
    # Remove everything between <think> and </think> (including the tags)
    cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    return cleaned.strip()


def _extract_json(text: str) -> dict:
    """Best-effort extraction of a JSON object from LLM output."""
    # Step 0: Strip <think>...</think> reasoning blocks (qwen3 models)
    text = _strip_think_tags(text)

    # Try direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Strip markdown fences
    cleaned = re.sub(r"```(?:json)?\s*", "", text)
    cleaned = cleaned.replace("```", "").strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # Find first { ... } block
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    # Give up
    return {"action": "error", "args": {}, "summary": f"Could not parse LLM output: {text[:300]}"}
