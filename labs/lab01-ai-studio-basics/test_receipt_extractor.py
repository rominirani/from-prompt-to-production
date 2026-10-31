"""Automated tests for Chapter 1 Lab (`receipt_extractor.py`).

Run with pytest:
    uv run pytest labs/lab01-ai-studio-basics/test_receipt_extractor.py
Or directly with Python:
    uv run python labs/lab01-ai-studio-basics/test_receipt_extractor.py
"""

from __future__ import annotations

import tempfile
from decimal import Decimal
from pathlib import Path

from pydantic import ValidationError

from receipt_extractor import (
    SAMPLE_RECEIPT_NOTE,
    ReceiptExtraction,
    ReceiptLineItem,
    build_multimodal_receipt_part,
    extract_receipt_from_text,
    verify_receipt_math,
)


def test_extract_sample_receipt_offline() -> None:
    """Extracting the sample cafe receipt produces a valid ReceiptExtraction object."""
    receipt = extract_receipt_from_text(SAMPLE_RECEIPT_NOTE, force_offline=True)
    assert receipt.merchant_name == "Sunrise Cafe - Seattle WA"
    assert receipt.receipt_date == "2026-05-14"
    assert len(receipt.items) == 3
    assert receipt.items[0].name == "Oat Milk Latte"
    assert receipt.items[0].quantity == 2
    assert receipt.items[0].line_total == Decimal("11.00")
    assert receipt.tax == Decimal("2.50")
    assert receipt.total_paid == Decimal("27.50")
    assert receipt.payment_method == "Visa"


def test_verify_receipt_math_consistent() -> None:
    """When items + tax equal total_paid, is_math_consistent is True and discrepancy is 0.00."""
    receipt = extract_receipt_from_text(SAMPLE_RECEIPT_NOTE, force_offline=True)
    report = verify_receipt_math(receipt)
    assert report.computed_subtotal == Decimal("25.00")
    assert report.computed_grand_total == Decimal("27.50")
    assert report.discrepancy == Decimal("0.00")
    assert report.is_math_consistent is True


def test_verify_receipt_math_catches_bad_total() -> None:
    """When a receipt has an arithmetic error (or AI hallucinated total), Python catches it."""
    bad_note = """\
Corner Market
Date: 2026-05-15
2x Sandwich @ $8.00 each
Tax: $1.60
Total Paid: $25.00 (Cash)
"""
    receipt = extract_receipt_from_text(bad_note, force_offline=True)
    report = verify_receipt_math(receipt)
    assert report.computed_subtotal == Decimal("16.00")
    assert report.computed_grand_total == Decimal("17.60")
    assert report.discrepancy == Decimal("7.40")
    assert report.is_math_consistent is False


def test_pydantic_rejects_invalid_quantity_or_negative_price() -> None:
    """Pydantic schema rejects zero quantity or negative unit prices."""
    try:
        ReceiptLineItem(name="Espresso", quantity=0, unit_price=Decimal("3.50"))
        raise AssertionError("Expected ValidationError for quantity=0")
    except ValidationError:
        pass

    try:
        ReceiptLineItem(name="Espresso", quantity=1, unit_price=Decimal("-1.00"))
        raise AssertionError("Expected ValidationError for negative unit_price")
    except ValidationError:
        pass


def test_multimodal_part_builder_validates_mime_and_file() -> None:
    """build_multimodal_receipt_part creates a google.genai Part and rejects disallowed MIME types."""
    with tempfile.NamedTemporaryFile(suffix=".jpg") as tmp:
        tmp.write(b"\xff\xd8\xff\xe0fake-jpeg-bytes")
        tmp.flush()
        part = build_multimodal_receipt_part(Path(tmp.name), mime_type="image/jpeg")
        assert part.inline_data is not None
        assert part.inline_data.mime_type == "image/jpeg"

        try:
            build_multimodal_receipt_part(Path(tmp.name), mime_type="application/x-sh")
            raise AssertionError("Expected ValueError for disallowed mime_type")
        except ValueError:
            pass


def test_json_roundtrip_matches_response_schema() -> None:
    """Verify ReceiptExtraction can serialize to JSON and validate back identically."""
    receipt = extract_receipt_from_text(SAMPLE_RECEIPT_NOTE, force_offline=True)
    raw_json = receipt.model_dump_json()
    restored = ReceiptExtraction.model_validate_json(raw_json)
    assert restored == receipt


if __name__ == "__main__":
    test_functions = [
        test_extract_sample_receipt_offline,
        test_verify_receipt_math_consistent,
        test_verify_receipt_math_catches_bad_total,
        test_pydantic_rejects_invalid_quantity_or_negative_price,
        test_multimodal_part_builder_validates_mime_and_file,
        test_json_roundtrip_matches_response_schema,
    ]
    for fn in test_functions:
        fn()
        print(f"  [PASS] {fn.__name__}")
    print(f"\nAll {len(test_functions)} tests in Lab 01 passed!")
