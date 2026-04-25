from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

from agent.analysis.clustering import ClusterInput, build_clusters
from agent.analysis.embeddings import embedding_sha1, load_embedding_provider
from agent.analysis.preprocess import preprocess_reviews
from agent.config import RuntimeSettings
from agent.models import AnalysisCluster, AnalysisResult, RunRecord, RunStatus
from agent.storage import (
    fetch_reviews_for_run,
    get_cached_embedding,
    replace_clusters_for_run,
    update_run_analysis_result,
    update_run_status,
    upsert_review_embedding,
)


def analyze_run(
    *,
    settings: RuntimeSettings,
    database_path: Path,
    run: RunRecord,
) -> AnalysisResult:
    update_run_status(database_path, run.run_id, RunStatus.ANALYZING)
    try:
        reviews = fetch_reviews_for_run(database_path, run)
        eligible_reviews, filtered_reviews = preprocess_reviews(
            reviews,
            min_review_length=settings.analysis_min_review_length,
        )
        if len(eligible_reviews) < settings.analysis_min_cluster_size:
            msg = "Insufficient eligible reviews for analysis"
            raise RuntimeError(msg)

        provider = load_embedding_provider(settings)
        inputs: list[ClusterInput] = []
        cache_hits = 0
        cache_misses = 0
        for eligible in eligible_reviews:
            sha = embedding_sha1(eligible.normalized_text)
            cached_embedding = get_cached_embedding(
                database_path=database_path,
                review_id=eligible.review.review_id,
                embedding_model=provider.model_name,
                embedding_sha1=sha,
            )
            if cached_embedding is None:
                vector = provider.embed(eligible.normalized_text)
                cache_misses += 1
                upsert_review_embedding(
                    database_path=database_path,
                    review_id=eligible.review.review_id,
                    embedding_model=provider.model_name,
                    embedding_sha1=sha,
                    vector=vector,
                )
            else:
                vector = cached_embedding
                cache_hits += 1
            inputs.append(ClusterInput(review=eligible, embedding=vector))

        clustering_output = build_clusters(
            run_id=run.run_id,
            inputs=inputs,
            similarity_threshold=settings.analysis_similarity_threshold,
            min_cluster_size=settings.analysis_min_cluster_size,
        )
        if not clustering_output.clusters:
            msg = "Analysis produced only noise clusters"
            raise RuntimeError(msg)

        artifact_path = _write_analysis_artifact(
            base_directory=settings.resolve_database_path().parent / "artifacts",
            run_id=run.run_id,
            clusters=clustering_output.clusters,
        )
        result = AnalysisResult(
            run_id=run.run_id,
            product_key=run.product_key,
            iso_week=run.iso_week,
            eligible_reviews=len(eligible_reviews),
            filtered_reviews=filtered_reviews,
            clusters_formed=len(clustering_output.clusters),
            noise_reviews=clustering_output.noise_count,
            embedding_cache_hits=cache_hits,
            embedding_cache_misses=cache_misses,
            embedding_model=provider.model_name,
            artifact_path=str(artifact_path),
            clusters=clustering_output.clusters,
        )
        replace_clusters_for_run(database_path, run.run_id, clustering_output.clusters)
        update_run_analysis_result(database_path, run.run_id, result)
        return result
    except Exception as exc:
        update_run_status(database_path, run.run_id, RunStatus.FAILED, error_message=str(exc))
        raise


def _write_analysis_artifact(
    *,
    base_directory: Path,
    run_id: str,
    clusters: Sequence[AnalysisCluster],
) -> Path:
    artifact_dir = base_directory / run_id
    artifact_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = artifact_dir / "clusters.json"
    payload = [cluster.model_dump(mode="json") for cluster in clusters]
    artifact_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return artifact_path
