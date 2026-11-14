"""BM25 keyword search over the SQLite chunk table."""

import pytest

from agentic_chatbot.bm25_store import BM25IndexStore, tokenize
from agentic_chatbot.database import create_connection, init_schema
from agentic_chatbot.models import Chunk
from agentic_chatbot.repository import DocumentsRepository


@pytest.fixture
def context(tmp_path):
    connection = create_connection(str(tmp_path / "bm25.db"))
    init_schema(connection)
    repository = DocumentsRepository(connection)
    store = BM25IndexStore(repository)

    try:
        yield repository, store
    finally:
        connection.close()


def _add(repository, namespace, source, chunks):
    _, row_ids = repository.replace_document(
        namespace, source, source.removesuffix(".md"), "hash", 0,
        [Chunk(content=text) for text in chunks],
    )
    return row_ids


def test_tokenize_lowercases_and_splits_identifiers():
    assert tokenize("Employee EMP-1042 joined") == [
        "employee",
        "emp",
        "1042",
        "joined",
    ]


def test_exact_keyword_match_ranks_the_matching_chunk_first(context):
    repository, store = context
    matching, other = _add(
        repository,
        "handbook",
        "handbook.md",
        ["onboarding starts on monday", "vacation policy is generous"],
    )

    hits = store.search(["handbook"], "onboarding", k=5)

    assert hits
    assert hits[0][0] == matching
    assert hits[0][1] > 0
    assert other not in [row_id for row_id, _ in hits]


def test_technical_terminology_matches(context):
    repository, store = context
    (row_id,) = _add(
        repository,
        "engineering",
        "notes.md",
        ["Retrieval augmented generation fuses BM25 and cosine similarity"],
    )

    hits = store.search(["engineering"], "BM25 cosine", k=5)

    assert [hit[0] for hit in hits] == [row_id]


def test_employee_id_and_product_codes_match(context):
    repository, store = context
    (employee_id,) = _add(
        repository,
        "people",
        "people.md",
        ["Alice Smith, employee EMP-1042, joined in 2021"],
    )
    (product_id,) = _add(
        repository,
        "products",
        "products.md",
        ["SKU-9931 is the wireless keyboard"],
    )

    employee_hits = store.search(["people"], "EMP-1042", k=5)
    product_hits = store.search(["products"], "SKU-9931", k=5)

    assert [hit[0] for hit in employee_hits] == [employee_id]
    assert [hit[0] for hit in product_hits] == [product_id]


def test_empty_query_returns_nothing(context):
    repository, store = context
    _add(repository, "handbook", "handbook.md", ["alpha beta"])

    assert store.search(["handbook"], "   ", k=5) == []
    assert store.search(["handbook"], "!!!", k=5) == []


def test_empty_namespace_returns_nothing(context):
    repository, store = context
    _add(repository, "handbook", "handbook.md", ["alpha beta"])

    assert store.search(["empty"], "alpha", k=5) == []


def test_unknown_namespace_returns_nothing(context):
    repository, store = context

    assert store.search(["does-not-exist"], "alpha", k=5) == []


def test_no_matching_documents_returns_nothing(context):
    repository, store = context
    _add(repository, "handbook", "handbook.md", ["alpha beta"])

    assert store.search(["handbook"], "zebra", k=5) == []


def test_search_spans_multiple_namespaces(context):
    repository, store = context
    first = _add(repository, "alpha", "a.md", ["shared keyword text"])[0]
    second = _add(repository, "beta", "b.md", ["shared keyword text"])[0]

    hits = store.search(["alpha", "beta"], "shared keyword", k=10)

    assert sorted(row_id for row_id, _ in hits) == sorted([first, second])


def test_results_are_limited_to_k(context):
    repository, store = context
    _add(
        repository,
        "handbook",
        "handbook.md",
        ["alpha one", "alpha two", "alpha three"],
    )

    assert len(store.search(["handbook"], "alpha", k=2)) == 2


def test_k_must_be_positive(context):
    repository, store = context
    _add(repository, "handbook", "handbook.md", ["alpha"])

    assert store.search(["handbook"], "alpha", k=0) == []


def test_index_rebuilds_after_ingest(context):
    repository, store = context
    _add(repository, "handbook", "handbook.md", ["alpha"])
    assert store.search(["handbook"], "zebra", k=5) == []

    new_id = _add(
        repository,
        "handbook",
        "handbook.md",
        ["alpha", "zebra crossing"],
    )[1]

    assert [hit[0] for hit in store.search(["handbook"], "zebra", k=5)] == [
        new_id
    ]


def test_reingest_does_not_leave_stale_chunks(context):
    repository, store = context
    _add(repository, "handbook", "handbook.md", ["obsolete wording"])
    assert store.search(["handbook"], "obsolete", k=5)

    _add(repository, "handbook", "handbook.md", ["replacement wording"])

    assert store.search(["handbook"], "obsolete", k=5) == []
    assert store.search(["handbook"], "replacement", k=5)


def test_deletion_removes_results(context):
    repository, store = context
    _add(repository, "handbook", "a.md", ["alpha"])
    document = repository.find_by_source("handbook", "a.md")

    repository.delete_document(document.doc_id)

    assert store.search(["handbook"], "alpha", k=5) == []


def test_a_store_with_no_documents_is_safe(context):
    _, store = context

    assert store.search(["anything"], "alpha", k=5) == []
    assert store.stats() == {}


def test_invalidate_drops_cached_namespaces(context):
    repository, store = context
    _add(repository, "handbook", "handbook.md", ["alpha"])
    store.search(["handbook"], "alpha", k=5)
    assert store.stats() == {"handbook": 1}

    store.invalidate("handbook")

    assert store.stats() == {}
    assert store.search(["handbook"], "alpha", k=5)


def test_new_store_instance_rebuilds_from_sqlite(context):
    repository, store = context
    _add(repository, "handbook", "handbook.md", ["alpha"])

    reopened = BM25IndexStore(repository)

    assert reopened.search(["handbook"], "alpha", k=5)
