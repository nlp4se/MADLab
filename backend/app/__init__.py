"""FastAPI web layer for the MADLab.

Thin driver over the headless ``mad`` engine: routers, DTO schemas, services,
SQLAlchemy persistence, credential security, and the async job runner. The
application bootstrap lives in :mod:`app.main` (``create_app``): settings
(:mod:`app.config`), CORS, DB init on startup, structured error handlers
(:mod:`app.errors`), and router registration.
"""
