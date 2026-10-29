"""Pure payroll maths - no database, no FastAPI. Everything is ``Decimal``.

The formulas (as required by the project brief):

    Gross = Basic + HRA + Allowances + Overtime + Bonus
    Net   = Gross - PF - Tax - Other Deductions
    Other Deductions = Loss-of-pay + Professional tax + Manual deduction

Every rate, slab, ceiling and threshold comes from ``Rules`` (loaded from the
database), so nothing statutory is hardcoded here.
"""
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Optional

ZERO = Decimal("0")
TWO_PLACES = Decimal("0.01")
HUNDRED = Decimal("100")
MONTHS = Decimal("12")


def q2(value) -> Decimal:
    """Round to paise (2 decimals), half-up, the way payslips are normally rounded."""
    return Decimal(value).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class Rules:
    pf_rate: Decimal                    # % of basic, employee share
    pf_wage_ceiling: Optional[Decimal]  # None = no cap on PF wage
    employer_pf_rate: Decimal
    standard_deduction: Decimal         # annual, subtracted before slabs
    cess_percent: Decimal
    rebate_limit: Decimal               # taxable income <= this pays no tax (0 = off)
    overtime_multiplier: Decimal
    standard_hours_per_day: Decimal
    professional_tax_amount: Decimal    # flat monthly amount (0 = off)
    professional_tax_threshold: Decimal # applies when gross >= threshold
    slabs: tuple = ()                   # ((lower, upper|None, rate_percent), ...) sorted


@dataclass
class PayInputs:
    basic: Decimal                 # full-month amounts from the salary structure
    hra: Decimal
    allowances: Decimal
    pf_enabled: bool
    days_in_month: int
    active_days: int               # days the employee was on payroll this month
    working_days: int              # working days in the month (holidays/weekly-offs removed)
    lop_days: Decimal = ZERO
    overtime_hours: Decimal = ZERO
    bonus: Decimal = ZERO
    manual_deduction: Decimal = ZERO


@dataclass
class PayResult:
    basic: Decimal = ZERO
    hra: Decimal = ZERO
    allowances: Decimal = ZERO
    overtime_pay: Decimal = ZERO
    bonus: Decimal = ZERO
    gross: Decimal = ZERO
    pf: Decimal = ZERO
    tax: Decimal = ZERO
    lop_deduction: Decimal = ZERO
    professional_tax: Decimal = ZERO
    manual_deduction: Decimal = ZERO
    other_deductions: Decimal = ZERO
    net: Decimal = ZERO
    employer_pf: Decimal = ZERO
    extra: dict = field(default_factory=dict)


# --------------------------------------------------------------------------- #
def annual_tax(taxable: Decimal, rules: Rules) -> Decimal:
    """Tax on one year of taxable income using the configured slabs (+ cess).

    No rounding here - the caller rounds the final monthly figure once.
    Marginal relief around the rebate limit is intentionally not modelled.
    """
    if taxable <= 0:
        return ZERO
    if rules.rebate_limit > 0 and taxable <= rules.rebate_limit:
        return ZERO
    tax = ZERO
    for lower, upper, rate in rules.slabs:
        if taxable <= lower:
            break
        top = taxable if upper is None else min(taxable, upper)
        tax += (top - lower) * rate / HUNDRED
    return tax + tax * rules.cess_percent / HUNDRED


def compute_lop_days(
    working_dates: set,
    absent: set,
    half_days: set,
    paid_leave: set,
    unpaid_leave: set,
) -> Decimal:
    """Loss-of-pay days for one employee.

    * Absent days and unpaid-leave days count 1 day each.
    * Half-day attendance counts 0.5.
    * An approved *paid* leave covering a day cancels any loss of pay for it.
    * Only working days count (weekly-offs and holidays never cost pay).
    """
    full = ((absent | unpaid_leave) & working_dates) - paid_leave
    half = ((half_days & working_dates) - full) - paid_leave
    return Decimal(len(full)) + Decimal("0.5") * len(half)


