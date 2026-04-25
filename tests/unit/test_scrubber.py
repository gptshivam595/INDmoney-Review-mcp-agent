from agent.ingestion.scrubber import scrub_pii


def test_scrub_pii_redacts_email_phone_and_aadhaar() -> None:
    scrubbed = scrub_pii(
        "Email me at test.user@example.com, phone +91 9876543210, Aadhaar 1234 5678 9012."
    )

    assert "[REDACTED_EMAIL]" in scrubbed
    assert "[REDACTED_PHONE]" in scrubbed
    assert "[REDACTED_AADHAAR]" in scrubbed

