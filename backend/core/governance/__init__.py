"""Employee-portal governance foundation (Backlog Phase 0-1).

Modules
-------
audit_chain       Tamper-evident (hash-chained) audit events           E03-01
sessions          Server-side login sessions, revoke, "my sessions"     E02-05
feature_registry  Feature registry, kill switch, staged rollout         E04-01/02/05
access            Time-bound grants, access requests, maker-checker,
                  separation-of-duties (SoD) rules, leaver revocation   E05/E06/E07
statutory         Effective-dated Indian statutory settings (PF, ESI,
                  PT, TDS sections) used by payroll                     E16-01
payroll_rules     Pure calculation helpers (PF ceiling, ESI, MH PT,
                  50% wage rule) - unit tested, no DB access            E16-03/04

Everything here is additive: existing routers keep working unchanged.
New endpoints live under /api/governance (see routers/governance.py).
"""
