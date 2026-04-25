# Phase 2 Edge Cases - Analysis Pipeline

## Cases to Handle

- too few reviews to form clusters
- all reviews collapse into noise
- embedding provider outage
- embedding vector dimension mismatch
- duplicate scrubbed texts across many reviews
- extremely long review bodies
- cluster seeds produce unstable assignments

## Expected Handling

- fail with a clear "insufficient data" outcome instead of fabricating clusters
- fall back to configured local embedding provider if supported
- reject corrupted embedding data before clustering
- cap or truncate oversized text consistently before embedding
- record instability as a test failure, not an acceptable runtime drift
