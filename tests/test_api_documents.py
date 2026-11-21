"""Document upload, listing, deletion, and isolation."""

from __future__ import annotations

TEXT = b"Onboarding starts on Monday and covers the handbook basics.\n"
PDF_BYTES = b"%PDF-1.4\n% a minimal but magic-valid header\n"


def upload(client, headers, name, content, content_type="application/octet-stream"):
    return client.post(
        "/api/v1/documents",
        headers=headers,
        files={"file": (name, content, content_type)},
    )


def test_uploading_a_text_document(api_client, auth_headers):
    response = upload(api_client, auth_headers(), "handbook.md", TEXT)

    assert response.status_code == 201
    body = response.json()
    assert body["document"]["title"]
    assert body["document"]["namespace"].startswith("u_")
    assert body["chunks_created"] >= 1
    assert body["skipped"] is False


def test_the_stored_path_is_never_returned(api_client, auth_headers, api_settings):
    response = upload(api_client, auth_headers(), "handbook.md", TEXT)

    assert response.status_code == 201
    assert api_settings.api_upload_path not in response.text
    assert "source" not in response.json()["document"]
    assert ".incoming" not in response.text


def test_an_unsupported_extension_is_refused(api_client, auth_headers):
    response = upload(api_client, auth_headers(), "payload.exe", b"MZ\x90\x00")

    assert response.status_code == 415
    assert response.json()["error"]["code"] == "UNSUPPORTED_FILE_TYPE"


def test_a_pdf_must_really_be_a_pdf(api_client, auth_headers):
    response = upload(api_client, auth_headers(), "fake.pdf", b"not a pdf at all")

    assert response.status_code == 415
    assert response.json()["error"]["code"] == "UNSUPPORTED_FILE_TYPE"


def test_a_text_file_with_binary_content_is_refused(api_client, auth_headers):
    response = upload(api_client, auth_headers(), "notes.txt", b"abc\x00def")

    assert response.status_code == 415


def test_an_invalid_utf8_text_file_is_refused(api_client, auth_headers):
    response = upload(api_client, auth_headers(), "notes.txt", b"\xff\xfe\xfd")

    assert response.status_code == 415


def test_an_empty_upload_is_refused(api_client, auth_headers):
    response = upload(api_client, auth_headers(), "empty.md", b"")

    assert response.status_code == 415
    assert response.json()["error"]["code"] == "EMPTY_FILE"


def test_an_oversized_upload_is_refused(api_client, auth_headers, api_settings):
    oversized = b"a" * (api_settings.api_max_upload_bytes + 1024)
    response = upload(api_client, auth_headers(), "huge.txt", oversized)

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "FILE_TOO_LARGE"


def test_nothing_is_stored_when_the_upload_is_rejected(
    api_client, auth_headers, api_settings
):
    from pathlib import Path

    upload(
        api_client,
        auth_headers(),
        "huge.txt",
        b"a" * (api_settings.api_max_upload_bytes + 1024),
    )

    incoming = Path(api_settings.api_upload_path) / ".incoming"
    assert not incoming.exists() or not any(incoming.iterdir())


def test_a_traversal_filename_is_harmless(api_client, auth_headers, api_settings):
    root = api_client.app.state.container.settings.api_upload_path
    response = upload(api_client, auth_headers(), "../../evil.md", TEXT)

    assert response.status_code == 201
    from pathlib import Path

    stored = list((Path(root) / "alice").iterdir())
    assert stored, "the document should be stored under the caller's directory"
    assert all(str(root) in str(path) for path in stored)
    assert not (Path(root).parent / "evil.md").exists()


def test_duplicate_uploads_are_skipped(api_client, auth_headers):
    headers = auth_headers()
    first = upload(api_client, headers, "handbook.md", TEXT)
    second = upload(api_client, headers, "handbook.md", TEXT)

    assert first.status_code == 201
    assert second.status_code == 201
    assert second.json()["skipped"] is True
    documents = api_client.get("/api/v1/documents", headers=headers).json()
    assert len(documents["documents"]) == 1


