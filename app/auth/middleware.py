from starlette.middleware.sessions import SessionMiddleware


class RequestSessionMiddleware:
    """Secure cookies on HTTPS; allow HTTP cookies only for local development."""

    def __init__(self, app, **kwargs):
        self.secure = SessionMiddleware(app, https_only=True, **kwargs)
        self.local = SessionMiddleware(app, https_only=False, **kwargs)

    async def __call__(self, scope, receive, send):
        middleware = self.secure if scope.get('scheme') in ('https', 'wss') else self.local
        await middleware(scope, receive, send)
