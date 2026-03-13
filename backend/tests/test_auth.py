import pytest
from app import create_app
from app.config import Config


class AuthTestConfig(Config):
    TESTING = True
    API_KEY = "test-secret-key"


class NoAuthConfig(Config):
    TESTING = True
    API_KEY = None


def test_health_always_accessible_without_key():
    app = create_app(AuthTestConfig)
    client = app.test_client()
    resp = client.get('/health')
    assert resp.status_code == 200


def test_api_rejected_without_key():
    app = create_app(AuthTestConfig)
    client = app.test_client()
    resp = client.get('/api/graph/')
    assert resp.status_code == 401


def test_api_rejected_with_wrong_key():
    app = create_app(AuthTestConfig)
    client = app.test_client()
    resp = client.get('/api/graph/', headers={'X-API-Key': 'wrong-key'})
    assert resp.status_code == 401


def test_api_accepted_with_valid_key():
    app = create_app(AuthTestConfig)
    client = app.test_client()
    resp = client.get('/api/graph/', headers={'X-API-Key': 'test-secret-key'})
    # Auth passes (endpoint may return 404/405 but NOT 401)
    assert resp.status_code != 401


def test_auth_disabled_when_no_key():
    app = create_app(NoAuthConfig)
    client = app.test_client()
    resp = client.get('/api/graph/')
    # No auth configured, so should not get 401
    assert resp.status_code != 401
