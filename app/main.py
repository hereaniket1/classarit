"""Application composition; routes and services live in dedicated modules."""
import secrets
from contextlib import asynccontextmanager

from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware

from .auth.settings import get_settings
from .auth.routes import router as auth_router
from .auth.dependencies import require_user
from .routes.public import router as public_router
from .routes.dashboard import router as dashboard_router
from .routes.teaching import router as teaching_router
from .config import PROJECT_DIR, UPLOAD_DIR
from .database import Base, engine, get_db
from .services.ownership import upgrade_local_ownership, get_teacher
from . import models


@asynccontextmanager
async def lifespan(app):
    Base.metadata.create_all(bind=engine)
    upgrade_local_ownership(engine)
    yield


settings = get_settings()
app = FastAPI(title='Classarit', lifespan=lifespan)
app.add_middleware(SessionMiddleware, secret_key=settings.session_secret or secrets.token_urlsafe(48),
                   session_cookie='classarit_session', max_age=43200, same_site='lax',
                   https_only=settings.secure_cookies)
app.mount('/static', StaticFiles(directory=PROJECT_DIR / 'app' / 'static'), name='static')
app.include_router(public_router)
app.include_router(auth_router)
app.include_router(dashboard_router)
app.include_router(teaching_router)


@app.exception_handler(HTTPException)
async def auth_errors(request: Request, exc: HTTPException):
    if exc.status_code == 401 and request.url.path == '/dashboard':
        return RedirectResponse('/login',status_code=303)
    return JSONResponse({'detail':exc.detail},status_code=exc.status_code,headers=exc.headers)


@app.middleware('http')
async def private_responses(request: Request, call_next):
    response = await call_next(request)
    if request.url.path.startswith(('/auth/', '/api/', '/uploads/', '/dashboard', '/login')):
        response.headers['Cache-Control'] = 'no-store'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'same-origin'
    return response


@app.get('/uploads/{filename}')
def private_upload(filename: str, db: Session=Depends(get_db), teacher=Depends(get_teacher)):
    material = db.query(models.Material).filter_by(teacher_id=teacher.id,file_path=f'/uploads/{filename}').first()
    path = (UPLOAD_DIR / filename).resolve()
    if not material or path.parent != UPLOAD_DIR.resolve() or not path.is_file():
        raise HTTPException(404,'File not found')
    return FileResponse(path)
