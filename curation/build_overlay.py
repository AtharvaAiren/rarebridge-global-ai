"""Build curation/atlas-overlay.json and curation/source-review-log.json.

Every record here was drafted from public sources read on CHECK_DATE.
All review_status values are 'pending': an AI assistant read the sources,
and no person has confirmed the assertions yet. A person promotes a record
to 'source_checked' only after reading the cited location themselves
(see HANDOVER.txt, "How to sign off").

Run from the repository root: python3 curation/build_overlay.py --output-dir /tmp/rarebridge-curation
Regeneration refuses to overwrite any target file containing a human sign-off.
Use derive_missing_review_rows(existing_overlay) for append-only coverage repair.
"""

import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path

CHECK_DATE = "2026-10-04"
REVIEWER = "AI pre-check (Claude) for Saanvi; awaiting human confirmation"
PENDING_LABEL = "Unassessed — source review pending"
OUT = Path(__file__).resolve().parent

STXBP1 = "MONDO:0012812"
SYNGAP1 = "MONDO:0012960"
PAPER = "DOI:10.1002/epi.70374"          # published Epilepsia article (canonical)
PREPRINT = "DOI:10.64898/2026.01.30.26344887"  # medRxiv v1 that we actually read
FRAMEWORK = "DOI:10.1002/epi.70374#framework"   # same asset ID as the base SYNGAP1 bundle

# ---------------------------------------------------------------- sources
# The PAPER entry is copied verbatim from rarebridge/data/assessment-syngap1.json
# so the integrated source registry never sees two different definitions.
SOURCES = {
    PAPER: {
        "title": "A prospective natural history study protocol for clinical trial readiness in synaptic disorders",
        "url": "https://doi.org/10.1002/epi.70374",
        "aliases": ["PMID:42446932"],
        "published_on": "2026-07-14",
        "source_kind": "human_observational_study",
        "note": "One paper, regardless of the number of claims or identifiers. Source checked for the narrow facts below; applicability still needs scientific review.",
    },
    PREPRINT: {
        "title": "A Prospective Natural History Study Protocol for Clinical Trial Readiness in Synaptic Disorders (medRxiv preprint v1)",
        "url": "https://www.medrxiv.org/content/10.64898/2026.01.30.26344887v1.full.pdf",
        "aliases": [],
        "published_on": "2026-02-02",
        "source_kind": "preprint",
        "note": "Earlier, not peer-reviewed version of DOI:10.1002/epi.70374. It is the text we could read; the published version was not accessed. It is NOT independent evidence: claims cite the published paper and the review log records that the preprint wording was read. Wording or numbers may differ in the published version.",
        "version_of": PAPER,
    },
    "WEB:stxbp1-foundation-starr": {
        "title": "STARR study page, STXBP1 Foundation",
        "url": "https://www.stxbp1disorders.org/starr",
        "aliases": [],
        "published_on": None,
        "source_kind": "organization_webpage",
        "note": f"Official STXBP1 Foundation page; undated. Read on {CHECK_DATE}. Current-status statements are only as current as the page.",
    },
    "WEB:stxbp1-foundation-home": {
        "title": "STXBP1 Foundation home page",
        "url": "https://www.stxbp1disorders.org/",
        "aliases": [],
        "published_on": None,
        "source_kind": "organization_webpage",
        "note": f"Read on {CHECK_DATE}. Lists a 30 Sep 2026 news item on STARR continuing through June 2028; the item itself could not be opened (HTTP 429).",
    },
    "WEB:curesyngap1-prommis-blog": {
        "title": "Four Stories, One Purpose: Our Visits to CHOP (CURE SYNGAP1 blog)",
        "url": "https://curesyngap1.org/blog/four-stories-one-purpose-syngap1-visits-to-chop/",
        "aliases": [],
        "published_on": "2026-03-26",
        "source_kind": "organization_webpage",
        "note": f"Official CURE SYNGAP1 blog post describing ProMMiS sites and how families register. Read on {CHECK_DATE}.",
    },
    "WEB:curesyngap1-request-nhs-data": {
        "title": "Request Citizen Health Natural History Study (NHS) Data, CURE SYNGAP1",
        "url": "https://curesyngap1.org/request-nhs-data/",
        "aliases": [],
        "published_on": "2023-03-01",
        "source_kind": "organization_webpage",
        "note": f"Page metadata says last modified 2025-10-31. Read on {CHECK_DATE}. Describes researcher access to a SYNGAP1 retrospective dataset.",
    },
    "WEB:endd-natural-history-study": {
        "title": "Natural History Study, ENDD Center (Penn Medicine / CHOP)",
        "url": "https://endd.med.upenn.edu/research/natural-history-study/",
        "aliases": [],
        "published_on": None,
        "source_kind": "institution_webpage",
        "note": f"Study team page for the STXBP1 and SYNGAP1 natural history studies. Read via search snippet on {CHECK_DATE}; full page not opened.",
    },
    "WEB:stanford-synaptopathy-research": {
        "title": "Synaptopathy Research and Innovation, Stanford Medicine Children's Health",
        "url": "https://www.stanfordchildrens.org/en/services/synaptopathy/research-innovation.html",
        "aliases": [],
        "published_on": None,
        "source_kind": "institution_webpage",
        "note": f"Read via search snippet on {CHECK_DATE}. Spells the SYNGAP1 study 'PRoMiSS'; the paper and CURE SYNGAP1 use 'ProMMiS'.",
    },
    "WEB:globalgenes-rarex-stxbp1-2024": {
        "title": "Global Genes and STXBP1 Foundation partnership to use RARE-X for the natural history study (press release)",
        "url": "https://globalgenes.org/press/global-genes-and-stxbp1-foundation-enter-partnership-to-use-rare-x-research-and-data-collection-platform-for-natural-history-study/",
        "aliases": [],
        "published_on": "2024-07-24",
        "source_kind": "press_release",
        "note": f"Read via search snippet on {CHECK_DATE}.",
    },
}

def edge(eid, source, target, relation, source_ids, explanation, origin="recorded", url=None):
    return {
        "id": eid, "source": source, "target": target, "relation": relation,
        "provenance": {"source_url": url or SOURCES[source_ids[0]]["url"], "retrieved_on": CHECK_DATE,
                       "curation_lane": "curation/build_overlay.py"},
        "review_status": "pending", "source_ids": source_ids,
        "confidence_label": PENDING_LABEL, "explanation": explanation, "claim_origin": origin,
    }

