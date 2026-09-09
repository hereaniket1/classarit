from fastapi import APIRouter, Request
from ..views import templates

router = APIRouter()


@router.get('/')
def home(request: Request):
    return templates.TemplateResponse('home.html', {'request':request})


@router.get('/health', include_in_schema=False)
def health():
    return {'status':'ok'}
