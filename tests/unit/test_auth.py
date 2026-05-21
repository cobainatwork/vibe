import pytest

from shared.auth import AuthError, verify_api_key


def test_valid_key_returns_name():
    keys = {"abc": "ops", "xyz": "cron"}
    assert verify_api_key("abc", keys) == "ops"
    assert verify_api_key("xyz", keys) == "cron"


def test_missing_key_raises():
    with pytest.raises(AuthError) as exc:
        verify_api_key(None, {"abc": "ops"})
    assert "missing" in str(exc.value).lower()


def test_empty_key_raises():
    with pytest.raises(AuthError):
        verify_api_key("", {"abc": "ops"})


def test_invalid_key_raises():
    with pytest.raises(AuthError):
        verify_api_key("wrong", {"abc": "ops"})