def calculate(inp: PayInputs, rules: Rules) -> PayResult:
    if inp.days_in_month <= 0:
        raise ValueError("days_in_month must be positive")
    if not 0 <= inp.active_days <= inp.days_in_month:
        raise ValueError("active_days must be between 0 and days_in_month")

    factor = Decimal(inp.active_days) / Decimal(inp.days_in_month)  # joiners / leavers
    working_days = max(inp.working_days, 1)

    # ---- earnings -------------------------------------------------------- #
    basic = q2(inp.basic * factor)
    hra = q2(inp.hra * factor)
    allowances = q2(inp.allowances * factor)
    fixed_full = inp.basic + inp.hra + inp.allowances

    hourly_rate = inp.basic / (Decimal(working_days) * rules.standard_hours_per_day)
    overtime_pay = q2(inp.overtime_hours * hourly_rate * rules.overtime_multiplier)
    bonus = q2(inp.bonus)
    gross = basic + hra + allowances + overtime_pay + bonus

    # ---- provident fund (on basic only) ---------------------------------- #
    pf = employer_pf = ZERO
    if inp.pf_enabled:
        pf_wage = basic
        if rules.pf_wage_ceiling is not None:
            pf_wage = min(pf_wage, rules.pf_wage_ceiling)
        pf = q2(pf_wage * rules.pf_rate / HUNDRED)
        employer_pf = q2(pf_wage * rules.employer_pf_rate / HUNDRED)

    # ---- income tax (TDS projection) ------------------------------------- #
    # 1/12 of the projected annual tax on *fixed* pay, plus the extra tax that
    # this month's overtime/bonus causes. This stops one bonus from being
    # multiplied by 12 while still taxing it at the right slab.
    annual_fixed = fixed_full * MONTHS
    extra_income = overtime_pay + bonus
    taxable_base = max(ZERO, annual_fixed - rules.standard_deduction)
    taxable_with_extra = max(ZERO, annual_fixed + extra_income - rules.standard_deduction)
    tax_base = annual_tax(taxable_base, rules)
    tax_with_extra = annual_tax(taxable_with_extra, rules)
    tax = q2(tax_base / MONTHS * factor + (tax_with_extra - tax_base))

    # ---- other deductions ------------------------------------------------ #
    per_day = fixed_full / Decimal(working_days)
    fixed_earned = basic + hra + allowances
    lop_deduction = min(q2(per_day * inp.lop_days), fixed_earned)

    professional_tax = ZERO
    if rules.professional_tax_amount > 0 and gross >= rules.professional_tax_threshold > 0:
        professional_tax = q2(rules.professional_tax_amount)

    manual_deduction = q2(inp.manual_deduction)
    other = lop_deduction + professional_tax + manual_deduction

    net = gross - pf - tax - other

    return PayResult(
        basic=basic, hra=hra, allowances=allowances, overtime_pay=overtime_pay,
        bonus=bonus, gross=gross, pf=pf, tax=tax, lop_deduction=lop_deduction,
        professional_tax=professional_tax, manual_deduction=manual_deduction,
        other_deductions=other, net=net, employer_pf=employer_pf,
    )


# --------------------------------------------------------------------------- #
# Net pay in words (Indian numbering: thousand, lakh, crore) - used on payslips
# --------------------------------------------------------------------------- #
_ONES = ("Zero One Two Three Four Five Six Seven Eight Nine Ten Eleven Twelve Thirteen "
         "Fourteen Fifteen Sixteen Seventeen Eighteen Nineteen").split()
_TENS = "Zero Ten Twenty Thirty Forty Fifty Sixty Seventy Eighty Ninety".split()


def _below_hundred(n: int) -> str:
    if n < 20:
        return _ONES[n]
    return _TENS[n // 10] + (f" {_ONES[n % 10]}" if n % 10 else "")


def _below_thousand(n: int) -> str:
    if n < 100:
        return _below_hundred(n)
    rest = f" {_below_hundred(n % 100)}" if n % 100 else ""
    return f"{_ONES[n // 100]} Hundred{rest}"


def amount_in_words(amount: Decimal) -> str:
    """12345.50 -> 'Rupees Twelve Thousand Three Hundred Forty Five and Fifty Paise Only'."""
    amount = q2(amount)
    if amount < 0:
        return "Minus " + amount_in_words(-amount)
    rupees, paise = int(amount), int((amount - int(amount)) * 100)
    if rupees == 0:
        words = "Zero"
    else:
        parts = []
        for unit, size in (("Crore", 10_000_000), ("Lakh", 100_000), ("Thousand", 1_000)):
            if rupees >= size:
                parts.append(f"{_below_hundred(rupees // size)} {unit}")
                rupees %= size
        if rupees:
            parts.append(_below_thousand(rupees))
        words = " ".join(parts)
    out = f"Rupees {words}"
    if paise:
        out += f" and {_below_hundred(paise)} Paise"
    return out + " Only"