from decimal import Decimal


MAX_COUNT_VALUE = Decimal("9999999999999999.99")


# Calculate cases x Qty/Case + pieces and variance using Decimal. Troubleshoot: inputs and database numeric limits.
def calculate_final_count(cases, pieces, qty_per_case, old_qty):
    total = (Decimal(cases) * Decimal(qty_per_case)) + Decimal(pieces)
    variance = total - Decimal(old_qty)

    if abs(total) > MAX_COUNT_VALUE or abs(variance) > MAX_COUNT_VALUE:
        raise ValueError("The calculated count exceeds the database field limit.")

    return total, variance

