from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query, UploadFile, status
from pydantic import BaseModel
from sqlalchemy import select

from scholariq.analytics.topics import RULE_VERSION
from scholariq.api.deps import (
    PolicyDep,
    SessionDep,
    SettingsDep,
    StoreDep,
    StudentDep,
    upload_limiter,
)
from scholariq.db.models import Assessment, Document, ExamBreakdown, Subject
from scholariq.domain.enums import AttemptStatus, BreakdownStatus, MasteryClass
from scholariq.domain.exams import BreakdownUpdate, NewBreakdown
from scholariq.exams import service
from scholariq.exams.analysis import (
    EXCLUSION_TEXT,
    Breakdown,
    Exclusion,
    Tally,
    percent,
    round_marks,
)
from scholariq.exams.service import Band
from scholariq.exams.suggest import TopicSuggester
from scholariq.ingestion.service import purge_expired_files
from scholariq.ingestion.validation import UploadRejected

router = APIRouter(prefix="/exam-breakdowns", tags=["exam breakdowns"])


class ModuleOut(BaseModel):
    id: str
    number: int
    name: str


class SubjectTopicOut(BaseModel):
    id: str
    slug: str
    name: str
    module_id: str | None


class CandidateOut(BaseModel):
    topic_id: str
    topic_name: str
    module_id: str | None
    score: float
    matched: list[str]


class SuggestionOut(BaseModel):
    status: Literal["clear", "ambiguous", "none"]
    candidates: list[CandidateOut]
    paper_module_id: str | None


class MappingOut(BaseModel):
    topic_id: str | None
    module_id: str | None
    share: Decimal


class QuestionOut(BaseModel):
    id: str
    position: int
    label: str
    section: str | None
    context: str | None
    text: str
    page: int | None
    max_marks: Decimal | None
    marks_obtained: Decimal | None
    attempt_status: AttemptStatus
    is_optional: bool
    choice_group: str | None
    needs_review: bool
    parse_confidence: Decimal | None
    paper_module: str | None
    mappings: list[MappingOut]
    suggestion: SuggestionOut
    counted: bool
    exclusion: str | None


class BreakdownSummary(BaseModel):
    id: str
    title: str
    subject_id: str
    subject_name: str
    assessment_id: str | None
    held_on: date | None
    status: BreakdownStatus
    question_count: int
    earned: Decimal | None
    possible: Decimal | None
    percentage: float | None
    complete: bool
    updated_at: datetime


class PaperOut(BaseModel):
    filename: str
    status: str
    error: str | None
    source: str | None
    notes: list[str]
    warnings: list[str]


class RecordedResult(BaseModel):
    assessment_label: str
    marks_obtained: Decimal | None
    max_marks: Decimal | None


class BreakdownDetail(BreakdownSummary):
    declared_total: Decimal | None
    choice_rules: dict[str, int]
    questions: list[QuestionOut]
    modules: list[ModuleOut]
    topics: list[SubjectTopicOut]
    paper: PaperOut | None
    recorded: RecordedResult | None
    warnings: list[str]


class PaperUploadOut(BaseModel):
    questions_found: int
    warnings: list[str]
    error: str | None
    source: str | None
    breakdown: BreakdownDetail


class ExcludedOut(BaseModel):
    reason: Exclusion
    text: str
    labels: list[str]


class OverallOut(BaseModel):
    earned: Decimal
    possible: Decimal
    percentage: float | None
    band: Band | None
    counted: int
    total_questions: int
    complete: bool
    excluded: list[ExcludedOut]
    unmapped: list[str]


class LostOut(BaseModel):
    label: str
    lost: Decimal


class ModuleRow(BaseModel):
    id: str | None
    number: int | None
    name: str
    earned: Decimal
    possible: Decimal
    percentage: float | None
    band: Band | None
    questions: list[str]
    marks_lost: Decimal
    lost_by: list[LostOut]
    topics: list[str]
    evidence: Literal["complete", "partial"]
    left_out: list[str]
    module_only: list[str]


class TopicRow(BaseModel):
    id: str
    name: str
    module_id: str | None
    module_name: str | None
    earned: Decimal
    possible: Decimal
    percentage: float | None
    band: Band | None
    questions: list[str]
    marks_lost: Decimal
    lost_by: list[LostOut]
    partial: bool
    classification: MasteryClass | None
    direct_observations: int
    min_observations: int
    evidence_sufficient: bool
    recommendation: str


