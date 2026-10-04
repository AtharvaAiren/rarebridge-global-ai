"""RareBridge backend API (contract rarebridge.handoff.v1).

Run from the repository root:
    python -m uvicorn rarebridge.api.app:app --host 127.0.0.1 --port 8000

Environment (all optional):
    RAREBRIDGE_OVERLAY       path to a curation overlay, or "off" to disable it
                             (default: curation/atlas-overlay.json if present)
    RAREBRIDGE_CORS_ORIGINS  extra comma-separated origins for local frontends
    RAREBRIDGE_AI_TIMEOUT    seconds to wait for the lead's AI service (default 90)
"""

from __future__ import annotations

import asyncio
import os

from fastapi import Body, FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from rarebridge.services.ai_bridge import AIBridge, AIServiceError, AIUnavailable
from rarebridge.services.assessments import AssessmentService, InvalidWithdrawal, UnknownAssessment
from rarebridge.services.constants import (DEFAULT_GOAL, GRAPH_NODES_DEFAULT, GRAPH_NODES_MAX,
                                           GRAPH_NODES_MIN, SCHEMA_VERSION, SEARCH_LIMIT_DEFAULT,
                                           SUPPORTED_GOALS)
from rarebridge.services.contacts import ContactService
from rarebridge.services.graph_select import GraphService, UnknownGraphTarget
from rarebridge.services.overview import OverviewService, UnknownDisease
from rarebridge.services.registry import Registry
from rarebridge.services.related import RelatedDiseases
from rarebridge.services.search import SearchIndex
from rarebridge.ai.research import ResearchService
from rarebridge.ai.transport import AIServiceError as ResearchAIError

from .models import AskRequest, DiscoverRequest, EvaluateRequest, ExplainRequest, ExtractRequest

DEFAULT_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"]


class ApiError(Exception):
    def __init__(self, status, code, message, details=None):
        self.status, self.code, self.message, self.details = status, code, message, details or []


def envelope(payload):
    return {"schema_version": SCHEMA_VERSION, **payload}


def error_body(code, message, details=None):
    return {"schema_version": SCHEMA_VERSION, "error": {"code": code, "message": message, "details": details or []}}


class Services:
    """All services built once from one registry, so every endpoint sees the same data."""

    def __init__(self, registry, ai_bridge=None, research_service=None):
        self.registry = registry
        self.search = SearchIndex(registry)
        self.related = RelatedDiseases(registry)
        self.contacts = ContactService(registry)
        self.overview = OverviewService(registry, self.related, self.contacts)
        self.graph = GraphService(registry, self.related, self.contacts)
        self.assessments = AssessmentService(registry, self.contacts)
        self.ai = ai_bridge or AIBridge()
        self.research = research_service or ResearchService(registry)
        self.research_budget = asyncio.Semaphore(2)


