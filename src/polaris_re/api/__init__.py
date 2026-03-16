"""
Polaris RE REST API package.

Provides a FastAPI application exposing the Polaris RE pricing engine
over HTTP. Import and run via:

    from polaris_re.api.main import app
    uvicorn polaris_re.api.main:app --reload
"""

from polaris_re.api.main import app

__all__ = ["app"]