class AnalysisOut(BaseModel):
    breakdown: BreakdownSummary
    overall: OverallOut
    modules: list[ModuleRow]
    focus_module_id: str | None
    topics: list[TopicRow]
    recorded: RecordedResult | None
    warnings: list[str]
    rule_version: str


# --------------------------------------------------------------------------- #


def _m(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"))


def _get(session: SessionDep, student_id: str, breakdown_id: str) -> ExamBreakdown:
    try:
        return service.owned(session, student_id, breakdown_id)
    except service.NotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Exam breakdown not found.") from exc


def _summary(session: SessionDep, b: ExamBreakdown, result: Breakdown) -> BreakdownSummary:
    subject = session.get(Subject, b.subject_id)
    o = result.overall
    counted = bool(o.questions)
    return BreakdownSummary(
        id=b.id,
        title=b.title,
        subject_id=b.subject_id,
        subject_name=subject.name if subject else "",
        assessment_id=b.assessment_id,
        held_on=b.held_on,
        status=b.status,
        question_count=len(b.questions),
        earned=round_marks(o.earned) if counted else None,
        possible=round_marks(o.possible) if counted else None,
        percentage=percent(o),
        complete=result.complete and counted,
        updated_at=b.updated_at,
    )


def _recorded(session: SessionDep, b: ExamBreakdown) -> RecordedResult | None:
    r = service.overall_result(session, b)
    if r is None:
        return None
    a = session.get(Assessment, r.assessment_id)
    label = (a.exam_name if a else None) or (
        f"Semester {a.semester}" if a and a.semester else "Exam"
    )
    return RecordedResult(
        assessment_label=label, marks_obtained=r.marks_obtained, max_marks=r.max_marks
    )


def _detail(session: SessionDep, settings: SettingsDep, b: ExamBreakdown) -> BreakdownDetail:
    result, s = service.compute(session, b)
    suggester = TopicSuggester(session, b.subject_id, settings.allow_unreviewed_content)
    by_id = {r.id: r for r in result.questions}
    paper = None
    if b.document_id and (doc := session.get(Document, b.document_id)) is not None:
        a = doc.analysis or {}
        paper = PaperOut(
            filename=doc.original_filename,
            status=doc.status.value,
            error=doc.error,
            source=a.get("source"),
            notes=a.get("notes", []),
            warnings=a.get("warnings", []),
        )
    questions = []
    for q in b.questions:
        sug = suggester.suggest(" ".join(filter(None, [q.context, q.text])), q.paper_module)
        r = by_id[q.id]
        questions.append(
            QuestionOut(
                id=q.id,
                position=q.position,
                label=q.label,
                section=q.section,
                context=q.context,
                text=q.text,
                page=q.page,
                max_marks=q.max_marks,
                marks_obtained=q.marks_obtained,
                attempt_status=q.attempt_status,
                is_optional=q.is_optional,
                choice_group=q.choice_group,
                needs_review=q.needs_review,
                parse_confidence=q.parse_confidence,
                paper_module=q.paper_module,
                mappings=[
                    MappingOut(topic_id=m.topic_id, module_id=m.module_id, share=m.share)
                    for m in q.mappings
                ],
                suggestion=SuggestionOut(
                    status=sug.status,
                    candidates=[
                        CandidateOut(
                            topic_id=c.topic_id,
                            topic_name=c.topic_name,
                            module_id=c.module_id,
                            score=c.score,
                            matched=list(c.matched),
                        )
                        for c in sug.candidates
                    ],
                    paper_module_id=sug.paper_module_id,
                ),
                counted=r.counted,
                exclusion=EXCLUSION_TEXT[r.exclusion] if r.exclusion else None,
            )
        )
    return BreakdownDetail(
        **_summary(session, b, result).model_dump(),
        declared_total=b.declared_total,
        choice_rules=b.choice_rules or {},
        questions=questions,
        modules=[ModuleOut(id=m.id, number=m.number, name=m.name) for m in s.modules],
        topics=[
            SubjectTopicOut(id=t.id, slug=t.slug, name=t.name, module_id=mid)
            for t, mid in s.topics.values()
        ],
        paper=paper,
        recorded=_recorded(session, b),
        warnings=service.checks(session, b, result),
    )


def _lost(t: Tally) -> list[LostOut]:
    merged: dict[str, Decimal] = defaultdict(Decimal)
    for label, lost in t.lost_by:
        merged[label] += lost
    rows = [LostOut(label=k, lost=_m(v)) for k, v in merged.items()]
    return sorted(rows, key=lambda r: -r.lost)


def _recommendation(
    name: str, t: Tally, band: str | None, classification: MasteryClass | None, sufficient: bool
) -> str:
    lost = _lost(t)
    parts = []
    if band == "needs_attention":
        parts.append(f"Revise {name} first in this subject")
    elif band == "developing":
        parts.append(f"Firm up {name}")
    else:
        parts.append(f"{name} went well in this exam")
    if lost and band != "strong":
        top = ", ".join(f"Q{r.label}" for r in lost[:3])
        parts[-1] += f": most marks were lost in {top}"
    parts[-1] += "."
    if not sufficient:
        parts.append(
            "There is not yet enough topic-level evidence to classify the topic; a diagnostic "
            "quiz would confirm whether this is a real gap."
        )
    elif classification is MasteryClass.NEEDS_ATTENTION:
        parts.append("Your overall evidence for this topic also says it needs attention.")
    return " ".join(parts)


def _analysis(session: SessionDep, policy: PolicyDep, b: ExamBreakdown) -> AnalysisOut:
    result, s = service.compute(session, b)
    o = result.overall
    mastery = service.mastery(session, b.student_id)
    min_obs = policy.topics.min_direct_observations
    module_names = {m.id: m for m in s.modules}
    topic_names = {tid: t.name for tid, (t, _) in s.topics.items()}

    modules = []
    for mid, t in result.modules.items():
        m = module_names.get(mid) if mid else None
        modules.append(
            ModuleRow(
                id=mid,
                number=m.number if m else None,
                name=m.name if m else "Topics not in a module",
                earned=_m(t.earned),
                possible=_m(t.possible),
                percentage=percent(t),
                band=service.performance_band(t, policy),
                questions=t.questions,
                marks_lost=_m(t.lost),
                lost_by=_lost(t),
                topics=[topic_names.get(x, x) for x in t.topic_ids],
                evidence="partial" if t.partial else "complete",
                left_out=t.left_out,
                module_only=t.module_only,
            )
        )
    modules.sort(key=lambda r: (r.number is None, r.number or 0))
    scored = [r for r in modules if r.possible > 0 and r.id is not None]
    focus = max(scored, key=lambda r: (r.marks_lost, -(r.percentage or 0)), default=None)

    topics = []
    for tid, t in result.topics.items():
        tm = mastery.get(tid)
        direct = int((tm.rationale or {}).get("direct_observations", 0)) if tm else 0
        classification = tm.classification if tm else None
        sufficient = classification not in (None, MasteryClass.INSUFFICIENT_EVIDENCE)
        band = service.performance_band(t, policy)
        mid = s.topics[tid][1] if tid in s.topics else None
        topics.append(
            TopicRow(
                id=tid,
                name=topic_names.get(tid, tid),
                module_id=mid,
                module_name=module_names[mid].name if mid in module_names else None,
                earned=_m(t.earned),
                possible=_m(t.possible),
                percentage=percent(t),
                band=band,
                questions=t.questions,
                marks_lost=_m(t.lost),
                lost_by=_lost(t),
                partial=t.partial,
                classification=classification,
                direct_observations=direct,
                min_observations=min_obs,
                evidence_sufficient=sufficient,
                recommendation=_recommendation(
                    topic_names.get(tid, "This topic"), t, band, classification, sufficient
                ),
            )
        )
    topics.sort(key=lambda r: (-r.marks_lost, r.percentage or 0, r.name))
    excluded = [
        ExcludedOut(reason=k, text=EXCLUSION_TEXT[k], labels=v) for k, v in result.excluded.items()
    ]
    return AnalysisOut(
        breakdown=_summary(session, b, result),
        overall=OverallOut(
            earned=_m(o.earned),
            possible=_m(o.possible),
            percentage=percent(o),
            band=service.performance_band(o, policy),
            counted=len(o.questions),
            total_questions=len(b.questions),
            complete=result.complete,
            excluded=excluded,
            unmapped=result.unmapped,
        ),
        modules=modules,
        focus_module_id=focus.id if focus and focus.marks_lost > 0 else None,
        topics=topics,
        recorded=_recorded(session, b),
        warnings=service.checks(session, b, result),
        rule_version=RULE_VERSION,
    )


# --------------------------------------------------------------------------- #
# Cross-exam summary (dashboard, Topics page)
# --------------------------------------------------------------------------- #


class SummaryModule(BaseModel):
    subject_id: str
    subject_name: str
    module_id: str
    number: int
    name: str
    earned: Decimal
    possible: Decimal
    percentage: float | None
    marks_lost: Decimal
    exams: int


class SummaryTopic(BaseModel):
    topic_id: str
    name: str
    earned: Decimal
    possible: Decimal
    percentage: float | None
    marks_lost: Decimal
    exams: int
    weak_in_exams: int
    repeated: bool
    classification: MasteryClass | None
    plan_position: int | None
    breakdown_ids: list[str]


class ExamSummary(BaseModel):
    confirmed: int
    drafts: int
    modules: list[SummaryModule]
    topics: list[SummaryTopic]


@router.get("/summary", response_model=ExamSummary)
def summary(student: StudentDep, session: SessionDep, policy: PolicyDep) -> ExamSummary:
    confirmed = service.confirmed_breakdowns(session, student.id)
    draft_count = len(
        session.scalars(
            select(ExamBreakdown.id).where(
                ExamBreakdown.student_id == student.id,
                ExamBreakdown.status == BreakdownStatus.DRAFT,
            )
        ).all()
    )
    modules: dict[str, Tally] = defaultdict(Tally)
    module_exams: dict[str, set[str]] = defaultdict(set)
    module_info: dict[str, tuple[str, str, int, str]] = {}
    topics: dict[str, Tally] = defaultdict(Tally)
    topic_exams: dict[str, list[str]] = defaultdict(list)
    weak: dict[str, int] = defaultdict(int)
    names: dict[str, str] = {}
    for b in confirmed:
        result, s = service.compute(session, b)
        for mid, t in result.modules.items():
            if mid is None or t.possible <= 0:
                continue
            m = next((x for x in s.modules if x.id == mid), None)
            if m is None:
                continue
            module_info[mid] = (s.subject.id, s.subject.name, m.number, m.name)
            modules[mid].earned += t.earned
            modules[mid].possible += t.possible
            module_exams[mid].add(b.id)
        for tid, t in result.topics.items():
            if t.possible <= 0:
                continue
            names[tid] = s.topics[tid][0].name if tid in s.topics else tid
            topics[tid].earned += t.earned
            topics[tid].possible += t.possible
            topic_exams[tid].append(b.id)
            if service.performance_band(t, policy) == "needs_attention":
                weak[tid] += 1
    mastery = service.mastery(session, student.id)
    plan = service.plan_positions(session, student.id)
    module_rows = [
        SummaryModule(
            subject_id=info[0],
            subject_name=info[1],
            module_id=mid,
            number=info[2],
            name=info[3],
            earned=_m(modules[mid].earned),
            possible=_m(modules[mid].possible),
            percentage=percent(modules[mid]),
            marks_lost=_m(modules[mid].lost),
            exams=len(module_exams[mid]),
        )
        for mid, info in module_info.items()
    ]
    module_rows.sort(key=lambda r: (-r.marks_lost, r.percentage or 0))
    topic_rows = [
        SummaryTopic(
            topic_id=tid,
            name=names[tid],
            earned=_m(t.earned),
            possible=_m(t.possible),
            percentage=percent(t),
            marks_lost=_m(t.lost),
            exams=len(topic_exams[tid]),
            weak_in_exams=weak[tid],
            repeated=weak[tid] >= 2,
            classification=mastery[tid].classification if tid in mastery else None,
            plan_position=plan.get(tid),
            breakdown_ids=topic_exams[tid],
        )
        for tid, t in topics.items()
    ]
    topic_rows.sort(key=lambda r: (-r.weak_in_exams, -r.marks_lost, r.percentage or 0))
    return ExamSummary(
        confirmed=len(confirmed), drafts=draft_count, modules=module_rows, topics=topic_rows
    )


# --------------------------------------------------------------------------- #
# CRUD
# --------------------------------------------------------------------------- #


@router.get("", response_model=list[BreakdownSummary])
def list_breakdowns(student: StudentDep, session: SessionDep) -> list[BreakdownSummary]:
    rows = session.scalars(
        select(ExamBreakdown.id)
        .where(ExamBreakdown.student_id == student.id)
        .order_by(ExamBreakdown.created_at.desc())
    ).all()
    out = []
    for bid in rows:
        b = service.owned(session, student.id, bid)
        result, _ = service.compute(session, b)
        out.append(_summary(session, b, result))
    return out


@router.post("", status_code=status.HTTP_201_CREATED, response_model=BreakdownDetail)
def create_breakdown(
    body: NewBreakdown, student: StudentDep, session: SessionDep, settings: SettingsDep
) -> BreakdownDetail:
    try:
        b = service.create(session, student, body)
    except service.BreakdownProblem as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    except service.BreakdownConflict as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT, {"message": str(exc), "breakdown_id": exc.existing_id}
        ) from exc
    return _detail(session, settings, _get(session, student.id, b.id))


