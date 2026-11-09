"""In-memory note-taking tools for everyday use.

Notes live for the lifetime of the process. Swap ``_NOTES`` for a database or
file-backed store if notes need to survive restarts.
"""

import json
import uuid
from datetime import datetime, timezone

from langchain_core.tools import tool

_NOTES: dict[str, dict] = {}


def _to_json(payload: dict) -> str:
    return json.dumps(payload, indent=2, ensure_ascii=False)


@tool
def save_note(title: str, content: str) -> str:
    """Save a note with a title and body and return its note ID."""
    if not title.strip():
        return "Error: title is required."

    note = {
        "note_id": str(uuid.uuid4()),
        "title": title.strip(),
        "content": content,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    _NOTES[note["note_id"]] = note

    return _to_json(note)


@tool
def list_notes() -> str:
    """List all saved notes with their IDs, titles, and creation times."""
    notes = sorted(_NOTES.values(), key=lambda note: note["created_at"])

    return _to_json({"count": len(notes), "notes": notes})


@tool
def search_notes(query: str) -> str:
    """Search saved notes by a case-insensitive title or body match."""
    needle = query.strip().lower()

    if not needle:
        return "Error: query is required."

    matches = [
        note
        for note in _NOTES.values()
        if needle in note["title"].lower() or needle in note["content"].lower()
    ]

    return _to_json({"query": query, "count": len(matches), "notes": matches})


@tool
def delete_note(note_id: str) -> str:
    """Delete a saved note by its note ID."""
    note = _NOTES.pop(note_id.strip(), None)

    if note is None:
        return f"Error: note '{note_id}' not found."

    return _to_json({"deleted": note["note_id"], "title": note["title"]})
