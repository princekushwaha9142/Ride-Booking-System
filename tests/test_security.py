import uuid
from datetime import datetime, timedelta, timezone

import jwt
import pytest

from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    hash_refresh_token,
    verify_password,
)
from tests.helpers import make_token


def test_password_hash_verifies_and_is_not_plaintext() -> None:
    hashed = hash_password("CorrectHorse1")
    assert hashed != "CorrectHorse1"
    assert hashed.startswith("$argon2id$")
    assert verify_password("CorrectHorse1", hashed) is True
    assert verify_password("WrongPassword1", hashed) is False


def test_same_password_hashes_differently_because_of_salt() -> None:
    assert hash_password("CorrectHorse1") != hash_password("CorrectHorse1")


def test_verify_password_returns_false_for_garbage_hash() -> None:
    assert verify_password("anything", "not-a-valid-hash") is False


def test_access_token_roundtrip() -> None:
    user_id = uuid.uuid4()
    payload = decode_access_token(create_access_token(user_id))
    assert payload["sub"] == str(user_id)
    assert payload["type"] == "access"


def test_decode_rejects_expired_token() -> None:
    token = make_token(uuid.uuid4(), expires_in=timedelta(minutes=-1))
    with pytest.raises(jwt.ExpiredSignatureError):
        decode_access_token(token)


def test_decode_rejects_token_signed_with_wrong_key() -> None:
    token = make_token(uuid.uuid4(), key="x" * 40)
    with pytest.raises(jwt.InvalidSignatureError):
        decode_access_token(token)


def test_decode_rejects_alg_none_token() -> None:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(uuid.uuid4()),
        "type": "access",
        "iat": now,
        "exp": now + timedelta(minutes=5),
    }
    token = jwt.encode(payload, None, algorithm="none")
    with pytest.raises(jwt.PyJWTError):
        decode_access_token(token)


def test_decode_rejects_wrong_token_type() -> None:
    token = make_token(uuid.uuid4(), token_type="refresh")
    with pytest.raises(jwt.InvalidTokenError):
        decode_access_token(token)


def test_refresh_token_hash_is_deterministic_sha256_hex() -> None:
    assert hash_refresh_token("abc") == hash_refresh_token("abc")
    assert len(hash_refresh_token("abc")) == 64