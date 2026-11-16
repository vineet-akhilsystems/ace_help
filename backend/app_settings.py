"""Local ACE login setup. Passwords are accepted but never returned."""
import os
import tempfile
from pathlib import Path

from dotenv import dotenv_values, set_key
from pydantic import BaseModel, ConfigDict, SecretStr, field_validator

from backend.config import ROOT, setting


class Credentials(BaseModel):
    model_config = ConfigDict(extra='forbid')
    username: str
    password: SecretStr

    @field_validator('username')
    @classmethod
    def valid_username(cls, value):
        value = value.strip()
        if not value or len(value) > 120 or any(c in value for c in '\r\n\x00'):
            raise ValueError('Enter a valid ACE username.')
        return value

    @field_validator('password')
    @classmethod
    def valid_password(cls, value):
        secret = value.get_secret_value()
        if not secret or len(secret) > 512 or any(c in secret for c in '\r\n\x00'):
            raise ValueError('Enter a valid ACE password.')
        return value


def login_status():
    username = setting('ACE_USERNAME', legacy='USERNAME')
    return {'username': username, 'configured': bool(username and setting('ACE_PASSWORD', legacy='PASSWORD'))}


def save_credentials(credentials, path=None):
    """Atomically save both quoted values; running sessions keep their current configuration."""
    path = Path(path) if path is not None else ROOT / '.env'
    descriptor, temporary = tempfile.mkstemp(dir=path.parent, prefix='.ace-login-', suffix='.tmp')
    os.close(descriptor)
    try:
        temporary = Path(temporary)
        temporary.write_bytes(path.read_bytes() if path.exists() else b'')
        set_key(temporary, 'ACE_USERNAME', credentials.username, quote_mode='always')
        set_key(temporary, 'ACE_PASSWORD', credentials.password.get_secret_value(), quote_mode='always')
        saved = dotenv_values(temporary, interpolate=False)
        if (saved.get('ACE_PASSWORD') != credentials.password.get_secret_value()
                or saved.get('ACE_USERNAME') != credentials.username):
            raise ValueError('Could not save ACE login.')
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)
