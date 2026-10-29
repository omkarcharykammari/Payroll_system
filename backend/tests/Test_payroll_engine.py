"""Unit tests for the pure payroll maths (no database). Expected values are hand-calculated."""
from datetime import date
from decimal import Decimal as D

import pytest

from payroll_engine import PayInputs, Rules, amount_in_words, calculate, compute_lop_days

SLABS = ((D(0), D(400000), D(0)), (D(400000), D(800000), D(5)), (D(800000), D(1200000), D(10)),
         (D(1200000), D(1600000), D(15)), (D(1600000), D(2000000), D(20)),
         (D(2000000), D(2400000), D(25)), (D(2400000), None, D(30)))

RULES = Rules(pf_rate=D(12), pf_wage_ceiling=None, employer_pf_rate=D(12), standard_deduction=D(75000),
              cess_percent=D(4), rebate_limit=D(1200000), overtime_multiplier=D("1.5"),
              standard_hours_per_day=D(8), professional_tax_amount=D(200),
              professional_tax_threshold=D(25000), slabs=SLABS)


def run(rules=RULES, **kw):
    base = dict(basic=D(100000), hra=D(40000), allowances=D(60000), pf_enabled=True,
                days_in_month=31, active_days=31, working_days=22)
    base.update(kw)
    return calculate(PayInputs(**base), rules)


def test_gross_net_tax_for_a_high_earner():
    r = run()                       # 2.4M a year -> taxable 2,325,000 -> 281,250 + 4% cess = 292,500
    assert r.gross == D("200000.00")
    assert r.pf == D("12000.00")
    assert r.tax == D("24375.00")   # 292,500 / 12
    assert r.professional_tax == D("200.00")
    assert r.net == r.gross - r.pf - r.tax - r.other_deductions == D("163425.00")


def test_rebate_means_no_tax_at_or_below_the_limit():
    assert run(basic=D(50000), hra=D(20000), allowances=D(30000)).tax == D("0.00")


def test_overtime_pay():
    r = run(basic=D(50000), hra=D(0), allowances=D(0), overtime_hours=D(10))
    assert r.overtime_pay == D("4261.36")          # 50000 / (22*8) * 10 * 1.5
    assert r.gross == D("54261.36")


def test_loss_of_pay_is_a_deduction_not_a_gross_change():
    r = run(working_days=20, lop_days=D(2))        # 200000 / 20 = 10000 per day
    assert r.lop_deduction == D("20000.00")
    assert r.gross == D("200000.00")
    assert r.other_deductions == D("20200.00")     # LOP + professional tax


def test_mid_month_joiner_is_prorated():
    r = run(days_in_month=30, active_days=15)
    assert r.basic == D("50000.00") and r.gross == D("100000.00")


def test_bonus_is_taxed_at_the_marginal_slab_once_not_times_twelve():
    assert run(bonus=D(100000)).tax - run().tax == D("27300.00")   # (75000*25% + 25000*30%) * 1.04


def test_pf_ceiling_and_pf_switch():
    capped = Rules(**{**RULES.__dict__, "pf_wage_ceiling": D(15000)})
    assert run(rules=capped, basic=D(100000), hra=D(0), allowances=D(0)).pf == D("1800.00")
    assert run(pf_enabled=False).pf == D("0.00")


def test_lop_day_counting():
    d = lambda n: date(2026, 9, n)
    work = {d(n) for n in range(1, 31) if d(n).weekday() < 5}
    # absent 1st+2nd, half-day 3rd, unpaid leave 4th, paid leave covers the 2nd
    assert compute_lop_days(work, {d(1), d(2)}, {d(3)}, {d(2)}, {d(4)}) == D("2.5")
    assert compute_lop_days(work, {d(5)}, set(), set(), set()) == D("0")   # a Saturday never costs pay


@pytest.mark.parametrize("bad", [dict(days_in_month=0), dict(active_days=40)])
def test_invalid_calendar_inputs_are_rejected(bad):
    with pytest.raises(ValueError):
        run(**bad)


def test_amount_in_words():
    assert amount_in_words(D("163425")) == "Rupees One Lakh Sixty Three Thousand Four Hundred Twenty Five Only"
    assert amount_in_words(D("12345.50")).endswith("Forty Five and Fifty Paise Only")
    assert amount_in_words(D("25000000")).startswith("Rupees Two Crore Fifty Lakh")