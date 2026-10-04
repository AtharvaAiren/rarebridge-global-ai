RareBridge — integrated data, assessment and AI components
Updated 4 October 2026

These components run behind the integrated FastAPI/React app. Search, the research
graph, scoped assessments, source hide/reset, briefs and Claude tools are built.
Public demo: https://rarebridge-global-ai.vercel.app. Anonymous HTML/API health
are verified; public discovery/Q&A and its 9/9 live browser journey passed.
Public extraction and hidden-source explanation also passed; the public release
checker passed 11/11 runtime/binding checks. See the root README.txt.

SCOPE AND MODEL
Three conditions: STXBP1-, SYNGAP1- and SCN2A-related disorders. One goal: preparing
a natural-history study. The unit is (target/subgroup, goal, resource, proposed use,
required checks). Disease similarity is not resource transferability. Four scoped
assessments cover the published STARR/ProMMiS framework and SYNGAP1 Citizen Health
dataset access case; other catalogue resources remain explicitly unassessed when
no matching bundle exists.

The active AI is the existing trained Claude Sonnet 4.6 model, claude-sonnet-4-6,
using source-linked local records. No graph foundation model has been trained,
Claude is not fine-tuned here, and scores are not clinical probabilities. Schema/
source binding constrains references/state, not medical truth or applicability.

LOCAL RUN AND CHECKS
Use Python 3.14 and Node 22.18+ in the 22.x line for the integrated app.
Run from the Global AI workspace/repository root:

  python3.14 -m venv .venv
  .venv/bin/python -m pip install -r requirements-backend.txt -r requirements-ai.txt
  npm run build
  .venv/bin/python -m uvicorn app:app --host 127.0.0.1 --port 8000

Open http://127.0.0.1:8000 for the real same-origin production build. AI transport
uses standard-library REST, without a provider SDK. Keys belong only in local/
server configuration. .tools/.venv are development installs, not shipped runtimes.

  .venv/bin/python scripts/check_workspace.py
  .venv/bin/python rarebridge/assessment.py rarebridge/data/assessment-syngap1.json
  .venv/bin/python rarebridge/assessment.py rarebridge/data/assessment-scn2a.json
  .venv/bin/python rarebridge/assessment.py rarebridge/data/assessment-syngap1.json --withdraw PMID:42446932
  .venv/bin/python -m unittest discover -s rarebridge -p 'test_assessment.py' -v
  .venv/bin/python -m unittest discover -s rarebridge/ai/tests -p 'test_*.py' -v
  .venv/bin/python -m pytest tests/api -q
  .venv/bin/python -m unittest discover -s curation -p 'test_*.py' -v
  .venv/bin/python curation/validate_overlay.py
  npm --prefix frontend test
  npm --prefix frontend run build

Verified: 11 foundation checks, 129 AI tests, 53 API tests, 27 curation tests,
115 frontend tests, 16 graph browser checks and 16 product/pilot browser checks.
Both browser reports used the integrated local production app. These establish
software behavior, not biomedical validity. Genuine Claude extraction, explanation,
withdrawn-source explanation and Q&A succeeded; genuine cache replay is verified.
Genuine live research-lead discovery passed with two pending hypotheses; 9/9 local
AI browser checks passed using genuine cached answers/leads. Actual results:
submission/AI_VERIFICATION.txt, submission/research-live-verification/summary.json,
submission/ai-browser-verification/report.json and graph/product browser reports.

COMPONENTS AND DATA
  data/raw/: unchanged YAML pinned by data/source-manifest.json.
  data/disorders.json: format conversion of the three records.
  data/graph.json: selected disease, gene, phenotype, mechanism, publication,
    evidence and resource derivative. Coverage is explicit.
  data/assessment-*.json: manually scoped framework demonstrations, separate from
    candidate ranking; narrow publication facts source checked.
  assessment.py: deterministic checks, outcomes and canonical source withdrawal.
  api/: search, overview, graph, assessment, source and AI HTTP endpoints.
  services/: registry, graph/search, assessment and AI/research bridges.
  ai/: provider calls, genuine request-bound cache, CLI, brief drafting and research
    assistance. New hypotheses/extractions stay pending/not imported.
  ../curation/atlas-overlay.json: additive resources, contacts, assessments/reviews.
    58 review rows: 20 preserved human sign-offs, 38 pending; coverage spans
    25 edges, 15 nodes and six contacts.

