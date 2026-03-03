"""
file_ops.py – local file-system executor
=========================================
Every public function returns a *dict* with keys:
    success : bool
    message : str            (human-readable summary)
    data    : Any | None     (extra payload – e.g. a file path to send)
"""

from __future__ import annotations

import os
import pathlib
import shutil
import datetime
from typing import Any

import psutil

import config


# ════════════════════════════════════════════════════════════════
#  Helpers
# ════════════════════════════════════════════════════════════════

def _ok(msg: str, **extra: Any) -> dict:
    return {"success": True, "message": msg, **extra}


def _err(msg: str) -> dict:
    return {"success": False, "message": msg, "data": None}


def _resolve(raw_path: str) -> pathlib.Path:
    """Turn a user-supplied path into an absolute Path safely."""
    p = pathlib.Path(raw_path.strip().strip('"').strip("'"))
    if not p.is_absolute():
        p = config.USER_HOME / p
    return p.resolve()


def _is_safe(path: pathlib.Path, *, writing: bool = False) -> str | None:
    """Return an error string if the path is blocked, else None."""
    parts_lower = {part.lower() for part in path.parts}
    if parts_lower & config.BLOCKED_DIRS:
        return f"🚫 Access denied – path touches a protected system directory."
    if writing and path.suffix.lower() in config.PROTECTED_EXTENSIONS:
        return f"🚫 Refusing to modify a protected file type ({path.suffix})."
    return None


# ════════════════════════════════════════════════════════════════
#  Core operations
# ════════════════════════════════════════════════════════════════

def list_directory(raw_path: str) -> dict:
    """List files and folders in a directory."""
    path = _resolve(raw_path)
    if not path.exists():
        return _err(f"❌ Path does not exist: `{path}`")
    if not path.is_dir():
        return _err(f"❌ Not a directory: `{path}`")
    if err := _is_safe(path):
        return _err(err)

    entries: list[str] = []
    try:
        for i, entry in enumerate(sorted(path.iterdir(), key=lambda e: (e.is_file(), e.name.lower()))):
            if i >= config.MAX_LIST_FILES:
                entries.append(f"… and more (showing first {config.MAX_LIST_FILES})")
                break
            icon = "📁" if entry.is_dir() else "📄"
            size = ""
            if entry.is_file():
                try:
                    sz = entry.stat().st_size
                    size = f"  ({_human_size(sz)})"
                except OSError:
                    pass
            entries.append(f"{icon} {entry.name}{size}")
    except PermissionError:
        return _err("🚫 Permission denied reading this directory.")

    body = "\n".join(entries) if entries else "(empty folder)"
    return _ok(f"📂 **{path}**\n\n{body}")


def send_file(raw_path: str) -> dict:
    """Locate a file and return its absolute path so the bot can send it."""
    path = _resolve(raw_path)
    if not path.exists():
        return _err(f"❌ File not found: `{path}`")
    if not path.is_file():
        return _err(f"❌ Not a file: `{path}`")
    if err := _is_safe(path):
        return _err(err)
    try:
        sz = path.stat().st_size
    except OSError:
        return _err("❌ Cannot read file metadata.")
    if sz > config.MAX_SEND_SIZE:
        return _err(f"❌ File too large ({_human_size(sz)}). Telegram limit is ~50 MB.")
    return _ok(f"📤 Sending `{path.name}` ({_human_size(sz)})", data=str(path))


def search_files(name_pattern: str, start_dir: str = "") -> dict:
    """Recursively search for files matching a name pattern."""
    root = _resolve(start_dir) if start_dir else config.USER_HOME
    if not root.is_dir():
        return _err(f"❌ Start directory not found: `{root}`")
    if err := _is_safe(root):
        return _err(err)

    pattern_lower = name_pattern.lower()
    matches: list[str] = []
    try:
        for item in _walk(root, config.MAX_SEARCH_DEPTH):
            if pattern_lower in item.name.lower():
                matches.append(str(item))
                if len(matches) >= 30:
                    break
    except Exception as exc:
        return _err(f"❌ Search error: {exc}")

    if not matches:
        return _ok(f"🔍 No files matching **{name_pattern}** found under `{root}`.")
    listing = "\n".join(f"• `{m}`" for m in matches)
    return _ok(f"🔍 Found **{len(matches)}** result(s) for **{name_pattern}**:\n\n{listing}")


