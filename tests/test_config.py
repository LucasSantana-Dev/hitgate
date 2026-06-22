"""Tests for config.py helpers and env var validation."""
import os
import pytest

from ragcore.config import _int_env, _bool_env, _choice_env


class TestIntEnv:
    """Test _int_env helper."""

    def test_int_env_uses_default_when_unset(self, monkeypatch):
        """Should return default if env var is unset."""
        monkeypatch.delenv("RAG_TEST_INT", raising=False)
        result = _int_env("RAG_TEST_INT", 42)
        assert result == 42

    def test_int_env_parses_valid_int(self, monkeypatch):
        """Should parse valid integer string."""
        monkeypatch.setenv("RAG_TEST_INT", "99")
        result = _int_env("RAG_TEST_INT", 42)
        assert result == 99

    def test_int_env_parses_zero(self, monkeypatch):
        """Should parse zero correctly."""
        monkeypatch.setenv("RAG_TEST_INT", "0")
        result = _int_env("RAG_TEST_INT", 42)
        assert result == 0

    def test_int_env_raises_on_non_integer(self, monkeypatch):
        """Should raise clear error on non-integer value."""
        monkeypatch.setenv("RAG_TEST_INT", "abc")
        with pytest.raises(ValueError) as excinfo:
            _int_env("RAG_TEST_INT", 42)
        assert "RAG_TEST_INT must be an integer" in str(excinfo.value)
        assert "'abc'" in str(excinfo.value)

    def test_int_env_raises_on_float_string(self, monkeypatch):
        """Should raise clear error on float string."""
        monkeypatch.setenv("RAG_TEST_INT", "3.14")
        with pytest.raises(ValueError) as excinfo:
            _int_env("RAG_TEST_INT", 42)
        assert "RAG_TEST_INT must be an integer" in str(excinfo.value)

    def test_int_env_minimum_bound_inclusive_zero(self, monkeypatch):
        """Should reject values <= minimum (with minimum=0, reject <=0)."""
        monkeypatch.setenv("RAG_TEST_INT", "0")
        with pytest.raises(ValueError) as excinfo:
            _int_env("RAG_TEST_INT", 42, minimum=0)
        assert "RAG_TEST_INT must be > 0" in str(excinfo.value)

    def test_int_env_minimum_bound_negative(self, monkeypatch):
        """Should reject negative values when minimum=0."""
        monkeypatch.setenv("RAG_TEST_INT", "-5")
        with pytest.raises(ValueError) as excinfo:
            _int_env("RAG_TEST_INT", 42, minimum=0)
        assert "RAG_TEST_INT must be > 0" in str(excinfo.value)

    def test_int_env_passes_minimum_bound(self, monkeypatch):
        """Should accept values > minimum."""
        monkeypatch.setenv("RAG_TEST_INT", "10")
        result = _int_env("RAG_TEST_INT", 42, minimum=0)
        assert result == 10

    def test_int_env_no_minimum_check(self, monkeypatch):
        """Should accept negative when minimum is None."""
        monkeypatch.setenv("RAG_TEST_INT", "-5")
        result = _int_env("RAG_TEST_INT", 42, minimum=None)
        assert result == -5


class TestBoolEnv:
    """Test _bool_env helper."""

    def test_bool_env_uses_default_when_unset(self, monkeypatch):
        """Should return default if env var is unset."""
        monkeypatch.delenv("RAG_TEST_BOOL", raising=False)
        assert _bool_env("RAG_TEST_BOOL", True) is True
        assert _bool_env("RAG_TEST_BOOL", False) is False

    def test_bool_env_truthy_values(self, monkeypatch):
        """Should recognize truthy values."""
        for val in ("on", "1", "true", "yes", "ON", "TRUE", "YES"):
            monkeypatch.setenv("RAG_TEST_BOOL", val)
            result = _bool_env("RAG_TEST_BOOL", False)
            assert result is True, f"Failed for {val!r}"

    def test_bool_env_falsy_values(self, monkeypatch):
        """Should recognize falsy values."""
        for val in ("off", "0", "false", "no", "OFF", "FALSE", "NO"):
            monkeypatch.setenv("RAG_TEST_BOOL", val)
            result = _bool_env("RAG_TEST_BOOL", True)
            assert result is False, f"Failed for {val!r}"

    def test_bool_env_raises_on_unrecognized(self, monkeypatch):
        """Should raise clear error on unrecognized value."""
        monkeypatch.setenv("RAG_TEST_BOOL", "maybe")
        with pytest.raises(ValueError) as excinfo:
            _bool_env("RAG_TEST_BOOL", True)
        assert "RAG_TEST_BOOL must be one of" in str(excinfo.value)
        assert "'maybe'" in str(excinfo.value)

    def test_bool_env_raises_on_typo(self, monkeypatch):
        """Should catch typo like 'of' instead of 'off'."""
        monkeypatch.setenv("RAG_TEST_BOOL", "of")
        with pytest.raises(ValueError) as excinfo:
            _bool_env("RAG_TEST_BOOL", True)
        assert "RAG_TEST_BOOL must be one of" in str(excinfo.value)