# ---------------------------------------------------------------- nodes
NODES = [
    {"id": PAPER, "type": "publication", "label": SOURCES[PAPER]["title"], "url": SOURCES[PAPER]["url"],
     "aliases": ["PMID:42446932"], "review_status": "pending"},
    {"id": "study:starr", "type": "study", "label": "STARR natural history study (STXBP1-RD)",
     "aliases": ["STXBP1 Clinical Trial Ready", "STARR"], "registry_ids_reported": ["NCT06555965"],
     "registry_note": "NCT ID is reported by the STXBP1 Foundation STARR page; the registry record itself was not machine-readable in our check.",
     "review_status": "pending"},
    {"id": "study:prommis", "type": "study", "label": "ProMMiS natural history study (SYNGAP1-RD)",
     "aliases": ["ProMMiS", "PRoMiSS"], "review_status": "pending"},
]

# ---------------------------------------------------------------- assets
ASSETS = [
    {"id": FRAMEWORK, "label": "STARR / ProMMiS natural-history framework", "type": "published_study_framework",
     "url": "https://doi.org/10.1002/epi.70374",
     "access_status": "Published description only. Permission to adopt the protocol, its instrument licences and staff/equipment needs are not checked.",
     "description": "Multi-site prospective natural history protocol for STXBP1-RD (STARR) and SYNGAP1-RD (ProMMiS): clinician-administered developmental measures, caregiver-reported measures, seizure-history reconstruction and quantitative EEG, with CHOP as prime site and data coordinating centre.",
     "goal_ids": ["natural_history"], "target_disease_ids": [STXBP1, SYNGAP1], "source_ids": [PAPER],
     "owner_status": "Study team documented (CHOP-led consortium). Ownership of protocol materials not established.",
     "proposed_use": "A patient organization planning a natural history study reviews which framework components could inform its own protocol.",
     "documented_context": "Studied in STXBP1-RD and SYNGAP1-RD cohorts only. The authors state an aim to generalize the framework to other DEEs; that extension is not demonstrated in this paper.",
     "unverified": ["instrument licensing", "protocol document access", "fit for other diseases or age ranges", "site capacity"],
     "public_researcher_routes": [
         {"name": "STARR study team via STXBP1 Foundation STARR page", "url": "https://www.stxbp1disorders.org/starr"},
         {"name": "ENDD Center natural history study page (CHOP / Penn)", "url": "https://endd.med.upenn.edu/research/natural-history-study/"}]},
    {"id": "asset:seizure-history-reconstruction", "label": "Medical-record seizure history reconstruction method",
     "type": "measurement_method", "url": "https://doi.org/10.1002/epi.70374",
     "access_status": "Method described in the paper and earlier cited work. Coding manual or templates not checked.",
     "description": "Month-by-month seizure type and frequency reconstructed from medical records and family interviews, seizure types coded with HPO terms and frequency mapped to the PELHS scale, with two extra levels added for very high SYNGAP1 seizure frequency.",
     "goal_ids": ["natural_history"], "target_disease_ids": [STXBP1, SYNGAP1], "source_ids": [PAPER],
     "owner_status": "Developed and applied by the CHOP/ENDD team per the paper; no public toolkit confirmed.",
     "proposed_use": "Collect seizure history with less family burden than daily diaries when planning a natural history study.",
     "documented_context": "Applied to 107 STXBP1-RD and 100 SYNGAP1-RD individuals in the preliminary analysis (preprint figures). The paper notes many seizures are uncountable, which limits seizure counts as trial endpoints.",
     "unverified": ["availability of coding templates", "training needed", "validity outside these cohorts"]},
    {"id": "asset:starr-prommis-qeeg-protocol", "label": "Quantitative EEG acquisition protocol (resting state, VEP, AEP)",
     "type": "biomarker_acquisition_protocol", "url": "https://doi.org/10.1002/epi.70374",
     "access_status": "Acquisition settings described in the paper. Analysis pipeline code availability not checked.",
     "description": "128-channel resting EEG with visual and auditory evoked potentials every 6 months, artifact removal by automated ICA and spectral analysis.",
     "goal_ids": ["natural_history"], "target_disease_ids": [STXBP1, SYNGAP1], "source_ids": [PAPER],
     "owner_status": "CHOP/ENDD study team per the paper.",
     "proposed_use": "Plan exploratory EEG biomarker collection alongside clinical outcome measures.",
     "documented_context": "The paper calls biomarker work an initial, exploratory step; evoked-potential results are not reported there. Not a validated endpoint.",
     "unverified": ["equipment requirements at other sites", "pipeline availability", "biomarker validity"]},
    {"id": "asset:curesyngap1-citizen-nhs-dataset", "label": "SYNGAP1 retrospective medical-record dataset (Citizen Health, via CURE SYNGAP1)",
     "type": "dataset", "url": "https://curesyngap1.org/request-nhs-data/",
     "access_status": "Documented access route for academic researchers: Researcher Agreement with Citizen Health plus an IRB submission. Access for a patient organization without an academic partner is not stated.",
     "description": "De-identified, standardized summaries of participating patients' medical records, including genetic and EEG results; the page states data for over 100 patients with a confirmed P/LP SYNGAP1 diagnosis.",
     "goal_ids": ["natural_history"], "target_disease_ids": [SYNGAP1], "source_ids": ["WEB:curesyngap1-request-nhs-data"],
     "owner_status": "Offered by CURE SYNGAP1 and Citizen Health per their page.",
     "proposed_use": "Retrospective baseline data to inform which outcomes a prospective SYNGAP1 study should measure.",
     "documented_context": "Retrospective, record-derived data; not a prospective protocol. Patient count is as stated on the page, not independently checked.",
     "unverified": ["current patient count", "eligibility of non-academic requesters", "data fields relevant to the chosen outcomes"],
     "public_researcher_routes": [{"name": "CURE SYNGAP1 data request page", "url": "https://curesyngap1.org/request-nhs-data/"}]},
    {"id": "asset:simons-searchlight-prom-data", "label": "Simons Searchlight retrospective caregiver-reported data (STXBP1, SYNGAP1)",
     "type": "registry_dataset", "url": "https://doi.org/10.1002/epi.70374",
     "access_status": "Use reported in the paper only. Access conditions not checked; Simons Searchlight's own pages not reviewed.",
     "description": "The paper combined existing Simons Searchlight data (STXBP1 n=67, SYNGAP1 n=39 in the preprint) with prospective RARE-X data to check feasibility of caregiver-reported measures such as the Vineland-3.",
     "goal_ids": ["natural_history"], "target_disease_ids": [STXBP1, SYNGAP1], "source_ids": [PAPER],
     "owner_status": "Simons Searchlight (registry operator); not confirmed from the operator's own pages.",
     "proposed_use": "Comparison data for planning caregiver-reported outcome measures.",
     "documented_context": "Counts come from the preprint text and may differ in the published version.",
     "unverified": ["access process", "current data volume", "permitted uses"]},
    {"id": "asset:rare-x-prom-collection", "label": "RARE-X caregiver-reported outcome collection (used by STARR/ProMMiS)",
     "type": "data_collection_platform", "url": "https://doi.org/10.1002/epi.70374",
     "access_status": "Paper states PROMs moved to RARE-X from year two once licensing agreements were finalized. Terms for another organization not checked.",
     "description": "Third-party platform through which the studies administer parent-reported outcome measures; a 2024 press release describes the STXBP1 Foundation partnership with Global Genes for STARR.",
     "goal_ids": ["natural_history"], "target_disease_ids": [STXBP1, SYNGAP1], "source_ids": [PAPER, "WEB:globalgenes-rarex-stxbp1-2024"],
     "owner_status": "Global Genes (RARE-X) per press release.",
     "proposed_use": "Remote collection of caregiver-reported measures for a new natural history study.",
     "documented_context": "The paper reports variable caregiver completion rates despite support.",
     "unverified": ["licensing cost and terms", "which instruments are licensed on the platform"]},
]

