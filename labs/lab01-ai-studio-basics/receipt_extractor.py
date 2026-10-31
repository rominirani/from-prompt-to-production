"""Chapter 1 Lab: Structured Receipt & Note Extractor using Google Gemini (`google-genai`).

This module shows how to turn messy text notes or receipt text into a guaranteed,
type-checked Pydantic object using Gemini's Structured Outputs (`response_schema`),
and then verify the extracted arithmetic in plain Python.
"""

from __future__ import annotations

import os
import re
from decimal import Decimal
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from google import genai
from google.genai import types
from pydantic import BaseModel, ConfigDict, Field

# Load environment variables from .env if present (never hardcode API keys in code!)
load_dotenv()

SYSTEM_INSTRUCTION = (
    "You are a careful bookkeeping assistant. Extract receipt details into the requested "
    "JSON schema. Never invent line items that are not in the input text. Format dates as "
    "YYYY-MM-DD when possible."
)

SAMPLE_RECEIPT_NOTE = """\
Sunrise Cafe - Seattle WA
Date: 2026-05-14
2x Oat Milk Latte @ $5.50 each
1x Blueberry Muffin @ $4.25 each
1x Avocado Toast @ $9.75 each
Tax: $2.50
Total Paid: $27.50 (Visa)
"""


class ReceiptLineItem(BaseModel):
    """A single item purchased on a receipt."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, description="Name of the item purchased")
    quantity: int = Field(ge=1, description="Quantity purchased (must be at least 1)")
    unit_price: Decimal = Field(
        ge=Decimal("0.00"), description="Price for a single unit in dollars"
    )

    @property
    def line_total(self) -> Decimal:
        """Calculate exact item subtotal using Decimal arithmetic."""
        return (self.unit_price * Decimal(self.quantity)).quantize(Decimal("0.01"))


class ReceiptExtraction(BaseModel):
    """Structured receipt data returned by Gemini."""

    model_config = ConfigDict(extra="forbid")

    merchant_name: str = Field(min_length=1, description="Name of the store or vendor")
    receipt_date: str = Field(description="Date on the receipt in YYYY-MM-DD format")
    items: list[ReceiptLineItem] = Field(
        min_length=1, description="Line items listed on the receipt"
    )
    tax: Decimal = Field(ge=Decimal("0.00"), description="Tax amount on the receipt")
    total_paid: Decimal = Field(
        ge=Decimal("0.00"), description="Final total printed on the receipt"
    )
    payment_method: str = Field(
        default="Unknown", description="Payment method such as Visa, Cash, Mastercard, etc."
    )


class ReceiptVerificationReport(BaseModel):
    """Result of checking Gemini's extracted numbers with exact Python math."""

    receipt: ReceiptExtraction
    computed_subtotal: Decimal
    computed_grand_total: Decimal
    discrepancy: Decimal
    is_math_consistent: bool


def verify_receipt_math(receipt: ReceiptExtraction) -> ReceiptVerificationReport:
    """Verify in plain Python whether the extracted items + tax equal the printed total."""
    subtotal = sum((item.line_total for item in receipt.items), Decimal("0.00")).quantize(
        Decimal("0.01")
    )
    grand_total = (subtotal + receipt.tax.quantize(Decimal("0.01"))).quantize(Decimal("0.01"))
    printed_total = receipt.total_paid.quantize(Decimal("0.01"))
    discrepancy = (printed_total - grand_total).quantize(Decimal("0.01"))

    return ReceiptVerificationReport(
        receipt=receipt,
        computed_subtotal=subtotal,
        computed_grand_total=grand_total,
        discrepancy=discrepancy,
        is_math_consistent=(discrepancy == Decimal("0.00")),
    )


