"""Credential Vault Provider Abstraction & Management Service.

Ensures authentication secrets (portal logins, assessment accounts, government logins)
are NEVER stored in cleartext in CRM records, nor returned in standard case payloads.

Provides:
- BaseVaultProvider ABC interface
- LocalEncryptedVaultProvider (AES/Fernet encryption using local key)
- CloudSecretVaultProvider (GCP/AWS/HashiCorp ready interface)
- VaultService: credential registry, audited temporary checkout, and masked retrieval
"""
from __future__ import annotations

import abc
import base64
import hashlib
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from cryptography.fernet import Fernet
from motor.motor_asyncio import AsyncIOMotorDatabase

from core.database import db
from services.audit_service import log_action

logger = logging.getLogger(__name__)

VAULT_COLLECTION = "case_vault_credentials"
VAULT_CHECKOUT_LOG = "case_vault_checkouts"


# ─────────────────────────────────────────────────────────────────────────────
# 1. Vault Provider Abstraction
# ─────────────────────────────────────────────────────────────────────────────

class BaseVaultProvider(abc.ABC):
    @abc.abstractmethod
    def store_secret(self, key: str, secret_value: str) -> str:
        """Store secret and return storage reference token."""
        pass

    @abc.abstractmethod
    def retrieve_secret(self, key: str) -> Optional[str]:
        """Retrieve cleartext secret given storage reference token."""
        pass

    @abc.abstractmethod
    def delete_secret(self, key: str) -> bool:
        """Delete secret by key."""
        pass


from dotenv import load_dotenv

load_dotenv()

class LocalEncryptedVaultProvider(BaseVaultProvider):
    """Local development and staging encrypted vault provider.
    
    Uses Fernet symmetric authenticated encryption. Key is derived
    from VAULT_KEY or JWT_SECRET via SHA-256, with fallback support.
    """

    def __init__(self, seed_secret: Optional[str] = None):
        raw_seed = seed_secret or os.environ.get("VAULT_KEY") or os.environ.get("JWT_SECRET") or "supersecretjwtkeyforleamssportal2026"
        key_bytes = hashlib.sha256(raw_seed.encode("utf-8")).digest()
        self._fernet = Fernet(base64.urlsafe_b64encode(key_bytes))

        # Secondary fallback keys to seamlessly decrypt credentials created under different env seeds
        candidate_fallbacks = [
            "supersecretjwtkeyforleamssportal2026",
            "leamss_local_vault_fallback_seed_2026"
        ]
        self._fallbacks = []
        for fb_seed in candidate_fallbacks:
            if fb_seed != raw_seed:
                fb_key = hashlib.sha256(fb_seed.encode("utf-8")).digest()
                self._fallbacks.append(Fernet(base64.urlsafe_b64encode(fb_key)))

    def store_secret(self, key: str, secret_value: str) -> str:
        ciphertext = self._fernet.encrypt(secret_value.encode("utf-8")).decode("ascii")
        return ciphertext

    def retrieve_secret(self, ciphertext: str) -> Optional[str]:
        try:
            return self._fernet.decrypt(ciphertext.encode("ascii")).decode("utf-8")
        except Exception:
            for fb in self._fallbacks:
                try:
                    return fb.decrypt(ciphertext.encode("ascii")).decode("utf-8")
                except Exception:
                    pass
            logger.error("Failed to decrypt vault secret with primary and fallback keys")
            return None

    def delete_secret(self, key: str) -> bool:
        return True


class CloudSecretVaultProvider(BaseVaultProvider):
    """Stub / Interface for production GCP Secret Manager / AWS Secrets Manager."""

    def __init__(self, project_id: Optional[str] = None):
        self.project_id = project_id or os.environ.get("GCP_PROJECT_ID", "leamss-prod")

    def store_secret(self, key: str, secret_value: str) -> str:
        # In cloud environment, this calls secretmanager.SecretManagerServiceClient
        logger.info("CloudSecretVaultProvider: store_secret called for key=%s", key)
        return f"cloud-ref://{self.project_id}/{key}"

    def retrieve_secret(self, key: str) -> Optional[str]:
        logger.info("CloudSecretVaultProvider: retrieve_secret called for ref=%s", key)
        return None

    def delete_secret(self, key: str) -> bool:
        return True


# Factory
def get_vault_provider() -> BaseVaultProvider:
    provider_type = os.environ.get("VAULT_PROVIDER", "local").lower()
    if provider_type in ("gcp", "aws", "cloud"):
        return CloudSecretVaultProvider()
    return LocalEncryptedVaultProvider()