def delete_item(raw_path: str) -> dict:
    """Delete a file or folder (folder is deleted recursively)."""
    path = _resolve(raw_path)
    if not path.exists():
        return _err(f"❌ Path not found: `{path}`")
    if err := _is_safe(path, writing=True):
        return _err(err)

    try:
        if path.is_file():
            path.unlink()
            return _ok(f"🗑️ Deleted file: `{path}`")
        elif path.is_dir():
            shutil.rmtree(path)
            return _ok(f"🗑️ Deleted folder (and contents): `{path}`")
        else:
            return _err("❌ Unknown path type.")
    except PermissionError:
        return _err("🚫 Permission denied.")
    except Exception as exc:
        return _err(f"❌ Delete failed: {exc}")


def create_item(raw_path: str, is_folder: bool = True, content: str = "") -> dict:
    """Create a folder or a text file."""
    path = _resolve(raw_path)
    if err := _is_safe(path, writing=True):
        return _err(err)

    try:
        if is_folder:
            path.mkdir(parents=True, exist_ok=True)
            return _ok(f"📁 Folder created: `{path}`")
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            return _ok(f"📄 File created: `{path}`")
    except PermissionError:
        return _err("🚫 Permission denied.")
    except Exception as exc:
        return _err(f"❌ Creation failed: {exc}")


def rename_item(raw_src: str, raw_dst: str) -> dict:
    """Rename / move a file or folder."""
    src = _resolve(raw_src)
    dst = _resolve(raw_dst)
    if not src.exists():
        return _err(f"❌ Source not found: `{src}`")
    if err := _is_safe(src, writing=True):
        return _err(err)
    if err := _is_safe(dst, writing=True):
        return _err(err)
    try:
        src.rename(dst)
        return _ok(f"✅ Renamed `{src.name}` → `{dst.name}`")
    except Exception as exc:
        return _err(f"❌ Rename failed: {exc}")


def move_item(raw_src: str, raw_dst_dir: str) -> dict:
    """Move a file/folder into another directory."""
    src = _resolve(raw_src)
    dst_dir = _resolve(raw_dst_dir)
    if not src.exists():
        return _err(f"❌ Source not found: `{src}`")
    if not dst_dir.is_dir():
        return _err(f"❌ Destination is not a directory: `{dst_dir}`")
    if err := _is_safe(src, writing=True):
        return _err(err)
    if err := _is_safe(dst_dir, writing=True):
        return _err(err)
    try:
        new_path = shutil.move(str(src), str(dst_dir))
        return _ok(f"✅ Moved `{src.name}` → `{new_path}`")
    except Exception as exc:
        return _err(f"❌ Move failed: {exc}")


def copy_item(raw_src: str, raw_dst: str) -> dict:
    """Copy a file or folder."""
    src = _resolve(raw_src)
    dst = _resolve(raw_dst)
    if not src.exists():
        return _err(f"❌ Source not found: `{src}`")
    if err := _is_safe(src):
        return _err(err)
    if err := _is_safe(dst, writing=True):
        return _err(err)
    try:
        if src.is_dir():
            shutil.copytree(str(src), str(dst))
        else:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(src), str(dst))
        return _ok(f"✅ Copied `{src.name}` → `{dst}`")
    except Exception as exc:
        return _err(f"❌ Copy failed: {exc}")


def get_file_info(raw_path: str) -> dict:
    """Return detailed metadata for a file or folder."""
    path = _resolve(raw_path)
    if not path.exists():
        return _err(f"❌ Not found: `{path}`")
    if err := _is_safe(path):
        return _err(err)
    try:
        stat = path.stat()
        kind = "Folder" if path.is_dir() else "File"
        lines = [
            f"📋 **Info for** `{path}`",
            f"• Type: {kind}",
            f"• Size: {_human_size(stat.st_size)}",
            f"• Created: {_ts(stat.st_ctime)}",
            f"• Modified: {_ts(stat.st_mtime)}",
            f"• Accessed: {_ts(stat.st_atime)}",
        ]
        if path.is_dir():
            try:
                count = sum(1 for _ in path.iterdir())
                lines.append(f"• Items inside: {count}")
            except PermissionError:
                lines.append("• Items inside: (permission denied)")
        return _ok("\n".join(lines))
    except Exception as exc:
        return _err(f"❌ Info failed: {exc}")


