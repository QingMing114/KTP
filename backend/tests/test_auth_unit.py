import time
import tempfile
import os

import pytest

from ktp_backend.auth import _encode_jwt, decode_jwt, _USER_ID_PATTERN
from v2.runtime.user_store import UserStore, _hash_password, hmac_compare


class TestJWTEncoding:
    def test_encode_and_decode(self):
        from v2.shared.schemas import AuthTokenPayload
        payload = AuthTokenPayload(user_id="testuser", role="admin", exp=time.time() + 3600)
        token = _encode_jwt(payload)
        decoded = decode_jwt(token)
        assert decoded.user_id == "testuser"
        assert decoded.role == "admin"

    def test_invalid_format_rejected(self):
        with pytest.raises(ValueError, match="Invalid JWT"):
            decode_jwt("not.a.valid.jwt.token.extra")

    def test_tampered_signature_rejected(self):
        from v2.shared.schemas import AuthTokenPayload
        payload = AuthTokenPayload(user_id="testuser", role="admin", exp=time.time() + 3600)
        token = _encode_jwt(payload)
        parts = token.split(".")
        tampered = parts[0] + "." + parts[1] + ".invalidsignature"
        with pytest.raises(ValueError, match="Invalid JWT"):
            decode_jwt(tampered)


class TestPasswordHashing:
    def test_hash_and_verify(self):
        hashed, salt = _hash_password("mypassword")
        assert isinstance(hashed, str)
        assert isinstance(salt, str)
        verify_hash, _ = _hash_password("mypassword", salt)
        assert hmac_compare(hashed, verify_hash)

    def test_different_passwords_different_hashes(self):
        h1, _ = _hash_password("password1")
        h2, _ = _hash_password("password2")
        assert h1 != h2

    def test_same_password_different_salts(self):
        h1, _ = _hash_password("samepassword")
        h2, _ = _hash_password("samepassword")
        assert h1 != h2


class TestUserIdValidation:
    def test_valid_user_ids(self):
        assert _USER_ID_PATTERN.match("admin")
        assert _USER_ID_PATTERN.match("user123")
        assert _USER_ID_PATTERN.match("my-user")
        assert _USER_ID_PATTERN.match("my_user")

    def test_invalid_user_ids(self):
        assert not _USER_ID_PATTERN.match("a")
        assert not _USER_ID_PATTERN.match("user with spaces")
        assert not _USER_ID_PATTERN.match("user@domain")


class TestUserStore:
    @pytest.fixture
    def store(self, tmp_path):
        db_path = str(tmp_path / "test_users.sqlite3")
        return UserStore(db_path=db_path)

    def test_create_user(self, store):
        user = store.create_user("testuser", "password123", role="admin")
        assert user.user_id == "testuser"
        assert user.role == "admin"

    def test_duplicate_user_raises(self, store):
        store.create_user("testuser", "password123")
        with pytest.raises(ValueError, match="already exists"):
            store.create_user("testuser", "password456")

    def test_verify_password(self, store):
        store.create_user("testuser", "password123")
        assert store.verify_password("testuser", "password123") is True
        assert store.verify_password("testuser", "wrongpassword") is False

    def test_get_user(self, store):
        store.create_user("testuser", "password123")
        user = store.get_user("testuser")
        assert user is not None
        assert user.user_id == "testuser"

    def test_get_nonexistent_user(self, store):
        assert store.get_user("nonexistent") is None

    def test_list_users(self, store):
        store.create_user("user1", "pass1")
        store.create_user("user2", "pass2")
        users = store.list_users()
        assert len(users) >= 2

    def test_count_users(self, store):
        store.create_user("user1", "pass1")
        store.create_user("user2", "pass2")
        assert store.count_users() >= 2

    def test_update_password(self, store):
        store.create_user("testuser", "oldpassword")
        store.update_password("testuser", "newpassword")
        assert store.verify_password("testuser", "newpassword") is True
        assert store.verify_password("testuser", "oldpassword") is False

    def test_update_last_login(self, store):
        store.create_user("testuser", "password123")
        store.update_last_login("testuser")
        user = store.get_user("testuser")
        assert user.last_login is not None