def create_app(registry: Registry | None = None, ai_bridge: AIBridge | None = None,
               research_service=None) -> FastAPI:
    services = Services(registry or Registry(), ai_bridge, research_service)
    reg = services.registry

    app = FastAPI(title="RareBridge API", version="0.1.0",
                  description="Evidence-qualified research-asset journey for a three-disease slice.")
    app.state.services = services

    extra = [o.strip() for o in os.environ.get("RAREBRIDGE_CORS_ORIGINS", "").split(",") if o.strip()]
    app.add_middleware(CORSMiddleware, allow_origins=DEFAULT_ORIGINS + extra, allow_credentials=False,
                       allow_methods=["GET", "POST", "OPTIONS"], allow_headers=["*"])

    # ------------------------------------------------------------ errors
    @app.exception_handler(ApiError)
    async def _api_error(_request: Request, exc: ApiError):
        return JSONResponse(error_body(exc.code, exc.message, exc.details), status_code=exc.status)

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_request: Request, exc: RequestValidationError):
        details = [{"loc": list(err.get("loc", [])), "msg": err.get("msg", "")} for err in exc.errors()]
        return JSONResponse(error_body("invalid_request", "The request does not match the API contract.", details),
                            status_code=422)

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_request: Request, exc: StarletteHTTPException):
        code = {404: "not_found", 405: "method_not_allowed"}.get(exc.status_code, "http_error")
        return JSONResponse(error_body(code, str(exc.detail)), status_code=exc.status_code)

    @app.exception_handler(Exception)
    async def _unexpected(_request: Request, exc: Exception):
        return JSONResponse(error_body("internal_error", f"Unexpected server error: {type(exc).__name__}"),
                            status_code=500)

    def check_goal(goal):
        if goal not in SUPPORTED_GOALS:
            raise ApiError(422, "unknown_goal", f"Goal '{goal}' is not supported.",
                           [{"loc": ["query", "goal"], "msg": f"Supported goals: {sorted(SUPPORTED_GOALS)}"}])

    # ------------------------------------------------------------ 1 health
    @app.get("/api/health")
    def health():
        caps, ai_reason = services.ai.capabilities()
        research_caps = services.research.capabilities()
        return envelope({
            "status": "ok",
            "capabilities": {"search": True, "assessment": True, "graph": True,
                             "curation_overlay": reg.overlay_meta["loaded"],
                             "ai_extraction": caps["ai_extraction"], "ai_explanation": caps["ai_explanation"],
                             "ai_discovery": research_caps["ai_discovery"],
                             "ai_assistant": research_caps["ai_assistant"]},
            "data_snapshot": reg.snapshot_commit,
            # additive
            "data_origin": reg.data_origin,
            "ai_status_note": ai_reason,
            "research_ai_status_note": research_caps.get("note", ""),
            "overlay": {key: reg.overlay_meta.get(key) for key in
                        ("loaded", "sha256", "counts", "review_log_status", "pending_edges", "merge_notes")},
            "counts": {**reg.total_counts(), "diseases": len(reg.disease_ids()),
                       "assessments": len(reg.bundles), "sources": len(reg.sources)},
            "goals": sorted(SUPPORTED_GOALS),
        })

    # ------------------------------------------------------------ 2 search
    @app.get("/api/search")
    def search(q: str = Query(default=""), limit: str = Query(default=str(SEARCH_LIMIT_DEFAULT))):
        result = services.search.search(q, limit)
        loaded = reg.overlay_meta["loaded"]
        scope = (f"Names, synonyms and IDs in a {len(reg.disease_ids())}-disease slice (STXBP1, SYNGAP1, SCN2A; "
                 "pinned DisMech snapshot" + (" plus curated overlay" if loaded else "") + "). "
                 "Not a literature search; no match here does not mean nothing exists.")
        return envelope({
            "query": q,
            "items": result["items"],
            "coverage": {"disease_count": len(reg.disease_ids()), "scope_note": scope},
            "total_matches": result["total_matches"],
            "limit": result["limit"],
        })

    # ---------------------------------------------------------- disease list (additive)
    @app.get("/api/diseases")
    def diseases():
        items = [{"id": d, "type": "disease", "label": reg.disease_label(d),
                  "synonyms": reg.disease_names(d)[1:]} for d in reg.disease_ids()]
        return envelope({"items": items, "coverage": {"disease_count": len(items),
                                                      "scope_note": "All diseases in this demonstration slice."}})

    # ---------------------------------------------------------- 3 overview
    @app.get("/api/diseases/{disease_id}/overview")
    def overview(disease_id: str, goal: str = Query(default=DEFAULT_GOAL)):
        check_goal(goal)
        try:
            return envelope(services.overview.build(disease_id, goal))
        except UnknownDisease:
            raise ApiError(404, "unknown_disease", "This disease is not in the current data slice.",
                           [{"loc": ["path", "disease_id"], "msg": disease_id}])

    # -------------------------------------------------------- 4 assessment
    @app.post("/api/assessments/evaluate")
    def evaluate(request: EvaluateRequest = Body(...)):
        try:
            return envelope(services.assessments.evaluate(request.assessment_id, request.withdrawn_source_ids)
                            | {"data_origin": reg.data_origin})
        except UnknownAssessment:
            raise ApiError(404, "unknown_assessment", "This assessment is not in the current data slice.",
                           [{"loc": ["body", "assessment_id"], "msg": request.assessment_id}])
        except InvalidWithdrawal as exc:
            raise ApiError(422, "invalid_withdrawal", str(exc), exc.details)

    # ------------------------------------------------------------ 5 graph
    @app.get("/api/graph")
    def graph(disease_id: str | None = Query(default=None), assessment_id: str | None = Query(default=None),
              max_nodes: str = Query(default=str(GRAPH_NODES_DEFAULT))):
        try:
            size = max(GRAPH_NODES_MIN, min(GRAPH_NODES_MAX, int(max_nodes)))
        except ValueError:
            raise ApiError(422, "invalid_request", "max_nodes must be an integer.",
                           [{"loc": ["query", "max_nodes"], "msg": max_nodes}])
        try:
            return envelope(services.graph.build(disease_id or None, assessment_id or None, size))
        except UnknownGraphTarget as exc:
            kind, value = exc.args[0]
            if kind == "missing":
                raise ApiError(422, "invalid_request", "Provide disease_id or assessment_id.",
                               [{"loc": ["query", "disease_id"], "msg": "required when assessment_id is absent"}])
            code = "unknown_assessment" if kind == "assessment" else "unknown_disease"
            raise ApiError(404, code, f"This {kind} is not in the current data slice.",
                           [{"loc": ["query", f"{kind}_id"], "msg": value}])

    # ----------------------------------------------------------- 6 sources
    @app.get("/api/sources/{source_id:path}")
    def source(source_id: str):
        canonical = reg.canonical_source(source_id)
        if canonical is None:
            raise ApiError(404, "unknown_source", "This source is not in the current data slice.",
                           [{"loc": ["path", "source_id"], "msg": source_id}])
        record = reg.source_record(canonical)
        cited_by = sorted(bid for bid, bundle in reg.bundles.items()
                          if canonical in bundle.get("sources", {}))
        return envelope({"canonical_id": canonical, "source": record,
                         "requested_id": source_id, "cited_by_assessments": cited_by})

    # ------------------------------------------------- optional AI wiring
    @app.post("/api/ai/extract")
    async def ai_extract(request: ExtractRequest = Body(...)):
        payload = request.model_dump()
        payload["source_id"] = reg.canonical_source(request.source_id) or request.source_id
        try:
            extraction = await services.ai.extract(payload)
        except AIUnavailable as exc:
            raise ApiError(503, "model_unavailable", "The AI extraction service is not connected.",
                           [{"msg": str(exc)}])
        except AIServiceError as exc:
            raise ApiError(exc.status_code, exc.code, str(exc), exc.details)
        return envelope({"extraction": extraction, "import_status": "not_imported",
                         "requested_source_id": request.source_id,
                         "note": "Extracted relationships remain pending in a preview; the curated graph is unchanged."})

    @app.post("/api/ai/explain")
    async def ai_explain(request: ExplainRequest = Body(...)):
        try:
            result = services.assessments.evaluate(request.assessment_id, request.withdrawn_source_ids)
        except UnknownAssessment:
            raise ApiError(404, "unknown_assessment", "This assessment is not in the current data slice.",
                           [{"loc": ["body", "assessment_id"], "msg": request.assessment_id}])
        except InvalidWithdrawal as exc:
            raise ApiError(422, "invalid_withdrawal", str(exc), exc.details)
        try:
            explanation = await services.ai.explain(result["after"], result["sources"])
        except AIUnavailable as exc:
            raise ApiError(503, "model_unavailable", "The AI explanation service is not connected.",
                           [{"msg": str(exc)}])
        except AIServiceError as exc:
            raise ApiError(exc.status_code, exc.code, str(exc), exc.details)
        return envelope({"assessment_id": request.assessment_id,
                         "withdrawn_source_ids": result["withdrawn_source_ids_applied"],
                         "explanation": explanation, "data_origin": reg.data_origin})

    async def research_call(work):
        # Limit simultaneous paid requests; do not build an unbounded queue or
        # retry a failed provider call automatically.
        try:
            await asyncio.wait_for(services.research_budget.acquire(), timeout=0.25)
        except asyncio.TimeoutError:
            raise ApiError(429, "ai_busy", "Research AI is busy; try again after the current requests finish.") from None
        try:
            return await asyncio.wait_for(work(), timeout=110)
        except ResearchAIError as exc:
            raise ApiError(exc.status_code, exc.code, exc.message, exc.details) from None
        except asyncio.TimeoutError:
            raise ApiError(504, "upstream_timeout", "The research AI request timed out.") from None
        finally:
            services.research_budget.release()

    @app.post("/api/ai/discover")
    async def ai_discover(request: DiscoverRequest = Body(...)):
        check_goal(request.goal_id)
        if request.disease_id not in reg.disease_ids():
            raise ApiError(404, "unknown_disease", "This disease is not in the current data slice.")
        discovery = await research_call(lambda: services.research.discover(request.disease_id, request.goal_id))
        return envelope({"discovery": discovery, "data_origin": reg.data_origin,
                         "import_status": "not_imported"})

    @app.post("/api/ai/ask")
    async def ai_ask(request: AskRequest = Body(...)):
        try:
            result = services.assessments.evaluate(request.assessment_id, request.withdrawn_source_ids)
        except UnknownAssessment:
            raise ApiError(404, "unknown_assessment", "This assessment is not in the current data slice.") from None
        except InvalidWithdrawal as exc:
            raise ApiError(422, "invalid_withdrawal", str(exc), exc.details) from None
        answer = await research_call(lambda: services.research.ask(
            result["after"], result["sources"], request.question, request.mode))
        return envelope({"assessment_id": request.assessment_id,
                         "withdrawn_source_ids": result["withdrawn_source_ids_applied"],
                         "answer": answer, "data_origin": reg.data_origin})

    return app


app = create_app()
