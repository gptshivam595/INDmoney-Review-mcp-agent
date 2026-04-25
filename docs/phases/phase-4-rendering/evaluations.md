# Phase 4 Evaluations - Report Rendering

## Objective

Prove that the agent can convert a `PulseReport` into deterministic Docs and Gmail artifacts without using live MCP tools yet.

## Test Matrix

| Area | Evaluation | Pass condition |
| --- | --- | --- |
| Docs rendering | render from golden `PulseReport` | heading, anchor, sections, and metadata are present |
| Email rendering | render HTML and text | concise teaser body is generated |
| Determinism | rerender same report twice | identical output bytes |
| Validation | feed malformed report object | render step fails clearly |
| Link placeholder | render before Docs publish | email contains unresolved Doc-link placeholder or field |

## Required Automated Checks

- snapshot tests for Docs payload
- snapshot tests for email HTML and text
- schema validation tests for invalid reports

## Demo

Run:

```text
pulse render --run <run_id>
```

Expected result:

- artifact directory contains Docs and email outputs
- Docs payload contains stable anchor
- email is short and ready for final link injection

## Metrics to Record

- render duration
- Docs payload size
- email HTML size
- email text size

## Exit Gate

Phase 4 passes when the agent can consistently render publish-ready artifacts from the same report input.
