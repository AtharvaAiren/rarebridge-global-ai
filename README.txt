RareBridge — research-resource reuse for patient organizations
Updated 4 October 2026

RareBridge helps a patient organization find an existing research resource,
inspect evidence for its particular proposed use, and prepare concrete questions
and a sourced collaboration proposal for an appropriate research partner.

The prototype covers STXBP1-, SYNGAP1- and SCN2A-related disorders and one goal:
preparing a natural-history study, which follows how a condition changes over time.
The assessment unit is the target disease/subgroup, goal, specific resource,
proposed use and conditions for use. Related diseases do not automatically share
suitable resources or treatments. See PROTOTYPE_SCOPE.txt.

CURRENT INTEGRATED STATE
The React/TypeScript frontend, animated research graph, patient/expert modes,
settings, evidence drawer, source hiding/reset, current-state collaboration brief,
AI tools and FastAPI backend are integrated and build successfully. The graph
anchors the selected assessment's resource and retains it when evidence closes.
Genuine Claude extraction, explanation, withdrawn-source explanation and Q&A have
succeeded; matching genuine cache replay is verified. The hidden-source answer
distinguishes the two checks that actually changed from three already unknown.

Public demo: https://rarebridge-global-ai.vercel.app
Anonymous app HTML and JSON API health are verified. Use this stable production
alias for judges. Fresh public discovery/Q&A and 9/9 actual public AI browser
checks passed with live provenance. Public source-excerpt extraction and the
hidden-source explanation also passed. The public release checker passed 11/11;
all five explanation statuses, exact next questions and zero hidden-paper
citations were checked. These are runtime/binding checks, not medical validation.

Verified checks: 115 frontend tests, 129 AI tests, 53 API tests, 27 curation tests
and 11 foundation checks. Production graph browser verification passed 16/16
checks against the real same-origin local API: staged motion, route trace,
pause/zoom, source hiding without layout churn, Citizen resource switching,
drag settling, mobile layout and both reduced-motion settings. See
submission/GRAPH_BROWSER_VERIFICATION.json and frontend/screenshots/integrated-graph-*.
Local product and timing-pilot browser verification also passed 16/16 checks,
with zero page errors or AI requests. See submission/PRODUCT_BROWSER_VERIFICATION.json.
These are checks of product/pilot controls, not actual impact measurements.

Genuine live AI research-lead discovery passed after earlier timeout/output
failures. The final response contains two pending leads: interpretation of a known
route and a proposed research hypothesis. Actual AI browser verification passed
9/9 using genuine cached answers/leads, including source/mode invalidation and
current-state text/PDF export. See submission/research-live-verification/ and
submission/ai-browser-verification/report.json. The timing tool contains no
measured impact results. No measured 10x gain is claimed.

The user-required public HTTPS application is deployed. The stable alias serves
the frontend and real API on one origin; health reports all four AI capabilities.
The final cloud build and source are frozen, with public verification recorded.
Optional human impact measurements and portal upload/submission remain in
submission/REMAINING_BEFORE_SUBMISSION.txt. The separate
60.00-second walkthrough and 2:15.01 team video are produced with real public
product footage and explicitly synthesized narration.

PORTABLE SETUP AND LOCAL PRODUCTION START
Install Python 3.14 and Node 22.18+ in the 22.x line with npm. The local .tools/
runtime and .venv are development installations, not portable deliverables.
Run from the repository/workspace root:

  python3.14 -m venv .venv
  .venv/bin/python -m pip install -r requirements-backend.txt -r requirements-ai.txt
  npm run build
  .venv/bin/python -m uvicorn app:app --host 127.0.0.1 --port 8000

Open http://127.0.0.1:8000. Root npm run build installs locked frontend dependencies
with npm ci and produces frontend/dist/. app.py serves the real API and frontend
on one origin. The recorded graph checks used this combined production setup on
port 18800. Neither localhost address is the final public demo.

