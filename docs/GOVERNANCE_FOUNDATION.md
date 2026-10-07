# Employee Portal — Governance Foundation (Backlog Phase 0–1)

This release adds the base layer that every later HRMS, payroll, sales and IT module
depends on. It is **additive**: existing screens and APIs keep working.

## What is included

| Backlog | What it does | Where |
|---|---|---|
| E02-05 | Real login sessions. Logout ends the token at once; "log out other devices"; admin can see and end any session | `core/governance/sessions.py` |
| E03-01 | Tamper-evident audit trail. Every event is hash-chained; one click verifies nothing was edited or deleted | `core/governance/audit_chain.py` |
| E04-01/02/05 | Feature registry (148 features), owner, risk, rollout stage (development → pilot → department → company → retired) and a kill switch | `core/governance/feature_registry.py` |
| E05/E06 | Access requests with approval steps by risk (manager → feature owner → security), time-limited grants, automatic expiry every 15 min | `core/governance/access.py` |
| E06-02 | Maker-checker: nobody approves their own request, a request for themselves, or two steps of one request | `access.can_approve_step` |
| E06-04 | Separation-of-duties rules (5 seeded) checked when access is granted, plus a report of people who already hold conflicting powers | `access.DEFAULT_SOD_RULES` |
| E07-02 | Leaver lock-out: deactivating a person ends all sessions, revokes grants, cancels requests and blocks the token immediately | `access.offboard_user` |
| E15 | Payroll maker-checker: the person who generated a payslip cannot approve it, and nobody approves their own payslip | `routers/payroll.py` |
| E16-01 | Effective-dated statutory settings (PF, ESI, PT, TDS section/form numbers). History is never overwritten | `core/governance/statutory.py` |
| E16-03/04 | Payroll now uses the **₹25,000 EPF wage ceiling from 17 Sep 2026**, the labour-code 50% wage rule, ESI up to and including ₹21,000, and Maharashtra PT slabs (₹300 in February) | `core/governance/payroll_rules.py` |
| — | Fixed: magic-link and OTP login responses were returning the user's password hash | `routers/pre_assess_portal.py` |
| UI | **Access & Security Center** at `/access-center` (link above *Logout* in the sidebar) | `frontend/src/pages/portal/AccessCenter.jsx` |

All new endpoints are under `/api/governance/…` (see the docstring at the top of
`backend/routers/governance.py`).

## Payroll changes to check with your CA before the next run

These change payslip numbers. They follow the published rules, but **have your Chartered
Accountant confirm them** on a staging copy before using them in production.

1. **PF ceiling** — wage months ending on or after 17 Sep 2026 use ₹25,000 (was ₹15,000).
   An employee with basic ≥ ₹25,000 now has PF of ₹3,000 instead of ₹1,800 (employee and
   employer each).
2. **50% wage rule** — if allowances are more than half of gross, the excess is added back to
   PF wages. Example: basic 15,000 + HRA 20,000 + special 15,000 → PF wages 25,000.
   Turn off with statutory key `labour_code.apply_wage_rule = false` if your CA advises.
3. **Professional tax** — structures that still have the old default ₹200 are now calculated
   from Maharashtra slabs (₹0 / ₹175 / ₹200, ₹300 in February; women exempt up to ₹25,000).
   Any other amount you typed in is kept as a manual override.
4. **ESI** — applies when gross is **up to and including** ₹21,000 (was "below"), and
   contributions are rounded up to the next rupee.

Every payslip now stores a `statutory` block showing the PF wages, ceiling and wage-rule
result that were used, so any number can be explained later.

## Test on staging before going live

### 1. Make a staging copy (never test on the live database)

```bash
# on the server
mongodump --uri "$MONGO_URL" --db leamss --out /backup/pre-governance-$(date +%F)
mongorestore --uri "$MONGO_URL" --nsFrom 'leamss.*' --nsTo 'leamss_staging.*' /backup/pre-governance-$(date +%F)
```

### 2. Run the new code against the copy