def organize_directory(raw_path: str) -> dict:
    """
    Organize files in a directory by moving them into sub-folders
    based on file extension categories.
    """
    path = _resolve(raw_path)
    if not path.is_dir():
        return _err(f"❌ Not a directory: `{path}`")
    if err := _is_safe(path, writing=True):
        return _err(err)

    CATEGORIES: dict[str, list[str]] = {
        "Images":      [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".svg", ".webp", ".ico", ".tiff"],
        "Documents":   [".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".txt", ".csv", ".odt", ".rtf"],
        "Videos":      [".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm"],
        "Audio":       [".mp3", ".wav", ".flac", ".aac", ".ogg", ".wma", ".m4a"],
        "Archives":    [".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz"],
        "Code":        [".py", ".js", ".ts", ".html", ".css", ".java", ".c", ".cpp", ".h", ".go", ".rs", ".json", ".xml", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".sh"],
        "Executables": [".exe", ".msi", ".apk", ".dmg"],
        "Fonts":       [".ttf", ".otf", ".woff", ".woff2"],
    }
    ext_to_cat: dict[str, str] = {}
    for cat, exts in CATEGORIES.items():
        for ext in exts:
            ext_to_cat[ext] = cat

    moved = 0
    skipped = 0
    try:
        for item in list(path.iterdir()):
            if item.is_dir():
                continue
            ext = item.suffix.lower()
            cat = ext_to_cat.get(ext, "Others")
            dest_dir = path / cat
            dest_dir.mkdir(exist_ok=True)
            dest_file = dest_dir / item.name
            if dest_file.exists():
                skipped += 1
                continue
            item.rename(dest_file)
            moved += 1
    except PermissionError:
        return _err("🚫 Permission denied while organizing.")
    except Exception as exc:
        return _err(f"❌ Organize failed: {exc}")

    return _ok(f"🗂️ Organized `{path}`\n• Moved: {moved} files\n• Skipped (conflicts): {skipped}")


def disk_usage() -> dict:
    """Return disk usage for all mounted partitions."""
    lines = ["💾 **Disk Usage**\n"]
    for part in psutil.disk_partitions(all=False):
        try:
            u = psutil.disk_usage(part.mountpoint)
            pct = u.percent
            bar = "█" * int(pct // 5) + "░" * (20 - int(pct // 5))
            lines.append(
                f"**{part.device}** (`{part.mountpoint}`)\n"
                f"  {bar} {pct}%\n"
                f"  {_human_size(u.used)} / {_human_size(u.total)}  (free: {_human_size(u.free)})\n"
            )
        except PermissionError:
            continue
    return _ok("\n".join(lines))


def system_health() -> dict:
    """Quick snapshot: CPU, RAM, disk."""
    cpu = psutil.cpu_percent(interval=1)
    mem = psutil.virtual_memory()
    swap = psutil.swap_memory()
    boot = datetime.datetime.fromtimestamp(psutil.boot_time())
    uptime = datetime.datetime.now() - boot

    lines = [
        "🖥️ **System Health**\n",
        f"• **CPU**: {cpu}%",
        f"• **RAM**: {mem.percent}%  ({_human_size(mem.used)} / {_human_size(mem.total)})",
        f"• **Swap**: {swap.percent}%  ({_human_size(swap.used)} / {_human_size(swap.total)})",
        f"• **Uptime**: {str(uptime).split('.')[0]}",
    ]
    return _ok("\n".join(lines))


def tree_view(raw_path: str, depth: int = 2) -> dict:
    """Show a tree view of a directory up to `depth` levels."""
    path = _resolve(raw_path)
    if not path.is_dir():
        return _err(f"❌ Not a directory: `{path}`")
    if err := _is_safe(path):
        return _err(err)

    lines = [f"🌳 `{path}`"]
    _build_tree(path, "", depth, lines, count=[0])
    if not lines[1:]:
        lines.append("  (empty)")
    return _ok("\n".join(lines))


# ════════════════════════════════════════════════════════════════
#  Internal utilities
# ════════════════════════════════════════════════════════════════

def _walk(root: pathlib.Path, max_depth: int, _depth: int = 0):
    """Yield files recursively with depth limit."""
    if _depth > max_depth:
        return
    try:
        for entry in root.iterdir():
            if entry.name.startswith("."):
                continue
            parts_lower = {p.lower() for p in entry.parts}
            if parts_lower & config.BLOCKED_DIRS:
                continue
            yield entry
            if entry.is_dir():
                yield from _walk(entry, max_depth, _depth + 1)
    except (PermissionError, OSError):
        return


def _build_tree(path: pathlib.Path, prefix: str, depth: int, lines: list[str], count: list[int]):
    if depth < 0 or count[0] > 200:
        return
    try:
        entries = sorted(path.iterdir(), key=lambda e: (e.is_file(), e.name.lower()))
    except PermissionError:
        return
    for i, entry in enumerate(entries):
        is_last = (i == len(entries) - 1)
        connector = "└── " if is_last else "├── "
        icon = "📁" if entry.is_dir() else "📄"
        lines.append(f"{prefix}{connector}{icon} {entry.name}")
        count[0] += 1
        if count[0] > 200:
            lines.append(f"{prefix}    … (truncated)")
            return
        if entry.is_dir():
            extension = "    " if is_last else "│   "
            _build_tree(entry, prefix + extension, depth - 1, lines, count)


def _human_size(nbytes: int | float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(nbytes) < 1024:
            return f"{nbytes:.1f} {unit}"
        nbytes /= 1024
    return f"{nbytes:.1f} PB"


def _ts(timestamp: float) -> str:
    return datetime.datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")


# ════════════════════════════════════════════════════════════════
#  Function registry (used by the LLM planner)
# ════════════════════════════════════════════════════════════════

FUNCTIONS: dict[str, dict] = {
    "list_directory": {
        "fn": list_directory,
        "description": "List files and folders in a directory",
        "parameters": {"raw_path": "str – directory path (relative to home or absolute)"},
    },
    "send_file": {
        "fn": send_file,
        "description": "Send/download a file to the user via Telegram",
        "parameters": {"raw_path": "str – file path"},
    },
    "search_files": {
        "fn": search_files,
        "description": "Recursively search for files by name pattern",
        "parameters": {
            "name_pattern": "str – filename or partial name to search",
            "start_dir": "str – starting directory (optional, defaults to home)",
        },
    },
    "delete_item": {
        "fn": delete_item,
        "description": "Delete a file or folder",
        "parameters": {"raw_path": "str – path to delete"},
    },
    "create_item": {
        "fn": create_item,
        "description": "Create a new folder or file",
        "parameters": {
            "raw_path": "str – path for the new item",
            "is_folder": "bool – True for folder, False for file",
            "content": "str – text content if creating a file (optional)",
        },
    },
    "rename_item": {
        "fn": rename_item,
        "description": "Rename or move a file/folder",
        "parameters": {
            "raw_src": "str – current path",
            "raw_dst": "str – new path / name",
        },
    },
    "move_item": {
        "fn": move_item,
        "description": "Move a file or folder into another directory",
        "parameters": {
            "raw_src": "str – source path",
            "raw_dst_dir": "str – destination directory",
        },
    },
    "copy_item": {
        "fn": copy_item,
        "description": "Copy a file or folder",
        "parameters": {
            "raw_src": "str – source path",
            "raw_dst": "str – destination path",
        },
    },
    "get_file_info": {
        "fn": get_file_info,
        "description": "Get detailed info/metadata of a file or folder",
        "parameters": {"raw_path": "str – path to inspect"},
    },
    "organize_directory": {
        "fn": organize_directory,
        "description": "Auto-organize files in a directory into categorized sub-folders (Images, Documents, Videos, etc.)",
        "parameters": {"raw_path": "str – directory to organize"},
    },
    "disk_usage": {
        "fn": disk_usage,
        "description": "Show disk space usage for all drives",
        "parameters": {},
    },
    "system_health": {
        "fn": system_health,
        "description": "Show CPU, RAM, swap, and uptime info",
        "parameters": {},
    },
    "tree_view": {
        "fn": tree_view,
        "description": "Show a tree view of a directory structure",
        "parameters": {
            "raw_path": "str – directory path",
            "depth": "int – how many levels deep (default 2)",
        },
    },
}
