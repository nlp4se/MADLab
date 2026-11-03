"""Shared FastAPI dependencies for the API routers.

Currently exposes :func:`get_session`, a request-scoped SQLAlchemy
:class:`~sqlalchemy.orm.Session` dependency that wraps
:func:`app.db.session.session_scope`. The session commits on a successful
request and rolls back if the handler (or a service it calls) raises, keeping
transaction management out of the individual routers (layering per Req 12.2).

Resource routers depend on this rather than touching the sessionmaker directly,
so tests can override the process-wide engine via settings and every endpoint
transparently uses the configured database.
"""

from __future__ import annotations

from typing import Iterator

from sqlalchemy.orm import Session

from app.db.session import session_scope


def get_session() -> Iterator[Session]:
    """Yield a transactional request-scoped :class:`Session`.

    Commits on normal completion and rolls back on exception via
    :func:`app.db.session.session_scope`.
    """
    with session_scope() as session:
        yield session


__all__ = ["get_session"]