For development, start the backend, then run these inside frontend/:

  npm ci
  VITE_API_BASE_URL=http://127.0.0.1:8000 npm run dev

An empty API setting in development explicitly uses saved examples. An empty
production setting, or VITE_API_BASE_URL=/, uses the real same-origin API. Absolute
HTTP(S) API URLs support split hosting with configured backend CORS. Live failures
show errors and Retry; they never substitute demo data. Only public API settings
belong in Vite variables. Provider credentials stay server-side.

OFFLINE CHECKS
After installing dependencies, run from the root:

  .venv/bin/python scripts/check_workspace.py
  .venv/bin/python scripts/check_workspace.py --json
  .venv/bin/python -m unittest discover -s rarebridge -p 'test_assessment.py' -v
  .venv/bin/python -m unittest discover -s rarebridge/ai/tests -p 'test_*.py' -v
  .venv/bin/python -m pytest tests/api -q
  .venv/bin/python -m unittest discover -s curation -p 'test_*.py' -v
  .venv/bin/python curation/validate_overlay.py
  npm --prefix frontend test
  npm --prefix frontend run lint
  npm --prefix frontend run build

The workspace doctor is read-only and does not call a provider or start servers.
A configured key/capability does not prove a successful request. Tests validate
software, evidence bookkeeping and schema/source binding, not biomedical truth.

SOURCE REVIEW AND SCOPED ASSESSMENTS
The curated overlay has 58 review-log rows: 20 supplied human sign-offs preserved
and 38 pending rows. Coverage includes 25 edges, 15 nodes and six contacts. Pending
records stay pending. Source sign-off checks a narrow assertion; it does not grant
consent, access, clinical suitability or approved reuse. Do not rebuild the signed
overlay. The builder refuses to overwrite signed files; generate any new pending
draft only in a fresh --output-dir. See curation/HANDOVER.txt.

The published STARR/ProMMiS framework is documented for STXBP1 and SYNGAP1, with
access/local-fit questions open. Its proposed extension to SCN2A has an unknown
applicability check. SCN2A has its own research resources; unknown fit for this
framework does not mean no SCN2A work exists. The Citizen Health dataset case
exposes governed access requirements and does not grant access to participant data.
Catalogue entries without a matching assessment explicitly remain unassessed.

PMID:42446932 and DOI:10.1002/epi.70374 identify one paper. Hiding either excludes
that canonical source from the current assessment view. Two checks lose support
while the overall result can remain needs_information. Hiding changes a view,
not stored graph records, signatures or biology. Briefs use the same after-state
and list hidden sources. Repeated identifiers are not independent studies, and
a preprint is a separate version from a published paper.

AI PROVIDER, MODEL AND PROVENANCE
The active model is Anthropic Claude Sonnet 4.6, claude-sonnet-4-6. The user reported
organizer approval of Claude credits; retain that approval with the submission.
It is not an independently verified prize-eligibility guarantee. Actual request/
cache results are in submission/AI_VERIFICATION.txt.

Claude is an existing trained general-purpose model. We have not trained a new
knowledge-graph foundation model, fine-tuned Claude or calibrated clinical
probabilities. The graph gives the model source-linked context. New hypotheses
and extracted relationships stay pending/not imported; they cannot rewrite
reviewed evidence or deterministic assessment outcomes.

Copy .env.example to .env if it does not exist and edit it locally:

  cp -n .env.example .env

Supported settings include:

  RAREBRIDGE_AI_PROVIDER=anthropic
  ANTHROPIC_API_KEY=<set locally>
  RAREBRIDGE_AI_MODEL=claude-sonnet-4-6
  RAREBRIDGE_AI_MODE=auto
  RAREBRIDGE_AI_CACHE_DIR=rarebridge/ai/cache
  RAREBRIDGE_AI_TIMEOUT_SECONDS=40
  RAREBRIDGE_AI_MAX_OUTPUT_TOKENS=6000

