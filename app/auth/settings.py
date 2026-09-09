import os
from dataclasses import dataclass
from urllib.parse import urlsplit

from ..config import PROJECT_DIR  # loads local .env before reading settings


@dataclass(frozen=True)
class AuthSettings:
    client_id: str
    client_secret: str
    redirect_uri: str
    session_secret: str
    secure_cookies: bool

    @property
    def ready(self):
        return bool(self.client_id and self.client_secret and self.redirect_uri and self.session_secret)

    @property
    def origin(self):
        parsed = urlsplit(self.redirect_uri)
        return f"{parsed.scheme}://{parsed.netloc}"


def get_settings():
    hosted = os.getenv("RENDER", "").lower() == "true"
    redirect = os.getenv("GOOGLE_REDIRECT_URI", "").strip()
    secret = os.getenv("SESSION_SECRET_KEY", "").strip()
    if secret and len(secret) < 32:
        raise ValueError("SESSION_SECRET_KEY must contain at least 32 characters")
    if redirect:
        parsed = urlsplit(redirect)
        if parsed.scheme not in ("http", "https") or not parsed.netloc or parsed.query or parsed.fragment:
            raise ValueError("GOOGLE_REDIRECT_URI must be an absolute callback URL")
        if parsed.path != "/auth/google/callback":
            raise ValueError("GOOGLE_REDIRECT_URI must end with /auth/google/callback")
        if parsed.scheme == "http" and parsed.hostname not in ("localhost", "127.0.0.1"):
            raise ValueError("Non-local Google callbacks require HTTPS")
    if hosted and (not secret or not redirect.startswith("https://")):
        raise ValueError("Render requires SESSION_SECRET_KEY and an HTTPS GOOGLE_REDIRECT_URI")
    return AuthSettings(
        os.getenv("GOOGLE_CLIENT_ID", "").strip(),
        os.getenv("GOOGLE_CLIENT_SECRET", "").strip(),
        redirect, secret, hosted or redirect.startswith("https://"),
    )
