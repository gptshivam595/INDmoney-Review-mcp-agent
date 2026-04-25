# Phase 0 Edge Cases - Foundations and Agent Skeleton

## Cases to Handle

- missing `products.yaml`
- malformed product entry
- missing environment variable for required runtime setting
- DB file path points to a non-writable directory
- duplicate `product_key` values in config
- invalid ISO week input
- time zone parsing failure
- rerunning `init-db` on an already initialized database

## Expected Handling

- fail fast with a clear error for config and environment problems
- never create partial schema silently
- make `init-db` safe to rerun
- reject invalid week input before any run row is written
- include actionable error text in CLI output and logs
