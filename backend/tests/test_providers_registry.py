"""Unit tests for the fork's provider registry (open_webui.routers.providers).

The router is imported with the surrounding FastAPI app stubbed out by
`conftest.py`, so these tests only need fastapi, pydantic and aiohttp.

    python -m pytest backend/tests
"""

from __future__ import annotations

import asyncio

import pytest


def test_sanitize_normalises_and_requires_url(providers_mod):
    form = providers_mod.ProviderForm(
        name='  DeepSeek ',
        kind='openai',
        base_url='https://api.deepseek.com/v1/',
        api_key='  sk-secret  ',
        model_ids=['deepseek-chat', ' ', 'deepseek-reasoner'],
    )
    provider = providers_mod._sanitize(form)

    assert provider['name'] == 'DeepSeek'
    assert provider['base_url'] == 'https://api.deepseek.com/v1'
    assert provider['api_key'] == 'sk-secret'
    assert provider['model_ids'] == ['deepseek-chat', 'deepseek-reasoner']
    assert provider['id']
    assert provider['enabled'] is True

    with pytest.raises(providers_mod.HTTPException):
        providers_mod._sanitize(providers_mod.ProviderForm(name='broken', base_url=''))


def test_update_keeps_stored_secret(providers_mod):
    stored = providers_mod._sanitize(
        providers_mod.ProviderForm(name='OpenAI', base_url='https://api.openai.com/v1', api_key='sk-live')
    )

    # api_key=None means "leave it alone"; "" explicitly clears it.
    kept = providers_mod._sanitize(
        providers_mod.ProviderForm(name='OpenAI rename', base_url='https://api.openai.com/v1'),
        stored,
    )
    assert kept['api_key'] == 'sk-live'
    assert kept['id'] == stored['id']

    cleared = providers_mod._sanitize(
        providers_mod.ProviderForm(name='OpenAI', base_url='https://api.openai.com/v1', api_key=''),
        stored,
    )
    assert cleared['api_key'] == ''


def test_public_masks_key(providers_mod):
    provider = providers_mod._sanitize(
        providers_mod.ProviderForm(name='x', base_url='https://x', api_key='sk-abcdefg123456')
    )

    public = providers_mod._public(provider)
    assert 'api_key' not in public
    assert public['api_key_masked'] == 'sk-…3456'
    assert public['has_key'] is True

    assert providers_mod._public(provider, reveal=True)['api_key'] == 'sk-abcdefg123456'


def test_connection_config_maps_auth_styles(providers_mod):
    bearer = providers_mod._sanitize(providers_mod.ProviderForm(name='b', base_url='https://b/v1', api_key='sk-b'))
    config = providers_mod._connection_config(bearer)
    assert config['auth_type'] == 'bearer'
    assert 'headers' not in config

    header = providers_mod._sanitize(
        providers_mod.ProviderForm(
            name='a',
            base_url='https://a/v1',
            api_key='azure-key',
            auth_style='header',
            auth_header='api-key',
            headers={'X-Team': 'core'},
        )
    )
    config = providers_mod._connection_config(header)
    assert config['auth_type'] == 'none'
    assert config['headers'] == {'api-key': 'azure-key', 'X-Team': 'core'}

    anthropic = providers_mod._sanitize(
        providers_mod.ProviderForm(
            name='c', kind='anthropic', base_url='https://api.anthropic.com/v1', api_key='sk-ant'
        )
    )
    config = providers_mod._connection_config(anthropic)
    assert config['provider'] == 'anthropic'
    assert config['headers']['anthropic-version']


def test_models_url_and_parsing(providers_mod):
    openai = {'kind': 'openai', 'base_url': 'https://api.openai.com/v1'}
    assert providers_mod._models_url(openai) == 'https://api.openai.com/v1/models'

    ollama = {'kind': 'ollama', 'base_url': 'https://ollama.internal'}
    assert providers_mod._models_url(ollama) == 'https://ollama.internal/api/tags'

    assert providers_mod._extract_model_ids('openai', {'data': [{'id': 'gpt-4o'}, {'id': 'gpt-4.1'}]}) == [
        'gpt-4o',
        'gpt-4.1',
    ]
    assert providers_mod._extract_model_ids('ollama', {'models': [{'name': 'llama3', 'model': 'llama3:latest'}]}) == [
        'llama3:latest'
    ]
    assert providers_mod._extract_model_ids('anthropic', {'models': [{'name': 'claude-sonnet-4'}]}) == [
        'claude-sonnet-4'
    ]
    assert providers_mod._extract_model_ids('openai', ['a', 'a', 'b']) == ['a', 'b']


