import pytest

from shared.config.settings import Settings


class TestSettingsDefaults:
    def test_default_values(self):
        s = Settings(
            _env_file=None,
            APP_NAME="test",
            APP_ENV="test",
        )
        assert s.app_name == "test"
        assert s.app_env == "test"
        assert s.app_host == "0.0.0.0"
        assert s.app_port == 18080
        assert s.log_level == "INFO"
        assert s.app_auth_enabled is False
        assert s.app_rate_limit == 300
        assert s.app_rate_window == 60

    def test_cors_origins_default(self):
        s = Settings(_env_file=None, APP_NAME="test")
        origins = s.get_cors_origins
        assert origins == ["*"]

    def test_cors_origins_custom(self):
        s = Settings(_env_file=None, APP_NAME="test", APP_CORS_ORIGINS="http://localhost:3000,http://localhost:3001")
        origins = s.get_cors_origins
        assert origins == ["http://localhost:3000", "http://localhost:3001"]

    def test_cors_origins_empty_string(self):
        s = Settings(_env_file=None, APP_NAME="test", APP_CORS_ORIGINS="")
        origins = s.get_cors_origins
        assert origins == ["*"]

    def test_cors_origins_is_property(self):
        s = Settings(_env_file=None, APP_NAME="test")
        assert isinstance(s.get_cors_origins, list)
