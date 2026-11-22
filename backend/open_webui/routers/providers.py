"""Provider registry for this fork of Open WebUI.

Upstream keeps model connections in three parallel, index-addressed settings
(``openai.api_base_urls`` / ``openai.api_keys`` / ``openai.api_configs``).  This
router adds a friendlier layer on top of that: a named list of providers where
an admin fills in the link, the API key / token, the model ids and any custom
headers, then presses one button to project the enabled entries into the native
connection settings.

Nothing in the request pipeline is patched: applying providers rewrites the
same settings the "Admin Settings → Connections" panel writes, so chat, image
generation and task models keep working exactly as before.  Connections that
were added manually in the upstream UI are left untouched - only entries
carrying ``managed_by == "providers"`` are owned by this router.
"""

from __future__ import annotations

import json
import logging
import os
import time
import uuid
from typing import Any, Optional

import aiohttp
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from open_webui.env import (
    AIOHTTP_CLIENT_SESSION_SSL,
    AIOHTTP_CLIENT_TIMEOUT_MODEL_LIST,
)
from open_webui.events import EVENTS, publish_event
from open_webui.models.config import Config
from open_webui.utils.auth import get_admin_user

log = logging.getLogger(__name__)

router = APIRouter()

PROVIDERS_CONFIG_KEY = 'providers.list'
PROVIDERS_STATE_CONFIG_KEY = 'providers.state'

MANAGED_BY = 'providers'
PROVIDER_KINDS = ('openai', 'anthropic', 'gemini', 'ollama', 'custom')
AUTH_STYLES = ('bearer', 'header', 'none')

# Providers given by the environment, e.g.
# PROVIDERS_JSON='[{"name":"DeepSeek","kind":"openai","base_url":"https://api.deepseek.com/v1","api_key":"sk-..."}]'
PROVIDERS_JSON = os.getenv('PROVIDERS_JSON', '')
# Seed + apply the environment providers on the first read of the panel.
PROVIDERS_AUTO_APPLY = os.getenv('PROVIDERS_AUTO_APPLY', 'true').lower() == 'true'

_bootstrapped = False


class ProviderForm(BaseModel):
    model_config = ConfigDict(extra='ignore')

    name: Optional[str] = None
    kind: str = 'openai'
    base_url: str = ''
    api_key: Optional[str] = None
    auth_style: str = 'bearer'
    auth_header: str = 'Authorization'
    model_ids: list[str] = Field(default_factory=list)
    headers: dict[str, str] = Field(default_factory=dict)
    prefix_id: str = ''
    enabled: bool = True
    notes: str = ''


class ProviderConnectionForm(BaseModel):
    """A provider that is not stored yet - used by /test and /models."""

    model_config = ConfigDict(extra='ignore')

    kind: str = 'openai'
    base_url: str = ''
    api_key: str = ''
    auth_style: str = 'bearer'
    auth_header: str = 'Authorization'
    headers: dict[str, str] = Field(default_factory=dict)


ERROR_MESSAGES = {
    'PROVIDER_NOT_FOUND': 'Provider not found',
    'BASE_URL_REQUIRED': 'Base URL is required',
    'CONNECTION_FAILED': 'Could not reach the provider',
}


def _now() -> int:
    return int(time.time())


def _mask_key(key: str) -> str:
    if not key:
        return ''
    if len(key) <= 8:
        return '•' * len(key)
    return f'{key[:3]}…{key[-4:]}'


def _normalize_url(url: str) -> str:
    return (url or '').strip().rstrip('/')


def _validate(form: ProviderForm) -> str:
    kind = (form.kind or 'openai').strip().lower()
    if kind not in PROVIDER_KINDS:
        raise HTTPException(status_code=400, detail=f"Unknown provider kind '{form.kind}'")
    auth_style = (form.auth_style or 'bearer').strip().lower()
    if auth_style not in AUTH_STYLES:
        raise HTTPException(status_code=400, detail=f"Unknown auth style '{form.auth_style}'")
    return kind


