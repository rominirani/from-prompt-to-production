# Lab 03: Stopping Bad Data & Catching Bugs Automatically (`Pydantic` & `pytest`)

Welcome to **Lab 03**! In this lab, we build a **Penny-Exact Trip Expense Splitter** that solves two of the most common bugs in AI-generated financial code:
1. **Unvalidated input data** (negative amounts, blank names, duplicate participants, or binary floating-point rounding glitches).
2. **Lost pennies** when splitting an odd total (like `$10.00` three ways) across a group of friends.

## What You'll Learn
- Why Python's `float` (`0.1 + 0.2 == 0.30000000000000004`) should never be used for money, and how `decimal.Decimal` fixes it.
- How to enforce strict data rules at the boundary using **Pydantic v2** (`BaseModel`, `Field`, `@field_validator`, `ConfigDict`).
- How to write fast, automated unit tests and **property-based invariant checks** using `pytest`.

## Files in This Lab
- `expense_splitter.py` — The Pydantic v2 models (`ExpenseItem`, `SplitShare`, `SettlementTransfer`) and penny-exact splitting and settlement functions.
- `test_expense_splitter.py` — Automated test suite verifying valid splits, `ValidationError` guardrails, and a 60-case property check ensuring pennies are never created or lost.

## How to Run the Lab

Run the automated test suite from the repository root:

```bash
uv run python labs/lab03-data-and-tests/test_expense_splitter.py
```

Or run `pytest` directly:

```bash
uv run pytest labs/lab03-data-and-tests/test_expense_splitter.py
```

You can also run the splitter demo directly:

```bash
uv run python labs/lab03-data-and-tests/expense_splitter.py
```
