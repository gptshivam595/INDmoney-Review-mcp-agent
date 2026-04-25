# Phase 4 Edge Cases - Report Rendering

## Cases to Handle

- missing top themes
- empty quote list
- oversized quote text that breaks layout
- special characters that need escaping in HTML
- missing Doc link at render time
- invalid or missing section anchor
- unsupported Docs payload shape for chosen MCP server

## Expected Handling

- fail fast on malformed report structure
- escape user text correctly in HTML and Docs payloads
- keep pre-publish email render separate from final link injection
- validate anchor presence before producing publish artifacts
