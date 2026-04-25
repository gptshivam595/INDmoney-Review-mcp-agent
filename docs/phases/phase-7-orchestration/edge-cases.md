# Phase 7 Edge Cases - Orchestration and Hardening

## Cases to Handle

- scheduler triggers the same product twice
- run crashes after Docs publish but before Gmail publish
- run crashes after Gmail draft creation but before local state update
- live source volume drops sharply week over week
- MCP server goes down mid-run
- LLM provider becomes unavailable
- backfill overlaps with scheduled run for same product and week
- artifact write fails while DB update succeeds

## Expected Handling

- enforce one active run per `product + iso_week`
- resume from checkpoint instead of replaying completed delivery work
- surface anomaly alerts for major data drops
- apply bounded retries for transient failures
- keep local state and external delivery reconciliation explicit
- fail loudly when reconciliation is not possible