Imported claims remain pending unless separately checked. A source check concerns
a narrow assertion, not clinical approval, access permission or validated reuse.
Never rebuild the signed overlay; generate pending drafts in fresh output folders.

ASSESSMENT AND SOURCE CONTRACT
DOI:10.1002/epi.70374 and PMID:42446932 identify one published paper. Multiple claims/
IDs are not independent studies; a preprint is a different version. Hiding a source
excludes its canonical appearances in the current view without erasing records/
signatures. Briefs use the same after-state and list exclusions.

Checks include scoped question, required flag, polarity, source-review status,
rationale, next question and contact role. Hiding the anchor changes two checks
while the overall result can stay needs_information. An already-unknown check is
not counted as newly changed in the AI comparison.

Outcomes:
  candidate_for_expert_review: required factual checks have recorded support.
  needs_information: a required check lacks decisive reviewed evidence.
  needs_source_review: evidence has not been source checked.
  needs_expert_review: required evidence conflicts.
  not_supported_for_stated_use: a required check has reviewed refuting evidence.
Unknown differs from refuted. No outcome automatically approves reuse.

AI HTTP INTERFACE
  POST /api/ai/extract: source_id, title, url, published_on, text. Pending extraction;
    import_status=not_imported.
  POST /api/ai/explain: assessment_id, withdrawn_source_ids. This exact view.
  POST /api/ai/ask: assessment_id, withdrawn_source_ids, question, mode=patient|expert.
  POST /api/ai/discover: disease_id, goal_id. Qualified hypotheses with recorded
    basis edges/sources; never automatically promoted into graph evidence.

Requests label genuine live/cached output and return explicit missing-key, timeout,
provider/output or missing-cache errors. No fake successes or automatic paid retries.
Configured capability booleans do not prove a successful request. Source-bound model
prose is not scientific verification; deterministic evidence remains usable without AI.

REPRODUCTION AND ATTRIBUTION
Deliberately regenerate base derivatives on a clean copy, from the root:

  ruby rarebridge/convert_sources.rb
  .venv/bin/python rarebridge/build_graph.py

This rewrites foundation files, not the signed overlay. The manifest records
upstream paths/commit identifiers; conversion does not verify biology.
Disease Mechanisms Knowledge Base (DisMech), Monarch Initiative contributors:
https://github.com/monarch-initiative/dismech
Content CC-BY-4.0: https://creativecommons.org/licenses/by/4.0/
Pinned commit: 3426c0eec2ade9297b6aadefe95e5dc7cd3806e6
Raw YAML unchanged; JSON is a conversion; graph is a selected derivative. DisMech
is AI curated. Literature/databases retain their terms; narrow paraphrases/links
are stored, not restricted datasets, instruments or participant information.

LIMITS AND REMAINING WORK
The STXBP1/SYNGAP1 anchor is already published: https://doi.org/10.1002/epi.70374.
It validates a workflow, not a new scientific discovery. Proposed SCN2A fit remains
unknown; this does not deny its own research resources. Access, cohort fit, current
availability and proposed reuse require appropriate partner/expert review. No
calibrated compatibility or clinical benefit is established. The optional lab
adapter/checkpoint has not been integrated.

The final build/source freeze, any actual impact measurements and portal submission
remain release checks. Both public-footage videos
are produced: the separate 60.00-second walkthrough and 2:15.01 team video, with
explicit synthetic narration. Clean portable startup passed eight isolated
Python 3.14/npm checks.
/impact-pilot.html is an empty measurement tool: run actual quality-controlled
manual/app comparisons before reporting numbers. No measured 10x effect is claimed.

Runtime caches, historical smoke runs, frontend/screenshots/ and private workspace
source notes are excluded from release archives. Included current reports, their
submission captures and both videos preserve actual provenance. A fresh
environment needs matching genuine cache or a configured provider for generation.
