"""Application composition; routes and services live in dedicated modules."""
import asyncio
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from .auth.middleware import RequestSessionMiddleware

from .auth.settings import get_settings
from .auth.routes import router as auth_router
from .auth.dependencies import require_user
from .routes.public import router as public_router
from .routes.dashboard import router as dashboard_router
from .routes.executive import router as executive_router
from .workspaces.routes import router as workspace_router
from .routes.teaching import router as teaching_router
from .config import PROJECT_DIR, UPLOAD_DIR
from .database import Base, engine, get_db
from .services.ownership import upgrade_local_ownership, get_teacher
from .services.telemetry import record_api_metric
from . import models


@asynccontextmanager
async def lifespan(app):
    Base.metadata.create_all(bind=engine)
    upgrade_local_ownership(engine)
    yield


settings = get_settings()
app = FastAPI(title='Classarit', lifespan=lifespan)
app.add_middleware(RequestSessionMiddleware, secret_key=settings.session_secret,
                   session_cookie='classarit_session', max_age=43200, same_site='lax')
app.mount('/static', StaticFiles(directory=PROJECT_DIR / 'app' / 'static'), name='static')
app.include_router(public_router)
app.include_router(auth_router)
app.include_router(dashboard_router)
app.include_router(executive_router)
app.include_router(teaching_router)
app.include_router(workspace_router)


@app.exception_handler(HTTPException)
async def auth_errors(request: Request, exc: HTTPException):
    if exc.status_code == 401 and (request.url.path in ('/dashboard','/legacy/dashboard','/executive') or request.url.path.startswith('/workspaces/')):
        return RedirectResponse('/login',status_code=303)
    return JSONResponse({'detail':exc.detail},status_code=exc.status_code,headers=exc.headers)


@app.middleware('http')
async def private_responses(request: Request, call_next):
    started = time.perf_counter()
    response = await call_next(request)
    latency_ms = int((time.perf_counter() - started) * 1000)
    if request.url.path.startswith(('/auth/', '/api/', '/uploads/', '/dashboard', '/login', '/workspaces/', '/invitations/', '/legacy/', '/executive', '/static/')):
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'same-origin'
    if request.url.path.startswith(('/api/', '/auth/')):
        route = request.scope.get('route')
        route_template = getattr(route, 'path', request.url.path) if route else request.url.path
        user_id = None
        state_user = getattr(request.state, 'user', None)
        if state_user:
            user_id = state_user.get('id')
        asyncio.create_task(record_api_metric(request.method, request.url.path, route_template, response.status_code, latency_ms, user_id))
    return response


@app.get('/uploads/{filename}')
def private_upload(filename: str, db: Session=Depends(get_db), teacher=Depends(get_teacher)):
    material = db.query(models.Material).filter_by(teacher_id=teacher.id,file_path=f'/uploads/{filename}').first()
    path = (UPLOAD_DIR / filename).resolve()
    if not material or path.parent != UPLOAD_DIR.resolve() or not path.is_file():
        raise HTTPException(404,'File not found')
    return FileResponse(path)
