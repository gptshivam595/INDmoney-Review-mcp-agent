# Phase 6 Edge Cases - Gmail MCP Delivery

## Cases to Handle

- Docs publish never produced a deep link
- Gmail MCP search fails before create
- draft creation succeeds but send fails
- duplicate message exists but local DB is missing message id
- recipient list is empty or invalid
- email body exceeds expected length
- Gmail headers or labels are unsupported by the chosen server

## Expected Handling

- block Gmail publish if the Doc destination is unknown
- rely on external search plus local state for dedupe
- preserve draft id if send fails after draft creation
- validate recipients before MCP call
- degrade gracefully if custom headers are unsupported, but keep another run-scoped dedupe strategy
