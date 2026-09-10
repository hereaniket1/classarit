from fastapi import APIRouter
from . import organizations, teaching, sessions

router = APIRouter()
for module in (organizations, teaching, sessions):
    router.include_router(module.router)
