"""Start Classarit locally or on Render: python run.py."""

import argparse
import os
from pathlib import Path

import uvicorn


def main():
    parser = argparse.ArgumentParser(description="Run Classarit")
    parser.add_argument("--reload", action="store_true", help="Reload on local code changes")
    args = parser.parse_args()
    on_render = os.environ.get("RENDER", "").lower() == "true"
    if on_render and args.reload:
        parser.error("--reload is for local development only")
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0" if on_render else "127.0.0.1",
        port=int(os.environ.get("PORT", "8000")),
        reload=args.reload,
        reload_dirs=[str(Path(__file__).resolve().parent / "app")] if args.reload else None,
        workers=1,
        proxy_headers=True,
        forwarded_allow_ips="*" if on_render else "127.0.0.1",
    )


if __name__ == "__main__":
    main()
