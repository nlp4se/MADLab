"""SQLAlchemy ORM models for the MAD platform persistence layer.

The schema follows the design's *Persistence* section exactly (Req 14.3):

* :class:`Provider` — a model backend (OpenAI/Anthropic/.../Ollama/
  openai_compatible) with an encrypted API key and a JSON list of model keys.
* :class:`Configuration` — a saved, taxonomy-complete MAD configuration whose
  ``artifact`` is the full ``MADConfig`` JSON document (Req 4, 5).
* :class:`Dataset` — an uploaded CSV with its columns and row count (Req 10.1).
* :class:`Execution` — one run of a configuration bound to an input. It carries
  an **immutable** ``config_snapshot`` capturing the exact configuration used,
  independent of later edits to the source configuration (Req 11.3).
* :class:`ExecutionInstance` — one debate within an execution (one ad-hoc
  instance or one dataset row), with its resolved input, transcript, final
  decision, optional ground truth, per-instance metrics and optional error.

A small :class:`SchemaMeta` key/value table records the persistence schema
version so the lightweight ``create_all`` init can stamp and detect the schema
(the design accepts ``create_all`` + a schema version marker in lieu of a full
migration framework).

Status / mode values are kept as plain strings (constrained by the application
and the enums below) to keep the SQLite schema simple and the JSON payloads
portable.
"""

from __future__ import annotations

from enum import Enum

from sqlalchemy import (
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.db.base import Base, JSONDict, JSONList, TimestampMixin


# ---------------------------------------------------------------------------
# Value enums (stored as their string ``value`` in the DB)
# ---------------------------------------------------------------------------


class InputMode(str, Enum):
    """How an execution is bound to input."""

    SINGLE = "single"
    BATCH = "batch"


class ExecutionStatus(str, Enum):
    """Lifecycle status of an execution (Req 10.5, 11.1)."""

    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    PARTIAL = "partial"


# ---------------------------------------------------------------------------
# Providers (Req 8)
# ---------------------------------------------------------------------------


class Provider(Base, TimestampMixin):
    """A configured model backend with encrypted credentials.

    Only the *encrypted* API key is ever stored; plaintext never reaches the
    database and is never returned to the frontend (Req 8.4). ``models`` holds
    the JSON list of available model keys for this provider.
    """

    __tablename__ = "providers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    # Provider kind: openai / anthropic / gemini / mistral / deepseek /
    # ollama / vllm / openai_compatible.
    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    base_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    # Ciphertext produced by the security layer (Fernet); may be NULL when no
    # key has been configured yet (e.g. a local Ollama endpoint).
    encrypted_api_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    models: Mapped[JSONList] = mapped_column(JSON, nullable=False, default=list)

    @property
    def has_key(self) -> bool:
        """Whether an API key is configured (the only key info exposed upward)."""
        return bool(self.encrypted_api_key)

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<Provider id={self.id!r} name={self.name!r} kind={self.kind!r}>"


# ---------------------------------------------------------------------------
# Configurations (Req 4, 5)
# ---------------------------------------------------------------------------


class Configuration(Base, TimestampMixin):
    """A saved MAD configuration; ``artifact`` is the full ``MADConfig`` JSON."""

    __tablename__ = "configurations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    artifact: Mapped[JSONDict] = mapped_column(JSON, nullable=False)
    schema_version: Mapped[str] = mapped_column(String(32), nullable=False)

    # Executions that were launched from this configuration. On delete the FK
    # on the execution side is nulled (SET NULL) so history survives a source
    # configuration deletion (Req 5.4, 11.3).
    executions: Mapped[list["Execution"]] = relationship(
        back_populates="config",
        passive_deletes=True,
    )

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<Configuration id={self.id!r} name={self.name!r}>"


# ---------------------------------------------------------------------------
# Datasets (Req 10.1)
# ---------------------------------------------------------------------------


class Dataset(Base, TimestampMixin):
    """An uploaded CSV dataset: source filename, stored path, columns, row count."""

    __tablename__ = "datasets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(512), nullable=False)
    stored_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    columns: Mapped[JSONList] = mapped_column(JSON, nullable=False, default=list)
    row_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<Dataset id={self.id!r} name={self.name!r} rows={self.row_count!r}>"


# ---------------------------------------------------------------------------
# Executions (Req 10, 11)
# ---------------------------------------------------------------------------


class Execution(Base, TimestampMixin):
    """A single run of a configuration over a bound input.

    ``config_snapshot`` is the immutable, verbatim copy of the configuration
    artifact used for this run. It is set once at creation and must never be
    mutated afterwards, so an execution's provenance is preserved even if the
    source :class:`Configuration` is later edited or deleted (Req 11.3). The
    ``config_id`` FK is nullable and uses ``ON DELETE SET NULL`` so deleting the
    source configuration does not cascade into history.
    """

    __tablename__ = "executions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    config_id: Mapped[int | None] = mapped_column(
        ForeignKey("configurations.id", ondelete="SET NULL"),
        nullable=True,
    )
    # Immutable snapshot of the config artifact used by this run (Req 11.3).
    config_snapshot: Mapped[JSONDict] = mapped_column(JSON, nullable=False)
    input_mode: Mapped[str] = mapped_column(String(16), nullable=False)
    # Ad-hoc field values (single) or dataset id + column mapping (batch).
    input_ref: Mapped[JSONDict] = mapped_column(JSON, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default=ExecutionStatus.QUEUED.value,
    )
    # Fraction complete in [0.0, 1.0] for progress reporting (Req 10.5).
    progress: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    metrics: Mapped[JSONDict | None] = mapped_column(JSON, nullable=True)

    config: Mapped["Configuration | None"] = relationship(
        back_populates="executions"
    )
    instances: Mapped[list["ExecutionInstance"]] = relationship(
        back_populates="execution",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="ExecutionInstance.instance_index",
    )

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return (
            f"<Execution id={self.id!r} status={self.status!r} "
            f"mode={self.input_mode!r}>"
        )


