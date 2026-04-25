# Phase 3 Edge Cases - Summarization and Grounding

## Cases to Handle

- LLM returns malformed JSON
- LLM returns themes with no supporting evidence
- quote text is paraphrased rather than verbatim
- quote validation passes only after whitespace normalization
- no valid quotes remain after validation
- action ideas are empty or generic
- model timeout or rate limit
- cost cap is exceeded mid-run

## Expected Handling

- retry once only where safe and useful
- reject output that cannot be grounded
- preserve enough raw response context for debugging
- fail loudly when minimum report quality cannot be met
- do not silently publish a report with invented quotes
