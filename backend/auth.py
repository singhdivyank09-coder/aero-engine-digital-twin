import hashlib
import os
import jwt
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from fastapi import HTTPException, Security, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "480"))  # 8 hours shift
PASSWORD_SALT = os.getenv("PASSWORD_SALT", "AERO_DIGITAL_TWIN_SALT_2026")

security_bearer = HTTPBearer(auto_error=False)

def get_jwt_secret_key() -> str:
    secret = os.getenv("JWT_SECRET_KEY") or os.getenv("JWT_SECRET") or os.getenv("SECRET_KEY")
    if not secret:
        env = os.getenv("ENVIRONMENT", "").lower()
        is_render = os.getenv("RENDER", "").lower() == "true"
        if env in ["production", "prod"] or is_render:
            raise RuntimeError("CRITICAL SECURITY FAILURE: JWT_SECRET_KEY environment secret is missing in production!")
        secret = "DEV_ONLY_LOCAL_JWT_SECRET_KEY_REPLACE_IN_PRODUCTION_2026"
    return secret

import secrets

def get_password_hash(password: str, username: str = "", salt: Optional[str] = None) -> str:
    """
    Generates a cryptographically secure PBKDF2-HMAC-SHA256 password hash using a 16-byte random per-user salt.
    Returns string formatted as: {salt}${pbkdf2_hex_hash}
    """
    if not salt:
        salt = secrets.token_hex(16)
    key = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt.encode('utf-8'), 100000)
    return f"{salt}${key.hex()}"

def verify_password(plain_password: str, hashed_password: str, username: str = "") -> bool:
    """
    Verifies a plain-text password against a stored hash string.
    Supports random per-user salt format (salt$hash), legacy username-based salt, and single-salt fallbacks.
    """
    if not hashed_password or not plain_password:
        return False

    if "$" in hashed_password:
        try:
            salt, stored_key = hashed_password.split("$", 1)
            calculated_hash = get_password_hash(plain_password, username, salt=salt)
            return calculated_hash == hashed_password
        except Exception:
            return False

    # Legacy fallback 1: username + PASSWORD_SALT
    legacy_user_salt = f"{username}:{PASSWORD_SALT}"
    legacy_key = hashlib.pbkdf2_hmac('sha256', plain_password.encode('utf-8'), legacy_user_salt.encode('utf-8'), 100000).hex()
    if legacy_key == hashed_password:
        return True

    # Legacy fallback 2: single PASSWORD_SALT
    fallback_key = hashlib.pbkdf2_hmac('sha256', plain_password.encode('utf-8'), PASSWORD_SALT.encode('utf-8'), 100000).hex()
    return fallback_key == hashed_password

def create_access_token(data: dict, expires_minutes: Optional[int] = None) -> str:
    to_encode = data.copy()
    mins = expires_minutes if expires_minutes is not None else ACCESS_TOKEN_EXPIRE_MINUTES
    expire = datetime.utcnow() + timedelta(minutes=mins)
    to_encode.update({"exp": expire})
    secret = get_jwt_secret_key()
    encoded_jwt = jwt.encode(to_encode, secret, algorithm=ALGORITHM)
    return encoded_jwt

def decode_token(credentials: Optional[HTTPAuthorizationCredentials] = Security(security_bearer)) -> dict:
    if not credentials or not credentials.credentials:
        raise HTTPException(status_code=401, detail="Authentication token required.")
    token = credentials.credentials
    try:
        secret = get_jwt_secret_key()
        payload = jwt.decode(token, secret, algorithms=[ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Session expired. Please login again.")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid authentication token.")

def verify_token(token: str) -> Optional[dict]:
    if not token:
        return None
    try:
        secret = get_jwt_secret_key()
        payload = jwt.decode(token, secret, algorithms=[ALGORITHM])
        return payload
    except Exception:
        return None

def authenticate_user(username: str, password: str) -> Optional[dict]:
    from backend.database import get_db_connection
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE username = ?;", (username,))
    user = cursor.fetchone()
    conn.close()

    if not user:
        return None
    if verify_password(password, user["password_hash"], username):
        return dict(user)
    return None

def require_role(allowed_roles: List[str]):
    def role_checker(token_payload: dict = Depends(decode_token)):
        user_role = token_payload.get("role")
        if user_role not in allowed_roles:
            raise HTTPException(status_code=403, detail=f"Access denied. Required role in {allowed_roles}, got '{user_role}'.")
        return token_payload
    return role_checker


