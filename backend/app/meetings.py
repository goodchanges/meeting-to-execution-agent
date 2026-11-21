import hashlib
import re
from datetime import date, timedelta
from pathlib import PurePath
from time import monotonic, sleep
from typing import Annotated, TypeVar

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel, ValidationError
from sqlalchemy import func, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from . import models as m
from .ai import (
    COMPARE,
    EXTRACT,
    Comparison,
    Extraction,
    ProviderError,
    Usage,
    clean,
    grounded,
    normalize,
    wrap,
)
from .auth import User
from .db import get_owned_or_404, insert, owned, rows
from .security import audit, current_user, limit, now
from .transcripts import TranscriptError, date_from_filename, deadline_for, parse

protected = APIRouter(prefix="/api", dependencies=[Depends(current_user)])
T = TypeVar("T", bound=BaseModel)
FORMATS = {
    "txt": {"text/plain", "application/octet-stream"},
    "vtt": {"text/vtt", "text/plain", "application/octet-stream"},
    "srt": {
        "application/x-subrip",
        "application/srt",
        "text/srt",
        "text/plain",
        "application/octet-stream",
    },
}


@protected.post("/meetings", status_code=201)
async def upload_meeting(
    request: Request,
    user: User,
    title: Annotated[str, Form(min_length=1, max_length=180)],
    meeting_date: Annotated[date | None, Form()] = None,
    transcript: Annotated[str | None, Form()] = None,
    file: Annotated[UploadFile | None, File()] = None,
    process_anyway: Annotated[bool, Form()] = False,
):
    settings = request.app.state.settings
    uid = user["id"]
    limit(request, "upload", settings.rate_upload, 3600, uid)
    if (transcript is None) == (file is None):
        raise HTTPException(422, "Provide a file or pasted text.")
    fmt, filename = "txt", None
    if file is not None:
        upload = file
        filename = PurePath(
            str(getattr(upload, "filename", "")).replace("\\", "/")
        ).name
        fmt = filename.rpartition(".")[2].lower()
        mime = (upload.content_type or "").split(";", 1)[0].strip().casefold()
        if fmt not in FORMATS or mime not in FORMATS[fmt]:
            raise HTTPException(415, "Upload a supported TXT, VTT, or SRT transcript.")
        raw = await file.read(settings.max_upload_bytes + 1)
    else:
        raw = (transcript or "").encode()
    if len(raw) > settings.max_upload_bytes:
        raise HTTPException(413, "Transcript exceeds the configured size limit.")
    chosen_date = meeting_date or date_from_filename(filename or "")
    if not chosen_date or not clean(title):
        raise HTTPException(422, "Enter a title and meeting date.")
    try:
        source = raw.decode("utf-8")
        segments = parse(source, fmt, settings.max_segments)
    except UnicodeDecodeError:
        raise HTTPException(
            422, "Save the transcript as UTF-8 and try again."
        ) from None
    except TranscriptError as exc:
        raise HTTPException(422, str(exc)) from None
    checksum = hashlib.sha256(raw).hexdigest()
    with request.app.state.engine.begin() as db:
        db.exec_driver_sql("BEGIN IMMEDIATE")
        duplicate = db.execute(
            owned(m.meetings, uid)
            .where(
                m.meetings.c.transcript_sha256 == checksum,
            )
            .limit(1)
        ).first()
        if duplicate and not process_anyway:
            raise HTTPException(
                409, "This transcript already exists. Confirm upload anyway."
            )
        meeting_id = insert(
            db,
            m.meetings,
            user_id=uid,
            title=clean(title),
            meeting_date=chosen_date,
            source_filename=(filename or "")[:255] or None,
            source_format=fmt,
            transcript_sha256=checksum,
            source=source,
            status="UPLOADED",
            processing_mode=settings.ai_mode,
            created_at=now(request),
        )
        for index, segment in enumerate(segments):
            insert(
                db,
                m.transcript_segments,
                user_id=uid,
                meeting_id=meeting_id,
                **segment.record(index),
            )
        for name in dict.fromkeys(
            segment.speaker_label for segment in segments if segment.speaker_label
        ):
            insert(
                db,
                m.meeting_participants,
                user_id=uid,
                meeting_id=meeting_id,
                name=name,
                resolved=True,
            )
    return {"id": meeting_id, "status": "UPLOADED"}


@protected.get("/meetings")
def meetings(request: Request, user: User):
    with request.app.state.engine.connect() as db:
        results = rows(
            db, owned(m.meetings, user["id"]).order_by(m.meetings.c.meeting_date.desc())
        )
    return [{k: v for k, v in row.items() if k != "source"} for row in results]