class TestChoiceEnv:
    """Test _choice_env helper."""

    def test_choice_env_uses_default_when_unset(self, monkeypatch):
        """Should return default if env var is unset."""
        monkeypatch.delenv("RAG_TEST_CHOICE", raising=False)
        result = _choice_env("RAG_TEST_CHOICE", "default", {"a", "b", "default"})
        assert result == "default"

    def test_choice_env_accepts_valid_choice(self, monkeypatch):
        """Should accept a valid choice."""
        monkeypatch.setenv("RAG_TEST_CHOICE", "full")
        result = _choice_env("RAG_TEST_CHOICE", "symbol", {"full", "symbol"})
        assert result == "full"

    def test_choice_env_case_insensitive(self, monkeypatch):
        """Should normalize to lowercase."""
        monkeypatch.setenv("RAG_TEST_CHOICE", "FULL")
        result = _choice_env("RAG_TEST_CHOICE", "symbol", {"full", "symbol"})
        assert result == "full"

    def test_choice_env_raises_on_invalid(self, monkeypatch):
        """Should raise clear error on invalid choice."""
        monkeypatch.setenv("RAG_TEST_CHOICE", "invalid")
        with pytest.raises(ValueError) as excinfo:
            _choice_env("RAG_TEST_CHOICE", "default", {"full", "symbol"})
        assert "RAG_TEST_CHOICE must be one of" in str(excinfo.value)
        assert "'invalid'" in str(excinfo.value)

    def test_choice_env_shows_valid_options(self, monkeypatch):
        """Should list valid options in error message."""
        monkeypatch.setenv("RAG_TEST_CHOICE", "wrong")
        with pytest.raises(ValueError) as excinfo:
            _choice_env("RAG_TEST_CHOICE", "default", {"full", "symbol"})
        err_msg = str(excinfo.value)
        assert "full" in err_msg
        assert "symbol" in err_msg


class TestConfigImport:
    """Integration tests: config.py should import with defaults."""

    def test_config_imports_with_default_env(self, monkeypatch, mocker):
        """Config should import cleanly with unset RAG_* vars (using defaults)."""
        # Clear all RAG_* env vars
        for key in list(os.environ.keys()):
            if key.startswith("RAG_"):
                monkeypatch.delenv(key, raising=False)

        # Re-import config to pick up defaults
        import importlib
        import ragcore.config

        importlib.reload(ragcore.config)

        # Verify defaults are applied
        assert ragcore.config.EMBED_DIM == 384
        assert ragcore.config.MAX_FILE_BYTES == 200000
        assert ragcore.config.GIT_LOG_DAYS == 180
        assert ragcore.config.CHUNK_CONTEXT_PREFIX is True
        assert ragcore.config.CHUNK_PREFIX_FORMAT == "full"

    def test_config_fails_fast_on_bad_embed_dim(self, monkeypatch):
        """Config import should fail with clear error on bad RAG_EMBED_DIM."""
        monkeypatch.setenv("RAG_EMBED_DIM", "not_a_number")
        import importlib
        import ragcore.config

        with pytest.raises(ValueError) as excinfo:
            importlib.reload(ragcore.config)
        assert "RAG_EMBED_DIM" in str(excinfo.value)
        assert "not_a_number" in str(excinfo.value)

    def test_config_fails_fast_on_bad_chunk_prefix(self, monkeypatch):
        """Config import should fail with clear error on bad RAG_CHUNK_CONTEXT_PREFIX."""
        monkeypatch.setenv("RAG_CHUNK_CONTEXT_PREFIX", "maybe")
        import importlib
        import ragcore.config

        with pytest.raises(ValueError) as excinfo:
            importlib.reload(ragcore.config)
        assert "RAG_CHUNK_CONTEXT_PREFIX" in str(excinfo.value)

    def test_config_fails_fast_on_bad_format(self, monkeypatch):
        """Config import should fail with clear error on bad RAG_CHUNK_PREFIX_FORMAT."""
        monkeypatch.setenv("RAG_CHUNK_PREFIX_FORMAT", "invalid")
        import importlib
        import ragcore.config

        with pytest.raises(ValueError) as excinfo:
            importlib.reload(ragcore.config)
        assert "RAG_CHUNK_PREFIX_FORMAT" in str(excinfo.value)
        assert "invalid" in str(excinfo.value)
