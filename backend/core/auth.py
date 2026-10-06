"""Authentication utilities"""
import os
import re
import hmac
import logging
import jwt
from datetime import datetime, timedelta, timezone
import bcrypt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from core.database import users_col

# Fix passlib compatibility with bcrypt >= 4.0.0
if not hasattr(bcrypt, "__about__"):
    class _About:
        __version__ = getattr(bcrypt, "__version__", "4.0.0")
    bcrypt.__about__ = _About()

logger = logging.getLogger(__name__)

_INSECURE_DEFAULT_SECRETS = {"", "leamss-portal-secret-key-2024-secure", "changeme", "secret"}


def _load_jwt_secret() -> str:
    """Load the JWT signing secret from the environment.

    SECURITY: there is intentionally NO hard-coded fallback. A public fallback
    secret lets anyone forge admin tokens. In development you may set
    ALLOW_INSECURE_DEV_SECRET=1 to auto-generate an ephemeral secret (tokens
    will be invalidated on every restart).
    """
    secret = os.environ.get("JWT_SECRET", "")
    if secret in _INSECURE_DEFAULT_SECRETS or len(secret) < 32:
        if os.environ.get("ALLOW_INSECURE_DEV_SECRET") == "1":
            import secrets as _secrets
            logger.warning("JWT_SECRET missing/weak - using an ephemeral DEV secret. Never do this in production.")
            return _secrets.token_urlsafe(48)
        raise RuntimeError(
            "JWT_SECRET environment variable is missing or too short (min 32 chars). "
            "Generate one with: python -c \"import secrets; print(secrets.token_urlsafe(48))\""
        )
    return secret


JWT_SECRET = _load_jwt_secret()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer()
optional_security = HTTPBearer(auto_error=False)

_HASH_PREFIXES = ("$2a$", "$2b$", "$2y$", "$argon2", "$pbkdf2", "$5$", "$6$")


def get_password_hash(password: str) -> str:
    if not password:
        return ""
    try:
        salt = bcrypt.gensalt()
        return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")
    except Exception:
        return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    if not plain or not hashed:
        return False
    # SECURITY: never accept the stored hash itself as a password. Plain-text
    # comparison is only allowed for legacy records that were stored un-hashed,
    # and uses a constant-time compare.
    if isinstance(hashed, str) and not hashed.startswith(_HASH_PREFIXES):
        logger.warning("Legacy plain-text password record encountered - it should be re-hashed.")
        return hmac.compare_digest(plain.encode("utf-8"), hashed.encode("utf-8"))
    try:
        if isinstance(hashed, str) and hashed.startswith(("$2a$", "$2b$", "$2y$")):
            return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
        return pwd_context.verify(plain, hashed)
    except Exception:
        return False


def validate_password_strength(pwd: str) -> tuple:
    """Returns (is_valid, message). Enforces 8+ chars, upper, lower, digit, special."""
    if not pwd or len(pwd) < 8:
        return False, "Password must be at least 8 characters"
    if not re.search(r"[a-z]", pwd):
        return False, "Password must include a lowercase letter"
    if not re.search(r"[A-Z]", pwd):
        return False, "Password must include an uppercase letter"
    if not re.search(r"\d", pwd):
        return False, "Password must include a number"
    if not re.search(r"[!@#$%^&*()_+\-=\[\]{};':\"\\|,.<>\/?]", pwd):
        return False, "Password must include a special character"
    return True, "Strong password"


def create_access_token(data: dict, expires_hours: int = 24) -> str:
    to_encode = data.copy()
    now = datetime.now(timezone.utc)
    to_encode["iat"] = int(now.timestamp())  # issued-at, used for force-logout
    to_encode["exp"] = now + timedelta(hours=expires_hours)
    return jwt.encode(to_encode, JWT_SECRET, algorithm="HS256")


def build_token_payload(user: dict) -> dict:
    """Compact JWT payload including RBAC fields for fast permission checks."""
    return {
        "sub": user["id"],
        "role": user.get("role"),                              # legacy — preserved
        "rbac_role": user.get("rbac_role") or user.get("role"), # new RBAC key
        "user_type": user.get("user_type"),
        "department": user.get("department"),
        "permissions": user.get("permissions") or [],
    }


async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=["HS256"])
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")
        
        user = await users_col.find_one({"id": user_id}, {"_id": 0})
        if not user:
            raise HTTPException(status_code=401, detail="User not found")

        # Force-logout if password was changed AFTER this token was issued
        pwd_changed_at = user.get("password_changed_at")
        token_iat = payload.get("iat", 0)
        if pwd_changed_at and token_iat:
            if isinstance(pwd_changed_at, datetime):
                pwd_ts = int(pwd_changed_at.timestamp())
                if token_iat < pwd_ts:
                    raise HTTPException(status_code=401, detail="Session invalidated. Please login again.")

        return user
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


async def get_optional_user(credentials: HTTPAuthorizationCredentials = Depends(optional_security)):
    """Return the authenticated user, or None when no/invalid token is supplied."""
    if not credentials:
        return None
    try:
        return await get_current_user(credentials)
    except HTTPException:
        return None


def require_role(allowed_roles: list):
    async def role_checker(current_user: dict = Depends(get_current_user)):
        if current_user["role"] not in [r.value if hasattr(r, 'value') else r for r in allowed_roles] and current_user["role"] not in [str(r) for r in allowed_roles]:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return current_user
    return role_checker