# ---------------------------------------------------------------- contacts
CONTACTS = [
    {"id": "org:stxbp1-foundation", "label": "STXBP1 Foundation", "kind": "organization",
     "url": "https://www.stxbp1disorders.org/starr",
     "role": "Parent-led patient organization; funds STARR and co-selected its outcome measures. The STARR page lists a research inbox for study questions.",
     "source_ids": ["WEB:stxbp1-foundation-starr", PAPER], "review_status": "pending", "last_checked": CHECK_DATE,
     "disease_ids": [STXBP1]},
    {"id": "org:cure-syngap1", "label": "CURE SYNGAP1", "kind": "organization",
     "url": "https://curesyngap1.org/contact/",
     "role": "Patient organization; supports ProMMiS and co-selected its outcome measures; runs a researcher data-request route for a retrospective SYNGAP1 dataset.",
     "source_ids": ["WEB:curesyngap1-prommis-blog", "WEB:curesyngap1-request-nhs-data", PAPER],
     "review_status": "pending", "last_checked": CHECK_DATE, "disease_ids": [SYNGAP1]},
    {"id": "team:chop-endd-nhs", "label": "CHOP / Penn ENDD natural history study team", "kind": "study_team",
     "url": "https://endd.med.upenn.edu/research/natural-history-study/",
     "role": "Prime site and data coordinating centre for STARR and ProMMiS per the paper; the ENDD page gives a study contact route.",
     "source_ids": [PAPER, "WEB:endd-natural-history-study"], "review_status": "pending", "last_checked": CHECK_DATE,
     "disease_ids": [STXBP1, SYNGAP1]},
    {"id": "researcher:ingo-helbig", "label": "Ingo Helbig, MD", "kind": "researcher",
     "url": "https://www.stxbp1disorders.org/starr",
     "role": "Corresponding author of the framework paper; named multi-site PI of STARR on the foundation page. A potential collaborator, not the confirmed owner of protocol materials.",
     "source_ids": [PAPER, "WEB:stxbp1-foundation-starr"], "review_status": "pending", "last_checked": CHECK_DATE,
     "disease_ids": [STXBP1, SYNGAP1]},
    {"id": "researcher:jillian-mckee", "label": "Jillian L. McKee, MD, PhD", "kind": "researcher",
     "url": "https://doi.org/10.1002/epi.70374",
     "role": "Corresponding (first) author of the framework paper. A potential collaborator.",
     "source_ids": [PAPER], "review_status": "pending", "last_checked": CHECK_DATE,
     "disease_ids": [STXBP1, SYNGAP1]},
    {"id": "team:stanford-synaptopathy", "label": "Stanford Medicine Children's Health synaptopathy team", "kind": "study_team",
     "url": "https://www.stanfordchildrens.org/en/services/synaptopathy/research-innovation.html",
     "role": "Study site for STARR and ProMMiS per the paper and its own page.",
     "source_ids": [PAPER, "WEB:stanford-synaptopathy-research"], "review_status": "pending", "last_checked": CHECK_DATE,
     "disease_ids": [STXBP1, SYNGAP1]},
]

# Every asset and contact is also a graph node so edges have real endpoints.
for _a in ASSETS:
    NODES.append({"id": _a["id"], "type": "asset", "label": _a["label"], "asset_type": _a["type"],
                  "url": _a["url"], "review_status": "pending"})
for _c in CONTACTS:
    NODES.append({"id": _c["id"], "type": _c["kind"], "label": _c["label"], "url": _c["url"],
                  "review_status": "pending"})

