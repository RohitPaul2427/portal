"""Pure unit tests for the governance foundation (no DB, no server)."""
from datetime import datetime, timezone

from core.governance import payroll_rules as pr
from core.governance.access import MAX_DAYS_BY_RISK, clamp_valid_to, sod_conflicts, sod_violations_for, DEFAULT_SOD_RULES
from core.governance.audit_chain import GENESIS_HASH, _body_of, compute_hash
from core.governance.feature_registry import stage_allows
from core.governance.statutory import period_end

R = dict(pr.DEFAULT_RULES)
R25 = {**R, "pf.wage_ceiling_inr": 25000}


# ── PF ────────────────────────────────────────────────────────────────
def test_pf_capped_at_old_ceiling():
    assert pr.pf_contribution(40000, R)["employee"] == 1800   # 12% of 15,000


def test_pf_capped_at_new_ceiling():
    out = pr.pf_contribution(40000, R25)
    assert out["pf_wages"] == 25000 and out["employee"] == 3000 and out["employer"] == 3000


def test_pf_below_ceiling_uses_actual_wages():
    assert pr.pf_contribution(12000, R25)["employee"] == 1440


def test_pf_uncapped_when_company_pays_on_full_wages():
    assert pr.pf_contribution(40000, {**R25, "pf.restrict_to_ceiling": False})["employee"] == 4800


# ── ESI ───────────────────────────────────────────────────────────────
def test_esi_applies_at_exact_threshold():
    out = pr.esi_contribution(21000, R)
    assert out["applicable"] and out["employee"] == 158 and out["employer"] == 683   # rounded up


def test_esi_not_applicable_above_threshold():
    assert not pr.esi_contribution(21001, R)["applicable"]


# ── Labour-code 50% wage rule ─────────────────────────────────────────
def test_wage_rule_compliant_structure():
    out = pr.deemed_wages({"basic": 25000, "hra": 12500, "special_allowance": 12500})
    assert out["compliant"] and out["add_back"] == 0 and out["deemed_wages"] == 25000


def test_wage_rule_adds_back_excess_allowances():
    # total 50,000; basic 15,000 -> wages must be 25,000 -> add back 10,000
    out = pr.deemed_wages({"basic": 15000, "hra": 20000, "special_allowance": 15000})
    assert out["add_back"] == 10000 and out["deemed_wages"] == 25000 and not out["compliant"]


def test_wage_rule_counts_custom_components():
    out = pr.deemed_wages({"basic": 10000, "custom": [{"name": "x", "amount": 10000}]})
    assert out["total_remuneration"] == 20000 and out["add_back"] == 0


# ── Maharashtra professional tax ──────────────────────────────────────
def test_pt_men_slabs():
    assert pr.professional_tax(7500, R, "male") == 0
    assert pr.professional_tax(9000, R, "male") == 175
    assert pr.professional_tax(30000, R, "male") == 200


def test_pt_women_exempt_up_to_25000():
    assert pr.professional_tax(25000, R, "female") == 0
    assert pr.professional_tax(25001, R, "female") == 200


def test_pt_february_top_slab():
    assert pr.professional_tax(30000, R, "male", month=2) == 300
    assert pr.professional_tax(9000, R, "male", month=2) == 175


def test_period_end_handles_leap_year():
    assert period_end("2028-02") == "2028-02-29"
    assert period_end("2026-09") == "2026-09-30"


# ── Payslip integration (pure function in routers/payroll.py) ─────────
def test_payslip_uses_new_ceiling_and_auto_pt():
    from routers.payroll import _compute_payslip
    structure = {"components": {"basic": 30000, "hra": 15000, "special_allowance": 15000},
                 "deductions": {"pf_employee_pct": 12, "pf_employer_pct": 12, "professional_tax_inr": 200}}
    slip = _compute_payslip(structure, {"lwp_days": 0}, 0, 0, rules=R25, gender="male", month=2)
    assert slip["deductions"]["pf_employee"] == 3000
    assert slip["deductions"]["professional_tax"] == 300
    assert slip["deductions"]["esi_employee"] == 0
    assert slip["statutory"]["pf_ceiling_inr"] == 25000


def test_payslip_manual_pt_override_is_kept():
    from routers.payroll import _compute_payslip
    structure = {"components": {"basic": 30000}, "deductions": {"professional_tax_inr": 150}}
    assert _compute_payslip(structure, {}, 0, 0, rules=R25)["deductions"]["professional_tax"] == 150


# ── Separation of duties ──────────────────────────────────────────────
def test_sod_detects_new_conflict():
    c = sod_conflicts({"commission.slabs_manager"}, "commission.payouts_queue", DEFAULT_SOD_RULES)
    assert [x["id"] for x in c] == ["sod-commission-slab-vs-payout"]


def test_sod_no_conflict_for_unrelated_feature():
    assert sod_conflicts({"commission.slabs_manager"}, "hr.leave_types", DEFAULT_SOD_RULES) == []


def test_sod_inactive_rule_ignored():
    rules = [{**DEFAULT_SOD_RULES[0], "active": False}]
    assert sod_conflicts({"commission.slabs_manager"}, "commission.payouts_queue", rules) == []


def test_sod_violations_report():
    v = sod_violations_for({"hr.salary_structures", "hr.payroll_admin"}, DEFAULT_SOD_RULES)
    assert v and v[0]["id"] == "sod-salary-vs-payroll"


# ── Grant duration limits ─────────────────────────────────────────────
def test_critical_access_is_capped_to_7_days():
    start = datetime(2026, 10, 1, tzinfo=timezone.utc)
    assert (clamp_valid_to("critical", start, 90) - start).days == MAX_DAYS_BY_RISK["critical"] == 7


def test_default_duration_is_the_max_for_risk():
    start = datetime(2026, 10, 1, tzinfo=timezone.utc)
    assert (clamp_valid_to("medium", start, None) - start).days == 180


# ── Rollout stages ────────────────────────────────────────────────────
def test_stage_rules():
    u = {"id": "u1", "department": "sales"}
    assert stage_allows({"stage": "company"}, u)
    assert not stage_allows({"stage": "development"}, u)
    assert stage_allows({"stage": "pilot", "pilot_user_ids": ["u1"]}, u)
    assert not stage_allows({"stage": "pilot", "pilot_user_ids": ["u2"]}, u)
    assert stage_allows({"stage": "department", "departments": ["sales"]}, u)
    assert not stage_allows({"stage": "department", "departments": ["hr"]}, u)
    assert not stage_allows({"stage": "retired"}, u)


# ── Audit hash chain ──────────────────────────────────────────────────
def test_hash_changes_when_content_changes():
    doc = {"id": "1", "seq": 1, "action": "x", "meta": {"a": 1}, "at": datetime(2026, 1, 1, tzinfo=timezone.utc)}
    h1 = compute_hash(GENESIS_HASH, _body_of(doc))
    h2 = compute_hash(GENESIS_HASH, _body_of({**doc, "meta": {"a": 2}}))
    assert h1 != h2 and len(h1) == 64


def test_hash_depends_on_previous_hash():
    doc = {"id": "1", "seq": 1, "action": "x"}
    assert compute_hash(GENESIS_HASH, _body_of(doc)) != compute_hash("f" * 64, _body_of(doc))
