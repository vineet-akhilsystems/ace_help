import os
from pathlib import Path
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
FILE_ENV = dotenv_values(ROOT / '.env')
# Login values are literal: a password may contain ${...}.
LOGIN_ENV = dotenv_values(ROOT / '.env', interpolate=False)


def setting(name: str, default: str = '', legacy: str = '') -> str:
    if name in ('ACE_USERNAME', 'ACE_PASSWORD'):
        return LOGIN_ENV.get(name) or os.environ.get(name) or (LOGIN_ENV.get(legacy) if legacy else '') or default
    # Windows defines USERNAME itself; prefer the explicit legacy .env value.
    return os.environ.get(name) or FILE_ENV.get(name) or (FILE_ENV.get(legacy) if legacy else '') or default


def save_setting(name: str, value: str, path=ROOT / '.env') -> None:
    """Sets one NAME=value line in .env (replacing it or adding it) and leaves every other line as it was."""
    text = path.read_bytes().decode('utf-8') if path.exists() else ''
    newline = '\r\n' if '\r\n' in text else '\n'
    lines = text.splitlines()
    line = f'{name}={value}'
    found = [i for i, l in enumerate(lines) if l.split('=', 1)[0].strip() == name]
    if found:
        lines[found[0]] = line
    else:
        lines.append(line)
    path.write_bytes((newline.join(lines) + newline).encode('utf-8'))
    if path == ROOT / '.env':
        FILE_ENV[name] = value
        if name in os.environ:
            os.environ[name] = value


RUNTIME = ROOT / 'runtime'
RUNTIME.mkdir(exist_ok=True)