# ---------------------------------------------------------------- edges
EDGES = [
    edge("edge:overlay:paper-describes-starr", PAPER, "study:starr", "describes_study", [PAPER],
         "The paper describes the STARR protocol for STXBP1-RD (Methods, Study Organization & Management)."),
    edge("edge:overlay:paper-describes-prommis", PAPER, "study:prommis", "describes_study", [PAPER],
         "The paper describes the ProMMiS protocol for SYNGAP1-RD (Methods, Study Organization & Management)."),
    edge("edge:overlay:stxbp1-studied-in-starr", STXBP1, "study:starr", "studied_in", [PAPER],
         "STXBP1-RD participants are enrolled in STARR (164 enrolled per preprint Recruitment section)."),
    edge("edge:overlay:syngap1-studied-in-prommis", SYNGAP1, "study:prommis", "studied_in", [PAPER],
         "SYNGAP1-RD participants are enrolled in ProMMiS (159 enrolled per preprint Recruitment section)."),
    edge("edge:overlay:framework-covers-starr", FRAMEWORK, "study:starr", "framework_used_by", [PAPER],
         "One published framework covers both studies."),
    edge("edge:overlay:framework-covers-prommis", FRAMEWORK, "study:prommis", "framework_used_by", [PAPER],
         "One published framework covers both studies."),
    edge("edge:overlay:syngap1-stxbp1-shared-framework", SYNGAP1, STXBP1, "shares_published_study_framework_with", [PAPER],
         "Inferred connection for navigation: both diseases have cohorts in the same published natural-history framework. "
         "This is a shared study method, not shared biology, treatment response or proof that results transfer; the paper reports disease-specific developmental and seizure patterns.",
         origin="inferred"),
    edge("edge:overlay:stxbp1-foundation-partners-starr", "org:stxbp1-foundation", "study:starr", "partners_on_study",
         ["WEB:stxbp1-foundation-starr", PAPER],
         "Foundation page says STARR is funded by the STXBP1 Foundation; the paper says outcome measures were selected with the foundation."),
    edge("edge:overlay:cure-syngap1-partners-prommis", "org:cure-syngap1", "study:prommis", "partners_on_study",
         ["WEB:curesyngap1-prommis-blog", PAPER],
         "CURE SYNGAP1 describes ProMMiS as powered by CURE SYNGAP1; the paper says outcome measures were selected with CURE SYNGAP1."),
    edge("edge:overlay:endd-coordinates-starr", "team:chop-endd-nhs", "study:starr", "coordinates_study", [PAPER],
         "CHOP is the prime site and data coordinating centre (paper Methods)."),
    edge("edge:overlay:endd-coordinates-prommis", "team:chop-endd-nhs", "study:prommis", "coordinates_study", [PAPER],
         "CHOP is the prime site and data coordinating centre (paper Methods)."),
    edge("edge:overlay:helbig-leads-starr", "researcher:ingo-helbig", "study:starr", "leads_study",
         ["WEB:stxbp1-foundation-starr"], "Foundation page names him multi-site Principal Investigator of STARR."),
    edge("edge:overlay:mckee-authors-paper", "researcher:jillian-mckee", PAPER, "corresponding_author_of", [PAPER],
         "Listed as corresponding author on the preprint title page."),
    edge("edge:overlay:helbig-authors-paper", "researcher:ingo-helbig", PAPER, "corresponding_author_of", [PAPER],
         "Listed as corresponding author on the preprint title page."),
    edge("edge:overlay:stanford-site-starr", "team:stanford-synaptopathy", "study:starr", "study_site_for",
         [PAPER, "WEB:stanford-synaptopathy-research"], "Listed as a STARR site in the paper and on its own page."),
    edge("edge:overlay:stanford-site-prommis", "team:stanford-synaptopathy", "study:prommis", "study_site_for",
         [PAPER, "WEB:stanford-synaptopathy-research"], "Listed as a ProMMiS site in the paper and on its own page (spelled PRoMiSS there)."),
    edge("edge:overlay:seizure-method-used-starr", "asset:seizure-history-reconstruction", "study:starr", "method_used_in", [PAPER],
         "Seizure history reconstruction is part of the protocol (Methods)."),
    edge("edge:overlay:seizure-method-used-prommis", "asset:seizure-history-reconstruction", "study:prommis", "method_used_in", [PAPER],
         "Seizure history reconstruction is part of the protocol; expanded PELHS scale added for SYNGAP1."),
    edge("edge:overlay:qeeg-used-starr", "asset:starr-prommis-qeeg-protocol", "study:starr", "method_used_in", [PAPER],
         "Quantitative EEG is collected every 6 months (Methods; Discussion)."),
    edge("edge:overlay:qeeg-used-prommis", "asset:starr-prommis-qeeg-protocol", "study:prommis", "method_used_in", [PAPER],
         "Quantitative EEG is collected every 6 months (Methods; Discussion)."),
    edge("edge:overlay:citizen-dataset-covers-syngap1", "asset:curesyngap1-citizen-nhs-dataset", SYNGAP1, "dataset_covers_disease",
         ["WEB:curesyngap1-request-nhs-data"], "The data request page describes SYNGAP1 patient records available to researchers."),
    edge("edge:overlay:cure-syngap1-offers-citizen-dataset", "org:cure-syngap1", "asset:curesyngap1-citizen-nhs-dataset", "provides_access_route_to",
         ["WEB:curesyngap1-request-nhs-data"], "The page invites academic researchers to request access via agreement and IRB."),
    edge("edge:overlay:searchlight-used-by-paper", "asset:simons-searchlight-prom-data", PAPER, "used_as_comparison_data_in", [PAPER],
         "The paper combined Simons Searchlight data with prospective data (Preliminary Results)."),
    edge("edge:overlay:rarex-used-starr", "asset:rare-x-prom-collection", "study:starr", "platform_used_in",
         [PAPER, "WEB:globalgenes-rarex-stxbp1-2024"], "PROMs are administered through RARE-X (paper Methods; 2024 press release)."),
    edge("edge:overlay:rarex-used-prommis", "asset:rare-x-prom-collection", "study:prommis", "platform_used_in", [PAPER],
         "The paper states PROMs for the natural history study are administered through RARE-X."),
]

# ---------------------------------------------------------------- bundles
def ev(source_id, polarity, rationale, evidence_type="human_observational"):
    return {"source_id": source_id, "polarity": polarity, "review_status": "pending",
            "rationale": rationale, "evidence_type": evidence_type}

FRAMEWORK_ASSET_FOR_BUNDLE = {k: ASSETS[0][k] for k in ("id", "label", "type", "url", "access_status", "public_researcher_routes")}