class ExecutionInstance(Base):
    """One debate within an execution (one ad-hoc instance or one CSV row)."""

    __tablename__ = "execution_instances"
    __table_args__ = (
        UniqueConstraint(
            "execution_id",
            "instance_index",
            name="uq_execution_instance_index",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    execution_id: Mapped[int] = mapped_column(
        ForeignKey("executions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # 0-based position of this instance within the execution's input.
    instance_index: Mapped[int] = mapped_column(Integer, nullable=False)
    resolved_input: Mapped[JSONDict] = mapped_column(JSON, nullable=False, default=dict)
    transcript: Mapped[JSONDict | None] = mapped_column(JSON, nullable=True)
    final_decision: Mapped[JSONDict | None] = mapped_column(JSON, nullable=True)
    ground_truth: Mapped[str | None] = mapped_column(Text, nullable=True)
    metrics: Mapped[JSONDict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    execution: Mapped["Execution"] = relationship(back_populates="instances")

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return (
            f"<ExecutionInstance id={self.id!r} "
            f"execution_id={self.execution_id!r} index={self.instance_index!r}>"
        )


# ---------------------------------------------------------------------------
# Schema version marker (lightweight "migration" stamp)
# ---------------------------------------------------------------------------


class SchemaMeta(Base):
    """Single-row-per-key metadata table recording the persistence schema version.

    The design accepts ``create_all`` plus a schema version marker in place of a
    full migration framework for the in-process SQLite database. This table is
    where :func:`app.db.session.init_db` stamps the current schema version.
    """

    __tablename__ = "schema_meta"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(String(256), nullable=False)

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<SchemaMeta key={self.key!r} value={self.value!r}>"


__all__ = [
    "InputMode",
    "ExecutionStatus",
    "Provider",
    "Configuration",
    "Dataset",
    "Execution",
    "ExecutionInstance",
    "SchemaMeta",
]
