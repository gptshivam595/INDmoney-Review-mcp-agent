# Phase 2 Evaluations - Analysis Pipeline

## Objective

Prove that the agent can transform stored reviews into stable, useful clusters for downstream summarization.

## Test Matrix

| Area | Evaluation | Pass condition |
| --- | --- | --- |
| Preprocessing | feed mixed-language and short reviews | unsupported or too-short reviews are excluded |
| Embeddings | run batch embed twice on same fixture | second run uses cache |
| Clustering | analyze golden review fixture | cluster count falls in expected range |
| Determinism | rerun with fixed seeds | assignments are stable |
| Ranking | inspect stored representatives | each non-noise cluster has representative evidence |

## Required Automated Checks

- unit tests for preprocessing filters
- unit tests for embedding cache keys
- integration test for stable cluster assignments on fixture input

## Demo

Run:

```text
pulse analyze --run <run_id>
```

Expected result:

- clusters are persisted
- noise reviews are counted separately
- representative review ids are available

## Metrics to Record

- number of eligible reviews
- embedding cache hit rate
- number of clusters
- noise ratio
- analysis duration

## Exit Gate

Phase 2 passes when the agent consistently produces a reasonable and stable cluster set from the same stored reviews.
