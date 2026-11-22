"""HTTP tests for the provider registry endpoints.

They exercise the real FastAPI routing (including the order of literal vs
parameterised paths), the masking of stored keys and the projection of enabled
providers onto Open WebUI's native connection settings.
"""

from __future__ import annotations

import pytest

httpx = pytest.importorskip('httpx')

from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture()
def client(providers_app):
    app, module, config = providers_app
    with TestClient(app) as test_client:
        yield test_client, module, config


BODY = {
    'name': 'DeepSeek',
    'kind': 'openai',
    'base_url': 'https://api.deepseek.com/v1/',
    'api_key': 'sk-secret12345',
    'model_ids': ['deepseek-chat'],
    'enabled': True,
}


def test_provider_crud_masks_the_key(client):
    http, module, config = client

    created = http.post('/api/v1/providers/', json=BODY)
    assert created.status_code == 200
    provider = created.json()
    provider_id = provider['id']

    # Secrets never leave the API in clear text, and the trailing slash is normalised.
    assert provider['base_url'] == 'https://api.deepseek.com/v1'
    assert 'api_key' not in provider
    assert provider['api_key_masked'] == 'sk-…2345'
    assert provider['has_key'] is True

    listing = http.get('/api/v1/providers/').json()
    assert [entry['name'] for entry in listing['providers']] == ['DeepSeek']
    assert 'api_key' not in listing['providers'][0]

    revealed = http.get('/api/v1/providers/?reveal=true').json()['providers'][0]
    assert revealed['api_key'] == 'sk-secret12345'

    # Updating without an api_key field keeps the stored secret.
    updated = http.put(
        f'/api/v1/providers/{provider_id}',
        json={**BODY, 'name': 'DeepSeek prod', 'api_key': None},
    ).json()
    assert updated['name'] == 'DeepSeek prod'
    assert config.values['providers.list'][0]['api_key'] == 'sk-secret12345'

    deleted = http.delete(f'/api/v1/providers/{provider_id}')
    assert deleted.status_code == 200
    assert http.get('/api/v1/providers/').json()['providers'] == []


def test_unknown_and_invalid_providers_are_rejected(client):
    http, module, config = client

    assert http.put('/api/v1/providers/missing', json=BODY).status_code == 404
    assert http.delete('/api/v1/providers/missing').status_code == 404

    missing_url = http.post('/api/v1/providers/', json={'name': 'broken', 'base_url': ''})
    assert missing_url.status_code == 400
    assert 'Base URL' in missing_url.json()['detail']

    bad_kind = http.post('/api/v1/providers/', json={'name': 'broken', 'base_url': 'https://x', 'kind': 'nope'})
    assert bad_kind.status_code == 400


def test_preview_route_is_not_swallowed_by_provider_id(client):
    """`/preview/test` must win over `/{provider_id}/test`."""
    http, module, config = client

    res = http.post('/api/v1/providers/preview/test', json={'base_url': 'https://api.openai.com/v1'})
    assert res.status_code == 200
    assert res.json()['models'] == ['stub-model-a', 'stub-model-b']


def test_apply_projects_connections_and_rolls_back(client):
    http, module, config = client

    config.values.update(
        {
            'openai.api_base_urls': ['https://manual.example/v1'],
            'openai.api_keys': ['manual-key'],
            'openai.api_configs': {},
            'ollama.base_urls': [],
            'ollama.api_configs': {},
        }
    )

    created = http.post('/api/v1/providers/', json=BODY).json()

    applied = http.post('/api/v1/providers/apply')
    assert applied.status_code == 200
    assert applied.json()['openai_connections'] == 1

    assert config.values['openai.api_base_urls'] == ['https://manual.example/v1', 'https://api.deepseek.com/v1']
    assert config.values['openai.api_keys'] == ['manual-key', 'sk-secret12345']

    managed = config.values['openai.api_configs']['1']
    assert managed['managed_by'] == 'providers'
    assert managed['provider_id'] == created['id']
    assert managed['model_ids'] == ['deepseek-chat']

    state = http.get('/api/v1/providers/state').json()
    assert state['openai_connections'] == 1

    # A second apply must not duplicate the managed connection.
    http.post('/api/v1/providers/apply')
    assert len(config.values['openai.api_base_urls']) == 2

    # Deleting the provider removes its connection and keeps the manual one.
    http.delete(f'/api/v1/providers/{created["id"]}')
    assert config.values['openai.api_base_urls'] == ['https://manual.example/v1']
    assert config.values['openai.api_keys'] == ['manual-key']
    assert config.values['openai.api_configs'] == {}


def test_model_import_stores_the_allow_list(client):
    http, module, config = client

    created = http.post('/api/v1/providers/', json=BODY).json()
    res = http.post(f'/api/v1/providers/{created["id"]}/models?save=true')

    assert res.status_code == 200
    assert res.json()['count'] == 2
    assert config.values['providers.list'][0]['model_ids'] == ['stub-model-a', 'stub-model-b']


def test_ollama_provider_lands_in_ollama_connections(client):
    http, module, config = client

    http.post('/api/v1/providers/', json={'name': 'Ollama', 'kind': 'ollama', 'base_url': 'http://ollama:11434'})

    assert config.values['ollama.base_urls'] == ['http://ollama:11434']
    assert config.values['ollama.enable'] is True
    assert config.values['ollama.api_configs']['0']['managed_by'] == 'providers'
