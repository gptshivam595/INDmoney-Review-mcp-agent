import re

WHITESPACE_RE = re.compile(r"\s+")


def normalize_for_quote_match(value: str) -> str:
    return WHITESPACE_RE.sub(" ", value.strip())


def quote_exists_in_reviews(quote: str, review_texts: list[str]) -> bool:
    normalized_quote = normalize_for_quote_match(quote)
    if not normalized_quote:
        return False
    return any(
        normalized_quote in normalize_for_quote_match(review_text)
        for review_text in review_texts
    )


def validate_quotes(quotes: list[str], review_texts: list[str]) -> tuple[list[str], list[str]]:
    valid: list[str] = []
    invalid: list[str] = []
    for quote in quotes:
        if quote_exists_in_reviews(quote, review_texts):
            valid.append(normalize_for_quote_match(quote))
        else:
            invalid.append(quote)
    return valid, invalid