@protected.get("/meetings/{meeting_id}")
def meeting_detail(meeting_id: str, request: Request, user: User):
    uid = user["id"]
    with request.app.state.engine.connect() as db:
        meeting = get_owned_or_404(db, m.meetings, uid, meeting_id)
        meeting.pop("source")
        for key, table in [
            ("segments", m.transcript_segments),
            ("participants", m.meeting_participants),
            ("decisions", m.decisions),
            ("action_items", m.action_items),
        ]:
            stmt = owned(table, uid).where(table.c.meeting_id == meeting_id)
            if table is m.transcript_segments:
                stmt = stmt.order_by(m.transcript_segments.c.idx)
            meeting[key] = rows(db, stmt)
        meeting["key_topics"] = list(
            dict.fromkeys(item["topic"] for item in meeting["decisions"])
        )
        return meeting


def call_ai(
    request: Request,
    uid: str,
    meeting_id: str,
    operation: str,
    payload: dict,
    schema: type[T],
) -> T:
    settings = request.app.state.settings
    provider = request.app.state.provider
    engine = request.app.state.engine
    repair = 0
    transient = 0
    packed = wrap(payload)
    if (len(packed.encode()) + 3) // 4 > settings.max_input_tokens:
        raise ProviderError("Transcript or comparison exceeds the AI input limit.")
    while True:
        started = monotonic()
        current = now(request)
        start = current.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        with engine.begin() as db:
            db.exec_driver_sql("BEGIN IMMEDIATE")
            user_cap = db.scalar(
                select(m.app_settings.c.ai_monthly_call_cap).where(
                    m.app_settings.c.user_id == uid,
                )
            )
            query = (
                select(func.count())
                .select_from(m.ai_usage)
                .where(
                    m.ai_usage.c.created_at >= start,
                    m.ai_usage.c.provider != "demo",
                )
            )
            if provider.name != "demo":
                month = start.date()
                global_count = (
                    db.scalar(
                        select(m.ai_monthly_totals.c.calls).where(
                            m.ai_monthly_totals.c.month == month,
                        )
                    )
                    or 0
                )
                if global_count >= settings.ai_global_monthly_call_cap or db.scalar(
                    query.where(m.ai_usage.c.user_id == uid)
                ) >= (
                    settings.ai_user_monthly_call_cap if user_cap is None else user_cap
                ):
                    raise ProviderError("The monthly AI call limit has been reached.")
                db.execute(
                    sqlite_insert(m.ai_monthly_totals)
                    .values(month=month, calls=1)
                    .on_conflict_do_update(
                        index_elements=["month"],
                        set_={"calls": m.ai_monthly_totals.c.calls + 1},
                    )
                )
            usage_id = insert(
                db,
                m.ai_usage,
                user_id=uid,
                meeting_id=meeting_id,
                operation=operation,
                provider=provider.name,
                model=provider.model,
                success=False,
                error_class="Interrupted",
                created_at=current,
            )
        usage = Usage()
        error = None
        try:
            prompt = EXTRACT if operation == "extract" else COMPARE
            if repair:
                prompt += " The previous response failed validation. Correct the output schema."
            result, usage = provider.generate_structured(
                prompt,
                packed,
                schema,
                settings.max_output_tokens,
                settings.ai_timeout,
            )
            result = schema.model_validate(
                result.model_dump() if isinstance(result, BaseModel) else result
            )
        except ProviderError as exc:
            error = exc
        except (ValidationError, ValueError, TypeError):
            error = ProviderError(
                "AI returned invalid structured output.", invalid=True
            )
        with engine.begin() as db:
            db.execute(
                m.ai_usage.update()
                .where(
                    m.ai_usage.c.id == usage_id,
                    m.ai_usage.c.user_id == uid,
                )
                .values(
                    input_tokens=usage.input_tokens,
                    output_tokens=usage.output_tokens,
                    latency_ms=int((monotonic() - started) * 1000),
                    success=error is None,
                    error_class=type(error).__name__ if error else None,
                )
            )
        if error is None:
            return result
        if error.invalid and not repair:
            repair += 1
        elif error.transient and transient < 2:
            sleep(0.25 * 2**transient)
            transient += 1
        else:
            raise error


def candidates_for(memory: list[dict], item: dict, maximum: int):
    def score(prior):
        a, b = [
            set(re.findall(r"\w+", normalize(row["description"])))
            for row in (item, prior)
        ]
        overlap = len(a & b) / max(1, len(a | b))
        same_key = item["subject_key"] == prior["subject_key"]
        same_topic = normalize(item["topic"]) == normalize(prior["topic"])
        return 10 * same_key + 3 * same_topic + (overlap if overlap >= 0.25 else 0)

    ranked = sorted(
        ((score(prior), prior) for prior in memory),
        key=lambda pair: pair[0],
        reverse=True,
    )
    return [prior for rank, prior in ranked[:maximum] if rank]


