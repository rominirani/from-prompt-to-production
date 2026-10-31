# Lab 01: Receipt & Note JSON Extractor (`google-genai` + Structured Outputs)

This lab accompanies [Chapter 1: How Gemini Actually Works (and Your First Steps in Google AI Studio)](../../chapters/ch01-how-gemini-works-ai-studio.md).

## What This Lab Demonstrates
1. Using the official **`google-genai`** SDK (`from google import genai`) with `gemini-3-flash-preview`.
2. Setting **System Instructions**, low **Temperature (`0.1`)**, and **Structured Outputs (`response_schema`)** with a **Pydantic v2** model so Gemini always returns clean, validated JSON.
3. Combining AI text extraction with exact Python arithmetic (`verify_receipt_math`) so your app never trusts raw LLM math blindly.
4. Safe API key handling (`os.environ.get("GEMINI_API_KEY")`) with a built-in offline parser fallback so you can run and test the lab with or without an active internet connection.

## How to Run
From the repository root:

```bash
# Run the demo script
uv run python labs/lab01-ai-studio-basics/receipt_extractor.py

# Run the automated tests
uv run python labs/lab01-ai-studio-basics/test_receipt_extractor.py
```