def test_uploaded_documents_are_scoped_to_their_owner(api_client, auth_headers):
    alice = auth_headers()
    bob = auth_headers("bob-secret")
    upload(api_client, alice, "alice.md", b"alice exclusive notes about onboarding")

    listed_for_bob = api_client.get("/api/v1/documents", headers=bob).json()
    listed_for_alice = api_client.get("/api/v1/documents", headers=alice).json()

    assert listed_for_bob == {"documents": [], "namespaces": []}
    assert len(listed_for_alice["documents"]) == 1
    assert listed_for_alice["namespaces"] == ["u_alice"]


def test_another_users_document_cannot_be_read_or_deleted(api_client, auth_headers):
    alice = auth_headers()
    bob = auth_headers("bob-secret")
    created = upload(api_client, alice, "alice.md", TEXT).json()["document"]
    doc_id = created["doc_id"]

    assert (
        api_client.get(f"/api/v1/documents/{doc_id}", headers=bob).status_code
        == 404
    )
    assert (
        api_client.delete(f"/api/v1/documents/{doc_id}", headers=bob).status_code
        == 404
    )
    # Still Alice's.
    assert (
        api_client.get(f"/api/v1/documents/{doc_id}", headers=alice).status_code
        == 200
    )


def test_deleting_a_document(api_client, auth_headers):
    headers = auth_headers()
    created = upload(api_client, headers, "handbook.md", TEXT).json()["document"]

    response = api_client.delete(
        f"/api/v1/documents/{created['doc_id']}", headers=headers
    )

    assert response.status_code == 204
    assert api_client.get("/api/v1/documents", headers=headers).json() == {
        "documents": [],
        "namespaces": [],
    }
    assert (
        api_client.get(
            f"/api/v1/documents/{created['doc_id']}", headers=headers
        ).status_code
        == 404
    )


def test_search_after_deletion_finds_nothing(api_client, auth_headers):
    headers = auth_headers()
    created = upload(api_client, headers, "handbook.md", TEXT).json()["document"]
    api_client.delete(f"/api/v1/documents/{created['doc_id']}", headers=headers)

    container = api_client.app.state.container
    assert container.document_service.search("onboarding", owner_id="alice") == []


def test_retrieval_is_scoped_to_the_uploading_user(api_client, auth_headers):
    alice = auth_headers()
    bob = auth_headers("bob-secret")
    upload(api_client, alice, "alice.md", b"alpha handbook onboarding")
    upload(api_client, bob, "bob.md", b"beta handbook onboarding")

    container = api_client.app.state.container
    alice_hits = container.document_service.search(
        "onboarding", owner_id="alice"
    )
    bob_hits = container.document_service.search("onboarding", owner_id="bob")

    assert alice_hits and bob_hits
    assert all("beta" not in hit.content for hit in alice_hits)
    assert all("alpha" not in hit.content for hit in bob_hits)


def test_documents_require_auth(api_client):
    assert api_client.get("/api/v1/documents").status_code == 401
    assert (
        upload(api_client, {}, "handbook.md", TEXT).status_code == 401
    )


def test_a_failed_ingestion_leaves_no_orphan(api_client, auth_headers, api_settings):
    """A parser failure must clean up both the scratch and the stored file."""
    from pathlib import Path

    container = api_client.app.state.container
    original = container.document_service.ingest_file

    def explode(*args, **kwargs):
        raise RuntimeError("cannot parse this document")

    container.document_service.ingest_file = explode

    try:
        response = upload(api_client, auth_headers(), "broken.md", TEXT)
    finally:
        container.document_service.ingest_file = original

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INGEST_FAILED"

    root = Path(api_settings.api_upload_path)
    incoming = root / ".incoming"
    assert not incoming.exists() or not any(incoming.iterdir())
    assert not any((root / "alice").glob("*.md"))
