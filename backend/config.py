import os
from pathlib import Path
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
FILE_ENV = dotenv_values(ROOT / '.env')


def setting(name: str, default: str = '', legacy: str = '') -> str:
    # Windows defines USERNAME itself; prefer the explicit legacy .env value.
    return os.environ.get(name) or FILE_ENV.get(name) or (FILE_ENV.get(legacy) if legacy else '') or default


RUNTIME = ROOT / 'runtime'
RUNTIME.mkdir(exist_ok=True)