def _sanitize(form: ProviderForm, existing: Optional[dict] = None) -> dict:
    """Merge an incoming form onto a stored provider, keeping secrets on update."""
    kind = _validate(form)
    base = dict(existing or {})

    name = (form.name or '').strip() or base.get('name') or f'{kind} provider'
    # api_key=None means "leave the stored token alone"; "" clears it.
    api_key = base.get('api_key', '') if form.api_key is None else form.api_key.strip()

    provider = {
        'id': base.get('id') or str(uuid.uuid4()),
        'name': name,
        'kind': kind,
        'base_url': _normalize_url(form.base_url or ''),
        'api_key': api_key,
        'auth_style': (form.auth_style or 'bearer').strip().lower(),
        'auth_header': (form.auth_header or 'Authorization').strip() or 'Authorization',
        'model_ids': [str(mid).strip() for mid in (form.model_ids or []) if str(mid).strip()],
        'headers': {str(k).strip(): str(v) for k, v in (form.headers or {}).items() if str(k).strip()},
        'prefix_id': (form.prefix_id or '').strip(),
        'enabled': bool(form.enabled),
        'notes': (form.notes or '').strip(),
        'created_at': base.get('created_at', _now()),
        'updated_at': _now(),
    }

    if not provider['base_url']:
        raise HTTPException(status_code=400, detail=ERROR_MESSAGES['BASE_URL_REQUIRED'])

    return provider


def _public(provider: dict, reveal: bool = False) -> dict:
    data = {key: value for key, value in provider.items() if key != 'api_key'}
    data['has_key'] = bool(provider.get('api_key'))
    data['api_key_masked'] = _mask_key(provider.get('api_key', ''))
    if reveal:
        data['api_key'] = provider.get('api_key', '')
    return data


async def _get_providers() -> list[dict]:
    providers = await Config.get(PROVIDERS_CONFIG_KEY)
    return providers if isinstance(providers, list) else []


async def _set_providers(providers: list[dict]) -> None:
    await Config.upsert({PROVIDERS_CONFIG_KEY: providers})


def _parse_bootstrap() -> list[dict]:
    """Read PROVIDERS_JSON once; invalid input must never break the app."""
    if not PROVIDERS_JSON.strip():
        return []
    try:
        raw = json.loads(PROVIDERS_JSON)
    except Exception as exc:
        log.error(f'providers: PROVIDERS_JSON is not valid JSON ({exc}); ignoring')
        return []

    if isinstance(raw, dict):
        raw = [raw]
    if not isinstance(raw, list):
        log.error('providers: PROVIDERS_JSON must be a JSON array of providers; ignoring')
        return []

    providers = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        try:
            providers.append(_sanitize(ProviderForm(**entry)))
        except HTTPException as exc:
            log.error(f"providers: skipping bootstrap entry '{entry.get('name')}': {exc.detail}")
    return providers


async def _ensure_bootstrapped(request: Request) -> list[dict]:
    """Seed stored providers from PROVIDERS_JSON on the first access, then apply once.

    Seeding only happens while the setting has never been written, so an admin who
    deliberately removed every provider does not get them back after a restart.
    """
    global _bootstrapped
    providers = await _get_providers()

    if _bootstrapped:
        return providers

    _bootstrapped = True
    if await Config.get(PROVIDERS_CONFIG_KEY, None) is not None or not PROVIDERS_JSON.strip():
        return providers

    seeded = _parse_bootstrap()
    if not seeded:
        return providers

    await _set_providers(seeded)
    log.info(f'providers: seeded {len(seeded)} provider(s) from PROVIDERS_JSON')

    if PROVIDERS_AUTO_APPLY:
        try:
            await _apply(request, seeded)

        except Exception as exc:
            log.error(f'providers: automatic apply failed: {exc}')

    return seeded


# Connection helpers -----------------------------------------------------------


def _auth_headers(provider: dict) -> dict:
    """Headers used when probing a provider outside of Open WebUI's own pipeline."""
    key = provider.get('api_key', '')
    style = provider.get('auth_style', 'bearer')
    headers = {'Content-Type': 'application/json'}

    if key and style == 'bearer':
        headers['Authorization'] = f'Bearer {key}'
    elif key and style == 'header':
        headers[provider.get('auth_header') or 'Authorization'] = key

    headers.update(provider.get('headers') or {})
    return headers


