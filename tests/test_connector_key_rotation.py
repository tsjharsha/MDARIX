"""Connector API keys carry a key ID so the encryption key can rotate; server secret names are per tenant."""

import base64
import os
import uuid

import pytest

from access_control import connector_secrets
from access_control.connector_secrets import open_sealed, seal, sealed_key_id
from backend.app.access.outbound import secret_ref_problem, tenant_secret_prefix

OLD = base64.urlsafe_b64encode(os.urandom(32)).decode()
NEW = base64.urlsafe_b64encode(os.urandom(32)).decode()


def _use(monkeypatch, key, key_id, older=""):
    monkeypatch.setenv("MDARIX_CONNECTOR_ENCRYPTION_KEY", key)
    monkeypatch.setenv("MDARIX_CONNECTOR_ENCRYPTION_KEY_ID", key_id)
    monkeypatch.setenv("MDARIX_CONNECTOR_ENCRYPTION_KEYS", older)


def test_a_rotated_key_still_opens_older_values_until_they_are_resealed(monkeypatch):
    tenant, connector = uuid.uuid4(), uuid.uuid4()
    _use(monkeypatch, OLD, "k1")
    token = seal("sk_live_value_1234", tenant, connector)
    assert sealed_key_id(token) == "k1"

    _use(monkeypatch, NEW, "k2", older=f"k1:{OLD}")
    assert open_sealed(token, tenant, connector) == "sk_live_value_1234"
    resealed = seal(open_sealed(token, tenant, connector), tenant, connector)
    assert sealed_key_id(resealed) == "k2"

    _use(monkeypatch, NEW, "k2")  # the old key is removed once everything is re-sealed
    assert open_sealed(resealed, tenant, connector) == "sk_live_value_1234"
    with pytest.raises(ValueError, match="CONNECTOR_KEY_ID_UNKNOWN"):
        open_sealed(token, tenant, connector)


def test_a_value_stays_bound_to_its_tenant_and_connector(monkeypatch):
    _use(monkeypatch, NEW, "k2")
    tenant, connector = uuid.uuid4(), uuid.uuid4()
    token = seal("sk_live_value_1234", tenant, connector)
    with pytest.raises(Exception):
        open_sealed(token, tenant, uuid.uuid4())


def test_values_sealed_before_key_ids_still_open(monkeypatch):
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    _use(monkeypatch, NEW, "k2")
    tenant, connector = uuid.uuid4(), uuid.uuid4()
    key = base64.urlsafe_b64decode(NEW + "=" * (-len(NEW) % 4))
    nonce = os.urandom(12)
    sealed = AESGCM(key).encrypt(nonce, b"sk_legacy_value_99", f"{tenant}:{connector}".encode())
    legacy = base64.urlsafe_b64encode(b"MDARIXCON1" + nonce + sealed).decode()
    assert open_sealed(legacy, tenant, connector) == "sk_legacy_value_99"


def test_a_malformed_keyring_entry_is_refused(monkeypatch):
    _use(monkeypatch, NEW, "k2", older="not-a-pair")
    with pytest.raises(connector_secrets.ConnectorSecretsUnavailable):
        connector_secrets.keyring()


def test_production_connectors_may_only_name_their_own_tenants_secrets(monkeypatch):
    assert tenant_secret_prefix("TEN0351") == "MDARIX_CONNECTOR_SECRET_TEN0351_"
    monkeypatch.setenv("MDARIX_ENV", "development")
    assert secret_ref_problem("MDARIX_CONNECTOR_SECRET_TRACKWISE", "TEN0351") is None
    monkeypatch.setenv("MDARIX_ENV", "production")
    assert (
        secret_ref_problem("MDARIX_CONNECTOR_SECRET_TRACKWISE", "TEN0351") == "CONNECTOR_CREDENTIAL_REF_NOT_FOR_TENANT"
    )
    assert secret_ref_problem("MDARIX_CONNECTOR_SECRET_TEN0352_TRACKWISE", "TEN0351") is not None
    assert secret_ref_problem("MDARIX_CONNECTOR_SECRET_TEN0351_TRACKWISE", "TEN0351") is None
    assert secret_ref_problem("MDARIX_SMTP_PASSWORD", "TEN0351") == "CONNECTOR_CREDENTIAL_REF_INVALID"