```bash
cd /srv/portal && git fetch && git checkout feat/employee-portal-foundation
cd backend && source venv/bin/activate && pip install -r requirements.txt
export DB_NAME=leamss_staging JWT_SECRET=... CORS_ORIGINS=https://staging.leamss.com
python -m migrations.run_all          # creates indexes + seeds registry, SoD rules, statutory rows
uvicorn server:app --host 127.0.0.1 --port 8101
```

Look for this line in the output: `[Governance] {'features_inserted': 148, 'sod_rules_inserted': 5, 'statutory_rows_inserted': 18}`.
On a second run all three numbers are 0 (seeding never overwrites your edits).

### 3. Automated checks

```bash
cd backend
pytest -q tests/unit                                   # 30 pure tests, no server needed
API_BASE_URL=http://127.0.0.1:8101 TEST_ADMIN_PASSWORD='<staging admin password>' \
  pytest -q tests/test_security_hardening.py tests/test_governance_api.py
```

The API tests create throw-away users named `gov-…@example.com`; delete them afterwards.

### 4. Manual checklist (about 30 minutes)

- [ ] Log in, open **Access & security** in the sidebar → *My sessions* shows "this device".
- [ ] Log in from a second browser, click *Log out other devices* → the second browser is logged out on its next click.
- [ ] Click *Logout*, then press the browser Back button → you are sent to the login page.
- [ ] As a normal employee, request *Refunds Management* for 14 days → appears as *pending, waiting for: manager*.
- [ ] As that employee's manager (or an admin) approve step 1; try to approve step 2 with the same account → refused.
- [ ] Approve step 2 with a different admin → the employee can now open refunds; it disappears automatically after 14 days.
- [ ] Request *Payout Queue* for someone who already has *Commission Slabs Manager* → final approval is blocked with a separation-of-duties message.
- [ ] Deactivate a test employee in People → their open browser session stops working immediately.
- [ ] *Feature registry* → kill a harmless feature, confirm it is blocked, then restore it.
- [ ] *Controls & audit* → "Verified — N events, no tampering detected".
- [ ] *Statutory settings* → PF ceiling shows 15,000 (2014-09-01) and 25,000 (2026-09-17).
- [ ] Payroll: generate October 2026 payslips for 3–5 real employees on the staging copy and have your CA compare them with last month. Approving with the same account that generated them must be refused.

### 5. Go live

1. Take a fresh `mongodump` of production.
2. Merge the pull request, `git pull` on the server, `pip install -r requirements.txt`.
3. `python -m migrations.run_all`, restart the API, rebuild the frontend (`npm ci --legacy-peer-deps && npm run build`).
4. Keep `REQUIRE_SESSION_ID=0` for the first 24 hours (tokens issued before the deploy have no
   session id and would otherwise log everyone out). After 24 hours set `REQUIRE_SESSION_ID=1`
   and restart.
5. If only one person runs payroll, set `PAYROLL_MAKER_CHECKER=0` until a second approver exists.

### Roll back

`git checkout <previous commit>` and restart. The new collections (`audit_events`,
`audit_chain_head`, `user_sessions`, `feature_registry`, `permission_grants`,
`access_requests`, `sod_rules`, `statutory_settings`) are simply ignored by the old code.
Payslips already generated keep the numbers they were generated with.

## Environment variables

| Variable | Default | Meaning |
|---|---|---|
| `REQUIRE_SESSION_ID` | `0` | `1` rejects tokens without a session id (turn on 24 h after deploy) |
| `PAYROLL_MAKER_CHECKER` | `1` | Generator of a payslip cannot approve it |
| `SECURITY_APPROVER_ROLES` | `admin_owner,it_admin` | Who approves the "security" step for critical access |

## What is not in this release (next sprints in the backlog)

- Wiring `require_feature(...)` into the existing 120+ routers (today it guards the new endpoints;
  existing screens still use RBAC v2 packs). Do this module by module, starting with payroll,
  payouts and refunds.
- MFA/TOTP enforcement, JIT production access and the quarterly access-review workflow.
- Attendance, leave, payroll run register, Form 130/138 generation, documents and letters,
  commissions with TDS, productivity — Phases 2–6 of the backlog.
