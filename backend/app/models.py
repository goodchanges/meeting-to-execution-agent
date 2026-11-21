from uuid import uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    UniqueConstraint,
)

metadata = MetaData()

users = Table(
    "users",
    metadata,
    Column("id", String, primary_key=True, default=lambda: str(uuid4())),
    Column("email", String, nullable=False, unique=True),
    Column("password_hash", String, nullable=False),
    Column("display_name", String, nullable=False),
    Column("created_at", DateTime, nullable=False),
)

sessions = Table(
    "sessions",
    metadata,
    Column("id", String, primary_key=True, default=lambda: str(uuid4())),
    Column(
        "user_id",
        String,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    ),
    Column("token_hash", String, nullable=False, unique=True),
    Column("csrf_hash", String, nullable=False),
    Column("created_at", DateTime, nullable=False),
    Column("expires_at", DateTime, nullable=False),
    Column("last_seen", DateTime, nullable=False),
    Column("revoked", Boolean, nullable=False),
)

password_reset_tokens = Table(
    "password_reset_tokens",
    metadata,
    Column("id", String, primary_key=True, default=lambda: str(uuid4())),
    Column(
        "user_id",
        String,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    ),
    Column("token_hash", String, nullable=False, unique=True),
    Column("expires_at", DateTime, nullable=False),
    Column("used_at", DateTime),
)

app_settings = Table(
    "app_settings",
    metadata,
    Column("id", String, primary_key=True, default=lambda: str(uuid4())),
    Column(
        "user_id",
        String,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    ),
    Column("github_repo", String),
    Column("timezone", String, nullable=False),
    Column("ai_monthly_call_cap", Integer),
    UniqueConstraint("user_id"),
)

meetings = Table(
    "meetings",
    metadata,
    Column("id", String, primary_key=True, default=lambda: str(uuid4())),
    Column(
        "user_id",
        String,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    ),
    Column("title", String, nullable=False),
    Column("meeting_date", Date, nullable=False),
    Column("source_filename", String),
    Column("source_format", String, nullable=False),
    Column("transcript_sha256", String, nullable=False),
    Column("source", Text, nullable=False),
    Column("status", String, nullable=False),
    Column("processing_mode", String, nullable=False),
    Column("failure_reason", String),
    Column("processing_started_at", DateTime),
    Column("created_at", DateTime, nullable=False),
)

