"""Small, bounded OpenAI-compatible chat adapter. No agent framework or fixed model."""
import json
import os
import urllib.parse
import urllib.request


def endpoint(base, resource, allow_http=False):
    parsed = urllib.parse.urlsplit(base)
    if (not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment
            or parsed.scheme not in ('https', 'http')
            or (parsed.scheme == 'http' and not allow_http)):
        raise ValueError('Configure an HTTPS API base URL, or explicitly allow HTTP for a local service.')
    return base.rstrip('/') + '/' + resource.lstrip('/')


def configured():
    return bool(os.environ.get('AI_BASE_URL') and os.environ.get('AI_MODEL'))


def chat_json(messages, max_tokens=3000):
    if not configured():
        raise ValueError('AI_BASE_URL and AI_MODEL are required.')
    url = endpoint(os.environ['AI_BASE_URL'], 'chat/completions', os.environ.get('AI_ALLOW_HTTP') == 'true')
    payload = {'model': os.environ['AI_MODEL'], 'messages': messages, 'temperature': 0}
    # Some compatible providers use different token-limit fields. This is configurable.
    field = os.environ.get('AI_TOKEN_LIMIT_FIELD', 'max_tokens')
    if field not in ('max_tokens', 'max_completion_tokens', ''):
        raise ValueError('Unsupported token-limit field.')
    if field:
        payload[field] = max_tokens
    headers = {'Content-Type': 'application/json'}
    key = os.environ.get('AI_API_KEY', '')
    if key:
        headers['Authorization'] = 'Bearer ' + key
    request = urllib.request.Request(url, json.dumps(payload, ensure_ascii=False).encode(), headers)
    # Provider errors are never logged with their body, authorization header or user content.
    try:
        with urllib.request.urlopen(request, timeout=150) as response:
            raw = response.read(2_000_001)
        if len(raw) > 2_000_000:
            raise ValueError('Response too large.')
        content = json.loads(raw)['choices'][0]['message']['content'].strip()
        if content.startswith('```'):
            content = content.partition('\n')[2].rsplit('```', 1)[0]
        result = json.loads(content)
        if not isinstance(result, dict):
            raise ValueError('Expected a JSON object.')
        return result
    except Exception:
        raise ValueError('The configured AI endpoint did not return a valid JSON result.') from None
