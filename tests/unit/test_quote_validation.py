from agent.summarization.quote_validation import (
    normalize_for_quote_match,
    quote_exists_in_reviews,
    validate_quotes,
)


def test_normalize_for_quote_match_collapses_whitespace() -> None:
    assert normalize_for_quote_match("  app   crashes \n often  ") == "app crashes often"


def test_quote_exists_in_reviews_uses_normalized_substring_matching() -> None:
    review_texts = ["The   app crashes often during   login."]

    assert quote_exists_in_reviews("app crashes often", review_texts) is True
    assert quote_exists_in_reviews("missing quote", review_texts) is False


def test_validate_quotes_splits_valid_and_invalid_quotes() -> None:
    valid, invalid = validate_quotes(
        ["app crashes often", "not in evidence"],
        ["The app crashes often during login."],
    )

    assert valid == ["app crashes often"]
    assert invalid == ["not in evidence"]
