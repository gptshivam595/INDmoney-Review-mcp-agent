# Phase 3 Evaluations - Summarization and Grounding

## Objective

Prove that the agent can turn clusters into a grounded `PulseReport` with validated quotes and useful action ideas.

## Test Matrix

| Area | Evaluation | Pass condition |
| --- | --- | --- |
| Structured output | mock LLM returns valid schema | `PulseReport` parses successfully |
| Quote grounding | compare returned quotes to scrubbed reviews | every quote is a real substring |
| Retry path | first quote attempt invalid, second valid | repair succeeds and is recorded |
| Cost control | simulate token overrun | run stops with explicit cost error |
| Report completeness | golden fixture summarization | minimum theme and quote counts are met |

## Required Automated Checks

- unit tests for quote validator
- unit tests for prompt-to-schema parsing
- integration test for end-to-end summary generation using mocked model responses

## Demo

Run:

```text
pulse summarize --run <run_id>
```

Expected result:

- `PulseReport` artifact is written
- report contains themes, quotes, actions, and `who_this_helps`
- token and cost metrics are stored

## Metrics to Record

- theme count
- valid quote count
- quote rejection count
- tokens used
- estimated cost
- summarization duration

## Exit Gate

Phase 3 passes when the agent can reliably generate a grounded weekly report and reject invalid or ungrounded model output.