BUNDLE_STXBP1 = {
    "id": "framework-for-stxbp1",
    "target_disease": {"id": STXBP1, "label": "STXBP1-related disorder"},
    "goal": "Plan a natural-history study using an existing assessment framework",
    "goal_id": "natural_history",
    "asset": FRAMEWORK_ASSET_FOR_BUNDLE,
    "sources": {PAPER: SOURCES[PAPER], "WEB:stxbp1-foundation-starr": SOURCES["WEB:stxbp1-foundation-starr"]},
    "coverage": "Checks one published framework and the STXBP1 Foundation STARR page for an STXBP1 target. Pending human source review. Does not search all natural-history studies, and does not confirm current recruitment.",
    "checks": [
        {"id": "documented-framework", "category": "research", "required": True,
         "question": "Is an existing natural-history framework documented?",
         "evidence": [ev(PAPER, "support", "Methods describe the STARR and ProMMiS protocols, sites and assessments.")],
         "next_question": "Which protocol components can be shared with our group?", "contact_role": "study coordinator"},
        {"id": "target-observed", "category": "research", "required": True,
         "question": "Does this paper report use in STXBP1-related disorder?",
         "evidence": [ev(PAPER, "support", "STARR is the STXBP1-RD arm; the preprint reports 164 STXBP1-RD participants enrolled.")],
         "next_question": "Do our proposed participants resemble the studied STXBP1 cohort (age range, severity, variant types)?",
         "contact_role": "clinical investigator"},
        {"id": "implementation-access", "category": "access", "required": True,
         "question": "Have permissions, materials and implementation resources been confirmed for our proposed study?",
         "evidence": [ev(PAPER, "uncertain", "The paper says caregiver measures moved to RARE-X only once licensing agreements were finalized, and several instruments are commercially published. This shows licences matter; it does not say what our group would need.")],
         "next_question": "Can we access the protocol and instrument materials, and which licences, trained staff and equipment (e.g. 128-channel EEG) are required?",
         "contact_role": "study coordinator"},
        {"id": "local-feasibility", "category": "implementation", "required": True,
         "question": "Has the framework been assessed for our group's age range, travel constraints and study sites?",
         "evidence": [],
         "next_question": "Which components need adapting to our cohort and local study capacity? The paper notes in-person visits limit families who cannot travel.",
         "contact_role": "clinical investigator"},
        {"id": "patient-org-involvement", "category": "community", "required": False,
         "question": "Is an STXBP1 patient organization documented as a partner in designing this framework?",
         "evidence": [ev(PAPER, "support", "Outcome measures were selected and reviewed with the STXBP1 Foundation (Methods)."),
                      ev("WEB:stxbp1-foundation-starr", "support", "Foundation page states it funds STARR.", "other")],
         "next_question": "Would the STXBP1 Foundation share what they learned from co-designing STARR?",
         "contact_role": "patient organization research lead"},
        {"id": "current-enrollment", "category": "status", "required": False,
         "question": "Is STARR currently enrolling?",
         "evidence": [ev("WEB:stxbp1-foundation-starr", "uncertain", "The undated foundation page says all five listed sites are enrolling; the page date is unknown, so current status needs confirmation.", "other")],
         "next_question": "Is STARR enrolling now, and at which sites?",
         "contact_role": "study coordinator"},
        {"id": "trial-endpoint", "category": "research", "required": False,
         "question": "Has responsiveness to treatment been established by this paper?",
         "evidence": [ev(PAPER, "uncertain", "Authors say longitudinal data are still needed, and countable seizures were present in only about a quarter of the STXBP1 cohort up to age 10.")],
         "next_question": "What additional validation is needed before selecting a treatment-trial endpoint?",
         "contact_role": "outcome-measure researcher"},
    ],
}

CITIZEN_ASSET = {k: ASSETS[3][k] for k in ("id", "label", "type", "url", "access_status", "public_researcher_routes")}
BUNDLE_CITIZEN = {
    "id": "citizen-dataset-for-syngap1",
    "target_disease": {"id": SYNGAP1, "label": "SYNGAP1-related disorder"},
    "goal": "Use existing retrospective data to inform outcome selection for a natural-history study",
    "goal_id": "natural_history",
    "asset": CITIZEN_ASSET,
    "sources": {"WEB:curesyngap1-request-nhs-data": SOURCES["WEB:curesyngap1-request-nhs-data"]},
    "coverage": "Checks one organization page describing a dataset and its access route. Pending human source review. Data contents and current volume were not inspected.",
    "checks": [
        {"id": "dataset-documented", "category": "research", "required": True,
         "question": "Is a SYNGAP1 dataset with a documented access route described?",
         "evidence": [ev("WEB:curesyngap1-request-nhs-data", "support", "The page describes de-identified record summaries for SYNGAP1 patients with confirmed P/LP diagnoses.", "other")],
         "next_question": "Which data fields and time ranges does the dataset include?", "contact_role": "patient organization research lead"},
        {"id": "requester-eligibility", "category": "access", "required": True,
         "question": "Can our group (a patient organization) request access directly?",
         "evidence": [ev("WEB:curesyngap1-request-nhs-data", "uncertain", "The page addresses academic researchers and requires a researcher agreement plus an IRB submission; it does not say whether a patient organization can apply.", "other")],
         "next_question": "Do we need an academic partner with an IRB to request this data, and who could act as that partner?",
         "contact_role": "patient organization research lead"},
        {"id": "fit-for-prospective-planning", "category": "research", "required": True,
         "question": "Does retrospective record data cover the outcomes our prospective study would measure?",
         "evidence": [],
         "next_question": "Which of our planned outcome domains (motor, communication, behaviour, sleep, seizures) are recorded in the dataset?",
         "contact_role": "clinical investigator"},
    ],
}

# ---------------------------------------------------------------- review log
def log(cid, sid, loc, assertion, caveat):
    return {"claim_or_check_id": cid, "source_id": sid, "source_location": loc, "assertion_checked": assertion,
            "review_status": "pending", "checked_by": REVIEWER, "checked_on": CHECK_DATE, "caveat": caveat}

