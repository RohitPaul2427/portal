"""Create indexes and seed governance data. Idempotent - safe on every deploy."""
from core.governance import access, audit_chain, feature_registry, sessions, statutory


async def ensure_governance_ready() -> dict:
    for mod in (audit_chain, sessions, feature_registry, access, statutory):
        await mod.ensure_indexes()
    reg = await feature_registry.seed_registry()
    return {
        "features_inserted": reg["inserted"],
        "sod_rules_inserted": await access.seed_sod_rules(),
        "statutory_rows_inserted": await statutory.seed_settings(),
    }
