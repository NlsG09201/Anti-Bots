from unittest.mock import Mock

import pytest
from celery import Celery

from app.workers import celery_app as celery_module


def test_celery_redis_backend_receives_managed_identity_and_verified_tls(monkeypatch):
    provider = object()
    monkeypatch.setattr(
        celery_module,
        "_get_redis_credential_provider",
        Mock(return_value=provider),
    )
    app = Celery("managed-identity-test", backend="rediss://cache.example.com:10000/0")

    celery_module.configure_managed_identity_backend(
        app,
        "rediss://cache.example.com:10000/0",
        "managed_identity",
    )

    connparams = app.backend.connparams
    assert connparams["credential_provider"] is provider
    assert connparams["ssl_check_hostname"] is True
    assert connparams["ssl_cert_reqs"] is not None


@pytest.mark.parametrize(
    "backend_url",
    [
        "redis://cache.example.com:6379/0",
        "rediss://user:password@cache.example.com:10000/0",
    ],
)
def test_celery_managed_identity_rejects_insecure_or_embedded_credentials(backend_url):
    app = Celery("managed-identity-test", backend=backend_url)

    with pytest.raises(ValueError, match="rediss:// without embedded credentials"):
        celery_module.configure_managed_identity_backend(
            app,
            backend_url,
            "managed_identity",
        )
