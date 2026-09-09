from fastapi.templating import Jinja2Templates
from .config import PROJECT_DIR

templates = Jinja2Templates(directory=str(PROJECT_DIR / 'app' / 'templates'))
