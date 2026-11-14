"""Database-backed, per-conversation note-taking tools.

Each tool reads the active ``thread_id`` from the LangGraph run config, so a
conversation can only see and modify its own notes.
"""

import json
from dataclasses import asdict

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool, tool

from agentic_chatbot.repository import NotesRepository

_MISSING_CONTEXT = "Error: no active conversation context for notes."


def _to_json(payload: dict) -> str:
    return json.dumps(payload, indent=2, ensure_ascii=False)


def _thread_id(config: RunnableConfig | None) -> str | None:
    if not config:
        return None

    configurable = config.get("configurable") or {}
    thread_id = configurable.get("thread_id")

    return str(thread_id) if thread_id else None


def create_note_tools(repository: NotesRepository) -> list[BaseTool]:
    """Build the note tools bound to a notes repository."""

    @tool
    def save_note(title: str, content: str, config: RunnableConfig) -> str:
        """Save a note for the current conversation and return its note ID.

        Use this when the user asks you to remember, save, or note something.
        """
        thread_id = _thread_id(config)
        if thread_id is None:
            return _MISSING_CONTEXT

        if not title.strip():
            return "Error: title is required."

        note = repository.create(thread_id, title.strip(), content)
        return _to_json(asdict(note))

    @tool
    def list_notes(config: RunnableConfig) -> str:
        """List the current conversation's saved notes with IDs, titles, and times.

        Use this when the user asks what notes they have or to show their notes.
        """
        thread_id = _thread_id(config)
        if thread_id is None:
            return _MISSING_CONTEXT

        notes = [asdict(note) for note in repository.list_all(thread_id)]
        return _to_json({"count": len(notes), "notes": notes})

    @tool
    def search_notes(query: str, config: RunnableConfig) -> str:
        """Search the current conversation's saved notes by title or body.

        Use this when the user asks to find, search, or recall something from
        their notes.
        """
        thread_id = _thread_id(config)
        if thread_id is None:
            return _MISSING_CONTEXT

        if not query.strip():
            return "Error: query is required."

        notes = [
            asdict(note) for note in repository.search(thread_id, query.strip())
        ]
        return _to_json({"query": query, "count": len(notes), "notes": notes})

    @tool
    def delete_note(note_id: str, config: RunnableConfig) -> str:
        """Delete one of the current conversation's saved notes by its note ID."""
        thread_id = _thread_id(config)
        if thread_id is None:
            return _MISSING_CONTEXT

        note = repository.get(thread_id, note_id.strip())

        if note is None:
            return f"Error: note '{note_id}' not found."

        repository.delete(thread_id, note.note_id)
        return _to_json({"deleted": note.note_id, "title": note.title})

    return [save_note, list_notes, search_notes, delete_note]