PRE = "preprint v1 (published version not read)"
REVIEW_LOG = [
    log("framework-for-stxbp1/documented-framework", PREPRINT, "Abstract (Methods); Methods: Study Organization & Management",
        "Paper describes multi-centre prospective protocols STARR (STXBP1-RD) and ProMMiS (SYNGAP1-RD).", PRE),
    log("framework-for-stxbp1/target-observed", PREPRINT, "Methods: Recruitment",
        "164 individuals with STXBP1-RD enrolled.", PRE + "; counts may be updated in the published version."),
    log("framework-for-stxbp1/implementation-access", PREPRINT, "Methods: Developmental and parent-reported outcome measures; References 35, 36, 64",
        "PROMs administered via RARE-X from year two once licensing agreements were finalized; several instruments cite commercial publishers.",
        PRE + "; does not establish what another group would need. Licence terms not checked."),
    log("framework-for-stxbp1/local-feasibility", PREPRINT, "Discussion (in-person assessment limitation)",
        "No evidence recorded; Discussion notes in-person visits may limit participation.", "Recorded as context for the next question, not as evidence."),
    log("framework-for-stxbp1/patient-org-involvement", PREPRINT, "Methods: Developmental and parent-reported outcome measures",
        "Measures selected in collaboration with the STXBP1 Foundation and CURE SYNGAP1; meetings reviewed the selection.", PRE),
    log("framework-for-stxbp1/patient-org-involvement", "WEB:stxbp1-foundation-starr", "Section: What is STARR?",
        "STARR is funded by the STXBP1 Foundation (FLOURISH campaign) and the ENDD Center.", "Undated organization page."),
    log("framework-for-stxbp1/current-enrollment", "WEB:stxbp1-foundation-starr", "Section: How Can I Join STARR",
        "Page lists 5 sites and states all are enrolling.",
        "Undated page. The preprint lists 6 STARR sites including Rush; the page lists 5 without Rush. Treat as a dated discrepancy, not a contradiction about the study."),
    log("framework-for-stxbp1/trial-endpoint", PREPRINT, "Preliminary Results (countable seizures); Discussion",
        "Countable seizures in about 25% of the STXBP1 cohort up to age 10; longitudinal assessment still needed.", PRE),
    log("citizen-dataset-for-syngap1/dataset-documented", "WEB:curesyngap1-request-nhs-data", "Main text",
        "De-identified record summaries incl. genetic and EEG results; over 100 patients; all with confirmed P/LP diagnosis.",
        "Patient count is the page's own statement; page last modified 2025-10-31."),
    log("citizen-dataset-for-syngap1/requester-eligibility", "WEB:curesyngap1-request-nhs-data", "Main text",
        "Addressed to academic researchers; requires Researcher Agreement and Cat 8 IRB template submission.",
        "Silence on patient-organization requesters is recorded as unknown, not as a refusal."),
    log("edge:overlay:syngap1-stxbp1-shared-framework", PREPRINT, "Results: disease-specific patterns; Figure 3 legend",
        "Both cohorts are in one framework; paper reports distinct developmental and seizure patterns between the two disorders.",
        "Inferred navigation edge. Must not be shown as shared biology or treatment transfer."),
    log("edge:overlay:helbig-leads-starr", "WEB:stxbp1-foundation-starr", "Section: STARR Study Leadership",
        "Ingo Helbig, MD is the multi-site Principal Investigator.", "Undated organization page."),
    log("edge:overlay:cure-syngap1-partners-prommis", "WEB:curesyngap1-prommis-blog", "Section: About the ProMMiS study",
        "ProMMiS powered by CURE SYNGAP1; sites CHOP, CHCO (Colorado) and Stanford.", "Blog post dated 2026-03-26."),
    log("edge:overlay:endd-coordinates-starr", PREPRINT, "Methods: Study Organization & Management",
        "CHOP is the prime site and Data Coordinating Center for both studies.", PRE),
    log("asset:seizure-history-reconstruction", PREPRINT, "Methods: Seizure history reconstruction; Preliminary Results",
        "Month-by-month reconstruction, HPO-coded seizure types, PELHS scale with two added levels; 107 STXBP1 and 100 SYNGAP1 in preliminary analysis.", PRE),
    log("asset:starr-prommis-qeeg-protocol", PREPRINT, "Methods: Quantitative EEG; Discussion (biomarkers)",
        "128-channel EEG, VEP/AEP, ICA artifact removal; biomarker work described as initial.", PRE),
    log("asset:simons-searchlight-prom-data", PREPRINT, "Preliminary Results: Parent-reported outcomes; Figure 4 legend",
        "Simons Searchlight data for STXBP1 (n=67) and SYNGAP1 (n=39) combined with RARE-X data.", PRE + "; operator's own pages not reviewed."),
    log("asset:rare-x-prom-collection", "WEB:globalgenes-rarex-stxbp1-2024", "Press release body (search snippet)",
        "Global Genes and STXBP1 Foundation partnership to use RARE-X for the STARR natural history study, launched July 2024.",
        "Read via search snippet only; full page not opened."),
    log("org:stxbp1-foundation", "WEB:stxbp1-foundation-starr", "Section: STARR Study Leadership",
        "Page lists a research email for STARR questions and a general info email.", "Contact route exists as of check date."),
    log("org:cure-syngap1", "WEB:curesyngap1-prommis-blog", "Section: Interested in participating?",
        "Families register via the ProMMiS page; questions go to a named staff inbox.", "We store the organization contact page, not personal inboxes."),
    log("team:chop-endd-nhs", "WEB:endd-natural-history-study", "Search snippet of page",
        "Page states Ingo Helbig leads the NHS for STXBP1 and SYNGAP1 and gives a study inbox.", "Full page not opened; snippet only."),
    log("study:starr", "WEB:stxbp1-foundation-starr", "Section: How Can I Join STARR",
        "Page reports the ClinicalTrials.gov ID NCT06555965.", "Registry page was not machine-readable; status there not checked."),
]

OVERLAY = {
    "schema_version": "rarebridge.handoff.v1",
    "sources": SOURCES,
    "nodes": NODES,
    "edges": EDGES,
    "assets": ASSETS,
    "contacts": CONTACTS,
    "assessment_bundles": [BUNDLE_STXBP1, BUNDLE_CITIZEN],
    "disease_synonyms": {
        STXBP1: ["STXBP1-RD", "STXBP1-related disorder", "STXBP1-related disorders", "STXBP1 encephalopathy"],
        SYNGAP1: ["SYNGAP1-RD", "SYNGAP1-related disorder", "SYNGAP1-related intellectual disability"],
    },
    "review_log": REVIEW_LOG,
    "coverage_note": (
        f"Curated slice built on {CHECK_DATE}: one published framework (read as its medRxiv preprint), two patient organizations, "
        "two study sites/teams, two researchers, six assets and two new assessment bundles. EVERY record is pending human source review; "
        "an AI assistant drafted them. Not a literature search. Missing items here are not evidence they do not exist."),
}