def _models_url(provider: dict) -> str:
    base = _normalize_url(provider.get('base_url', ''))
    if provider.get('kind') == 'ollama':
        return f'{base}/api/tags'
    if provider.get('kind') == 'anthropic' and 'api.anthropic.com' in base:
        return f'{base}/models'
    return f'{base}/models'


def _extract_model_ids(kind: str, payload: Any) -> list[str]:
    """Accept OpenAI, Anthropic and Ollama model-list shapes."""
    if isinstance(payload, list):
        entries = payload
    elif isinstance(payload, dict):
        entries = payload.get('data') or payload.get('models') or payload.get('objects') or []
    else:
        entries = []

    ids: list[str] = []
    for entry in entries:
        if isinstance(entry, str):
            ids.append(entry)
            continue
        if not isinstance(entry, dict):
            continue
        model_id = entry.get('id') or entry.get('name') or entry.get('model')
        if not model_id:
            continue
        if kind == 'ollama' and isinstance(entry.get('model'), str):
            model_id = entry['model']
        ids.append(str(model_id))

    # Keep order, drop duplicates.
    return list(dict.fromkeys(ids))


async def _fetch_models(provider: dict) -> tuple[list[str], int]:
    started = time.monotonic()
    url = _models_url(provider)
    timeout = aiohttp.ClientTimeout(total=AIOHTTP_CLIENT_TIMEOUT_MODEL_LIST or 30)

    try:
        async with aiohttp.ClientSession(timeout=timeout, trust_env=True) as session:
            async with session.get(
                url,
                headers=_auth_headers(provider),
                ssl=AIOHTTP_CLIENT_SESSION_SSL,
            ) as response:
                if response.status >= 400:
                    body = (await response.text())[:400]
                    raise HTTPException(
                        status_code=400,
                        detail=f'{response.status} {response.reason or ""} — {body}'.strip(),
                    )
                payload = await response.json(content_type=None)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f'{ERROR_MESSAGES["CONNECTION_FAILED"]}: {exc}') from exc

    return _extract_model_ids(provider.get('kind', 'openai'), payload), int((time.monotonic() - started) * 1000)


def _connection_config(provider: dict) -> dict:
    """Translate a provider into an Open WebUI ``openai.api_configs`` entry."""
    auth_type = 'bearer' if provider.get('auth_style', 'bearer') == 'bearer' else 'none'

    config: dict[str, Any] = {
        'enable': True,
        'model_ids': provider.get('model_ids') or None,
        'prefix_id': provider.get('prefix_id') or None,
        'auth_type': auth_type,
        'connection_type': 'external',
        'managed_by': MANAGED_BY,
        'provider_id': provider['id'],
    }

    if provider.get('kind') == 'anthropic':
        config['provider'] = 'anthropic'

    headers = {}
    if auth_type == 'none' and provider.get('api_key'):
        headers[provider.get('auth_header') or 'Authorization'] = provider['api_key']
    if provider.get('kind') == 'anthropic':
        headers.setdefault('anthropic-version', '2023-06-01')
    headers.update(provider.get('headers') or {})

    if headers:
        config['headers'] = headers

    return {key: value for key, value in config.items() if value not in (None, {}, '')}


def _ollama_config(provider: dict) -> dict:
    config: dict[str, Any] = {
        'enable': True,
        'model_ids': provider.get('model_ids') or None,
        'prefix_id': provider.get('prefix_id') or None,
        'connection_type': 'external',
        'managed_by': MANAGED_BY,
        'provider_id': provider['id'],
    }
    if provider.get('api_key'):
        config['headers'] = {**(provider.get('headers') or {}), 'Authorization': f'Bearer {provider["api_key"]}'}
    return {key: value for key, value in config.items() if value not in (None, {}, '')}