ANTHROPIC_WORKSPACE_ID is optional for keys requiring a workspace. Exported values
override .env. Do not source an untrusted .env, commit keys, send them to teammates,
expose them in logs or put them in browser configuration. Only the selected
provider's key is needed. Defaults are openai/gpt-4o-mini or anthropic/claude-sonnet-4-6
when the model is omitted. To use OpenAI, select provider openai, set OPENAI_API_KEY
locally and select its model. The earlier Claude workspace-required failure is
resolved in this workspace.

live calls the provider; cache uses an exact matching genuine saved response;
auto uses a matching cache or calls the provider; off disables generation. Genuine
cache identity includes provider/model, source/context and assessment/withdrawal
state. Output is labeled live or cached truthfully. Missing keys, timeouts,
provider/output failures or missing cache matches produce explicit errors; no
successful output is fabricated and paid retries are not automatic. Source-binding
guards restrict references and recorded state; they do not verify scientific truth
or the medical meaning of generated prose. Changed prompts/context invalidate
older cache matches.

HTTP AI TOOLS
POST /api/ai/extract: source_id, title, url, published_on, text. Returns pending
  extraction with import_status=not_imported, not a curated graph mutation.
POST /api/ai/explain: assessment_id, withdrawn_source_ids. Explains this exact view.
POST /api/ai/ask: assessment_id, withdrawn_source_ids, question, mode=patient|expert.
  Answers from the current source-bound assessment context.
POST /api/ai/discover: disease_id, goal_id. Qualified research hypotheses reference
  graph basis edge IDs and sources. Genuine live generation and local browser
  display passed; biological proposals remain pending, not established findings.
GET /api/health: safe capability/configuration booleans, never key values.
AI requests are explicit. The evidence journey remains available without AI;
failures stay visible and are never replaced by a fake successful answer.

AI CLI EXAMPLES
This standard-library component is importable and has a CLI; it is not an HTTP
server. live/auto commands can request paid generation when a key is configured:

  .venv/bin/python -m rarebridge.ai doctor
  .venv/bin/python -m rarebridge.ai extract --source SOURCE_PAYLOAD.json --output EXTRACTION.json --preview PREVIEW.json
  .venv/bin/python -m rarebridge.ai explain --bundle rarebridge/data/assessment-syngap1.json --output EXPLANATION.json
  .venv/bin/python -m rarebridge.ai explain --bundle rarebridge/data/assessment-syngap1.json --withdraw PMID:42446932 --output WITHDRAWN_EXPLANATION.json
  .venv/bin/python -m rarebridge.ai brief --bundle rarebridge/data/assessment-syngap1.json --output BRIEF.json --text-output BRIEF.txt
  .venv/bin/python -m rarebridge.ai smoke --mode cache --output-dir rarebridge/ai/runs/cache-smoke

--mode overrides configuration. smoke exercises extraction, explanation and
withdrawal-specific explanation; cache smoke needs exact genuine responses.
brief is deterministic by default; --with-ai requests model prose. --response PATH
can supply an assessment API response. See rarebridge/ai/INTEGRATION.txt. Release
archives exclude runtime caches and smoke runs; cache smoke requires matching
genuine responses in that environment and is not a keyless fresh-install demo.

PRODUCT AND IMPACT BOUNDARIES
Patient/simple and doctor/expert show the same records at different detail. Settings,
text size and motion preferences work. Contact routes link to public organizations/
investigators. Signup/login is a local-profile preview without cloud authentication.
Booking is a discussion preview, without an appointment or outreach. Brief messages
remain reviewable artifacts; nothing is sent automatically.

Open /impact-pilot.html for the timing tool. It starts with no results. Run two
teammates in reversed order: manual then app, app then manual. Freeze identical
sources/task/fictional constraints; time reading, revisions and six-item quality
review. Retain artifacts, reviewer IDs, failures, raw times and exported CSV/JSON.
See evaluation/README.txt and submission/IMPACT_CASE.txt. A brief-preparation ratio
does not measure expert approval, study launch, treatment or a clinical milestone.

