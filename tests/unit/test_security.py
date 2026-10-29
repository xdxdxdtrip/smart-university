"""Unit-тесты хеширования паролей и JWT."""

import jwt
import pytest

from app.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


def test_password_hash_is_salted_and_verifiable():
    first = hash_password("Secret123", iterations=1000)
    second = hash_password("Secret123", iterations=1000)
    assert first != second  # разная соль
    assert first.startswith("pbkdf2_sha256$1000$")
    assert "Secret123" not in first
    assert verify_password("Secret123", first)


def test_wrong_password_and_broken_hash_fail():
    stored = hash_password("Secret123", iterations=1000)
    assert not verify_password("secret123", stored)
    assert not verify_password("Secret123", "not-a-hash")
    assert not verify_password("Secret123", "md5$1$abc$def")


def test_jwt_roundtrip_contains_user_and_role():
    token = create_access_token(42, "teacher")
    payload = decode_access_token(token)
    assert payload["sub"] == "42"
    assert payload["role"] == "teacher"


def test_expired_jwt_is_rejected():
    token = create_access_token(1, "student", expires_minutes=-1)
    with pytest.raises(jwt.ExpiredSignatureError):
        decode_access_token(token)


def test_tampered_jwt_is_rejected():
    token = create_access_token(1, "student")
    header, payload, signature = token.split(".")
    tampered = f"{header}.{payload}.{signature[:-2]}xx"
    with pytest.raises(jwt.PyJWTError):
        decode_access_token(tampered)
