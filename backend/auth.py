import hashlib
import os
import jwt
from datetime import datetime, timedelta
from fastapi import HTTPException, Security, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

SECRET_KEY = "DEFENSE_GRADE_MALE_UAV_DIGITAL_TWIN_SECRET_KEY_2026"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 480  # 8 hours shift

security_bearer = HTTPBearer()

def get_password_hash(password: str) -> str:
    salt = "DEFENSE_SALT_2026"
    key = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt.encode('utf-8'), 100000)
    return key.hex()

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return get_password_hash(plain_password) == hashed_password


def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def decode_token(credentials: HTTPAuthorizationCredentials = Security(security_bearer)):
    token = credentials.credentials
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Session expired. Please login again.")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid authentication token.")

def verify_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except Exception:
        return None

def authenticate_user(username: str, password: str):
    from backend.database import get_db_connection
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE username = ?;", (username,))
    user = cursor.fetchone()
    conn.close()

    if not user:
        return None
    if verify_password(password, user["password_hash"]):
        return dict(user)
    return None

def require_role(allowed_roles: list):
    def role_checker(token_payload: dict = Depends(decode_token)):
        user_role = token_payload.get("role")
        if user_role not in allowed_roles:
            raise HTTPException(status_code=403, detail=f"Access denied. Required role: {allowed_roles}")
        return token_payload
    return role_checker

