# Phase 1 Edge Cases - Review Ingestion and Normalization

## Cases to Handle

- source returns zero reviews in the selected window
- source returns malformed or partially missing fields
- same review appears multiple times across pages
- review body is empty or whitespace only
- review language is unsupported or missing
- network timeout mid-pagination
- one source succeeds and the other fails
- PII scrubber removes the entire body

## Expected Handling

- store the run as failed or partial ingestion, not silently successful, when mandatory source work fails
- skip malformed reviews with structured warnings when safe
- dedupe repeated reviews deterministically
- keep raw payload for audit even when a review is skipped
- allow zero-review runs only if that state is explicit and logged
