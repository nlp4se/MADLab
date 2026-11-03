"""FastAPI web layer for the MAD platform.

Thin driver over the headless ``mad`` engine: routers, DTO schemas, services,
SQLAlchemy persistence, credential security, and the async job runner. The full
application bootstrap is implemented in task 6.1; ``main.py`` here is a minimal
placeholder.
"""
