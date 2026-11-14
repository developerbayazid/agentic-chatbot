"""Reciprocal Rank Fusion (RRF) for combining ranked retrieval results.

RRF ignores the raw score scales of the fused retrievers (cosine similarity and
BM25 are not comparable) and uses only the position of each document in each
ranked list:

    RRF(d) = sum(1 / (k + rank(d))) over every list that contains d

The constant ``k`` (default 60) damps the influence of the very top ranks so a
single retriever cannot dominate the fused ordering.
"""

from __future__ import annotations

from collections.abc import Sequence


def reciprocal_rank_fusion(
    rankings: Sequence[Sequence[int]],
    *,
    k: int = 60,
    limit: int | None = None,
) -> list[tuple[int, float]]:
    """Fuse ranked id lists into ``[(id, score), ...]`` ordered best first.

    ``rankings`` holds one best-first list of ids per retriever. An id present in
    several lists accumulates their contributions; a duplicate inside one list
    counts only once. Ties are broken deterministically by the best rank the id
    achieved, then by id, so equal scores keep a stable order.
    """
    if k < 0:
        raise ValueError("k must be non-negative")

    scores: dict[int, float] = {}
    best_rank: dict[int, int] = {}

    for ids in rankings:
        unique_ids = list(dict.fromkeys(ids))

        for rank, doc_id in enumerate(unique_ids, start=1):
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank)

            if doc_id not in best_rank or rank < best_rank[doc_id]:
                best_rank[doc_id] = rank

    fused = sorted(
        scores.items(),
        key=lambda item: (-item[1], best_rank[item[0]], item[0]),
    )

    if limit is not None:
        fused = fused[: max(0, limit)]

    return fused
