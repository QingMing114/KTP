"""Tests for API gateway middleware and auth."""
import pytest
from ktp_backend.auth import _encode_jwt, decode_jwt, _JWT_SECRET
from v2.shared.schemas import AuthTokenPayload
import time


class TestJWTEncoding:
    def test_encode_decode_roundtrip(self):
        payload = AuthTokenPayload(user_id="testuser", role="user", exp=time.time() + 3600)
        token = _encode_jwt(payload)
        assert isinstance(token, str)
        decoded = decode_jwt(token)
        assert decoded.user_id == "testuser"
        assert decoded.role == "user"

    def test_expired_token_raises(self):
        payload = AuthTokenPayload(user_id="testuser", role="user", exp=time.time() - 100)
        token = _encode_jwt(payload)
        with pytest.raises(ValueError, match="expired"):
            decode_jwt(token)

    def test_invalid_signature_raises(self):
        payload = AuthTokenPayload(user_id="testuser", role="user", exp=time.time() + 3600)
        token = _encode_jwt(payload)
        # Tamper with the token
        parts = token.split(".")
        parts[2] = parts[2][:-4] + "XXXX"
        tampered = ".".join(parts)
        with pytest.raises(ValueError, match="Invalid"):
            decode_jwt(tampered)

    def test_malformed_token_raises(self):
        with pytest.raises(ValueError):
            decode_jwt("not.a.valid.jwt.token.format")

    def test_admin_role_preserved(self):
        payload = AuthTokenPayload(user_id="admin", role="admin", exp=time.time() + 3600)
        token = _encode_jwt(payload)
        decoded = decode_jwt(token)
        assert decoded.role == "admin"


class TestAuthMiddleware:
    """Test auth middleware logic (without full FastAPI test client)."""

    def test_no_auth_paths_include_login(self):
        """Login endpoint should be in the no-auth whitelist."""
        from apps.api_gateway.main import _NO_AUTH_PATHS
        assert "/v2/auth/login" in _NO_AUTH_PATHS

    def test_no_auth_paths_include_register(self):
        from apps.api_gateway.main import _NO_AUTH_PATHS
        assert "/v2/auth/register" in _NO_AUTH_PATHS

    def test_no_auth_paths_include_health(self):
        from apps.api_gateway.main import _NO_AUTH_PATHS
        assert "/health" in _NO_AUTH_PATHS
