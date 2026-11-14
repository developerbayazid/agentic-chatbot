"""Per-namespace FAISS index behaviour."""

import pytest

from agentic_chatbot.vector_store import VectorIndexStore

NS_A = "alpha"
NS_B = "beta"


@pytest.fixture
def store(tmp_path):
    return VectorIndexStore(tmp_path / "faiss", dimensions=2)


def test_add_and_search_round_trip(store):
    store.add(NS_A, [10, 20], [[1.0, 0.0], [0.0, 1.0]])

    hits = store.search([NS_A], [1.0, 0.0], k=1)

    assert hits[0][0] == 10
    assert hits[0][1] == pytest.approx(1.0, abs=1e-5)


def test_one_file_per_namespace(tmp_path, store):
    store.add(NS_A, [1], [[1.0, 0.0]])
    store.add(NS_B, [2], [[0.0, 1.0]])

    assert store.path_for(NS_A) != store.path_for(NS_B)
    assert store.path_for(NS_A).exists()
    assert store.path_for(NS_B).exists()


def test_search_is_scoped_to_requested_namespaces(store):
    store.add(NS_A, [1], [[1.0, 0.0]])
    store.add(NS_B, [2], [[1.0, 0.0]])

    hits = store.search([NS_A], [1.0, 0.0], k=5)

    assert [row_id for row_id, _ in hits] == [1]


def test_search_merges_namespaces_by_score(store):
    store.add(NS_A, [1], [[1.0, 0.0]])
    store.add(NS_B, [2], [[0.0, 1.0]])

    hits = store.search([NS_A, NS_B], [1.0, 0.0], k=2)

    assert hints_ids(hits) == [1, 2]
    assert hits[0][1] > hits[1][1]


def test_replace_removes_old_ids_and_adds_new(store):
    store.add(NS_A, [1, 2], [[1.0, 0.0], [0.0, 1.0]])
    store.replace(NS_A, [1], [3], [[1.0, 0.0]])

    ids = hints_ids(store.search([NS_A], [1.0, 0.0], k=10))

    assert 1 not in ids
    assert sorted(ids) == [2, 3]


def test_remove_deletes_the_index_file_when_empty(store):
    store.add(NS_A, [1], [[1.0, 0.0]])
    path = store.path_for(NS_A)

    store.remove(NS_A, [1])

    assert not path.exists()
    assert store.search([NS_A], [1.0, 0.0], k=5) == []


def test_index_survives_a_new_store_instance(tmp_path):
    store = VectorIndexStore(tmp_path / "faiss", dimensions=2)
    store.add(NS_A, [1], [[1.0, 0.0]])

    reopened = VectorIndexStore(tmp_path / "faiss", dimensions=2)

    assert hints_ids(reopened.search([NS_A], [1.0, 0.0], k=1)) == [1]


def test_dimension_mismatch_on_load_raises(tmp_path):
    store = VectorIndexStore(tmp_path / "faiss", dimensions=2)
    store.add(NS_A, [1], [[1.0, 0.0]])

    other = VectorIndexStore(tmp_path / "faiss", dimensions=3)

    with pytest.raises(RuntimeError, match="dimension"):
        other.search([NS_A], [1.0, 0.0, 0.0], k=1)


def test_add_rejects_wrong_vector_width(store):
    with pytest.raises(ValueError, match="columns"):
        store.add(NS_A, [1], [[1.0, 0.0, 0.0]])


def test_empty_operations_are_no_ops(tmp_path):
    store = VectorIndexStore(tmp_path / "faiss", dimensions=2)

    store.add(NS_A, [], [])
    store.remove(NS_A, [])
    assert store.search([], [1.0, 0.0], k=3) == []
    assert store.search([NS_A], [1.0, 0.0], k=0) == []


def test_stats_reports_loaded_indexes(store):
    store.add(NS_A, [1, 2], [[1.0, 0.0], [0.0, 1.0]])

    assert store.stats() == {NS_A: 2}


def hints_ids(hits):
    return [row_id for row_id, _ in hits]
