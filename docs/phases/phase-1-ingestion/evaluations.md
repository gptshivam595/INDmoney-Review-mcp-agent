# Phase 1 Evaluations - Review Ingestion and Normalization

## Objective

Prove that the agent can fetch recent public reviews, normalize them into one contract, scrub PII, and persist them without duplication.

## Test Matrix

| Area | Evaluation | Pass condition |
| --- | --- | --- |
| App Store ingestion | replay stored feed fixtures | expected review rows are created |
| Play Store ingestion | replay stored response fixtures | expected review rows are created |
| Normalization | compare both sources against `RawReview` schema | all fields conform |
| Scrubbing | run input containing emails and phone numbers | PII is removed from `body_scrubbed` |
| Deduplication | rerun same window twice | no duplicate review rows appear |
| Audit snapshot | inspect raw snapshot artifact | source payloads are persisted |

## Required Automated Checks

- fixture-based unit tests for both fetchers
- property or table-driven tests for scrubber patterns
- integration test for dedupe on repeated ingest

## Demo

Run:

```text
pulse ingest --product indmoney --weeks 10
```

Expected result:

- reviews are inserted or updated
- raw snapshot file is written
- output reports inserts, updates, and skipped duplicates

## Metrics to Record

- reviews fetched per source
- reviews inserted
- reviews updated
- scrubber match count
- ingest duration

## Exit Gate

Phase 1 passes when the agent can reliably populate the review store for at least one product and rerun safely without data duplication.