def evidence(quote, segments):
    return next((row for row in segments if grounded(quote, row["text"])), None)


def process_records(request, meeting, segments, memory):
    uid, mid = meeting["user_id"], meeting["id"]
    date_value = meeting["meeting_date"]
    settings = request.app.state.settings
    known = {
        normalize(row["speaker_label"]): row["speaker_label"]
        for row in segments
        if row["speaker_label"]
    }
    breakdown = call_ai(
        request,
        uid,
        mid,
        "extract",
        {
            "meeting_title": meeting["title"],
            "meeting_date": date_value.isoformat(),
            "segments": [
                {"speaker": row["speaker_label"], "text": row["text"]}
                for row in segments
            ],
        },
        Extraction,
    )
    decisions, tasks = [], []
    for obj in breakdown.decisions:
        item = obj.model_dump()
        excerpt = clean(obj.evidence_excerpt)
        proof = evidence(excerpt, segments)
        speaker = known.get(normalize(obj.responsible_speaker or ""))
        item.update(
            {
                "description": clean(obj.description),
                "topic": clean(obj.topic),
                "evidence_excerpt": excerpt,
                "responsible_speaker": speaker,
                "evidence_verified": bool(proof),
                "evidence_ts": proof["start_ts"] if proof else None,
                "status": "PROPOSED"
                if (
                    proof
                    and (not obj.responsible_speaker or speaker)
                    and obj.confidence >= settings.confidence_threshold
                )
                else "NEEDS_REVIEW",
            }
        )
        prior_rows = candidates_for(memory, item, settings.memory_candidates)
        relations = []
        if prior_rows:
            fields = ("subject_key", "topic", "description", "evidence_excerpt")
            response = call_ai(
                request,
                uid,
                mid,
                "compare",
                {
                    "new": {key: item[key] for key in fields},
                    "prior": [
                        {key: row[key] for key in (*fields, "id")} for row in prior_rows
                    ],
                },
                Comparison,
            )
            by_id = {row.prior_id: row for row in response.relations}
            if set(by_id) != {row["id"] for row in prior_rows} or len(by_id) != len(
                response.relations
            ):
                raise ProviderError(
                    "AI comparison did not cover the expected decisions."
                )
            for prior in prior_rows:
                relation = by_id[prior["id"]]
                valid = grounded(relation.new_evidence, excerpt) and grounded(
                    relation.prior_evidence,
                    prior["evidence_excerpt"],
                )
                kind = relation.relation
                if not valid or relation.confidence < settings.confidence_threshold:
                    kind = "UNCERTAIN"
                if kind == "UNRELATED":
                    continue
                if kind != "CONSISTENT":
                    item["status"] = "NEEDS_REVIEW"
                relations.append(
                    {
                        "prior_decision_id": prior["id"],
                        "relation": kind,
                        "reason": clean(relation.reason),
                        "new_evidence": clean(relation.new_evidence)
                        if valid
                        else excerpt,
                        "prior_evidence": clean(relation.prior_evidence)
                        if valid
                        else prior["evidence_excerpt"],
                        "ai_confidence": relation.confidence,
                        "resolution": "PENDING",
                    }
                )
        decisions.append((item, relations))
    for task in breakdown.action_items:
        title, description, excerpt = [
            clean(value)
            for value in (task.title, task.description, task.evidence_excerpt)
        ]
        proof = evidence(excerpt, segments)
        owner = known.get(normalize(task.owner or ""))
        if not proof or (
            owner
            and normalize(owner) != normalize(proof["speaker_label"] or "")
            and not re.search(rf"(?<!\w){re.escape(owner)}(?!\w)", excerpt, re.I)
        ):
            owner = None
        raw = clean(task.deadline_raw) if task.deadline_raw else None
        deadline = (
            deadline_for(raw, date_value)
            if raw and proof and grounded(raw, excerpt)
            else None
        )
        tasks.append(
            dict(
                title=title,
                description=description,
                evidence_excerpt=excerpt,
                evidence_verified=bool(proof),
                evidence_ts=proof["start_ts"] if proof else None,
                owner=owner,
                owner_resolved=bool(owner),
                deadline_raw=raw,
                deadline=deadline,
                approval_status="PENDING"
                if proof and owner and deadline
                else "NEEDS_REVIEW",
            )
        )
    return decisions, tasks


