"""Lab 03: Trip Budget & Penny-Exact Expense Splitter.

Demonstrates Python 3.12+ type hints, exact monetary arithmetic with Decimal,
and strict input validation with Pydantic v2.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

PENNY = Decimal("0.01")


class ExpenseItem(BaseModel):
    """A single validated trip expense paid by one person for a group."""

    model_config = ConfigDict(str_strip_whitespace=True, frozen=True)

    description: str = Field(
        ...,
        min_length=1,
        max_length=120,
        description="Short description of the expense (e.g., 'Cabin groceries').",
    )
    amount: Decimal = Field(
        ...,
        gt=Decimal("0.00"),
        description="Total expense amount in dollars and cents (must be > 0).",
    )
    paid_by: str = Field(
        ...,
        min_length=1,
        max_length=60,
        description="Name of the person who paid the bill.",
    )
    participants: list[str] = Field(
        ...,
        min_length=1,
        description="Ordered list of people sharing this expense.",
    )

    @field_validator("amount", mode="before")
    @classmethod
    def validate_and_quantize_amount(cls, value: Any) -> Decimal:
        """Reject binary floats and normalize valid inputs to exact cents."""
        if isinstance(value, float):
            raise ValueError(
                "Do not pass a float for money (binary floats cause rounding bugs). "
                "Pass a string like '19.99' or Decimal('19.99') instead."
            )
        try:
            decimal_val = Decimal(str(value))
        except (InvalidOperation, ValueError, TypeError) as exc:
            raise ValueError(f"Invalid monetary amount: {value!r}") from exc

        quantized = decimal_val.quantize(PENNY, rounding=ROUND_HALF_UP)
        if quantized != decimal_val:
            raise ValueError(
                f"Amount {value!r} cannot have more than 2 decimal places."
            )
        return quantized

    @field_validator("participants")
    @classmethod
    def validate_participants(cls, raw_list: list[str]) -> list[str]:
        """Ensure participant names are non-empty and unique."""
        cleaned: list[str] = []
        seen: set[str] = set()
        for name in raw_list:
            stripped = name.strip()
            if not stripped:
                raise ValueError("Participant names cannot be empty or blank.")
            normalized = stripped.lower()
            if normalized in seen:
                raise ValueError(
                    f"Duplicate participant '{stripped}' is not allowed in the same expense."
                )
            seen.add(normalized)
            cleaned.append(stripped)
        return cleaned


class SplitShare(BaseModel):
    """One participant's exact dollar-and-cent share of an ExpenseItem."""

    model_config = ConfigDict(frozen=True)

    participant: str
    amount_owed: Decimal


class SettlementTransfer(BaseModel):
    """A single payment from one person to another to settle the trip."""

    model_config = ConfigDict(frozen=True)

    from_person: str
    to_person: str
    amount: Decimal


def split_expense_exact(expense: ExpenseItem) -> list[SplitShare]:
    """Split an expense across participants without losing or inventing pennies.

    Any remainder cents (when total_cents is not evenly divisible by the number
    of participants) are distributed one cent at a time to the first
    `remainder_cents` participants in `expense.participants`.
    """
    total_cents = int((expense.amount * 100).to_integral_exact())
    num_people = len(expense.participants)
    base_cents, remainder_cents = divmod(total_cents, num_people)

    shares: list[SplitShare] = []
    for index, person in enumerate(expense.participants):
        extra_cent = 1 if index < remainder_cents else 0
        person_cents = base_cents + extra_cent
        person_amount = (Decimal(person_cents) / Decimal(100)).quantize(PENNY)
        shares.append(SplitShare(participant=person, amount_owed=person_amount))

    return shares


def calculate_net_balances(expenses: list[ExpenseItem]) -> dict[str, Decimal]:
    """Compute each person's net balance across all trip expenses.

    A positive balance means the person is owed money overall.
    A negative balance means the person owes money overall.
    The sum of all net balances is guaranteed to equal Decimal('0.00').
    """
    balances: dict[str, Decimal] = {}

    for expense in expenses:
        balances.setdefault(expense.paid_by, Decimal("0.00"))
        balances[expense.paid_by] += expense.amount

        for share in split_expense_exact(expense):
            balances.setdefault(share.participant, Decimal("0.00"))
            balances[share.participant] -= share.amount_owed

    return balances


def settle_trip_balances(expenses: list[ExpenseItem]) -> list[SettlementTransfer]:
    """Calculate the exact transfers needed so every participant settles to $0.00."""
    net_balances = calculate_net_balances(expenses)

    debtors: list[list[Any]] = []
    creditors: list[list[Any]] = []

    for person in sorted(net_balances.keys()):
        balance = net_balances[person]
        if balance < Decimal("0.00"):
            debtors.append([person, -balance])
        elif balance > Decimal("0.00"):
            creditors.append([person, balance])

    transfers: list[SettlementTransfer] = []
    d_idx = 0
    c_idx = 0

    while d_idx < len(debtors) and c_idx < len(creditors):
        debtor_name, debt_amount = debtors[d_idx]
        creditor_name, credit_amount = creditors[c_idx]

        transfer_amount = min(debt_amount, credit_amount).quantize(PENNY)
        if transfer_amount > Decimal("0.00"):
            transfers.append(
                SettlementTransfer(
                    from_person=debtor_name,
                    to_person=creditor_name,
                    amount=transfer_amount,
                )
            )

        debtors[d_idx][1] -= transfer_amount
        creditors[c_idx][1] -= transfer_amount

        if debtors[d_idx][1] == Decimal("0.00"):
            d_idx += 1
        if creditors[c_idx][1] == Decimal("0.00"):
            c_idx += 1

    return transfers


if __name__ == "__main__":
    sample_expenses = [
        ExpenseItem(
            description="Dinner in Yosemite",
            amount=Decimal("100.00"),
            paid_by="Maya",
            participants=["Maya", "Liam", "Noah"],
        ),
        ExpenseItem(
            description="Campfire firewood & s'mores",
            amount=Decimal("25.00"),
            paid_by="Liam",
            participants=["Maya", "Liam", "Noah"],
        ),
    ]

    print("--- Exact Shares for Dinner ($100.00 / 3) ---")
    for share in split_expense_exact(sample_expenses[0]):
        print(f"  {share.participant}: ${share.amount_owed}")

    print("\n--- Final Settlement Transfers ---")
    for transfer in settle_trip_balances(sample_expenses):
        print(f"  {transfer.from_person} pays {transfer.to_person}: ${transfer.amount}")
