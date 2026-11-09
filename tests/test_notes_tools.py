import json

from agentic_chatbot.tools.notes import (
    delete_note,
    list_notes,
    save_note,
    search_notes,
)


def test_note_lifecycle_round_trip():
    saved = json.loads(
        save_note.invoke(
            {
                "title": "Grocery list",
                "content": "Milk, eggs, spinach",
            }
        )
    )

    assert saved["title"] == "Grocery list"

    listed = json.loads(list_notes.invoke({}))
    assert any(
        note["note_id"] == saved["note_id"] for note in listed["notes"]
    )

    matches = json.loads(search_notes.invoke({"query": "spinach"}))
    assert any(
        note["note_id"] == saved["note_id"] for note in matches["notes"]
    )

    deleted = json.loads(delete_note.invoke({"note_id": saved["note_id"]}))
    assert deleted["deleted"] == saved["note_id"]

    remaining = json.loads(search_notes.invoke({"query": "spinach"}))
    assert all(
        note["note_id"] != saved["note_id"] for note in remaining["notes"]
    )


def test_save_note_requires_title():
    assert save_note.invoke(
        {"title": "  ", "content": "body"}
    ).startswith("Error:")


def test_search_notes_requires_query():
    assert search_notes.invoke({"query": "   "}).startswith("Error:")


def test_delete_missing_note_reports_error():
    assert delete_note.invoke({"note_id": "missing"}).startswith("Error:")
