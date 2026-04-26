from __future__ import annotations

import hashlib
import math
import re
from collections import Counter
from dataclasses import dataclass

from agent.analysis.preprocess import EligibleReview
from agent.models import AnalysisCluster

STOPWORDS = {
    "a",
    "an",
    "and",
    "app",
    "are",
    "be",
    "but",
    "for",
    "from",
    "has",
    "have",
    "i",
    "in",
    "is",
    "it",
    "my",
    "of",
    "on",
    "or",
    "the",
    "this",
    "to",
    "was",
    "with",
}

TOKEN_RE = re.compile(r"[a-zA-Z][a-zA-Z0-9'-]{2,}")


@dataclass(frozen=True)
class ClusterInput:
    review: EligibleReview
    embedding: list[float]


@dataclass(frozen=True)
class ClusterOutput:
    clusters: list[AnalysisCluster]
    noise_count: int


def build_clusters(
    *,
    run_id: str,
    inputs: list[ClusterInput],
    similarity_threshold: float,
    min_cluster_size: int,
) -> ClusterOutput:
    components = _connected_components(inputs, similarity_threshold)
    cluster_payloads: list[AnalysisCluster] = []
    noise_count = 0
    cluster_index = 0

    for component in components:
        if len(component) < min_cluster_size:
            noise_count += len(component)
            continue

        ordered_component = sorted(
            component,
            key=lambda item: item.review.review.review_id,
        )
        representative_review_id = _medoid_review_id(ordered_component)
        keyphrases = _extract_keyphrases(ordered_component)
        sentiment_score = _sentiment_score(ordered_component)
        review_ids = [item.review.review.review_id for item in ordered_component]
        cluster_id = hashlib.sha1(f"{run_id}:{cluster_index}".encode()).hexdigest()
        cluster_payloads.append(
            AnalysisCluster(
                cluster_id=cluster_id,
                cluster_index=cluster_index,
                review_ids=review_ids,
                review_count=len(review_ids),
                representative_review_id=representative_review_id,
                keyphrases=keyphrases,
                sentiment_score=sentiment_score,
                noise=False,
            )
        )
        cluster_index += 1

    ranked_clusters = sorted(
        cluster_payloads,
        key=lambda cluster: (
            -cluster.review_count,
            -abs(cluster.sentiment_score),
            cluster.cluster_id,
        ),
    )
    reindexed: list[AnalysisCluster] = []
    for new_index, cluster in enumerate(ranked_clusters):
        reindexed.append(cluster.model_copy(update={"cluster_index": new_index}))

    return ClusterOutput(clusters=reindexed, noise_count=noise_count)


def build_csv_fallback_clusters(
    *,
    run_id: str,
    inputs: list[ClusterInput],
    max_clusters: int = 3,
) -> ClusterOutput:
    if not inputs:
        return ClusterOutput(clusters=[], noise_count=0)

    buckets = [
        [item for item in inputs if item.review.review.rating <= 2],
        [item for item in inputs if item.review.review.rating >= 4],
        [item for item in inputs if item.review.review.rating == 3],
    ]
    non_empty_buckets = [bucket for bucket in buckets if bucket]
    if len(non_empty_buckets) <= 1:
        non_empty_buckets = [inputs]

    ranked_buckets = sorted(
        non_empty_buckets,
        key=lambda bucket: (-len(bucket), -abs(_sentiment_score(bucket))),
    )[:max_clusters]

    clusters: list[AnalysisCluster] = []
    for cluster_index, bucket in enumerate(ranked_buckets):
        ordered_bucket = sorted(
            bucket,
            key=lambda item: item.review.review.review_id,
        )
        review_ids = [item.review.review.review_id for item in ordered_bucket]
        cluster_id = hashlib.sha1(
            f"{run_id}:csv-fallback:{cluster_index}:{','.join(review_ids)}".encode()
        ).hexdigest()
        clusters.append(
            AnalysisCluster(
                cluster_id=cluster_id,
                cluster_index=cluster_index,
                review_ids=review_ids,
                review_count=len(review_ids),
                representative_review_id=_fallback_representative_review_id(ordered_bucket),
                keyphrases=_extract_keyphrases(ordered_bucket),
                sentiment_score=_sentiment_score(ordered_bucket),
                noise=False,
            )
        )
    return ClusterOutput(clusters=clusters, noise_count=0)


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if len(left) != len(right):
        msg = "Embedding dimensions must match"
        raise ValueError(msg)
    return sum(a * b for a, b in zip(left, right, strict=True))


def _connected_components(
    inputs: list[ClusterInput],
    similarity_threshold: float,
) -> list[list[ClusterInput]]:
    adjacency: dict[str, set[str]] = {
        item.review.review.review_id: set() for item in inputs
    }
    lookup = {item.review.review.review_id: item for item in inputs}

    for index, left in enumerate(inputs):
        for right in inputs[index + 1 :]:
            similarity = cosine_similarity(left.embedding, right.embedding)
            if similarity >= similarity_threshold:
                left_id = left.review.review.review_id
                right_id = right.review.review.review_id
                adjacency[left_id].add(right_id)
                adjacency[right_id].add(left_id)

    components: list[list[ClusterInput]] = []
    seen: set[str] = set()
    for review_id in sorted(adjacency):
        if review_id in seen:
            continue
        stack = [review_id]
        component_ids: list[str] = []
        while stack:
            current = stack.pop()
            if current in seen:
                continue
            seen.add(current)
            component_ids.append(current)
            stack.extend(sorted(adjacency[current] - seen))
        components.append([lookup[current_id] for current_id in sorted(component_ids)])
    return components


def _medoid_review_id(component: list[ClusterInput]) -> str:
    best_id = component[0].review.review.review_id
    best_score = -math.inf
    for candidate in component:
        score = 0.0
        for other in component:
            score += cosine_similarity(candidate.embedding, other.embedding)
        candidate_id = candidate.review.review.review_id
        if score > best_score or (score == best_score and candidate_id < best_id):
            best_id = candidate_id
            best_score = score
    return best_id


def _fallback_representative_review_id(component: list[ClusterInput]) -> str:
    return max(
        component,
        key=lambda item: (
            len(item.review.normalized_text),
            item.review.review.review_id,
        ),
    ).review.review.review_id


def _extract_keyphrases(component: list[ClusterInput], limit: int = 5) -> list[str]:
    counter: Counter[str] = Counter()
    for item in component:
        for token in TOKEN_RE.findall(item.review.normalized_text.lower()):
            if token in STOPWORDS:
                continue
            counter[token] += 1
    return [token for token, _count in counter.most_common(limit)]


def _sentiment_score(component: list[ClusterInput]) -> float:
    rating_values = [item.review.review.rating - 3 for item in component]
    return sum(rating_values) / len(rating_values)
