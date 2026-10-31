"""Automated tests for Lab 03: Penny-Exact Trip Expense Splitter."""

from __future__ import annotations

from decimal import Decimal
import sys
from pathlib import Path

from pydantic import ValidationError

# Ensure the lab directory is importable regardless of current working directory
sys.path.insert(0, str(Path(__file__).resolve().parent))

from expense_splitter import (
    ExpenseItem,
    calculate_net_balances,
    settle_trip_balances,
    split_expense_exact,
)


def test_even_split_three_ways() -> None:
    """An amount evenly divisible by 3 splits into three identical shares."""
    expense = ExpenseItem(
        description="Campsite reservation",
        amount=Decimal("90.00"),
        paid_by="Maya",
        participants=["Maya", "Liam", "Noah"],
    )
    shares = split_expense_exact(expense)
    assert len(shares) == 3
    assert [s.amount_owed for s in shares] == [
        Decimal("30.00"),
        Decimal("30.00"),
        Decimal("30.00"),
    ]
    assert sum(s.amount_owed for s in shares) == expense.amount


def test_uneven_split_distributes_remainder_pennies_deterministically() -> None:
    """Splitting $100.00 three ways gives $33.34, $33.33, $33.33 (sum == $100.00)."""
    expense = ExpenseItem(
        description="Dinner in Yosemite",
        amount="100.00",
        paid_by="Maya",
        participants=["Maya", "Liam", "Noah"],
    )
    shares = split_expense_exact(expense)
    assert [s.participant for s in shares] == ["Maya", "Liam", "Noah"]
    assert [s.amount_owed for s in shares] == [
        Decimal("33.34"),
        Decimal("33.33"),
        Decimal("33.33"),
    ]
    assert sum(s.amount_owed for s in shares) == Decimal("100.00")


def test_property_penny_conservation_across_60_tricky_combinations() -> None:
    """Property check: for any amount and headcount, shares always sum to the exact total."""
    tricky_cents = [
        1, 2, 3, 7, 10, 11, 13, 17, 19, 29, 99, 100, 101, 333, 999, 1000, 1999, 5003, 9999, 12345
    ]
    headcounts = [1, 2, 3, 6, 7]

    cases_checked = 0
    for cents in tricky_cents:
        for count in headcounts:
            amount = (Decimal(cents) / Decimal(100)).quantize(Decimal("0.01"))
            participants = [f"Person_{i}" for i in range(1, count + 1)]
            expense = ExpenseItem(
                description=f"Property check {cents}c / {count}",
                amount=amount,
                paid_by="Person_1",
                participants=participants,
            )
            shares = split_expense_exact(expense)

            # Invariant 1: Sum of individual shares equals the exact receipt total
            total_shared = sum((s.amount_owed for s in shares), Decimal("0.00"))
            assert total_shared == amount, f"Lost penny for {amount} / {count}"

            # Invariant 2: No two shares differ by more than $0.01
            amounts = [s.amount_owed for s in shares]
            assert max(amounts) - min(amounts) <= Decimal("0.01")
            cases_checked += 1

    assert cases_checked == 100


def test_net_balances_and_settlement_transfers_conserve_money() -> None:
    """Net balances across multiple expenses sum to 0.00 and settle cleanly."""
    expenses = [
        ExpenseItem(
            description="Cabin rental",
            amount=Decimal("100.00"),
            paid_by="Maya",
            participants=["Maya", "Liam", "Noah"],
        ),
        ExpenseItem(
            description="Groceries",
            amount=Decimal("25.00"),
            paid_by="Liam",
            participants=["Maya", "Liam", "Noah"],
        ),
    ]

    balances = calculate_net_balances(expenses)
    # Conservation of money: net balances across all people must add up to $0.00
    assert sum(balances.values(), Decimal("0.00")) == Decimal("0.00")

    transfers = settle_trip_balances(expenses)
    # Verify that applying the settlement transfers brings everyone to $0.00
    post_settlement = dict(balances)
    for t in transfers:
        post_settlement[t.from_person] += t.amount
        post_settlement[t.to_person] -= t.amount

    for person, final_balance in post_settlement.items():
        assert final_balance == Decimal("0.00"), f"{person} left with {final_balance}"


def test_rejects_negative_and_zero_amounts() -> None:
    """Zero or negative expense amounts must raise a Pydantic ValidationError."""
    for bad_amount in ["0.00", "-15.50", Decimal("-0.01")]:
        try:
            ExpenseItem(
                description="Bad expense",
                amount=bad_amount,
                paid_by="Maya",
                participants=["Maya", "Liam"],
            )
            raise AssertionError(f"Expected ValidationError for amount={bad_amount!r}")
        except ValidationError:
            pass


def test_rejects_raw_binary_float_and_sub_cent_amounts() -> None:
    """Passing a raw float or >2 decimal places must raise a ValidationError."""
    for bad_amount in [19.99, "19.999"]:
        try:
            ExpenseItem(
                description="Float or sub-cent trap",
                amount=bad_amount,  # type: ignore[arg-type]
                paid_by="Maya",
                participants=["Maya", "Liam"],
            )
            raise AssertionError(f"Expected ValidationError for amount={bad_amount!r}")
        except ValidationError:
            pass


def test_rejects_empty_or_duplicate_participants() -> None:
    """Blank names, empty participant lists, or duplicate names must be rejected."""
    invalid_participant_lists = [
        [],
        ["   "],
        ["Maya", "maya"],
        ["Liam", "  Liam  "],
    ]
    for bad_list in invalid_participant_lists:
        try:
            ExpenseItem(
                description="Invalid participants",
                amount=Decimal("20.00"),
                paid_by="Maya",
                participants=bad_list,
            )
            raise AssertionError(f"Expected ValidationError for participants={bad_list!r}")
        except ValidationError:
            pass


if __name__ == "__main__":
    test_functions = [
        test_even_split_three_ways,
        test_uneven_split_distributes_remainder_pennies_deterministically,
        test_property_penny_conservation_across_60_tricky_combinations,
        test_net_balances_and_settlement_transfers_conserve_money,
        test_rejects_negative_and_zero_amounts,
        test_rejects_raw_binary_float_and_sub_cent_amounts,
        test_rejects_empty_or_duplicate_participants,
    ]
    passed = 0
    for fn in test_functions:
        fn()
        print(f"[PASS] {fn.__name__}")
        passed += 1
    print(f"\nAll {passed}/{len(test_functions)} Lab 03 tests passed!")