def test_split_managed_reindexes_and_keeps_manual(providers_mod):
    urls = ['https://manual/v1', 'https://managed/v1', 'https://manual2/v1']
    keys = ['k0', 'k1', 'k2']
    configs = {
        '1': {'managed_by': 'providers', 'provider_id': 'p1'},
        '2': {'prefix_id': 'm/'},
    }

    kept_urls, kept_keys, kept_configs = providers_mod._split_managed(urls, keys, configs)

    assert kept_urls == ['https://manual/v1', 'https://manual2/v1']
    assert kept_keys == ['k0', 'k2']
    assert kept_configs == {'1': {'prefix_id': 'm/'}}


def test_apply_projects_providers_into_connections(providers_mod):
    config = providers_mod.Config  # FakeConfig instance stored by the fixture
    config.values.update(
        {
            'openai.enable': False,
            'openai.api_base_urls': ['https://manual.example/v1'],
            'openai.api_keys': ['manual-key'],
            'openai.api_configs': {},
            'ollama.enable': True,
            'ollama.base_urls': [],
            'ollama.api_configs': {},
        }
    )

    openai_provider = providers_mod._sanitize(
        providers_mod.ProviderForm(
            name='DeepSeek', base_url='https://api.deepseek.com/v1', api_key='sk-deep', model_ids=['deepseek-chat']
        )
    )
    ollama_provider = providers_mod._sanitize(
        providers_mod.ProviderForm(name='Ollama', kind='ollama', base_url='https://ollama.internal/')
    )
    disabled = providers_mod._sanitize(
        providers_mod.ProviderForm(name='Off', base_url='https://off.example/v1', enabled=False)
    )

    state = asyncio.run(providers_mod._apply(None, [openai_provider, ollama_provider, disabled]))

    assert state['openai_connections'] == 1
    assert state['ollama_connections'] == 1

    urls = config.values['openai.api_base_urls']
    keys = config.values['openai.api_keys']
    configs = config.values['openai.api_configs']

    assert urls == ['https://manual.example/v1', 'https://api.deepseek.com/v1']
    assert keys == ['manual-key', 'sk-deep']
    assert configs['1']['managed_by'] == 'providers'
    assert configs['1']['model_ids'] == ['deepseek-chat']
    assert configs['1']['provider_id'] == openai_provider['id']
    assert config.values['openai.enable'] is True

    assert config.values['ollama.base_urls'] == ['https://ollama.internal']
    assert '0' in config.values['ollama.api_configs']

    # Applying twice must not duplicate the managed connections.
    asyncio.run(providers_mod._apply(None, [openai_provider, ollama_provider, disabled]))
    assert config.values['openai.api_base_urls'] == urls
    assert config.values['ollama.base_urls'] == ['https://ollama.internal']

    # Removing the provider drops its connection again, manual entries survive.
    asyncio.run(providers_mod._apply(None, []))
    assert config.values['openai.api_base_urls'] == ['https://manual.example/v1']
    assert config.values['openai.api_keys'] == ['manual-key']
    assert config.values['openai.api_configs'] == {}


def test_bootstrap_from_env_is_lenient(providers_mod, monkeypatch):
    providers_mod.PROVIDERS_JSON = json_dumps_providers()
    seeded = providers_mod._parse_bootstrap()
    assert len(seeded) == 2
    assert seeded[0]['base_url'] == 'https://api.openai.com/v1'

    providers_mod.PROVIDERS_JSON = 'not json'
    assert providers_mod._parse_bootstrap() == []

    providers_mod.PROVIDERS_JSON = '[{"name": "missing url"}]'
    assert providers_mod._parse_bootstrap() == []


def json_dumps_providers() -> str:
    import json

    return json.dumps(
        [
            {'name': 'OpenAI', 'base_url': 'https://api.openai.com/v1/', 'api_key': 'sk-1'},
            {'name': 'no url'},
            {'name': 'Ollama', 'kind': 'ollama', 'base_url': 'http://localhost:11434'},
        ]
    )