def _split_managed(urls: list[str], keys: list[str], configs: dict) -> tuple[list[str], list[str], dict]:
    """Drop the connections this router owns, returning the manual remainder."""
    kept_urls: list[str] = []
    kept_keys: list[str] = []
    kept_configs: dict = {}

    for idx, url in enumerate(urls):
        config = configs.get(str(idx), {}) if isinstance(configs, dict) else {}
        if isinstance(config, dict) and config.get('managed_by') == MANAGED_BY:
            continue
        kept_urls.append(url)
        kept_keys.append(keys[idx] if idx < len(keys) else '')
        if isinstance(config, dict) and config:
            kept_configs[str(len(kept_urls) - 1)] = config

    return kept_urls, kept_keys[: len(kept_urls)], kept_configs


async def _apply(request: Request, providers: list[dict], actor: Any = None) -> dict:
    """Project enabled providers onto Open WebUI's native OpenAI/Ollama settings."""
    from open_webui.routers import ollama as ollama_router
    from open_webui.routers import openai as openai_router

    enabled = [provider for provider in providers if provider.get('enabled') and provider.get('base_url')]
    openai_providers = [provider for provider in enabled if provider['kind'] != 'ollama']
    ollama_providers = [provider for provider in enabled if provider['kind'] == 'ollama']

    openai_values = await Config.get_many(
        'openai.enable', 'openai.api_base_urls', 'openai.api_keys', 'openai.api_configs'
    )
    urls = list(openai_values.get('openai.api_base_urls') or [])
    keys = list(openai_values.get('openai.api_keys') or [])
    configs = dict(openai_values.get('openai.api_configs') or {})

    urls, keys, configs = _split_managed(urls, keys, configs)

    for provider in openai_providers:
        idx = len(urls)
        urls.append(_normalize_url(provider['base_url']))
        keys.append(provider.get('api_key', '') if provider.get('auth_style') == 'bearer' else '')
        configs[str(idx)] = _connection_config(provider)

    ollama_values = await Config.get_many('ollama.enable', 'ollama.base_urls', 'ollama.api_configs')
    ollama_urls = list(ollama_values.get('ollama.base_urls') or [])
    ollama_configs = dict(ollama_values.get('ollama.api_configs') or {})

    ollama_urls, _, ollama_configs = _split_managed(ollama_urls, [''] * len(ollama_urls), ollama_configs)

    for provider in ollama_providers:
        idx = len(ollama_urls)
        ollama_urls.append(_normalize_url(provider['base_url']))
        ollama_configs[str(idx)] = _ollama_config(provider)

    updates: dict[str, Any] = {
        'openai.api_base_urls': urls,
        'openai.api_keys': keys,
        'openai.api_configs': configs,
        'ollama.base_urls': ollama_urls,
        'ollama.api_configs': ollama_configs,
    }

    # Only take over the master switches when we actually own connections, so a
    # fresh install keeps its default behaviour.
    if openai_providers or not openai_values.get('openai.enable'):
        updates['openai.enable'] = bool(openai_providers)
    if ollama_providers:
        updates['ollama.enable'] = True

    await Config.upsert(updates)

    state = {
        'applied_at': _now(),
        'openai_connections': len(openai_providers),
        'ollama_connections': len(ollama_providers),
        'provider_count': len(providers),
    }
    await Config.upsert({PROVIDERS_STATE_CONFIG_KEY: state})

    await openai_router.clear_models_cache(request)
    await ollama_router.clear_models_cache(request)

    await publish_event(
        request,
        EVENTS.MODEL_PROVIDER_CONFIG_UPDATED,
        actor=actor,
        subject_id='providers',
        subject_type='model.provider_config',
        data={
            'provider': 'providers',
            'openai_connections': len(openai_providers),
            'ollama_connections': len(ollama_providers),
        },
    )

    return state


# Endpoints -------------------------------------------------------------------


@router.get('/')
async def list_providers(request: Request, reveal: bool = False, user=Depends(get_admin_user)):
    providers = await _ensure_bootstrapped(request)
    state = await Config.get(PROVIDERS_STATE_CONFIG_KEY) or {}
    return {
        'providers': [_public(provider, reveal) for provider in providers],
        'kinds': list(PROVIDER_KINDS),
        'auth_styles': list(AUTH_STYLES),
        'state': state,
    }


