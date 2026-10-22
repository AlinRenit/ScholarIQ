# Performance measurements

Measured 2026-10-22 with `backend/benchmarks/run.py` (3 run(s), median shown).

* Machine: x86_64, 4 CPU(s), Linux 6.18.44-fc-v140
* Python 3.12.3, SQLite database, outbound network blocked
* In-process through the FastAPI app: includes validation, database access and serialisation; excludes the network hop and the web front end.

| Operation | Time (ms) |
| --- | ---: |
| migrate (empty database) | 187 |
| load curriculum | 79 |
| parse and validate knowledge files | 631 |
| sync knowledge base into database | 655 |
| build retrieval index (BM25) | 70 |
| app start-up (builds index and tutor vocabulary) | 284 |
| import digital PDF marksheet | 93 |
| import scanned marksheet (Tesseract OCR) | 314 |
| confirm results | 51 |
| dashboard analysis | 23 |
| topic classification (all topics) | 33 |
| add a topic test result | 33 |
| first tutor answer | 65 |
| start a diagnostic quiz | 25 |
| submit and mark a quiz | 56 |
| build study plan | 56 |
| knowledge-base search | 11 |
| delete all of a student's data | 26 |

Tutor answers over the 60 gold-standard questions (index already built), 180 answers in total:

| p50 | p95 | max |
| ---: | ---: | ---: |
| 26 ms | 36 ms | 44 ms |

Notes:

* The retrieval index and the tutor's vocabulary are built when the API starts (`SCHOLARIQ_WARM_CACHES_ON_START`, on by default), so the first question is as fast as the rest. Without it the first question after a restart took about 320 ms on this machine.
* Loading content (parse, validate, sync) runs once per deployment or content change, not per request.
* OCR time depends on the scan: the sample is one page. Large scanned PDFs (up to 20 pages) take several seconds, during the upload request.