def clear_unreviewed(db, request, uid, meeting_id):
    decisions = select(m.decisions.c.id).where(
        m.decisions.c.user_id == uid,
        m.decisions.c.meeting_id == meeting_id,
    )
    tasks = select(m.action_items.c.id).where(
        m.action_items.c.user_id == uid,
        m.action_items.c.meeting_id == meeting_id,
    )
    comparisons = select(m.decision_relations.c.id).where(
        m.decision_relations.c.user_id == uid,
        m.decision_relations.c.new_decision_id.in_(decisions),
    )
    touched = db.scalar(
        select(m.audit_logs.c.id)
        .where(
            m.audit_logs.c.object_id.in_(decisions.union_all(tasks, comparisons)),
        )
        .limit(1)
    )
    if touched:
        raise HTTPException(
            409,
            "Reviewed or edited records are preserved. Upload a separate copy to run a new extraction.",
        )
    for table in (m.decisions, m.action_items):
        db.execute(
            table.delete().where(
                table.c.user_id == uid, table.c.meeting_id == meeting_id
            )
        )
    audit(db, request, uid, "replace_unreviewed", "meeting", meeting_id)


@protected.post("/meetings/{meeting_id}/process")
def process_meeting(
    meeting_id: str, request: Request, user: User, reprocess: bool = False
):
    from uuid import uuid4

    uid = user["id"]
    settings = request.app.state.settings
    limit(request, "process", settings.rate_ai, 3600, uid)
    engine = request.app.state.engine
    claim = now(request)
    mode = settings.ai_mode
    with engine.begin() as db:
        db.exec_driver_sql("BEGIN IMMEDIATE")
        meeting = get_owned_or_404(db, m.meetings, uid, meeting_id)
        if meeting["status"] == "EXTRACTED":
            if not reprocess:
                raise HTTPException(409, "This meeting has already been extracted.")
            clear_unreviewed(db, request, uid, meeting_id)
        if meeting["status"] == "PROCESSING" and meeting[
            "processing_started_at"
        ] > claim - timedelta(minutes=15):
            raise HTTPException(409, "This meeting is already processing.")
        db.execute(
            m.meetings.update()
            .where(m.meetings.c.id == meeting_id, m.meetings.c.user_id == uid)
            .values(
                status="PROCESSING",
                failure_reason=None,
                processing_mode=mode,
                processing_started_at=claim,
            )
        )
        segments = rows(
            db,
            owned(m.transcript_segments, uid)
            .where(
                m.transcript_segments.c.meeting_id == meeting_id,
            )
            .order_by(m.transcript_segments.c.idx),
        )
        memory = rows(
            db,
            owned(m.decisions, uid)
            .where(m.decisions.c.status == "APPROVED")
            .order_by(m.decisions.c.updated_at.desc())
            .limit(1000),
        )
    failure = None
    try:
        decisions, tasks = process_records(request, meeting, segments, memory)
    except ProviderError as exc:
        failure = str(exc)
    except Exception as exc:  # noqa: BLE001 - persist recoverable failure
        request.app.state.logger.error(
            "meeting processing failed: %s", type(exc).__name__
        )
        failure = "Processing could not finish. Try again."
    with engine.begin() as db:
        db.exec_driver_sql("BEGIN IMMEDIATE")
        latest = get_owned_or_404(db, m.meetings, uid, meeting_id)
        if latest["processing_started_at"] != claim:
            raise HTTPException(409, "A newer processing attempt has started.")
        shared = dict(user_id=uid, meeting_id=meeting_id, processing_mode=mode)
        if not failure:
            for item, relations in decisions:
                decision_id = insert(
                    db,
                    m.decisions,
                    **shared,
                    **item,
                    created_at=claim,
                    updated_at=claim,
                )
                for relation in relations:
                    insert(
                        db,
                        m.decision_relations,
                        user_id=uid,
                        new_decision_id=decision_id,
                        processing_mode=mode,
                        **relation,
                    )
            for task in tasks:
                insert(
                    db,
                    m.action_items,
                    **shared,
                    **task,
                    github_state="NOT_CREATED",
                    idempotency_key=str(uuid4()),
                    edited_by_user=False,
                )
        status = "FAILED" if failure else "EXTRACTED"
        db.execute(
            m.meetings.update()
            .where(m.meetings.c.id == meeting_id, m.meetings.c.user_id == uid)
            .values(status=status, failure_reason=failure)
        )
        audit(
            db,
            request,
            uid,
            "process",
            "meeting",
            meeting_id,
            "failed" if failure else "success",
        )
    return {"status": status, "failure_reason": failure}
