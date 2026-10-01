import pytest
from services.safe_http import UnsafeURLError, validate_url, safe_urlopen


def test_rejects_file_scheme():
    with pytest.raises(UnsafeURLError):
        validate_url("file:///etc/passwd")


def test_rejects_gopher():
    with pytest.raises(UnsafeURLError):
        validate_url("gopher://example.com/")


def test_rejects_http_public():
    with pytest.raises(UnsafeURLError):
        validate_url("http://example.com/x")


def test_rejects_metadata_ip():
    with pytest.raises(UnsafeURLError):
        validate_url("http://169.254.169.254/latest/meta-data/")


def test_rejects_private_https_by_default():
    with pytest.raises(UnsafeURLError):
        validate_url("https://192.168.1.1/")


def test_allows_https_public():
    assert validate_url("https://example.com/api")


def test_allows_http_loopback_when_enabled():
    assert validate_url(
        "http://127.0.0.1:8741/health",
        allowed_schemes=("http", "https"),
        allow_private=True,
    )


def test_host_allowlist():
    with pytest.raises(UnsafeURLError):
        validate_url("https://evil.com/", host_allowlist=["api.openai.com"])
    assert validate_url("https://api.openai.com/v1", host_allowlist=["api.openai.com"])
