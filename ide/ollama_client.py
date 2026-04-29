"""Thin wrapper around the Ollama local REST API.

Uses stdlib only (urllib) — no extra dependency. Errors are normalized into
OllamaError so callers can render a friendly message.
"""
import json
import urllib.request
import urllib.error
from django.conf import settings


class OllamaError(Exception):
    pass


def _base_url():
    return getattr(settings, 'OLLAMA_BASE_URL', 'http://localhost:11434').rstrip('/')


def _request(path, payload=None, method='GET', timeout=None):
    url = f"{_base_url()}{path}"
    data = json.dumps(payload).encode('utf-8') if payload is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={'Content-Type': 'application/json'} if data else {},
    )
    timeout = timeout if timeout is not None else getattr(settings, 'OLLAMA_TIMEOUT', 120)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode('utf-8'))
    except urllib.error.URLError as exc:
        raise OllamaError(f"Could not reach Ollama at {_base_url()}: {exc.reason}") from exc
    except json.JSONDecodeError as exc:
        raise OllamaError(f"Invalid JSON from Ollama: {exc}") from exc


def list_models():
    """Return a list of installed model names. Empty list if Ollama is unreachable."""
    try:
        data = _request('/api/tags')
    except OllamaError:
        return []
    return [m.get('name', '') for m in data.get('models', []) if m.get('name')]


def generate(model, prompt, options=None, timeout=None):
    """Run a non-streaming completion. Returns the full response dict from Ollama.

    The response includes 'response' (text), 'total_duration', 'eval_count',
    'prompt_eval_count', etc. — see Ollama's /api/generate docs.
    """
    payload = {
        'model': model,
        'prompt': prompt,
        'stream': False,
    }
    if options:
        payload['options'] = options
    return _request('/api/generate', payload=payload, method='POST', timeout=timeout)
