"""Reciprocal Rank Fusion math and ordering."""

import pytest

from agentic_chatbot.rrf import reciprocal_rank_fusion


def test_scores_follow_the_rrf_formula():
    fused = reciprocal_rank_fusion([[1, 2]], k=60)

    assert fused == [
        (1, pytest.approx(1 / 61)),
        (2, pytest.approx(1 / 62)),
    ]


def test_a_chunk_in_both_lists_accumulates_scores():
    fused = reciprocal_rank_fusion([[1, 2], [2, 3]], k=60)
    scores = dict(fused)

    assert scores[2] == pytest.approx(1 / 62 + 1 / 61)
    assert scores[1] == pytest.approx(1 / 61)
    assert scores[3] == pytest.approx(1 / 62)
    assert [doc_id for doc_id, _ in fused] == [2, 1, 3]


def test_duplicates_within_one_list_count_once():
    fused = reciprocal_rank_fusion([[1, 1, 1], [1]], k=60)

    assert fused == [(1, pytest.approx(1 / 61 + 1 / 61))]


def test_duplicate_does_not_advance_the_rank_of_later_items():
    fused = reciprocal_rank_fusion([[7, 7, 8]], k=60)
    scores = dict(fused)

    assert scores[7] == pytest.approx(1 / 61)
    assert scores[8] == pytest.approx(1 / 62)


def test_empty_result_lists_are_safe():
    assert reciprocal_rank_fusion([]) == []
    assert reciprocal_rank_fusion([[], []]) == []


def test_ties_are_broken_stably_by_best_rank_then_id():
    fused = reciprocal_rank_fusion([[1], [2]], k=60)

    assert [doc_id for doc_id, _ in fused] == [1, 2]


def test_equal_scores_break_ties_by_id():
    # 9 and 8 both rank first in their own list, so they tie on score and best
    # rank; the id makes the order deterministic and stable across runs.
    fused = reciprocal_rank_fusion([[9, 3], [8, 1]], k=60)

    assert [doc_id for doc_id, _ in fused] == [8, 9, 1, 3]
    assert fused[0][1] == pytest.approx(fused[1][1])


def test_limit_keeps_the_top_results():
    fused = reciprocal_rank_fusion([[1, 2, 3, 4]], k=60, limit=2)

    assert [doc_id for doc_id, _ in fused] == [1, 2]


def test_negative_k_is_rejected():
    with pytest.raises(ValueError):
        reciprocal_rank_fusion([[1]], k=-1)


def test_k_zero_uses_plain_reciprocal_rank():
    fused = reciprocal_rank_fusion([[1, 2]], k=0)

    assert fused[0][1] == pytest.approx(1.0)
    assert fused[1][1] == pytest.approx(0.5)
