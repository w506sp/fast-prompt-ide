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
    except urllib.error.HTTPError as exc:
        body = exc.read().decode('utf-8', errors='replace') if exc.fp else ''
        raise OllamaError(f"Ollama returned HTTP {exc.code}: {body or exc.reason}") from exc
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


def generate_stream(model, prompt, options=None, timeout=None):
    """Stream a completion from Ollama. Yields dicts as Ollama emits them.

    Each yielded dict has 'response' (a chunk of text) and 'done' (bool). The
    final dict (done=True) carries 'eval_count', 'prompt_eval_count', etc.
    Raises OllamaError on transport failure.
    """
    payload = {'model': model, 'prompt': prompt, 'stream': True}
    if options:
        payload['options'] = options
    url = f"{_base_url()}/api/generate"
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode('utf-8'),
        method='POST',
        headers={'Content-Type': 'application/json'},
    )
    timeout = timeout if timeout is not None else getattr(settings, 'OLLAMA_TIMEOUT', 120)
    try:
        resp = urllib.request.urlopen(req, timeout=timeout)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode('utf-8', errors='replace') if exc.fp else ''
        raise OllamaError(f"Ollama returned HTTP {exc.code}: {body or exc.reason}") from exc
    except urllib.error.URLError as exc:
        raise OllamaError(f"Could not reach Ollama at {_base_url()}: {exc.reason}") from exc
    with resp:
        for raw in resp:
            line = raw.decode('utf-8', errors='replace').strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                # Ollama emits one JSON object per line — skip garbage rather than abort.
                continue


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
