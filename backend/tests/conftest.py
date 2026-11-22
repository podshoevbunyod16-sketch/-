"""Shared fixtures for the fork's backend tests.

`open_webui.routers.providers` is imported with the surrounding FastAPI app
stubbed out, so these tests need only fastapi, pydantic, aiohttp and (for the
TestClient) httpx — no database and no running server.
"""

from __future__ import annotations

import importlib.util
import pathlib
import sys
import types

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1] / 'open_webui'


class FakeConfig:
    """Minimal stand-in for open_webui.models.config.Config."""

    def __init__(self, values: dict | None = None) -> None:
        self.values = dict(values or {})

    async def get(self, key, default=None, **kwargs):
        return self.values.get(key, default)

    async def get_many(self, *keys, **kwargs):
        return {key: self.values[key] for key in keys if key in self.values}

    async def upsert(self, updates, **kwargs):
        self.values.update(updates)


async def _clear_models_cache(request):  # pragma: no cover - cache is not under test
    return None


async def _get_admin_user():  # pragma: no cover - auth is not under test
    return {'id': 'test-admin', 'role': 'admin'}


def load_providers_module(monkeypatch, config: FakeConfig, published: list | None = None):
    """Import routers/providers.py against stubbed open_webui modules."""
    package = types.ModuleType('open_webui')
    package.__path__ = [str(ROOT)]

    env = types.ModuleType('open_webui.env')
    env.AIOHTTP_CLIENT_SESSION_SSL = True
    env.AIOHTTP_CLIENT_TIMEOUT_MODEL_LIST = 10

    events = types.ModuleType('open_webui.events')

    class _Events:
        MODEL_PROVIDER_CONFIG_UPDATED = 'model.provider_config.updated'

    events.EVENTS = _Events()

    async def publish_event(request, event, **kwargs):
        if published is not None:
            published.append(kwargs)

    events.publish_event = publish_event

    models_pkg = types.ModuleType('open_webui.models')
    models_pkg.__path__ = [str(ROOT / 'models')]
    config_mod = types.ModuleType('open_webui.models.config')
    config_mod.Config = config

    utils_pkg = types.ModuleType('open_webui.utils')
    utils_pkg.__path__ = [str(ROOT / 'utils')]
    auth_mod = types.ModuleType('open_webui.utils.auth')
    auth_mod.get_admin_user = _get_admin_user

    routers_pkg = types.ModuleType('open_webui.routers')
    routers_pkg.__path__ = [str(ROOT / 'routers')]

    openai_stub = types.ModuleType('open_webui.routers.openai')
    ollama_stub = types.ModuleType('open_webui.routers.ollama')
    openai_stub.clear_models_cache = _clear_models_cache
    ollama_stub.clear_models_cache = _clear_models_cache

    stubs = {
        'open_webui': package,
        'open_webui.env': env,
        'open_webui.events': events,
        'open_webui.models': models_pkg,
        'open_webui.models.config': config_mod,
        'open_webui.utils': utils_pkg,
        'open_webui.utils.auth': auth_mod,
        'open_webui.routers': routers_pkg,
        'open_webui.routers.openai': openai_stub,
        'open_webui.routers.ollama': ollama_stub,
    }

    for name, module in stubs.items():
        monkeypatch.setitem(sys.modules, name, module)

    spec = importlib.util.spec_from_file_location('providers_under_test', ROOT / 'routers' / 'providers.py')
    module = importlib.util.module_from_spec(spec)
    # Register before exec so pydantic can resolve annotations of this module.
    sys.modules['providers_under_test'] = module
    spec.loader.exec_module(module)

    module._bootstrapped = True  # never read PROVIDERS_JSON during tests
    return module


@pytest.fixture()
def providers_mod(monkeypatch):
    config = FakeConfig()
    module = load_providers_module(monkeypatch, config)
    module.config = config
    return module


@pytest.fixture()
def providers_app(monkeypatch):
    """A FastAPI app exposing the router, plus a stubbed model fetch."""
    from fastapi import FastAPI

    config = FakeConfig()
    module = load_providers_module(monkeypatch, config)

    async def fake_fetch(provider):
        return (['stub-model-a', 'stub-model-b'], 25)

    module._fetch_models = fake_fetch

    app = FastAPI()
    app.include_router(module.router, prefix='/api/v1/providers')
    return app, module, config
