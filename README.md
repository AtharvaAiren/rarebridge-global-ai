# RareBridge

Help a patient organization find a research resource, inspect evidence for its proposed use, and prepare a sourced collaboration proposal with concrete questions for a research partner.

[Open the public demo](https://rarebridge-global-ai.vercel.app) · [Source repository](https://github.com/AtharvaAiren/rarebridge-global-ai)

The prototype covers STXBP1-, SYNGAP1- and SCN2A-related disorders and one goal: preparing a natural-history study, which follows how a condition changes over time. An assessment concerns a particular disease or subgroup, goal, resource, proposed use and conditions for use. Related diseases do not automatically share suitable resources or treatments.

## Try the workflow

1. Choose a condition and a research resource.
2. Read the assessment checks and open their evidence.
3. Hide a source to see which checks depend on it.
4. Prepare a collaboration brief with public research contacts and unresolved questions.
5. Optionally ask the source-bound AI assistant or discover qualified research leads.

The published STARR/ProMMiS framework is documented for STXBP1 and SYNGAP1; access and local-fit questions remain open. Its proposed extension to SCN2A has an unknown applicability check. SCN2A has its own research resources. The Citizen Health dataset example exposes governed access conditions without granting access to participant data.

Patient and doctor/researcher modes show the same records at different detail. Source references remain accessible in both. Account and appointment screens are explicitly local previews; they do not authenticate users, book appointments or send messages.

The interface now uses a white background throughout the page, research map and content panels, including on computers using dark mode. Navy text and stronger graph colours keep labels readable; motion and evidence controls remain available. See the separate [white-interface verification](submission/white-theme-verification/report.json). For your own recordings, the [complete recording guide](submission/SELF_RECORDING_GUIDE.txt) provides a 60-second walkthrough and a four-minute technical demo with exact clicks, spoken text and public-page links.

## Run locally

Use Python **3.14** and Node **22.18+ in the 22.x line**, with npm. From the repository root:

```sh
python3.14 -m venv .venv
.venv/bin/python -m pip install -r requirements-backend.txt -r requirements-ai.txt
npm run build
.venv/bin/python -m uvicorn app:app --host 127.0.0.1 --port 8000
```

Open <http://127.0.0.1:8000>. The build installs locked frontend dependencies and produces the React/TypeScript application. FastAPI serves the frontend and API on one origin.

The graph, assessments, evidence controls and deterministic briefs work without a provider key. A clean isolated copy was installed and built with fresh dependencies and passed eight startup checks, including all four assessment bundles, source withdrawal and preservation of the signed curation log. See [PORTABLE_STARTUP_VERIFICATION.json](submission/PORTABLE_STARTUP_VERIFICATION.json).

For optional AI tools, copy the empty credential template locally and configure your provider:

```sh
cp -n .env.example .env
```

Supported providers are Anthropic and OpenAI. The demonstrated provider is Anthropic Claude Sonnet 4.6. Credentials belong only in server-side configuration. See [README.txt](README.txt) for exact settings, development setup, endpoints and checks. A fresh clone contains no provider credentials or runtime response cache. Missing credentials or failed generation produce explicit unavailable/error states.

## Architecture

The pinned YAML/JSON data snapshot and additive signed overlay feed a [registry](rarebridge/services/registry.py) for search and graph views. [Deterministic resource checks](rarebridge/assessment.py) produce the assessment and recompute it when a source is hidden. The [server-side AI services](rarebridge/ai/) use that bounded context for Claude extraction, research discovery, Q&A and explanation. The [React/TypeScript SVG/d3 interface](frontend/src/features/graph/) displays the graph, checks and evidence, while the [brief assembler](rarebridge/ai/brief.py) exports the current assessment state and collaboration questions. [app.py](app.py) serves the application and FastAPI routes together.

Source/status binding remains controlled by code. AI output cannot change recorded check outcomes; new extractions and hypotheses stay pending without automatic import. Provider keys remain server-side. See [README.txt](README.txt) for the API contracts and reproduction details.

## Evidence and AI boundaries

The overlay contains 58 review-log rows: 20 supplied human sign-offs preserved and 38 pending rows. Coverage includes 25 edges, 15 nodes and six contacts. A source sign-off checks a narrow recorded assertion; it does not grant consent, instrument permission, data access or clinical suitability. **Do not rebuild the signed overlay.** Generate a pending draft in a fresh output directory if needed; see [curation/HANDOVER.txt](curation/HANDOVER.txt).

`PMID:42446932` and `DOI:10.1002/epi.70374` identify one paper. Hiding either excludes the canonical source from the current view. Two checks lose support while the overall assessment can remain `needs_information`. A preprint remains a separate source version. Hiding a source changes the view, not stored records, signatures or biology.

AI uses the current source-linked assessment context. Generated explanations, questions and research leads retain provenance. Extracted relationships and hypotheses stay pending and are not imported into the reviewed graph. Output checks enforce schema, source bindings and current recorded state; they do not verify biomedical truth. RareBridge has not trained a new graph foundation model or calibrated clinical probabilities. See [AI_VERIFICATION.txt](submission/AI_VERIFICATION.txt) and the public verification reports under [submission](submission/).

## Reproduction and attribution

[source-manifest.json](rarebridge/data/source-manifest.json) pins the base source material. The included DisMech data uses upstream commit `3426c0eec2ade9297b6aadefe95e5dc7cd3806e6` and is attributed to the [Disease Mechanisms Knowledge Base / Monarch Initiative contributors](https://github.com/monarch-initiative/dismech), under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Raw YAML is unchanged; the JSON graph is a selected derivative. DisMech is AI curated; citations do not establish correctness.

The published STXBP1/SYNGAP1 framework is an existing research anchor, not a RareBridge scientific discovery: [primary study](https://doi.org/10.1002/epi.70374). Existing patient/researcher measurement collaboration includes the [Inchstone Project](https://inchstoneproject.org/). Literature and program pages retain their terms; the prototype stores narrow paraphrases and links, not restricted participant datasets or instruments.

Deliberate regeneration of the base derivatives on a clean copy uses:

```sh
ruby rarebridge/convert_sources.rb
.venv/bin/python rarebridge/build_graph.py
```

These commands rewrite base derivatives, not the signed overlay. They do not verify biology.

## Submission artifacts and impact measurement

The [submission directory](submission/) contains verification reports, portal text, a [60-second walkthrough](submission/walkthrough/RareBridge-60s-walkthrough.mp4) and a [2:15 team video](submission/team-video/RareBridge-team-video.mp4). These videos are optional backups of the previous navy-graph interface. They use real public product capture and explicitly synthesized narration; their verification metadata records the actual durations and provenance. The user is recording new videos of the current white interface using [SELF_RECORDING_GUIDE.txt](submission/SELF_RECORDING_GUIDE.txt). The [timing pilot](https://rarebridge-global-ai.vercel.app/impact-pilot.html) starts with no results. It compares matched manual/app brief-preparation tasks using the same source pack and quality review; see [evaluation/README.txt](evaluation/README.txt). No measured 10× gain, expert approval, launched study or treatment improvement is claimed.

`scripts/package_release.py` builds a source archive from an explicit allowlist. The separately generated `submission/RELEASE_ARCHIVE.json` records its SHA-256 and integrity check; it is excluded from the archive to avoid self-reference. Packaging excludes credentials, private attachments, runtime caches, dependencies, local tooling, builds and screenshots. Public verification reports document actual checks; packaging itself does not rerun a cloud deployment.