transcript_segments = Table(
    "transcript_segments",
    metadata,
    Column("id", String, primary_key=True, default=lambda: str(uuid4())),
    Column(
        "user_id",
        String,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    ),
    Column(
        "meeting_id",
        String,
        ForeignKey("meetings.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("idx", Integer, nullable=False),
    Column("speaker_label", String),
    Column("start_ts", String),
    Column("end_ts", String),
    Column("text", Text, nullable=False),
    Column("speaker_resolved", Boolean, nullable=False),
)

meeting_participants = Table(
    "meeting_participants",
    metadata,
    Column("id", String, primary_key=True, default=lambda: str(uuid4())),
    Column(
        "user_id",
        String,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    ),
    Column(
        "meeting_id",
        String,
        ForeignKey("meetings.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("name", String, nullable=False),
    Column("resolved", Boolean, nullable=False),
)

decisions = Table(
    "decisions",
    metadata,
    Column("id", String, primary_key=True, default=lambda: str(uuid4())),
    Column(
        "user_id",
        String,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    ),
    Column(
        "meeting_id",
        String,
        ForeignKey("meetings.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("topic", String, nullable=False),
    Column("subject_key", String, nullable=False),
    Column("description", Text, nullable=False),
    Column("responsible_speaker", String),
    Column("evidence_excerpt", Text, nullable=False),
    Column("evidence_ts", String),
    Column("evidence_verified", Boolean, nullable=False),
    Column("confidence", Float, nullable=False),
    Column("status", String, nullable=False),
    Column(
        "superseded_by_decision_id",
        String,
        ForeignKey("decisions.id", ondelete="SET NULL"),
    ),
    Column("processing_mode", String, nullable=False),
    Column("created_at", DateTime, nullable=False),
    Column("updated_at", DateTime, nullable=False),
)

decision_relations = Table(
    "decision_relations",
    metadata,
    Column("id", String, primary_key=True, default=lambda: str(uuid4())),
    Column(
        "user_id",
        String,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    ),
    Column(
        "new_decision_id",
        String,
        ForeignKey("decisions.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column(
        "prior_decision_id",
        String,
        ForeignKey("decisions.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("relation", String, nullable=False),
    Column("reason", Text, nullable=False),
    Column("new_evidence", Text, nullable=False),
    Column("prior_evidence", Text, nullable=False),
    Column("ai_confidence", Float, nullable=False),
    Column("resolution", String, nullable=False),
    Column("resolved_at", DateTime),
    Column("resolution_note", Text),
    Column("processing_mode", String, nullable=False),
)

action_items = Table(
    "action_items",
    metadata,
    Column("id", String, primary_key=True, default=lambda: str(uuid4())),
    Column(
        "user_id",
        String,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    ),
    Column(
        "meeting_id",
        String,
        ForeignKey("meetings.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("title", String, nullable=False),
    Column("description", Text, nullable=False),
    Column("owner", String),
    Column("owner_resolved", Boolean, nullable=False),
    Column("deadline", Date),
    Column("deadline_raw", String),
    Column("evidence_excerpt", Text, nullable=False),
    Column("evidence_ts", String),
    Column("evidence_verified", Boolean, nullable=False),
    Column("approval_status", String, nullable=False),
    Column("github_state", String, nullable=False),
    Column("github_issue_number", Integer),
    Column("github_issue_url", String),
    Column("github_error", String),
    Column("github_repo", String),
    Column("github_claimed_at", DateTime),
    Column("idempotency_key", String, nullable=False, unique=True),
    Column("completed_at", DateTime),
    Column("edited_by_user", Boolean, nullable=False),
    Column("processing_mode", String, nullable=False),
)

notifications = Table(
    "notifications",
    metadata,
    Column("id", String, primary_key=True, default=lambda: str(uuid4())),
    Column(
        "user_id",
        String,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    ),
    Column("kind", String, nullable=False),
    Column("action_item_id", String, ForeignKey("action_items.id", ondelete="CASCADE")),
    Column("message", Text, nullable=False),
    Column("read_at", DateTime),
    Column("dedupe_key", String, nullable=False),
    Column("processing_mode", String, nullable=False),
    UniqueConstraint("user_id", "dedupe_key"),
)

digests = Table(
    "digests",
    metadata,
    Column("id", String, primary_key=True, default=lambda: str(uuid4())),
    Column(
        "user_id",
        String,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    ),
    Column("person_name", String, nullable=False),
    Column("week_start", Date, nullable=False),
    Column("payload", JSON, nullable=False),
    Column("generated_at", DateTime, nullable=False),
    Column("processing_mode", String, nullable=False),
    UniqueConstraint("user_id", "person_name", "week_start"),
)

ai_usage = Table(
    "ai_usage",
    metadata,
    Column("id", String, primary_key=True, default=lambda: str(uuid4())),
    Column(
        "user_id",
        String,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    ),
    Column("meeting_id", String, ForeignKey("meetings.id", ondelete="CASCADE")),
    Column("operation", String, nullable=False),
    Column("provider", String, nullable=False),
    Column("model", String, nullable=False),
    Column("input_tokens", Integer),
    Column("output_tokens", Integer),
    Column("latency_ms", Integer),
    Column("success", Boolean, nullable=False),
    Column("error_class", String),
    Column("created_at", DateTime, nullable=False),
)

audit_logs = Table(
    "audit_logs",
    metadata,
    Column("id", String, primary_key=True, default=lambda: str(uuid4())),
    Column("user_ref", String, nullable=False),
    Column("action", String, nullable=False),
    Column("object_type", String, nullable=False),
    Column("object_id", String),
    Column("outcome", String, nullable=False),
    Column("request_id", String, nullable=False),
    Column("ip_hash", String, nullable=False),
    Column("created_at", DateTime, nullable=False),
    Column("detail", JSON, nullable=False),
)