# ─────────────────────────────────────────────────────────────────────────────
# 2. Vault Service
# ─────────────────────────────────────────────────────────────────────────────

class VaultService:
    @staticmethod
    async def register_credential(
        case_id: str,
        portal_name: str,
        username_or_id: str,
        secret_value: str,
        actor_id: str,
        actor_email: Optional[str] = None,
        portal_url: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Encrypt secret and store credential record linked to case."""
        provider = get_vault_provider()
        cred_id = str(uuid.uuid4())
        ref_key = f"vault_cred_{case_id}_{cred_id}"
        encrypted_token = provider.store_secret(ref_key, secret_value)

        now = datetime.now(timezone.utc)
        record = {
            "id": cred_id,
            "case_id": case_id,
            "portal_name": portal_name,
            "portal_url": portal_url,
            "username_or_id": username_or_id,
            "encrypted_secret": encrypted_token,
            "notes": notes,
            "created_by": actor_id,
            "created_by_email": actor_email,
            "created_at": now,
            "updated_at": now,
            "last_accessed_at": None,
            "last_accessed_by": None,
        }
        await db[VAULT_COLLECTION].insert_one(record)

        await log_action(
            db,
            action="vault.credential_registered",
            user_id=actor_id,
            summary={"case_id": case_id, "portal_name": portal_name, "username": username_or_id},
            severity="info",
        )

        return {
            "id": cred_id,
            "case_id": case_id,
            "portal_name": portal_name,
            "portal_url": portal_url,
            "username_or_id": username_or_id,
            "notes": notes,
            "created_at": now.isoformat(),
        }

    @staticmethod
    async def list_credentials_for_case(case_id: str) -> List[Dict[str, Any]]:
        """List credentials for case without decrypting or exposing secrets."""
        results = []
        cursor = db[VAULT_COLLECTION].find({"case_id": case_id}, {"encrypted_secret": 0})
        async for doc in cursor:
            if "id" not in doc or not doc.get("id"):
                doc["id"] = str(doc.get("_id"))
            if "_id" in doc:
                doc["_id"] = str(doc.get("_id"))
            if isinstance(doc.get("created_at"), datetime):
                doc["created_at"] = doc["created_at"].isoformat()
            if isinstance(doc.get("updated_at"), datetime):
                doc["updated_at"] = doc["updated_at"].isoformat()
            if isinstance(doc.get("last_accessed_at"), datetime):
                doc["last_accessed_at"] = doc["last_accessed_at"].isoformat()
            results.append(doc)
        return results

    @staticmethod
    async def checkout_credential_secret(
        credential_id: str,
        actor_id: str,
        actor_email: str,
        reason: str,
        ip: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Audited temporary retrieval of secret."""
        record = await db[VAULT_COLLECTION].find_one({
            "$or": [{"id": credential_id}, {"_id": credential_id}]
        })
        if not record:
            try:
                from bson import ObjectId
                if ObjectId.is_valid(credential_id):
                    record = await db[VAULT_COLLECTION].find_one({"_id": ObjectId(credential_id)})
            except Exception:
                pass

        if not record:
            raise ValueError(f"Credential record not found (ID: {credential_id})")

        provider = get_vault_provider()
        decrypted = provider.retrieve_secret(record["encrypted_secret"])
        if decrypted is None:
            raise ValueError("Decryption failed")

        now = datetime.now(timezone.utc)
        # Update last accessed metadata
        await db[VAULT_COLLECTION].update_one(
            {"_id": record["_id"]},
            {"$set": {"last_accessed_at": now, "last_accessed_by": actor_id}},
        )

        # Log dedicated checkout audit record
        checkout_doc = {
            "id": str(uuid.uuid4()),
            "credential_id": credential_id,
            "case_id": record.get("case_id"),
            "portal_name": record.get("portal_name"),
            "actor_id": actor_id,
            "actor_email": actor_email,
            "reason": reason,
            "ip": ip,
            "checked_out_at": now,
        }
        await db[VAULT_CHECKOUT_LOG].insert_one(checkout_doc)

        await log_action(
            db,
            action="vault.secret_checked_out",
            user_id=actor_id,
            user_name=actor_email,
            summary={
                "credential_id": credential_id,
                "case_id": record.get("case_id"),
                "portal_name": record.get("portal_name"),
                "reason": reason,
            },
            severity="warn",
            ip=ip,
        )

        return {
            "credential_id": credential_id,
            "case_id": record.get("case_id"),
            "portal_name": record.get("portal_name"),
            "username_or_id": record.get("username_or_id"),
            "secret_value": decrypted,
            "checked_out_at": now.isoformat(),
        }
