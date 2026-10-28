import asyncio
import json
import os
import shutil
import subprocess
import tempfile
import httpx
from backend.config import setting


class ProviderError(RuntimeError):
    pass


async def post_json(provider: str, url: str, **kwargs) -> dict:
    async with httpx.AsyncClient(timeout=90) as client:
        for attempt in range(3):
            try:
                response = await client.post(url, **kwargs)
            except httpx.RequestError:
                raise ProviderError(f'{provider} could not be reached. Please retry.') from None
            if response.status_code in (429, 502, 503, 529) and attempt < 2:
                await asyncio.sleep(2 ** attempt)
                continue
            if response.is_error:
                # Never return provider bodies, which may contain credentials or private input.
                raise ProviderError(f'{provider} returned HTTP {response.status_code}. Check configuration or quota.')
            try:
                return response.json()
            except ValueError:
                raise ProviderError(f'{provider} returned an invalid response.') from None


def api_key(name: str) -> str:
    value = setting(name)
    if not value:
        raise ProviderError(f'Configure {name} in the server .env file.')
    return value


LABELS = {'antigravity': 'Antigravity', 'claude': 'Claude Code', 'codex': 'Codex'}


def strict_schema(node):
    """Codex structured output needs every property required, no defaults and no titles."""
    if isinstance(node, list):
        return [strict_schema(n) for n in node]
    if not isinstance(node, dict):
        return node
    out = {k: strict_schema(v) for k, v in node.items() if k not in ('default', 'title', 'properties', '$defs')}
    for key in ('properties', '$defs'):  # maps of names to schemas: keep every name
        if isinstance(node.get(key), dict):
            out[key] = {name: strict_schema(v) for name, v in node[key].items()}
    if 'properties' in out:
        out['required'] = list(out['properties'])
        out['additionalProperties'] = False
    return out


def _structured(stdout: str) -> dict:
    payload = json.loads(stdout)
    if isinstance(payload.get('structured_output'), dict):
        return payload['structured_output']
    for key in ('response', 'result'):
        if isinstance(payload.get(key), str) and payload[key].strip():
            return json.loads(payload[key])
    raise ValueError('no structured output')


def _run_agent_sync(agent: str, prompt: str, schema: dict) -> dict:
    """Asks a local coding agent for JSON only: no tools, no files, nothing written."""
    label = LABELS.get(agent)
    exe = {'antigravity': setting('ANTIGRAVITY_CMD', 'agy'), 'claude': 'claude', 'codex': 'codex'}.get(agent)
    cmd = shutil.which(exe) if exe else None
    if not cmd:
        raise ProviderError(f'{label or agent} is not installed or not on PATH. Pick another agent.')
    folder = tempfile.mkdtemp(prefix='ace-agent-')
    schema_file, answer_file = os.path.join(folder, 'schema.json'), os.path.join(folder, 'answer.json')
    stdin = None
    try:
        with open(schema_file, 'w', encoding='utf-8') as f:
            json.dump(strict_schema(schema) if agent == 'codex' else schema, f, ensure_ascii=False)
        if agent == 'antigravity':
            args = [cmd, '-p', prompt, '--output-format', 'json', '--json-schema', schema_file,
                    '--disable-slash-commands', '--effort', setting('ANTIGRAVITY_EFFORT', 'low')]
            if setting('ANTIGRAVITY_MODEL'):
                args += ['--model', setting('ANTIGRAVITY_MODEL')]
        elif agent == 'claude':
            args, stdin = [cmd, '-p', '--output-format', 'json', '--json-schema', json.dumps(schema),
                           '--tools', '', '--strict-mcp-config', '--no-session-persistence'], prompt
        else:
            # codex is a .cmd shim that mangles multi-line arguments, so the prompt goes through stdin.
            args, stdin = [cmd, 'exec', '--skip-git-repo-check', '--ephemeral', '-s', 'read-only',
                           '--disable', 'shell_tool', '-c', 'approval_policy="never"', '-C', folder,
                           '--output-schema', schema_file, '-o', answer_file, '-'], prompt
        res = subprocess.run(args, input=stdin, capture_output=True, text=True, encoding='utf-8', errors='replace',
                             timeout=float(setting('AGENT_TIMEOUT_SECONDS', '180')), check=False, cwd=folder)
        if res.returncode != 0:
            raise ProviderError(f'{label} could not draft the tasks. Please retry or pick another agent.')
        if agent == 'codex':
            with open(answer_file, encoding='utf-8') as f:
                return json.loads(f.read())
        return _structured(res.stdout)
    except subprocess.TimeoutExpired:
        raise ProviderError(f'{label} timed out while drafting the tasks. Please retry.') from None
    except (OSError, ValueError, KeyError, TypeError):
        raise ProviderError(f'{label} did not return usable tasks. Try clearer notes.') from None
    finally:
        shutil.rmtree(folder, ignore_errors=True)


async def agent_json(agent: str, prompt: str, schema: dict) -> dict:
    return await asyncio.to_thread(_run_agent_sync, agent, prompt, schema)


async def transcribe(data: bytes, filename: str, content_type: str) -> str:
    result = await post_json('Sarvam', 'https://api.sarvam.ai/speech-to-text',
        headers={'api-subscription-key': api_key('SARVAM_API_KEY')},
        files={'file': (filename, data, content_type)},
        data={'model': setting('SARVAM_MODEL', 'saarika:v2.5'), 'language_code': 'unknown'})
    transcript = result.get('transcript', '').strip()
    if not transcript:
        raise ProviderError('No speech was detected. Record again or type your notes.')
    return transcript