@router.get("/{breakdown_id}", response_model=BreakdownDetail)
def get_breakdown(
    breakdown_id: str, student: StudentDep, session: SessionDep, settings: SettingsDep
) -> BreakdownDetail:
    return _detail(session, settings, _get(session, student.id, breakdown_id))


@router.post("/{breakdown_id}/paper", response_model=PaperUploadOut)
async def upload_paper(
    breakdown_id: str,
    file: UploadFile,
    student: StudentDep,
    session: SessionDep,
    settings: SettingsDep,
    store: StoreDep,
    policy: PolicyDep,
    replace: Annotated[bool, Query()] = False,
) -> PaperUploadOut:
    b = _get(session, student.id, breakdown_id)
    if not upload_limiter.allow(student.id):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many uploads; try later.")
    data = await file.read(settings.max_upload_bytes + 1)
    try:
        outcome = service.attach_paper(
            session, settings, store, policy, student, b, file.filename, data, replace
        )
    except UploadRejected as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    except service.BreakdownProblem as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    except service.BreakdownConflict as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    purge_expired_files(session, store)
    return PaperUploadOut(
        questions_found=outcome.questions_found,
        warnings=outcome.warnings,
        error=outcome.error,
        source=outcome.source,
        breakdown=_detail(session, settings, _get(session, student.id, breakdown_id)),
    )


