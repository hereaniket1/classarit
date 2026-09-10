import os
import secrets
import tempfile
from dataclasses import dataclass
from pathlib import Path

from fastapi import Request

from ..config import DATA_DIR  # loads local .env before reading settings


def session_signing_key():
    """Use an optional shared key, otherwise atomically persist a generated key."""
    configured = os.getenv('SESSION_SECRET_KEY', '').strip()
    if configured:
        if len(configured) < 32:
            raise ValueError('An explicitly set SESSION_SECRET_KEY must contain at least 32 characters')
        return configured
    key_path = DATA_DIR / '.session_secret'
    if not key_path.exists():
        # Publish a complete file atomically; concurrent workers use the same winner.
        with tempfile.NamedTemporaryFile(mode='w', dir=DATA_DIR, prefix='.session_secret-', delete=False) as temporary:
            temporary.write(secrets.token_urlsafe(48))
            temporary.flush()
            os.fsync(temporary.fileno())
            temporary_path = Path(temporary.name)
        try:
            try:
                os.link(temporary_path, key_path)
            except FileExistsError:
                pass
        finally:
            temporary_path.unlink()
    key = key_path.read_text().strip()
    if len(key) < 32:
        raise ValueError('The saved session signing key is invalid; restore it or set SESSION_SECRET_KEY')
    return key


@dataclass(frozen=True)
class AuthSettings:
    client_id: str
    client_secret: str
    session_secret: str

    @property
    def ready(self):
        return bool(self.client_id and self.client_secret)


def google_callback_url(request: Request):
    """Build the registered callback on the origin that began the login flow."""
    url = request.url_for('google_callback')
    if url.scheme != 'https' and url.hostname not in ('localhost', '127.0.0.1', '::1'):
        raise ValueError('Open Classarit over HTTPS to sign in with Google')
    return str(url)


def get_settings():
    return AuthSettings(
        os.getenv('GOOGLE_CLIENT_ID', '').strip(),
        os.getenv('GOOGLE_CLIENT_SECRET', '').strip(),
        session_signing_key(),
    )
