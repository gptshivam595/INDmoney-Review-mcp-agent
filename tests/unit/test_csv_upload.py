from agent.ingestion.csv_upload import parse_uploaded_csv_reviews


def test_parse_uploaded_csv_reviews_accepts_flexible_headers() -> None:
    csv_text = """id,stars,review,review_date,language
1,5,"Great onboarding and fast account setup.",2026-04-20,en-IN
2,1,"App crashes during login and support is slow.",2026-04-21,en-IN
"""

    reviews = parse_uploaded_csv_reviews(
        csv_text=csv_text,
        product_key="indmoney",
        upload_id="upload-123",
    )

    assert len(reviews) == 2
    assert reviews[0].product_key == "indmoney"
    assert reviews[0].source == "csv-upload-upload123"
    assert reviews[0].rating == 5
    assert reviews[0].body_raw == "Great onboarding and fast account setup."
    assert reviews[0].locale == "en-IN"


def test_parse_uploaded_csv_reviews_requires_review_text() -> None:
    csv_text = """id,rating,date
1,5,2026-04-20
"""

    try:
        parse_uploaded_csv_reviews(
            csv_text=csv_text,
            product_key="indmoney",
            upload_id="upload-123",
        )
    except ValueError as exc:
        assert "review text column" in str(exc)
    else:
        raise AssertionError("Expected missing review text column to raise ValueError")
