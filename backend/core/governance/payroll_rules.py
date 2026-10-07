"""E16-03/04 - Pure Indian payroll calculation helpers (no DB, fully unit-tested).

All rates/thresholds come in through a ``rules`` dict built by
``core.governance.statutory.payroll_rules_for(period)`` so a rate change is a
data change (effective-dated), never a code change.

IMPORTANT: these implement the commonly applied reading of the rules. Have
your Chartered Accountant / labour-law adviser confirm each value in the
statutory settings before the first live payroll run.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

# Fallbacks used only if the statutory_settings collection is empty.
DEFAULT_RULES: Dict[str, Any] = {
    "pf.wage_ceiling_inr": 15000,
    "pf.employee_pct": 12.0,
    "pf.employer_pct": 12.0,
    "pf.restrict_to_ceiling": True,
    "esi.gross_threshold_inr": 21000,
    "esi.employee_pct": 0.75,
    "esi.employer_pct": 3.25,
    "labour_code.min_wage_pct": 50.0,
    "labour_code.apply_wage_rule": True,
    "pt.state": "MH",
    "pt.MH": {
        "male": [[7500, 0], [10000, 175], [None, 200]],
        "female": [[25000, 0], [None, 200]],
        "february_top_slab_inr": 300,
    },
}

# Components that count as "wages" under the Code on Wages / Social Security
# (basic + dearness allowance + retaining allowance). Everything else in gross
# is an exclusion for the 50% test.
WAGE_COMPONENTS = ("basic", "da", "dearness_allowance", "retaining_allowance")


def deemed_wages(components: Dict[str, Any], min_pct: float = 50.0) -> Dict[str, int]:
    """Labour-code 50% rule: if exclusions exceed 50% of total remuneration,
    the excess is added back to wages for PF / gratuity / ESI purposes."""
    wages = sum(int(components.get(k, 0) or 0) for k in WAGE_COMPONENTS)
    total = sum(int(v or 0) for k, v in components.items() if k != "custom" and isinstance(v, (int, float)))
    total += sum(int(c.get("amount", 0) or 0) for c in (components.get("custom") or []))
    exclusions = total - wages
    allowed_exclusions = total * (100 - min_pct) / 100
    add_back = int(round(max(0, exclusions - allowed_exclusions)))
    return {"wages": wages, "total_remuneration": total, "exclusions": exclusions,
            "add_back": add_back, "deemed_wages": wages + add_back,
            "compliant": add_back == 0}


def pf_contribution(pf_wages: int, rules: Dict[str, Any], emp_pct: Optional[float] = None,
                    er_pct: Optional[float] = None) -> Dict[str, int]:
    ceiling = int(rules.get("pf.wage_ceiling_inr", 15000))
    base = min(pf_wages, ceiling) if rules.get("pf.restrict_to_ceiling", True) else pf_wages
    e = rules.get("pf.employee_pct", 12.0) if emp_pct is None else emp_pct
    r = rules.get("pf.employer_pct", 12.0) if er_pct is None else er_pct
    return {"pf_wages": base, "employee": int(round(base * e / 100)), "employer": int(round(base * r / 100)),
            "ceiling": ceiling}


def esi_contribution(gross: int, rules: Dict[str, Any], emp_pct: Optional[float] = None,
                     er_pct: Optional[float] = None) -> Dict[str, Any]:
    threshold = int(rules.get("esi.gross_threshold_inr", 21000))
    if gross > threshold:          # covered up to and including the threshold
        return {"applicable": False, "employee": 0, "employer": 0, "threshold": threshold}
    e = rules.get("esi.employee_pct", 0.75) if emp_pct is None else emp_pct
    r = rules.get("esi.employer_pct", 3.25) if er_pct is None else er_pct
    # ESIC rounds contributions UP to the next rupee.
    import math
    return {"applicable": True, "employee": int(math.ceil(gross * e / 100)),
            "employer": int(math.ceil(gross * r / 100)), "threshold": threshold}


def professional_tax(gross: int, rules: Dict[str, Any], gender: Optional[str] = None,
                     month: Optional[int] = None, state: Optional[str] = None) -> int:
    """Slab-based PT. Slabs are [[upper_limit_or_None, amount], ...] ascending."""
    st = state or rules.get("pt.state", "MH")
    table = rules.get(f"pt.{st}")
    if not table:
        return 0
    g = "female" if (gender or "").lower() in ("f", "female", "woman") else "male"
    slabs = table.get(g) or table.get("male") or []
    amount = 0
    for upper, amt in slabs:
        if upper is None or gross <= upper:
            amount = int(amt)
            break
    top = slabs[-1][1] if slabs else 0
    if month == 2 and amount and amount == top and table.get("february_top_slab_inr"):
        amount = int(table["february_top_slab_inr"])
    return amount