@router.put("/{breakdown_id}", response_model=BreakdownDetail)
def update_breakdown(
    breakdown_id: str,
    body: BreakdownUpdate,
    student: StudentDep,
    session: SessionDep,
    settings: SettingsDep,
    policy: PolicyDep,
) -> BreakdownDetail:
    b = _get(session, student.id, breakdown_id)
    try:
        service.update(session, policy, student, b, body)
    except service.BreakdownProblem as exc:
        session.rollback()
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    except service.BreakdownConflict as exc:
        session.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT, {"message": str(exc), "breakdown_id": exc.existing_id}
        ) from exc
    return _detail(session, settings, _get(session, student.id, breakdown_id))


@router.post("/{breakdown_id}/confirm", response_model=AnalysisOut)
def confirm_breakdown(
    breakdown_id: str, student: StudentDep, session: SessionDep, policy: PolicyDep
) -> AnalysisOut:
    b = _get(session, student.id, breakdown_id)
    try:
        service.confirm(session, policy, student, b)
    except service.BreakdownProblem as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    return _analysis(session, policy, _get(session, student.id, breakdown_id))


@router.post("/{breakdown_id}/reopen", response_model=BreakdownSummary)
def reopen_breakdown(
    breakdown_id: str, student: StudentDep, session: SessionDep, policy: PolicyDep
) -> BreakdownSummary:
    b = _get(session, student.id, breakdown_id)
    service.reopen(session, policy, student, b)
    b = _get(session, student.id, breakdown_id)
    return _summary(session, b, service.compute(session, b)[0])


@router.get("/{breakdown_id}/analysis", response_model=AnalysisOut)
def get_analysis(
    breakdown_id: str, student: StudentDep, session: SessionDep, policy: PolicyDep
) -> AnalysisOut:
    return _analysis(session, policy, _get(session, student.id, breakdown_id))


@router.delete("/{breakdown_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_breakdown(
    breakdown_id: str,
    student: StudentDep,
    session: SessionDep,
    store: StoreDep,
    policy: PolicyDep,
) -> None:
    b = _get(session, student.id, breakdown_id)
    service.delete_breakdown(session, store, policy, student, b)
