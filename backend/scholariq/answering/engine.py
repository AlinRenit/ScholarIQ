"""The answer engine: read the question, decide, pick a handler, check, answer.

Decision rules (version ``tutor-rules/1``), in order:

1. Code in the question goes to the code handler (E).
2. A solver that recognises the problem answers it (D). A "solve" question no
   solver recognises gets the list of supported problem types.
3. Follow-ups ("simplify", "the second step", "another example") apply to the
   concepts of the previous answer in the same conversation.
4. "What should I study" uses the student's own topic evidence.
5. Otherwise the question must be about something in the knowledge base:
   * a name or alias that matches more than one concept, or two candidates
     scoring within AMBIGUITY_RATIO of each other without a clear name match,
     gets a clarifying question listing the options;
   * no candidate scoring at least MIN_SCORE, or fewer than MIN_COVERAGE of the
     question's subject words known to the knowledge base, without a concept
     name in the question, gets an honest "not covered" answer (F);
   * otherwise the top concept (or a named topic) is answered by the handler
     for the question type: definitions and explanations (A), comparisons (B),
     procedures (C), prerequisites, practice.
6. Every section is checked to come from the knowledge base, a solver or a
   fixed template before the answer is returned.

The thresholds were set from the retrieval evaluation set, so they fit that
set better than they will fit new questions; see docs/eval/answers.md.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

from sqlalchemy import select
from sqlalchemy.orm import Session

from scholariq.analytics.policy import Policy
from scholariq.analytics.service import compute_topics, load_result_rows
from scholariq.analytics.subjects import summarise_subjects
from scholariq.answering import code as code_analysis
from scholariq.answering import sections as S
from scholariq.answering.content import ConceptBundle, ref_of
from scholariq.answering.handlers.advice import study_advice
from scholariq.answering.handlers.base import HandlerContext
from scholariq.answering.handlers.compare import compare
from scholariq.answering.handlers.explain import explain_brief, explain_concept, topic_overview
from scholariq.answering.handlers.practice import practice
from scholariq.answering.handlers.prerequisites import prerequisites
from scholariq.answering.handlers.procedure import procedure_for_concept, procedure_for_topic
from scholariq.answering.handlers.unknown import abstain
from scholariq.answering.model import (
    Answer,
    Clarification,
    ConceptRef,
    Item,
    Origin,
    Personalisation,
    Reading,
    Review,
    Section,
    Suggestion,
)
from scholariq.answering.solvers import SUPPORTED, Solution, SolverError, solve
from scholariq.db.models import Concept, Subject, Topic
from scholariq.domain.enums import KnowledgeDocumentKind as K
from scholariq.domain.enums import MasteryClass, TrustStatus
from scholariq.knowledge.index import ConceptIndex, SearchHit, allowed_trust
from scholariq.nlu.intents import Depth, FollowUp, Intent
from scholariq.nlu.lexicon import Lexicon
from scholariq.nlu.parser import Context, ParsedQuery, parse, split_parts
from scholariq.tutoring.policy import POLICY_VERSION, TeachingPlan, plan_for

MIN_SCORE = 9.0
MIN_COVERAGE = 0.5
AMBIGUITY_RATIO = 0.9
MAX_PARTS = 3

UNREVIEWED_LABEL = (
    "Not yet reviewed by a person. This answer is built from knowledge-base entries that no "
    "one has checked yet; check anything important against the further reading."
)

HANDLER_LABELS = {
    "A": "Definition and explanation",
    "B": "Comparison",
    "C": "Step by step",
    "D": "Worked problem",
    "E": "Code question",
    "F": "Not covered",
    "prerequisites": "Prerequisites",
    "practice": "Practice",
    "advice": "What to study",
    "clarify": "Clarifying question",
    "follow-up": "Follow-up",
}


@dataclass
class Request:
    text: str
    context: Context | None = None
    action: FollowUp | None = None  # a button press: simplify, example, check, deeper
    asked: set[str] = field(default_factory=set)
    # The concept the student picked from a clarifying question: an ambiguous
    # name in the text is read as this meaning.
    meaning: str | None = None


@dataclass
class Outcome:
    answer: Answer
    context: Context  # what a follow-up to this answer refers to


class Engine:
    def __init__(
        self,
        session: Session,
        lexicon: Lexicon,
        *,
        allow_unreviewed: bool,
        student_id: str | None = None,
        policy: Policy | None = None,
    ) -> None:
        self.session = session
        self.lex = lexicon
        self.index: ConceptIndex = lexicon.index
        self.allowed: tuple[TrustStatus, ...] = allowed_trust(allow_unreviewed)
        self.student_id = student_id
        self.policy = policy
        self._classes: dict[str, MasteryClass] | None = None
        self._previous: Context | None = None

    # ----------------------------------------------------------------- public

    def answer(self, req: Request) -> Outcome:
        has_code = "```" in req.text or "\n" in req.text.strip()
        parts = split_parts(req.text) if req.action is None and not has_code else [req.text]
        if len(parts) > 1:
            # Each part can refer back to the one before
            # ("what is a stack? how is a queue different?").
            outcomes: list[Outcome] = []
            context = req.context
            for part in parts[:MAX_PARTS]:
                outcome = self._answer_one(Request(part, context, None, req.asked))
                outcomes.append(outcome)
                context = outcome.context if outcome.context.concepts else context
            return self._merge(outcomes, len(parts) > MAX_PARTS)
        return self._answer_one(req)

    # --------------------------------------------------------------- pipeline

    def _answer_one(self, req: Request) -> Outcome:
        parsed = parse(req.text, self.lex, req.context)
        if req.meaning:
            for m in parsed.mentions:
                if m.kind == "concept" and len(m.refs) > 1 and req.meaning in m.refs:
                    parsed.mentions = [
                        replace(x, refs=(req.meaning,)) if x is m else x for x in parsed.mentions
                    ]
                    parsed.trace.append(f'Read "{m.text}" as {req.meaning}: the meaning you chose.')
                    parsed.resolved = req.meaning
                    break
        if req.action is not None and req.context and req.context.concepts:
            parsed.intent, parsed.follow_up, parsed.used_context = (
                Intent.FOLLOW_UP,
                req.action,
                True,
            )
            parsed.trace.append(
                f"Button: {req.action.value.replace('_', ' ')} on the previous answer."
            )
        ctx = HandlerContext(
            self.session, self.allowed, parsed, self._plan, set(req.asked), self.student_id
        )
        self._previous = req.context

        if parsed.intent is Intent.CODE:
            return self._code(parsed)
        if req.action is None:
            # A problem written out in full is solved even mid-conversation.
            solved = solve(parsed.text)
            if solved is not None:
                parsed.intent, parsed.follow_up = Intent.WORKED_PROBLEM, None
                parsed.trace = [t for t in parsed.trace if not t.startswith("Follow-up")]
                return self._solved(ctx, solved)
            if parsed.intent is Intent.WORKED_PROBLEM and not parsed.concepts():
                return self._unsupported_problem(parsed)
        if parsed.intent is Intent.FOLLOW_UP and req.context:
            return self._follow_up(ctx, req.context)
        if parsed.intent is Intent.STUDY_ADVICE:
            return self._advice(parsed)
        return self._knowledge(ctx)

    def _knowledge(self, ctx: HandlerContext) -> Outcome:
        p = ctx.parsed
        decision: list[str] = []
        concept_mentions = p.concepts()

        ambiguous = next((m for m in concept_mentions if len(m.refs) > 1), None)
        if ambiguous is not None:
            resolved = self._resolve(p, ambiguous.refs)
            if resolved is None:
                return self._clarify(
                    p,
                    f'"{ambiguous.text}" can mean more than one thing. Which did you mean?',
                    list(ambiguous.refs),
                )
            p.mentions = [replace(m, refs=(resolved,)) if m is ambiguous else m for m in p.mentions]
            p.resolved = resolved
            concept_mentions = p.concepts()
            p.trace.append(
                f'Read "{ambiguous.text}" as {resolved}: the rest of the question fits it better.'
            )

        if p.intent is Intent.COMPARISON:
            slugs = [m.refs[0] for m in concept_mentions]
            prev = self._previous.concepts if self._previous else []
            if len(slugs) == 1 and prev and prev[0] != slugs[0]:
                # "How is a queue different?" right after an answer about stacks.
                slugs = [prev[0], slugs[0]]
                p.trace.append(f"Comparing with {prev[0]} from the previous answer.")
            return self._comparison(ctx, slugs)

        topic = p.topics()[0].refs[0] if p.topics() else None
        if p.intent in (Intent.PREREQUISITES, Intent.PRACTICE) and (concept_mentions or topic):
            slugs = [m.refs[0] for m in concept_mentions]
            return self._list_handler(ctx, slugs, None if slugs else topic)

        if len(concept_mentions) >= 2 and p.intent in (
            Intent.DEFINITION,
            Intent.EXPLANATION,
            Intent.UNKNOWN,
        ):
            return self._several(ctx, [m.refs[0] for m in concept_mentions])

        cands = p.candidates
        if p.resolved and [m.refs[0] for m in concept_mentions] == [p.resolved]:
            # A name shared by several concepts scores the same for each; once one
            # meaning is settled and it is the only concept named, it comes first.
            named_hit = [h for h in cands if h.concept.slug == p.resolved]
            cands = named_hit + [h for h in cands if h not in named_hit]
        top = cands[0] if cands else None
        named = top is not None and top.name_match is not None
        if topic and not concept_mentions:
            if p.intent is Intent.PROCEDURE:
                return self._topic_procedure(ctx, topic)
            return self._topic(ctx, topic)

        if top is None or (not named and (top.score < MIN_SCORE or p.coverage < MIN_COVERAGE)):
            return self._abstain(p, top)
        decision.append(
            f"Best match: {top.concept.name} (score {top.score:.1f}"
            + (f', names "{top.name_match}"' if named else "")
            + ")."
        )
        second = cands[1] if len(cands) > 1 else None
        extra_words = len(p.content_words) - len((top.name_match or "").split())
        if (
            second is not None
            and second.score >= AMBIGUITY_RATIO * top.score
            and (not named or extra_words >= 2)
        ):
            return self._clarify(
                p,
                "Your question fits more than one concept about equally well. Which did you mean?",
                [h.concept.slug for h in cands[:3]],
                decision
                + [
                    f"{second.concept.name} scores {second.score:.1f}, "
                    f"within {AMBIGUITY_RATIO:.0%}."
                ],
            )
        b = ctx.bundle(top.concept.slug)
        if b is None:
            return self._abstain(p, top)
        if p.intent is Intent.PRACTICE:
            return self._list_handler(ctx, [b.ref.slug], None, decision)
        if p.intent is Intent.PREREQUISITES:
            return self._list_handler(ctx, [b.ref.slug], None, decision)
        if p.intent in (Intent.PROCEDURE, Intent.WORKED_PROBLEM):
            return self._concept(ctx, b, "C", decision)
        return self._concept(ctx, b, "A", decision)

    # --------------------------------------------------------------- handlers

    def _concept(
        self,
        ctx: HandlerContext,
        b: ConceptBundle,
        handler: str,
        decision: list[str],
        depth: Depth | None = None,
    ) -> Outcome:
        p = ctx.parsed
        plan, pers = self._plan(b.ref.topic_slug, depth or p.depth)
        if handler == "C":
            secs = procedure_for_concept(ctx, b)
            if p.intent is Intent.WORKED_PROBLEM:
                secs.insert(0, self._supported_note())
        else:
            secs = explain_concept(ctx, b, plan, reasoning=p.intent is Intent.REASONING)
        answer = self._make(p, handler, secs, [b.ref], decision, pers, b.reading)
        answer.suggestions = self._concept_suggestions(b)
        if plan.offer_diagnostic:
            answer.suggestions.append(
                Suggestion(
                    label=f"Practice {b.ref.topic_name}",
                    action="ask",
                    query=f"Give me questions on {b.ref.name}",
                )
            )
        return Outcome(answer, self._context_for(answer, b.ref.topic_slug, plan))

    def _several(self, ctx: HandlerContext, slugs: list[str]) -> Outcome:
        bundles = [b for s in dict.fromkeys(slugs) if (b := ctx.bundle(s))]
        secs: list[Section] = []
        for b in bundles:
            secs += explain_brief(b)
        answer = self._make(
            ctx.parsed,
            "A",
            secs,
            [b.ref for b in bundles],
            [],
            None,
            [r for b in bundles for r in b.reading],
        )
        if len(bundles) >= 2:
            answer.suggestions = [
                Suggestion(
                    label=f"Compare {bundles[0].ref.name} and {bundles[1].ref.name}",
                    action="ask",
                    query=f"Difference between {bundles[0].ref.name} and {bundles[1].ref.name}",
                )
            ]
        answer.suggestions += [
            Suggestion(label=f"Explain {b.ref.name}", action="ask", query=f"Explain {b.ref.name}")
            for b in bundles
        ]
        return Outcome(
            answer, Context(concepts=[b.ref.slug for b in bundles], intent=ctx.parsed.intent.value)
        )

    def _comparison(self, ctx: HandlerContext, slugs: list[str]) -> Outcome:
        p = ctx.parsed
        slugs = list(dict.fromkeys(slugs))
        if len(slugs) == 1:
            b = ctx.bundle(slugs[0])
            options = [r.slug for r in (b.contrasts + b.related)][:4] if b else []
            if b and options:
                return self._clarify(
                    p,
                    f"Compare {b.ref.name} with what?",
                    options,
                    query_template=f"Difference between {b.ref.name} and {{name}}",
                )
        if len(slugs) < 2:
            return self._abstain(
                p,
                p.candidates[0] if p.candidates else None,
                "I could not find two concepts to compare. Name both, for example "
                '"difference between a stack and a queue".',
            )
        bundles = [b for s in slugs[:2] if (b := ctx.bundle(s))]
        if len(bundles) < 2:
            return self._abstain(p, None)
        secs = compare(bundles)
        answer = self._make(
            p,
            "B",
            secs,
            [b.ref for b in bundles],
            [f"Comparing {bundles[0].ref.name} with {bundles[1].ref.name}."],
            None,
            bundles[0].reading + bundles[1].reading,
        )
        answer.suggestions = [
            Suggestion(label=f"Explain {b.ref.name}", action="ask", query=f"Explain {b.ref.name}")
            for b in bundles
        ]
        return Outcome(answer, Context(concepts=[b.ref.slug for b in bundles], intent="comparison"))

    def _list_handler(
        self,
        ctx: HandlerContext,
        slugs: list[str],
        topic: str | None,
        decision: list[str] | None = None,
    ) -> Outcome:
        p = ctx.parsed
        if p.intent is Intent.PRACTICE:
            secs, used = practice(ctx, slugs, topic)
            handler = "practice"
        else:
            secs, used = prerequisites(ctx, slugs, topic)
            handler = "prerequisites"
        refs = self._refs(used)
        answer = self._make(p, handler, secs, refs, decision or [], None, [])
        if handler == "prerequisites" and refs:
            answer.suggestions = [
                Suggestion(label=f"Explain {r.name}", action="ask", query=f"Explain {r.name}")
                for r in refs[:3]
            ]
        return Outcome(answer, Context(concepts=slugs or used, topic=topic, intent=p.intent.value))

    def _topic(self, ctx: HandlerContext, topic: str) -> Outcome:
        secs = topic_overview(ctx, topic)
        found = self.session.scalar(select(Topic).where(Topic.slug == topic))
        concepts = [
            c
            for c in self.session.scalars(
                select(Concept).where(
                    Concept.topic.has(slug=topic), Concept.trust_status.in_(self.allowed)
                )
            ).all()
        ]
        refs = [ref_of(c, found) for c in concepts] if found else []
        if not secs:
            return self._abstain(
                ctx.parsed,
                None,
                f"The knowledge base has no entries for {found.name if found else topic} yet.",
            )
        answer = self._make(
            ctx.parsed,
            "A",
            secs,
            refs,
            [f"Answering at topic level: {found.name if found else topic}."],
            None,
            [],
        )
        answer.suggestions = [
            Suggestion(label=f"Explain {r.name}", action="ask", query=f"Explain {r.name}")
            for r in refs[:3]
        ]
        answer.suggestions.append(
            Suggestion(
                label="What should I learn first?",
                action="ask",
                query=f"What should I learn before {found.name if found else topic}?",
            )
        )
        return Outcome(
            answer, Context(concepts=[r.slug for r in refs], topic=topic, intent="explanation")
        )

    def _topic_procedure(self, ctx: HandlerContext, topic: str) -> Outcome:
        secs, used = procedure_for_topic(ctx, topic)
        if not secs:
            return self._abstain(ctx.parsed, None)
        answer = self._make(
            ctx.parsed,
            "C",
            secs,
            self._refs(used),
            ["Walking through the topic's concepts in prerequisite order."],
            None,
            [],
        )
        return Outcome(answer, self._context_for(answer, topic, None))

    def _follow_up(self, ctx: HandlerContext, prev: Context) -> Outcome:
        p = ctx.parsed
        kind = p.follow_up or FollowUp.CONTINUE
        slugs = prev.concepts
        b = ctx.bundle(slugs[0]) if slugs else None
        if b is None:
            return self._abstain(
                p, None, "I could not tell what this refers to. Ask the full question again."
            )
        decision = [f"Continuing with {b.ref.name} from the previous answer."]
        if kind is FollowUp.REPEAT_STEP:
            n = p.step
            if not prev.steps or n is None or n == 0 or abs(n) > len(prev.steps):
                return self._abstain(p, None, "The previous answer has no step with that number.")
            text = prev.steps[n - 1] if n > 0 else prev.steps[-1]
            label = f"step {n}" if n > 0 else "the last step"
            secs = [
                Section(kind="steps", title=f"Again: {label}", steps=[text], origin=S.knowledge(b))
            ]
            secs += [S.document(b, d) for d in b.docs(K.EXAMPLE)[:1]]
            answer = self._make(p, "follow-up", secs, [b.ref], decision, None, b.reading)
            answer.suggestions = self._concept_suggestions(b)
            return Outcome(answer, prev)
        if kind is FollowUp.EXAMPLE:
            examples = b.docs(K.EXAMPLE, K.EXERCISE)
            secs = [S.document(b, d) for d in examples] or [
                Section(
                    kind="note",
                    title="No worked example",
                    text=f"The knowledge base has no worked example for {b.ref.name} yet.",
                    origin=Origin(kind="template"),
                )
            ]
            answer = self._make(p, "follow-up", secs, [b.ref], decision, None, b.reading)
            answer.suggestions = self._concept_suggestions(b)
            return Outcome(answer, prev)
        if kind is FollowUp.CHECK:
            p.intent = Intent.PRACTICE
            return self._list_handler(ctx, [b.ref.slug], None, decision)
        if kind in (FollowUp.SIMPLIFY, FollowUp.DEEPER):
            depth = Depth.SIMPLER if kind is FollowUp.SIMPLIFY else Depth.DEEPER
            return self._concept(ctx, b, "A", decision, depth)
        # CONTINUE: same concept, the newly asked question type (or the previous one).
        if p.intents:
            p.intent = p.intents[0].intent
        elif prev.intent:
            p.intent = (
                Intent(prev.intent)
                if prev.intent in Intent._value2member_map_
                else Intent.EXPLANATION
            )
        if p.intent is Intent.COMPARISON and len(slugs) >= 2:
            return self._comparison(ctx, slugs)
        if p.intent in (Intent.PRACTICE, Intent.PREREQUISITES):
            return self._list_handler(ctx, [b.ref.slug], None, decision)
        handler = "C" if p.intent is Intent.PROCEDURE else "A"
        return self._concept(ctx, b, handler, decision)

    def _solved(self, ctx: HandlerContext, result: Solution | SolverError) -> Outcome:
        p = ctx.parsed
        refs = self._refs([result.concept] if result.concept else [])
        if isinstance(result, SolverError):
            secs = [
                Section(
                    kind="note",
                    title="Could not solve this as written",
                    text=result.message,
                    origin=Origin(kind="solver", solver=result.solver),
                )
            ]
            answer = self._make(
                p, "D", secs, refs, [f"Recognised as a {result.solver} problem."], None, []
            )
            answer.status = "abstained"
            answer.missing = result.message
            return Outcome(
                answer, Context(concepts=[r.slug for r in refs], intent="worked_problem")
            )
        origin = Origin(kind="solver", solver=result.solver)
        secs = [Section(kind="definition", title="Answer", text=result.result, origin=origin)]
        if result.steps:
            secs.append(
                Section(
                    kind="steps", title="How it was worked out", steps=result.steps, origin=origin
                )
            )
        if result.rows:
            secs.append(
                Section(
                    kind="table",
                    title=result.title,
                    columns=result.columns,
                    rows=result.rows,
                    origin=origin,
                )
            )
        answer = self._make(
            p, "D", secs, refs, [f"Solved with the {result.solver} solver."], None, []
        )
        answer.limitations = result.limitations
        if refs:
            answer.suggestions = [
                Suggestion(
                    label=f"Explain {refs[0].name}", action="ask", query=f"Explain {refs[0].name}"
                )
            ]
        steps = result.steps
        return Outcome(
            answer, Context(concepts=[r.slug for r in refs], intent="worked_problem", steps=steps)
        )

    def _unsupported_problem(self, p: ParsedQuery) -> Outcome:
        answer = self._make(p, "F", [self._supported_note()], [], [], None, [])
        answer.status = "abstained"
        answer.missing = "No solver recognised this problem."
        return Outcome(answer, Context())

    def _supported_note(self) -> Section:
        return Section(
            kind="list",
            title="Problems I can solve when you write them out",
            items=[Item(text=d) for d in SUPPORTED],
            origin=Origin(kind="template"),
        )

    def _code(self, p: ParsedQuery) -> Outcome:
        block = p.code[0]
        lang = code_analysis.detect_language(block.code, block.language)
        secs: list[Section] = [
            Section(
                kind="code",
                title=f"Your code ({lang})",
                code=block.code,
                origin=Origin(kind="template"),
            )
        ]
        limitations = ["Code is analysed without running it."]
        if lang != "python":
            secs.append(
                Section(
                    kind="note",
                    title="Not analysed",
                    text=f"Only Python code is parsed. I cannot analyse {lang} code, so "
                    "nothing is said about what it does or how fast it is.",
                    origin=Origin(kind="template"),
                )
            )
        else:
            report = code_analysis.analyse_python(block.code)
            origin = Origin(kind="analysis", solver="python-ast")
            if not report.parsed:
                secs.append(
                    Section(kind="note", title="Syntax error", text=report.error, origin=origin)
                )
            else:
                units = report.functions + ([report.top_level] if report.top_level else [])
                secs.append(
                    Section(
                        kind="table",
                        title="Structure and running time",
                        columns=[
                            "Part",
                            "Loops",
                            "Deepest nesting",
                            "Calls itself",
                            "Running time",
                        ],
                        rows=[
                            [
                                u.name,
                                str(u.loops),
                                str(u.max_nesting),
                                str(u.recursive_calls),
                                u.cost.show(),
                            ]
                            for u in units
                        ],
                        origin=origin,
                    )
                )
                rules = [r for u in units for r in u.rules]
                if rules:
                    secs.append(
                        Section(
                            kind="steps", title="Templates that matched", steps=rules, origin=origin
                        )
                    )
                limitations.append(
                    "Running time comes from fixed templates for common patterns; it is "
                    "an estimate for those patterns, not a proof, and n is the input size."
                )
        answer = self._make(p, "E", secs, self._refs(["ds.complexity-big-o"]), [], None, [])
        answer.limitations = limitations
        answer.suggestions = [
            Suggestion(label="Explain Big-O notation", action="ask", query="Explain Big-O notation")
        ]
        return Outcome(answer, Context(concepts=["ds.complexity-big-o"], intent="code"))

    def _advice(self, p: ParsedQuery) -> Outcome:
        if self.student_id is None or self.policy is None:
            return self._abstain(
                p,
                None,
                "To suggest what to study I need your results. Create a profile "
                "and import a marksheet in My Academics first.",
            )
        secs = study_advice(self.session, self.student_id, self.policy)
        answer = self._make(p, "advice", secs, [], ["Using your topic classifications."], None, [])
        answer.suggestions = [
            Suggestion(label=f"Explain {i.text}", action="ask", query=f"Explain {i.text}")
            for s in secs
            if s.kind == "list"
            for i in s.items[:2]
        ]
        return Outcome(answer, Context(intent="study_advice"))

    def _clarify(
        self,
        p: ParsedQuery,
        question: str,
        slugs: list[str],
        decision: list[str] | None = None,
        query_template: str | None = None,
    ) -> Outcome:
        refs = self._refs(slugs)
        template = query_template or "Explain {name}"
        options = [
            Suggestion(
                label=f"{r.name} ({r.topic_name})",
                action="ask",
                query=template.format(name=r.name),
                concept=r.slug,
            )
            for r in refs
        ]
        answer = Answer(
            status="clarify",
            handler="clarify",
            handler_label=HANDLER_LABELS["clarify"],
            intent=p.intent.value,
            concepts=refs,
            clarification=Clarification(question=question, options=options),
            interpretation=p.trace + (decision or []),
        )
        return Outcome(answer, Context(concepts=[], intent=p.intent.value))

    def _abstain(self, p: ParsedQuery, top: SearchHit | None, reason: str | None = None) -> Outcome:
        explicit = reason is not None and p.intent is Intent.STUDY_ADVICE
        if reason is None:
            if p.unmatched:
                reason = (
                    "The knowledge base has nothing about "
                    + ", ".join(f'"{w}"' for w in p.unmatched)
                    + ", so I cannot answer this."
                )
            elif top is not None:
                reason = (
                    "Nothing in the knowledge base matches this question closely enough "
                    "to answer it "
                    f"(best match scored {top.score:.1f}; at least {MIN_SCORE:g} is needed)."
                )
            else:
                reason = "Nothing in the knowledge base matches this question."
        # Closest concepts help only when the question was about content.
        closest = [h for h in p.candidates[:3] if h.score > 0] if not explicit else []
        subjects = sorted(
            {
                s.name
                for s in self.session.scalars(select(Subject).where(Subject.is_custom.is_(False)))
            }
        )
        secs, sugg = abstain(reason, closest, subjects)
        answer = Answer(
            status="abstained",
            handler="F",
            handler_label=HANDLER_LABELS["F"],
            intent=p.intent.value,
            sections=secs,
            interpretation=p.trace,
            missing=reason,
            suggestions=sugg,
        )
        return Outcome(answer, Context())

    # ---------------------------------------------------------------- helpers

    def _resolve(self, p: ParsedQuery, refs: tuple[str, ...]) -> str | None:
        """Pick one meaning of an ambiguous name if the whole question clearly favours it:
        first by subject (other names in the question belong to one meaning's subject),
        then by search score over the whole question."""
        lex = self.lex

        def subjects_of_concept(slug: str) -> set[str]:
            return set(lex.topic_subjects.get(lex.concept_topic.get(slug, ""), []))

        context: set[str] = set()
        for m in p.mentions:
            if m.kind == "concept" and len(m.refs) == 1:
                context |= subjects_of_concept(m.refs[0])
            elif m.kind == "topic":
                context |= set(lex.topic_subjects.get(m.refs[0], []))
            elif m.kind == "subject":
                context |= set(m.refs)
        fitting = [r for r in refs if subjects_of_concept(r) & context]
        if len(fitting) == 1:
            return fitting[0]
        scores = {h.concept.slug: h.score for h in self.index.search(p.corrected, k=50)}
        ranked = sorted(refs, key=lambda r: -scores.get(r, 0.0))
        best, second = scores.get(ranked[0], 0.0), scores.get(ranked[1], 0.0)
        return ranked[0] if best > 0 and second <= AMBIGUITY_RATIO * best * 0.9 else None

    def _plan(
        self, topic_slug: str | None, depth: Depth = Depth.STANDARD
    ) -> tuple[TeachingPlan, Personalisation]:
        cls = self._classification(topic_slug)
        name = self.lex.topic_names.get(topic_slug or "", None)
        plan = plan_for(cls, depth, name)
        return plan, Personalisation(
            topic=topic_slug,
            classification=cls.value if cls else None,
            level=plan.level,
            explanation=plan.reason,
        )

    def _classification(self, topic_slug: str | None) -> MasteryClass | None:
        if self.student_id is None or self.policy is None or topic_slug is None:
            return None
        if self._classes is None:
            rows = load_result_rows(self.session, self.student_id)
            views = compute_topics(
                self.session, self.student_id, self.policy, summarise_subjects(rows, self.policy)
            )
            self._classes = {v.topic.slug: v.classification.label for v in views}
        return self._classes.get(topic_slug)

    def _refs(self, slugs: list[str]) -> list[ConceptRef]:
        out = []
        for s in dict.fromkeys(slugs):
            row = self.session.execute(
                select(Concept, Topic)
                .join(Topic, Concept.topic_id == Topic.id)
                .where(Concept.slug == s, Concept.trust_status.in_(self.allowed))
            ).first()
            if row:
                out.append(ref_of(row[0], row[1]))
        return out

    def _concept_suggestions(self, b: ConceptBundle) -> list[Suggestion]:
        out = [
            Suggestion(label="Simplify this", action="simplify"),
            Suggestion(label="Show a worked example", action="example"),
            Suggestion(label="Test my understanding", action="check"),
            Suggestion(label="Go deeper", action="deeper"),
        ]
        if b.contrasts:
            other = b.contrasts[0].name
            out.append(
                Suggestion(
                    label=f"{b.ref.name} vs {other}",
                    action="ask",
                    query=f"Difference between {b.ref.name} and {other}",
                )
            )
        if b.requires:
            out.append(
                Suggestion(
                    label="What should I learn first?",
                    action="ask",
                    query=f"What should I learn before {b.ref.name}?",
                )
            )
        return out

    def _context_for(self, answer: Answer, topic: str | None, plan: TeachingPlan | None) -> Context:
        steps = [s for sec in answer.sections if sec.kind == "procedure" for s in sec.steps]
        steps += [s for sec in answer.sections if sec.kind == "steps" for s in sec.steps]
        return Context(
            concepts=[c.slug for c in answer.concepts],
            topic=topic,
            intent=answer.intent,
            depth=plan.level if plan else "balanced",
            steps=steps,
        )

    def _make(
        self,
        p: ParsedQuery,
        handler: str,
        secs: list[Section],
        refs: list[ConceptRef],
        decision: list[str],
        pers: Personalisation | None,
        reading: list[Reading],
    ) -> Answer:
        validate(secs)
        trusts = {s.origin.concept: s.origin.trust for s in secs if s.origin.trust is not None}
        unreviewed = sorted(
            {r.slug for r in refs if r.trust is not TrustStatus.VERIFIED}
            | {c for c, t in trusts.items() if c and t is not TrustStatus.VERIFIED}
        )
        uses_knowledge = any(s.origin.kind == "knowledge" for s in secs)
        review = Review(
            all_reviewed=not (unreviewed and uses_knowledge),
            label=UNREVIEWED_LABEL if unreviewed and uses_knowledge else None,
            unreviewed=unreviewed if uses_knowledge else [],
        )
        unique_reading = list({r.title: r for r in reading}.values())
        if pers is not None:
            pers.explanation = f"{pers.explanation} ({POLICY_VERSION})"
        return Answer(
            status="answered",
            handler=handler,
            handler_label=HANDLER_LABELS[handler],
            intent=p.intent.value,
            concepts=refs,
            sections=secs,
            review=review,
            personalisation=pers,
            interpretation=p.trace + decision,
            further_reading=unique_reading,
        )

    def _merge(self, outcomes: list[Outcome], truncated: bool) -> Outcome:
        first = outcomes[0].answer
        secs: list[Section] = []
        for i, o in enumerate(outcomes, 1):
            a = o.answer
            body = a.sections or (
                [
                    Section(
                        kind="note",
                        title=a.clarification.question,
                        items=[Item(text=x.label) for x in a.clarification.options],
                        origin=Origin(kind="template"),
                    )
                ]
                if a.clarification
                else []
            )
            secs.append(
                Section(kind="note", title=f"Part {i}", text=None, origin=Origin(kind="template"))
            )
            secs += body
        concepts = list({c.slug: c for o in outcomes for c in o.answer.concepts}.values())
        unreviewed = sorted({u for o in outcomes for u in o.answer.review.unreviewed})
        merged = Answer(
            status="answered"
            if any(o.answer.status == "answered" for o in outcomes)
            else first.status,
            handler="multi",
            handler_label="Several questions",
            intent="multi-part",
            concepts=concepts,
            sections=secs,
            review=Review(
                all_reviewed=not unreviewed,
                label=UNREVIEWED_LABEL if unreviewed else None,
                unreviewed=unreviewed,
            ),
            interpretation=[f"Split into {len(outcomes)} questions."]
            + [t for o in outcomes for t in o.answer.interpretation],
            suggestions=[s for o in outcomes for s in o.answer.suggestions][:6],
            further_reading=list(
                {r.title: r for o in outcomes for r in o.answer.further_reading}.values()
            ),
            limitations=[x for o in outcomes for x in o.answer.limitations]
            + (["Only the first three questions were answered."] if truncated else []),
        )
        return Outcome(merged, outcomes[-1].context)


class UnbackedSection(AssertionError):
    pass


def validate(sections: list[Section]) -> None:
    """Every section must name where it came from; knowledge sections must name a concept."""
    for s in sections:
        o = s.origin
        if o.kind == "knowledge" and not o.concept and s.kind != "list":
            raise UnbackedSection(
                f"section {s.title!r} claims knowledge-base content without a concept"
            )
        if o.kind == "solver" and not o.solver:
            raise UnbackedSection(f"section {s.title!r} claims a solver without naming it")


def build_engine(
    session: Session,
    lexicon: Lexicon,
    *,
    allow_unreviewed: bool,
    student_id: str | None,
    policy: Policy | None,
) -> Engine:
    return Engine(
        session, lexicon, allow_unreviewed=allow_unreviewed, student_id=student_id, policy=policy
    )
