"""Tool catalog: read-only, authenticated, and honest about approval policy."""

from __future__ import annotations

from agentic_chatbot.inventory.approvals import SENSITIVE_TOOLS


def test_tools_require_auth(api_client):
    assert api_client.get("/api/v1/tools").status_code == 401


def test_the_catalog_lists_every_registered_tool(api_client, auth_headers):
    container = api_client.app.state.container
    response = api_client.get("/api/v1/tools", headers=auth_headers())

    assert response.status_code == 200
    body = response.json()
    names = {tool["name"] for tool in body["tools"]}

    assert body["count"] == len(body["tools"])
    assert body["count"] == len(container.tools)
    assert names == {tool.name for tool in container.tools}


def test_approval_flag_matches_the_real_policy(api_client, auth_headers):
    """The list must not claim a tool is safe when the graph would gate it."""
    body = api_client.get("/api/v1/tools", headers=auth_headers()).json()
    flagged = {tool["name"] for tool in body["tools"] if tool["requires_approval"]}

    assert flagged == set(SENSITIVE_TOOLS)


def test_entries_are_grouped_and_described(api_client, auth_headers):
    body = api_client.get("/api/v1/tools", headers=auth_headers()).json()
    by_name = {tool["name"]: tool for tool in body["tools"]}

    assert by_name["calculator"]["category"] == "Math"
    assert by_name["search_documents"]["category"] == "Documents"
    assert by_name["save_note"]["category"] == "Notes"
    assert any(t["category"] == "Inventory (demo)" for t in body["tools"])

    # Descriptions are single-line and bounded, never a full docstring.
    for tool in body["tools"]:
        assert "\n" not in tool["description"]
        assert len(tool["description"]) <= 300


def test_the_catalog_exposes_no_arguments_or_internals(api_client, auth_headers):
    response = api_client.get("/api/v1/tools", headers=auth_headers())
    body = response.json()
    serialised = str(body)

    # Schema is exactly the four documented fields.
    for tool in body["tools"]:
        assert set(tool) == {"name", "description", "category", "requires_approval"}

    # No filesystem paths or credentials leak through descriptions.
    assert "API_KEY" not in serialised
    assert ":\\" not in serialised.replace('":\\', "")