PUBLIC HOSTING AND RELEASE
The Vercel plan uses app.py, app.frontend() static/CDN handling, Python 3.14,
Node 22 and root npm run build. scripts/deploy_vercel.py prepare checks packaging
offline; probe inspects an account/project; configure/deploy require actual Vercel
authentication and server-side secret setup. Deployment cache uses
/tmp/rarebridge-ai-cache. The stable public app is available at
https://rarebridge-global-ai.vercel.app; anonymous HTML/API health passed.
Public discovery/Q&A and its browser withdrawal/reset/current brief/text/PDF
journey passed; public SFARI extraction returned two pending/not-imported claims.
The genuine hidden-source explanation passed with exact recorded status/question
bindings and zero hidden-paper citations. See
submission/public-release-verification/explanation-retest/summary.json. Preserve
actual live/cached labels in public demonstrations; source binding does not
establish the scientific meaning of all generated prose.

DATA REPRODUCTION AND ATTRIBUTION
rarebridge/data/source-manifest.json pins raw YAML and upstream identifiers.
Deliberately regenerate derived foundation files on a clean copy, from the root:

  ruby rarebridge/convert_sources.rb
  .venv/bin/python rarebridge/build_graph.py

These rewrite base derivatives, not the signed overlay, and do not verify biology.
Disease Mechanisms Knowledge Base (DisMech), Monarch Initiative contributors:
https://github.com/monarch-initiative/dismech
Content CC-BY-4.0: https://creativecommons.org/licenses/by/4.0/
Pinned commit: 3426c0eec2ade9297b6aadefe95e5dc7cd3806e6
Raw YAML is unchanged; disorders.json is a conversion; graph.json is a selected
derivative. Imported claims remain pending unless separately source checked.
DisMech is AI curated; valid citations do not establish correctness. Literature/
program pages retain their terms. We store narrow paraphrases/links, not restricted
participant datasets or instruments. The STXBP1/SYNGAP1 anchor is published, not
a RareBridge scientific discovery: https://doi.org/10.1002/epi.70374
Existing patient/researcher measurement collaboration includes Inchstone:
https://inchstoneproject.org/

TEAM AND SUBMISSION
Srinath supplied the frontend; Saanvi owns evidence review; Dhruv owns evaluation/
timing; Atharva and the lead assistant integrate, deploy and assemble submission.
Source repository:
https://github.com/AtharvaAiren/rarebridge-global-ai
Fresh isolated Python 3.14/npm setup passed eight portable startup checks; see
submission/PORTABLE_STARTUP_VERIFICATION.json.
The baseline contract is rarebridge.handoff.v1 in handoffs/contracts/. No lab
repository, GPU, patient records or newly trained checkpoint is required.

Final public end-to-end checks passed and the source repository is published.
Run any actual evaluation/pilot before claiming measured impact. Check portal
fields/limits, upload both produced videos and retain
the submission receipt. Product MP4: submission/walkthrough/RareBridge-60s-walkthrough.mp4
(60.00 seconds). Team MP4: submission/team-video/RareBridge-team-video.mp4 (2:15.01).
Their VIDEO_VERIFICATION.json files record real public footage, truthful credits
and macOS Samantha synthesized narration. Original challenge:
source-notes/global AI PS.txt. Do not claim world-first science, calibrated
probabilities, approved reuse or measured 10x acceleration from these tests.

Release archives exclude runtime caches, smoke runs, frontend/screenshots/ and
private workspace attachments/source-notes. Current accepted provider/browser
reports, their submission captures, both videos, source data, review records and
reproducible setup are included. The original
challenge text at source-notes/global AI PS.txt is workspace-only; the portal's
challenge and included scope documents establish submission context.