def _review_inventory(overlay):
    """Check record identities, retaining intentional node/contact overlap."""
    groups = {}
    for name in ("edges", "nodes", "contacts", "assets"):
        records = overlay.get(name, [])
        if not isinstance(records, list):
            raise ValueError(f"{name} must be a list")
        by_id = {}
        for item in records:
            if not isinstance(item, dict) or not isinstance(item.get("id"), str) or not item["id"]:
                raise ValueError(f"{name} has a record without an ID")
            if item["id"] in by_id:
                raise ValueError(f"Duplicate {name} record ID: {item['id']}")
            by_id[item["id"]] = item
        groups[name] = by_id
    if groups["edges"].keys() & (groups["nodes"].keys() | groups["contacts"].keys()):
        raise ValueError("An edge ID cannot also identify a node or contact")
    for cid, contact in groups["contacts"].items():
        node = groups["nodes"].get(cid)
        if node and (node.get("label"), node.get("type"), node.get("url")) != (
                contact.get("label"), contact.get("kind"), contact.get("url")):
            raise ValueError(f"Ambiguous shared node/contact identity: {cid}")
    sources = overlay.get("sources", {})
    if not isinstance(sources, dict):
        raise ValueError("sources must be an object")
    aliases = {}
    for sid, source in sources.items():
        if not isinstance(source, dict) or not source.get("url"):
            raise ValueError(f"Source {sid} lacks attribution metadata")
        for alias in [sid, *source.get("aliases", [])]:
            if alias in aliases and aliases[alias] != sid:
                raise ValueError(f"Ambiguous source alias: {alias}")
            aliases[alias] = sid
        version_of = source.get("version_of")
        if version_of and (version_of not in sources or version_of == sid):
            raise ValueError(f"Source {sid} has an invalid version_of")
    return groups, aliases


def _location(record, source, group):
    """Localization pointers from the existing curation notes, not a new read."""
    note = source.get("note", "").casefold()
    if "snippet" in note or "full page not opened" in note:
        return "Original curation search snippet; full-page source verification pending"
    if source.get("source_kind") == "preprint":
        relation = record.get("relation")
        identifier = record["id"]
        if group != "edges" and record.get("kind") == "researcher":
            return "Preprint v1 title page and correspondence block; public discovery route still needs checking"
        if relation == "corresponding_author_of":
            return "Preprint v1 title page and correspondence block"
        if relation == "studied_in":
            return "Preprint v1 Methods: Recruitment"
        if "qeeg" in identifier:
            return "Preprint v1 Methods: Quantitative EEG; Discussion (biomarkers)"
        if "seizure" in identifier:
            return "Preprint v1 Methods: Seizure history reconstruction"
        if "searchlight" in identifier or relation == "used_as_comparison_data_in":
            return "Preprint v1 Preliminary Results: Parent-reported outcomes; Figure 4 legend"
        if "rarex" in identifier or relation == "partners_on_study":
            return "Preprint v1 Methods: Developmental and parent-reported outcome measures"
        return "Preprint v1 Methods: Study Organization & Management; relevant study description"
    if source.get("source_kind") == "human_observational_study":
        return "Inherited publication metadata (title, DOI and PMID); published text not read by this curation lane"
    url = source.get("url", "")
    if "/starr" in url:
        if record.get("kind") == "researcher" or record.get("relation") == "leads_study":
            return "STARR page: STARR Study Leadership; public page route"
        return "STARR page: What is STARR?; public page route"
    if "request-nhs-data" in url:
        return "Data-request page main text: dataset description and researcher access requirements"
    if "four-stories-one-purpose" in url:
        return "Blog post: About the ProMMiS study; study naming and site information"
    return "Existing curation source URL and metadata; relevant assertion location requires review"


def _review_source(overlay, cited_source_id, *, publication_metadata=False):
    """Keep the reviewed-text version separate from the published citation ID."""
    sources = overlay["sources"]
    if cited_source_id not in sources:
        raise ValueError(f"Record refers to an unknown source: {cited_source_id}")
    if publication_metadata:
        return cited_source_id
    versions = [sid for sid, source in sources.items()
                if source.get("version_of") == cited_source_id
                and source.get("source_kind") == "preprint"]
    if len(versions) > 1:
        raise ValueError(f"Multiple preprint versions need an explicit review choice for {cited_source_id}")
    return versions[0] if versions else cited_source_id


def _pending_row(overlay, identifier, record, cited_source_id, record_groups, facets, assertion):
    publication_metadata = record.get("type") == "publication"
    source_id = _review_source(overlay, cited_source_id, publication_metadata=publication_metadata)
    source = overlay["sources"][source_id]
    caveats = [
        "Pending review pointer generated only from existing curation metadata; no new source was read and no human sign-off is implied.",
        "Source checking is narrow factual review, not clinical validation, resource compatibility or permission to use a resource.",
    ]
    if source_id != cited_source_id:
        caveats.append(
            f"This pointer is for the medRxiv preprint version_of {cited_source_id}; the published article was not read by this curation lane. "
            "Confirm the relevant preprint wording and check the published version separately; versions are not independent evidence."
        )
    elif publication_metadata:
        caveats.append("Publication identifiers and date were inherited from the base source record; no published-text review is claimed.")
    if source.get("note"):
        caveats.append("Existing source note (context, not a sign-off of this assertion): " + source["note"])
    if len(record.get("source_ids", [])) > 1:
        caveats.append("This is one source pointer for a multi-source assertion; verify the part supported by each source before signing the shared record ID.")
    row = {
        "claim_or_check_id": identifier, "source_id": source_id,
        "source_location": _location(record, source, "edges" if "edges" in record_groups else "nodes"),
        "assertion_checked": "Pending assertion to verify (not yet checked): " + assertion,
        "review_status": "pending", "checked_by": "Pending review pointer; no human reviewer",
        "checked_on": "", "caveat": " ".join(caveats),
        "record_groups": record_groups, "review_facets": facets,
        "cited_source_id": cited_source_id,
        "review_entry_id": "pending-review:" + hashlib.sha256(
            json.dumps([identifier, source_id, cited_source_id, record_groups], separators=(",", ":")).encode()
        ).hexdigest()[:24],
        "prepared_from": "existing_curation_metadata_only",
    }
    return row