@router.post('/')
async def create_provider(request: Request, form_data: ProviderForm, user=Depends(get_admin_user)):
    providers = await _ensure_bootstrapped(request)
    provider = _sanitize(form_data)
    providers.append(provider)
    await _set_providers(providers)
    await _apply(request, providers, actor=user)
    return _public(provider)


@router.put('/{provider_id}')
async def update_provider(request: Request, provider_id: str, form_data: ProviderForm, user=Depends(get_admin_user)):
    providers = await _get_providers()
    idx = next((i for i, provider in enumerate(providers) if provider.get('id') == provider_id), None)
    if idx is None:
        raise HTTPException(status_code=404, detail=ERROR_MESSAGES['PROVIDER_NOT_FOUND'])

    providers[idx] = _sanitize(form_data, providers[idx])
    await _set_providers(providers)
    await _apply(request, providers, actor=user)
    return _public(providers[idx])


@router.delete('/{provider_id}')
async def delete_provider(request: Request, provider_id: str, user=Depends(get_admin_user)):
    providers = await _get_providers()
    remaining = [provider for provider in providers if provider.get('id') != provider_id]
    if len(remaining) == len(providers):
        raise HTTPException(status_code=404, detail=ERROR_MESSAGES['PROVIDER_NOT_FOUND'])

    await _set_providers(remaining)
    await _apply(request, remaining, actor=user)
    return {'status': True}


@router.post('/preview/test')
async def test_ad_hoc(request: Request, form_data: ProviderConnectionForm, user=Depends(get_admin_user)):
    """Probe a form that has not been saved yet (used by the settings editor)."""
    provider = form_data.model_dump()
    provider['base_url'] = _normalize_url(provider.get('base_url', ''))
    if not provider['base_url']:
        raise HTTPException(status_code=400, detail=ERROR_MESSAGES['BASE_URL_REQUIRED'])

    model_ids, latency_ms = await _fetch_models(provider)
    return {'status': 'ok', 'models': model_ids, 'count': len(model_ids), 'latency_ms': latency_ms}


@router.post('/{provider_id}/test')
async def test_provider(request: Request, provider_id: str, user=Depends(get_admin_user)):
    providers = await _get_providers()
    provider = next((item for item in providers if item.get('id') == provider_id), None)
    if provider is None:
        raise HTTPException(status_code=404, detail=ERROR_MESSAGES['PROVIDER_NOT_FOUND'])

    model_ids, latency_ms = await _fetch_models(provider)
    return {'status': 'ok', 'models': model_ids, 'count': len(model_ids), 'latency_ms': latency_ms}


@router.post('/{provider_id}/models')
async def fetch_provider_models(request: Request, provider_id: str, save: bool = False, user=Depends(get_admin_user)):
    """List the models a provider exposes; ``save=true`` stores them as the allow-list."""
    providers = await _get_providers()
    provider = next((item for item in providers if item.get('id') == provider_id), None)
    if provider is None:
        raise HTTPException(status_code=404, detail=ERROR_MESSAGES['PROVIDER_NOT_FOUND'])

    model_ids, _ = await _fetch_models(provider)

    if save:
        for idx, item in enumerate(providers):
            if item.get('id') == provider_id:
                item['model_ids'] = model_ids
                item['updated_at'] = _now()
                providers[idx] = item
        await _set_providers(providers)
        await _apply(request, providers, actor=user)

    return {'models': model_ids, 'count': len(model_ids), 'saved': save}


@router.post('/apply')
async def apply_providers(request: Request, user=Depends(get_admin_user)):
    """Push every enabled provider into Admin Settings → Connections."""
    providers = await _ensure_bootstrapped(request)
    state = await _apply(request, providers, actor=user)
    return {'status': True, **state}


@router.get('/state')
async def get_state(request: Request, user=Depends(get_admin_user)):
    return await Config.get(PROVIDERS_STATE_CONFIG_KEY) or {}
