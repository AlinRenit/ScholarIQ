# Knowledge-base content

Versioned academic content, loaded and validated by the backend on sync.

| Path | What it holds |
| --- | --- |
| `curriculum/` | Curricula: subjects, their aliases and codes, and the topics each covers. |
| `knowledge/<subject>/<topic>.yaml` | Concepts for one topic: definition, key facts, explanations and worked examples, practice questions, links to other concepts, further reading and a review block. |
| `sources.yaml` | Books and RFCs cited as further reading. |
| `eval/retrieval.yaml` | Queries used to measure search quality. |

All explanations and questions were written for ScholarIQ in original wording;
sources are cited for further reading, not quoted.

Rules the loader enforces:

* A topic file must be in the folder of a subject that covers the topic, and be
  named after the topic.
* Concept, question and source slugs are unique; every link and citation must
  point at something that exists; `requires` links may not form a cycle.
* Multiple-choice questions have 2 to 6 distinct options and a valid answer
  index; numeric questions have a value; short-answer questions list accepted
  answers.
* A concept counts as reviewed only when its review block is `verified` and its
  hash matches the current content. Use `python -m scholariq.knowledge.review`
  in `backend/` to produce the block.

Run `python -m scholariq.curriculum.sync` in `backend/` to load changes, and
`python -m scholariq.knowledge.evaluate` to re-measure search.