def _offline_parse_receipt_text(raw_text: str) -> ReceiptExtraction:
    """Deterministic local parser used when running tests offline without a GEMINI_API_KEY."""
    lines = [line.strip() for line in raw_text.strip().splitlines() if line.strip()]
    if not lines:
        raise ValueError("Receipt text cannot be empty.")

    merchant_name = lines[0]
    receipt_date = "Unknown"
    tax = Decimal("0.00")
    total_paid = Decimal("0.00")
    payment_method = "Unknown"
    items: list[ReceiptLineItem] = []

    item_pattern = re.compile(
        r"^(?P<qty>\d+)x\s+(?P<name>.+?)\s+@?\s*\$(?P<price>\d+(?:\.\d{1,2})?)(?:\s+each)?$",
        re.IGNORECASE,
    )

    for line in lines[1:]:
        if line.lower().startswith("date:"):
            receipt_date = line.split(":", 1)[1].strip()
            continue

        if line.lower().startswith("tax:"):
            match = re.search(r"\$(?P<tax>\d+(?:\.\d{1,2})?)", line)
            if match:
                tax = Decimal(match.group("tax"))
            continue

        if line.lower().startswith("total"):
            match = re.search(r"\$(?P<total>\d+(?:\.\d{1,2})?)", line)
            if match:
                total_paid = Decimal(match.group("total"))
            pm_match = re.search(r"\((?P<method>[^)]+)\)", line)
            if pm_match:
                payment_method = pm_match.group("method").strip()
            continue

        item_match = item_pattern.match(line)
        if item_match:
            items.append(
                ReceiptLineItem(
                    name=item_match.group("name").strip(),
                    quantity=int(item_match.group("qty")),
                    unit_price=Decimal(item_match.group("price")),
                )
            )

    if not items:
        raise ValueError("Could not find any valid line items in the receipt note.")

    return ReceiptExtraction(
        merchant_name=merchant_name,
        receipt_date=receipt_date,
        items=items,
        tax=tax,
        total_paid=total_paid,
        payment_method=payment_method,
    )


def extract_receipt_from_text(
    raw_receipt_text: str,
    *,
    api_key: Optional[str] = None,
    model_name: str = "gemini-3-flash-preview",
    force_offline: bool = False,
) -> ReceiptExtraction:
    """Extract structured receipt data using Gemini Structured Outputs (`google-genai`).

    If `force_offline=True` or no `GEMINI_API_KEY` is set in the environment, falls back
    to the local deterministic parser so learners can run tests before creating an API key.
    """
    if not raw_receipt_text or not raw_receipt_text.strip():
        raise ValueError("raw_receipt_text must not be empty.")

    resolved_key = api_key if api_key is not None else os.environ.get("GEMINI_API_KEY", "").strip()
    if force_offline or not resolved_key or resolved_key == "your_gemini_api_key_here":
        return _offline_parse_receipt_text(raw_receipt_text)

    client = genai.Client(api_key=resolved_key)
    response = client.models.generate_content(
        model=model_name,
        contents=raw_receipt_text,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_INSTRUCTION,
            temperature=0.1,
            response_mime_type="application/json",
            response_schema=ReceiptExtraction,
        ),
    )

    if not response.text:
        raise RuntimeError("Gemini returned an empty response.")

    return ReceiptExtraction.model_validate_json(response.text)


def build_multimodal_receipt_part(image_path: str | Path, mime_type: str = "image/jpeg") -> types.Part:
    """Create a `google-genai` multimodal Part from a local receipt photo Safely.

    Validates that the file exists and is within a safe 5 MB size limit.
    """
    resolved = Path(image_path).resolve()
    if not resolved.is_file():
        raise FileNotFoundError(f"Receipt image not found: {resolved.name}")

    max_bytes = 5 * 1024 * 1024
    file_size = resolved.stat().st_size
    if file_size > max_bytes:
        raise ValueError(f"Receipt image exceeds 5 MB limit ({file_size} bytes).")

    allowed_mimes = {"image/jpeg", "image/png", "image/webp", "application/pdf"}
    if mime_type not in allowed_mimes:
        raise ValueError(f"Unsupported mime_type '{mime_type}'. Allowed: {sorted(allowed_mimes)}")

    return types.Part.from_bytes(data=resolved.read_bytes(), mime_type=mime_type)


if __name__ == "__main__":
    print("=== Chapter 1 Lab: Structured Receipt Extractor ===")
    extracted = extract_receipt_from_text(SAMPLE_RECEIPT_NOTE)
    report = verify_receipt_math(extracted)
    print(report.model_dump_json(indent=2))