def derive_missing_review_rows(overlay):
    """Return missing *pending* log rows without mutating any overlay object.

    Existing rows, including human signatures, remain untouched. Where one ID
    represents both a graph node and a contact, its new rows explicitly cover
    identity, collaborator role and public discovery route together. sign_off.py
    requires all rows under that shared ID to be signed before promoting it.
    """
    groups, aliases = _review_inventory(overlay)
    logs = overlay.get("review_log", [])
    if not isinstance(logs, list):
        raise ValueError("review_log must be a list")
    logged = {row["claim_or_check_id"] for row in logs}
    added = []
    for identifier, edge_record in groups["edges"].items():
        if identifier in logged:
            continue
        sources = edge_record.get("source_ids", [])
        if not sources:
            raise ValueError(f"Cannot derive a review pointer without source IDs: {identifier}")
        for supplied_id in sources:
            source_id = aliases.get(supplied_id)
            if source_id is None:
                raise ValueError(f"Unknown source binding for {identifier}: {supplied_id}")
            assertion = (
                f"Recorded relation {edge_record['source']} --{edge_record['relation']}--> {edge_record['target']}. "
                + edge_record["explanation"]
            )
            added.append(_pending_row(overlay, identifier, edge_record, source_id,
                                      ["edges"], ["recorded_relationship"], assertion))
    for identifier in dict.fromkeys([*groups["nodes"], *groups["contacts"]]):
        if identifier in logged:
            continue
        node, contact = groups["nodes"].get(identifier), groups["contacts"].get(identifier)
        asset = groups["assets"].get(identifier)
        record = contact or node
        record_groups = (["nodes"] if node else []) + (["contacts"] if contact else [])
        facets = (["node_identity"] if node else []) + (["contact_role", "public_route"] if contact else [])
        parts = []
        if node:
            parts.append(f"Node identity: {node['label']} ({node['type']}, ID {identifier}).")
            if node.get("aliases"):
                parts.append("Recorded aliases: " + ", ".join(node["aliases"]) + ".")
        if contact:
            parts.extend(["Recorded collaborator role: " + contact["role"],
                          "Public discovery route to verify: " + contact["url"] +
                          ". This route is not confirmation of current availability or ownership."])
        if asset:
            parts.append("Resource description to verify: " + asset.get("description", asset["label"]))
        sources = (contact or asset or node).get("source_ids", [])
        if not sources and node and node.get("type") == "publication":
            sources = [identifier]
        if not sources:
            sources = list(dict.fromkeys(sid for edge_record in groups["edges"].values()
                                         if identifier in {edge_record["source"], edge_record["target"]}
                                         for sid in edge_record.get("source_ids", [])))
        if not sources:
            raise ValueError(f"Cannot derive a grounded node/contact review pointer: {identifier}")
        for supplied_id in sources:
            source_id = aliases.get(supplied_id)
            if source_id is None:
                raise ValueError(f"Unknown source binding for {identifier}: {supplied_id}")
            added.append(_pending_row(overlay, identifier, record, source_id,
                                      record_groups, facets, " ".join(parts)))
    return added


def validate_review_coverage(overlay):
    """Fail if an edge/node/contact lacks a log or identities are ambiguous.

    This validates coverage, not source truth or a human signature. Legacy rows
    retain their historical form. New combined contact/node rows must declare
    all three facets so a name-only assertion cannot certify a collaborator route.
    """
    groups, aliases = _review_inventory(overlay)
    known_ids = set().union(*(group.keys() for group in groups.values()))
    known_ids.update(f"{bundle['id']}/{check['id']}" for bundle in overlay.get("assessment_bundles", [])
                     for check in bundle.get("checks", []))
    logs = overlay.get("review_log", [])
    logged, row_keys, entry_ids = set(), set(), set()
    for row in logs:
        identifier, sid = row.get("claim_or_check_id"), row.get("source_id")
        if identifier not in known_ids:
            raise ValueError(f"Review row has an unknown record ID: {identifier}")
        if sid not in aliases:
            raise ValueError(f"Review row has an unknown source: {sid}")
        key = (identifier, aliases[sid], row.get("source_location"), row.get("cited_source_id"))
        if key in row_keys:
            raise ValueError(f"Duplicate review row for {identifier} and {sid}")
        row_keys.add(key)
        entry_id = row.get("review_entry_id")
        if entry_id and entry_id in entry_ids:
            raise ValueError(f"Duplicate review entry ID: {entry_id}")
        if entry_id:
            entry_ids.add(entry_id)
        cited = row.get("cited_source_id")
        if cited and (cited not in aliases or (aliases[sid] != aliases[cited]
                     and overlay["sources"][aliases[sid]].get("version_of") != aliases[cited])):
            raise ValueError(f"Review row has an invalid source-version binding: {identifier}")
        if row.get("prepared_from") == "existing_curation_metadata_only":
            covered_groups = set(row.get("record_groups", []))
            facets = set(row.get("review_facets", []))
            if identifier in groups["nodes"] and identifier in groups["contacts"]:
                if not {"nodes", "contacts"} <= covered_groups or not {"node_identity", "contact_role", "public_route"} <= facets:
                    raise ValueError(f"Shared contact/node review does not cover role and route: {identifier}")
        logged.add(identifier)
    missing = {name: sorted(group.keys() - logged) for name, group in groups.items()
               if name in {"edges", "nodes", "contacts"} and group.keys() - logged}
    if missing:
        raise ValueError("Missing review-log coverage: " + json.dumps(missing, sort_keys=True))
    return {name: len(groups[name]) for name in ("edges", "nodes", "contacts")}


def build_overlay():
    """Return a complete fresh pending draft without touching signed files."""
    result = deepcopy(OVERLAY)
    result["review_log"].extend(derive_missing_review_rows(result))
    validate_review_coverage(result)
    return result


def _contains_signoff(value):
    if isinstance(value, dict):
        return value.get("review_status") == "source_checked" or any(_contains_signoff(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_signoff(item) for item in value)
    return False


def write_overlay(output_dir):
    """Write only after ensuring neither target would discard a sign-off."""
    directory = Path(output_dir)
    targets = [directory / "atlas-overlay.json", directory / "source-review-log.json"]
    for path in targets:
        if path.exists():
            existing = json.loads(path.read_text(encoding="utf-8"))
            if _contains_signoff(existing):
                raise ValueError(f"Refusing to overwrite signed curation: {path}. Choose a fresh --output-dir.")
    overlay = build_overlay()
    directory.mkdir(parents=True, exist_ok=True)
    targets[0].write_text(json.dumps(overlay, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    targets[1].write_text(json.dumps({"schema_version": overlay["schema_version"], "entries": overlay["review_log"]},
                                      indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return overlay


def main():
    parser = argparse.ArgumentParser(description="Build a pending curation draft without overwriting human sign-offs")
    parser.add_argument("--output-dir", type=Path, default=OUT)
    args = parser.parse_args()
    try:
        overlay = write_overlay(args.output_dir)
    except (ValueError, OSError) as exc:
        parser.exit(2, str(exc) + "\n")
    print("wrote pending overlay: " + ", ".join(f"{len(overlay[name])} {name}" for name in
                                                 ("nodes", "edges", "assets", "contacts", "assessment_bundles", "review_log")))


if __name__ == "__main__":
    main()
