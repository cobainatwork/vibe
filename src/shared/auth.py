"""API key verification."""


class AuthError(Exception):
    """Raised when API key auth fails."""


def verify_api_key(api_key: str | None, valid_keys: dict[str, str]) -> str:
    """Verify api_key against allowed keys mapping (key -> name).

    Returns the key's display name on success.
    Raises AuthError on failure.
    """
    if not api_key:
        raise AuthError("missing X-API-Key header")
    if api_key not in valid_keys:
        raise AuthError("invalid X-API-Key")
    return valid_keys[api_key]
