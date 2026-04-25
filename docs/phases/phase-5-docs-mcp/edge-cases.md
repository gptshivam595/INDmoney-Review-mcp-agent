# Phase 5 Edge Cases - Google Docs MCP Append

## Cases to Handle

- running Doc does not exist yet
- Docs MCP server is unreachable
- pre-append document read succeeds but append fails
- append succeeds but response lacks heading id
- anchor search finds multiple matches
- rendered payload is incompatible with server tool schema
- user reruns publish after a partial timeout

## Expected Handling

- create the Doc when safe and configured
- fail before Gmail if Docs publish is not confirmed
- use read-before-write and read-after-write to recover from uncertainty
- persist fallback link information even when heading metadata is limited
- treat multiple anchor matches as a data integrity problem and stop
