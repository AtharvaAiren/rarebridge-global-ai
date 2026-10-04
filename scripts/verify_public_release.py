#!/usr/bin/env python3
"""Verify the anonymous public release using fixed public research data.

Default checks are read-only API requests and an actual browser brief download
with every AI route blocked. --paid-ai makes exactly two additional requests:
one hidden-source explanation and one short SFARI public-excerpt extraction.
--paid-explanation-only makes one explanation request after a diagnosed fix.
There are no automatic paid retries or credential/.env reads.
"""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


ROOT = Path(__file__).resolve().parents[1]
DOI = "DOI:10.1002/epi.70374"
PMID = "PMID:42446932"
SYNGAP1 = "MONDO:0012960"
ASSESSMENTS = {"framework-for-syngap1", "framework-for-scn2a",
               "framework-for-stxbp1", "citizen-dataset-for-syngap1"}
MAX_BYTES = 3_000_000
SAFE_VALIDATION_CHECKS = {
    "literal_source_excerpt", "entity_identity", "unique_identifiers", "source_binding",
    "recorded_status", "required_followups", "prose_safety", "output_shape",
    "explanation_check_coverage", "explanation_selection_shape", "unregistered_prose_url",
    "unavailable_prose_publication", "unregistered_contact",
}


class CheckFailure(Exception):
    pass


class NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, new_url):
        raise CheckFailure("Public request redirected; anonymous access or deployment protection needs review.")


def require(condition, message):
    if not condition:
        raise CheckFailure(message)


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode()).hexdigest()


def public_base(value):
    parsed = urlsplit(value)
    require(parsed.scheme == "https" and bool(parsed.hostname) and "." in parsed.hostname
            and not parsed.username and not parsed.password and parsed.port in {None, 443}
            and parsed.path in {"", "/"} and not parsed.query and not parsed.fragment,
            "Provide a public HTTPS origin without credentials, path, query or fragment.")
    return value.rstrip("/")


class PublicClient:
    def __init__(self, base):
        self.base = public_base(base)
        self.opener = build_opener(NoRedirects())

    def request(self, path, payload=None, *, json_body=True, expected=200):
        data = json.dumps(payload).encode() if payload is not None else None
        request = Request(self.base + path, data=data,
                          headers={"Accept": "application/json" if json_body else "text/html",
                                   "Content-Type": "application/json"},
                          method="POST" if payload is not None else "GET")
        try:
            response = self.opener.open(request, timeout=115)
        except HTTPError as exc:
            response = exc
        except (URLError, OSError, TimeoutError):
            raise CheckFailure("Public endpoint could not be reached within the request budget.") from None
        with response:
            status = response.code
            raw = response.read(MAX_BYTES + 1)
            require(len(raw) <= MAX_BYTES, "Public response exceeded the bounded verification size.")
            content_type = response.headers.get("Content-Type", "")
        if status != expected:
            code = "non_json_response"
            validation_checks = []
            try:
                error = json.loads(raw).get("error", {})
                candidate = error.get("code", "")
                if isinstance(candidate, str) and re.fullmatch(r"[a-z_]{1,60}", candidate):
                    code = candidate
                for detail in error.get("details", []):
                    if isinstance(detail, dict) and detail.get("validation_check") in SAFE_VALIDATION_CHECKS:
                        validation_checks.append(detail["validation_check"])
            except (ValueError, AttributeError):
                pass
            diagnostic = " / " + ",".join(sorted(set(validation_checks))) if validation_checks else ""
            raise CheckFailure("Public endpoint returned HTTP " + str(status) + " (" + code + diagnostic + ").")
        if not json_body:
            require("text/html" in content_type, "The public frontend did not return HTML.")
            return raw.decode("utf-8")
        require("application/json" in content_type, "API request returned HTML or a login page instead of JSON.")
        try:
            result = json.loads(raw)
        except (ValueError, UnicodeError):
            raise CheckFailure("Public API returned invalid JSON.") from None
        require(isinstance(result, dict) and result.get("schema_version") == "rarebridge.handoff.v1",
                "Public API did not return the RareBridge contract.")
        return result


def save(output, name, value):
    (output / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def provider_record(result):
    provenance = result.get("provenance", {})
    provider = result.get("provider") or provenance.get("provider")
    response_id = result.get("response_id") or provenance.get("response_id", "")
    require(result.get("generation_mode") in {"live", "cached"}, "AI response was not provider-generated or genuine cache replay.")
    require(provider in {"anthropic", "openai"}, "AI response has no recognized provider provenance.")
    require(isinstance(response_id, str) and response_id.startswith("msg_" if provider == "anthropic" else "resp_"),
            "AI response has no provider response identifier.")
    require(isinstance(result.get("model"), str) and bool(result["model"]), "AI response has no actual model ID.")
    require(re.fullmatch(r"[0-9a-f]{64}", provenance.get("request_sha256", "")) is not None,
            "AI response has no request fingerprint.")
    return {"generation_mode": result["generation_mode"], "provider": provider,
            "model": result["model"], "response_id": response_id}


BROWSER_CHECK = r"""
import assert from 'node:assert/strict';
import { readFile, writeFile } from 'node:fs/promises';
import { chromium } from './.tools/node_modules/playwright/index.mjs';
const [base, output] = process.argv.slice(1);
const browser = await chromium.launch();
const context = await browser.newContext({viewport:{width:1360,height:960},acceptDownloads:true});
const page = await context.newPage();
let blockedAIRequests=0;const errors=[];
page.on('pageerror',()=>errors.push('browser_page_error'));
await page.route('**/api/ai/**', route=>{blockedAIRequests++;return route.abort();});
try {
  await page.goto(base+'/#/disease/MONDO%3A0012960?goal=natural_history&evidence=framework-for-syngap1',{waitUntil:'networkidle',timeout:45000});
  await page.getByRole('tabpanel',{name:'Evidence',exact:true}).getByRole('heading',{name:'STARR / ProMMiS natural-history framework',exact:true}).waitFor({timeout:30000});
  await page.locator('.dependence').getByRole('button',{name:'Hide',exact:true}).click();
  await page.waitForFunction(()=>document.querySelectorAll('.change-summary__item').length===2);
  await page.getByRole('button',{name:'Prepare collaboration brief',exact:true}).click();
  const pending=page.waitForEvent('download');
  await page.getByRole('button',{name:'Download as text',exact:true}).click();
  const downloaded=await pending;const path=output+'/hidden-source-brief.txt';
  await downloaded.saveAs(path);const text=await readFile(path,'utf8');
  assert.match(text,/DOI:10\.1002\/epi\.70374/);
  assert.match(text,/hidden/i);assert.match(text,/Information missing|unknown/i);
  assert.ok(text.length>500);assert.equal(errors.length,0);
  await page.screenshot({path:output+'/public-hidden-source-export.png',fullPage:true});
  await page.emulateMedia({media:'print'});
  await page.pdf({path:output+'/public-hidden-source-brief.pdf',format:'A4',printBackground:true});
  const result={passed:true,actual_download:true,download_name:downloaded.suggestedFilename(),changed_checks:2,blocked_ai_requests:blockedAIRequests,browser_errors:errors,pdf_scope:'Headless print layout; OS dialog not tested'};
  await writeFile(output+'/browser-report.json',JSON.stringify(result,null,2)+'\n');
  console.log(JSON.stringify(result));
} catch(error) {
  const result={passed:false,actual_download:false,blocked_ai_requests:blockedAIRequests,browser_errors:errors,error_kind:error.name};
  await writeFile(output+'/browser-report.json',JSON.stringify(result,null,2)+'\n');
  console.log(JSON.stringify(result));process.exitCode=1;
} finally {await context.close();await browser.close();}
"""


def browser_export(base, output):
    node = ROOT / ".tools/node-v22.23.3-darwin-arm64/bin/node"
    require(node.is_file() and (ROOT / ".tools/node_modules/playwright/index.mjs").is_file(),
            "Installed Node/Playwright tooling is required for the actual public export check.")
    try:
        completed = subprocess.run([str(node), "--input-type=module", "-e", BROWSER_CHECK, base, str(output)],
                                   cwd=ROOT, capture_output=True, text=True, timeout=110, check=False)
    except (OSError, subprocess.TimeoutExpired):
        raise CheckFailure("Public browser export check could not finish within its budget.") from None
    report_path = output / "browser-report.json"
    if report_path.is_file():
        result = json.loads(report_path.read_text())
    else:
        raise CheckFailure("Public browser did not produce an export verification report.")
    require(completed.returncode == 0 and result.get("passed") is True,
            "Actual public browser export check failed; inspect the sanitized browser report.")
    return result


def paid_explanation(client, hidden, output):
    body = client.request("/api/ai/explain", {"assessment_id": "framework-for-syngap1",
                                               "withdrawn_source_ids": [PMID]})
    explanation = body["explanation"]
    record = provider_record(explanation)
    require(body["withdrawn_source_ids"] == [DOI], "Explanation did not preserve canonical source hiding.")
    require(explanation.get("validation", {}).get("status") == "passed", "Explanation validation marker is absent.")
    require(explanation["provenance"].get("assessment_sha256") == fingerprint(hidden["after"]),
            "Explanation fingerprint differs from the actual public assessment state.")
    expected = {row["id"]: row for row in hidden["after"]["checks"]}
    rows = explanation["check_explanations"]
    require(len(rows) == len(expected) and {row["check_id"] for row in rows} == set(expected),
            "Explanation did not preserve every recorded check exactly once.")
    for row in rows:
        require(row["status"] == expected[row["check_id"]]["status"], "Explanation rewrote a recorded check status.")
        require(row["source_ids"] == [], "Hidden-source explanation cited removed evidence.")
    require(explanation["cited_source_ids"] == [], "Explanation cited a hidden or unavailable publication.")
    expected_steps = {row["id"]: (row["next_question"], row["contact_role"])
                      for row in expected.values() if row["required"] and row["status"] != "supported"}
    steps = {row["check_id"]: (row["question"], row["contact_role"]) for row in explanation["next_steps"]}
    require(all(steps.get(cid) == step for cid, step in expected_steps.items()),
            "Explanation failed to preserve a required recorded question/contact role.")
    require(bool(explanation.get("draft_message", "").strip()), "Explanation supplied no reviewable draft message.")
    save(output, "explanation-withdrawn.json", body)
    return {**record, "withdrawn_source_ids": [DOI], "cited_source_ids": [], "checks": len(rows)}


def paid_extraction(client, output):
    sample = json.loads((ROOT / "rarebridge/ai/samples/sfari-access-source.json").read_text())
    payload = {key: sample[key] for key in ("source_id", "title", "url", "published_on", "text")}
    require(payload["url"] == "https://www.sfari.org/resource/sfari-base/" and len(payload["text"]) < 500,
            "Extraction smoke input must remain the fixed short public SFARI excerpt.")
    body = client.request("/api/ai/extract", payload)
    extraction = body["extraction"]
    record = provider_record(extraction)
    require(body["import_status"] == "not_imported", "Extraction unexpectedly merged its output into the graph.")
    require(extraction["source_id"] == payload["source_id"], "Extraction source binding differs from the public sample.")
    require(extraction.get("validation", {}).get("status") == "passed", "Extraction validation marker is absent.")
    require(extraction["provenance"].get("source_sha256") == hashlib.sha256(payload["text"].encode()).hexdigest(),
            "Extraction input hash differs from the literal public excerpt.")
    sys.path.insert(0, str(ROOT))
    from rarebridge.ai.contracts import validate_extraction
    from rarebridge.ai.service import known_entities
    raw = {key: extraction[key] for key in ("entities", "claims", "limitations")}
    # Known public resource identities may appear in the standalone preview.
    # Reuse the shipped identity catalogue rather than treating a legitimate
    # existing ID as a fictional external identifier.
    validate_extraction(raw, payload, known_entities=known_entities())
    require(bool(extraction["claims"]), "The extraction returned no relationships from the public access requirement.")
    preview = extraction["graph_preview"]
    require(preview["data_origin"] == "ai_pending_preview" and bool(preview["edges"]), "Extraction supplied no pending graph preview.")
    require(all(edge["review_status"] == "pending" and edge["claim_origin"] == "imported"
                for edge in preview["edges"]), "The extraction preview promoted unreviewed model claims.")
    save(output, "extraction-sfari-public.json", body)
    return {**record, "claims": len(extraction["claims"]), "source_id": payload["source_id"],
            "literal_excerpt_chars": len(payload["text"]), "import_status": "not_imported",
            "independent_identity_check": "shipped_registry_catalogue"}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "submission/public-release-verification")
    paid = parser.add_mutually_exclusive_group()
    paid.add_argument("--paid-ai", action="store_true", help="Make exactly one explanation and one extraction provider request")
    paid.add_argument("--paid-explanation-only", action="store_true", help="Make one explanation request after a diagnosed fix; do not repeat extraction")
    parser.add_argument("--skip-browser", action="store_true", help="Skip browser export; report records this as unverified")
    args = parser.parse_args(argv)
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    report = {"checked_at": datetime.now(timezone.utc).isoformat(), "base_url": args.base_url,
              "scope": "Public runtime, provenance and workflow checks; not biomedical or clinical validation.",
              "checks": [], "paid_ai_requested": args.paid_ai or args.paid_explanation_only,
              "paid_scope": "explanation_and_extraction" if args.paid_ai else "explanation_only" if args.paid_explanation_only else "none",
              "paid_requests_attempted": 0}

    def check(name, operation):
        try:
            details = operation()
            report["checks"].append({"name": name, "passed": True, "details": details or {}})
            print(name + " PASS", flush=True)
            return details
        except (CheckFailure, KeyError, ValueError, TypeError) as exc:
            reason = str(exc) if isinstance(exc, CheckFailure) else "Public response failed the expected structural contract."
            report["checks"].append({"name": name, "passed": False, "reason": reason})
            print(name + " FAILED: " + reason, flush=True)
            return None

    try:
        client = PublicClient(args.base_url)
        def health_check():
            html = client.request("/", json_body=False)
            require('<div id="root"' in html and "/assets/" in html, "Public origin did not serve the built frontend.")
            health = client.request("/api/health")
            require(health["status"] == "ok" and health["counts"]["diseases"] == 3
                    and health["counts"]["assessments"] == 4 and health["overlay"]["loaded"],
                    "Public deployment is missing the actual registry/curation overlay.")
            require(all(health["capabilities"].get(key) for key in
                        ("ai_extraction", "ai_explanation", "ai_discovery", "ai_assistant")),
                    "Public deployment does not advertise all four configured AI capabilities.")
            save(output, "health.json", health)
            return {"anonymous_access": True, "counts": health["counts"], "data_snapshot": health["data_snapshot"]}
        health = check("anonymous_live_health", health_check)
        require(health is not None, "Anonymous live health failed; no paid request was made.")
        assessments = {}
        for assessment_id in sorted(ASSESSMENTS):
            def evaluate(aid=assessment_id):
                body = client.request("/api/assessments/evaluate", {"assessment_id": aid, "withdrawn_source_ids": []})
                require(body["before"] == body["after"] and body["after"]["assessment_id"] == aid,
                        "An assessment changed without a withdrawal or has the wrong identity.")
                assessments[aid] = body
                save(output, aid + ".json", body)
                return {"assessment_id": aid, "outcome": body["after"]["outcome"], "checks": len(body["after"]["checks"])}
            check("assessment_" + assessment_id, evaluate)
        hidden = {}
        def withdrawal_check():
            by_pmid = client.request("/api/assessments/evaluate", {"assessment_id": "framework-for-syngap1", "withdrawn_source_ids": [PMID]})
            by_doi = client.request("/api/assessments/evaluate", {"assessment_id": "framework-for-syngap1", "withdrawn_source_ids": [DOI]})
            require(by_pmid["after"] == by_doi["after"] and by_pmid["withdrawn_source_ids_applied"] == [DOI],
                    "DOI/PMID aliases did not hide the same canonical publication.")
            require({row["check_id"] for row in by_pmid["changed_checks"]} == {"documented-framework", "target-observed"},
                    "Source hiding did not change exactly the two supported framework checks.")
            require(all(row["status"] == "unknown" for row in by_pmid["after"]["checks"]),
                    "Hidden-paper assessment retained unsupported positive check states.")
            source = client.request("/api/sources/" + quote(PMID, safe=""))
            require(source["canonical_id"] == DOI, "Public source lookup did not resolve the publication alias.")
            reset = client.request("/api/assessments/evaluate", {"assessment_id": "framework-for-syngap1", "withdrawn_source_ids": []})
            require(reset["after"] == by_pmid["before"], "Source hiding mutated the underlying recorded assessment.")
            hidden.update(by_pmid)
            save(output, "assessment-hidden-source.json", by_pmid)
            return {"canonical_source": DOI, "changed_checks": 2, "nondestructive_reset": True}
        check("canonical_source_hiding", withdrawal_check)
        def unknown_check():
            body = client.request("/api/diseases/MONDO%3A0000000/overview", expected=404)
            require(body["error"]["code"] == "unknown_disease", "Unknown disease response did not remain a safe error.")
            return {"status": 404, "code": "unknown_disease"}
        check("unknown_disease_safe", unknown_check)
        def graph_check():
            query = urlencode({"disease_id": SYNGAP1, "assessment_id": "framework-for-syngap1", "max_nodes": 80})
            body = client.request("/api/graph?" + query)
            save(output, "graph.json", body)
            node_ids = {node["id"] for node in body["nodes"]}
            require(all(edge["source"] in node_ids and edge["target"] in node_ids for edge in body["edges"]),
                    "Public graph has unresolved endpoints.")
            inferred = [edge for edge in body["edges"] if edge.get("claim_origin") == "inferred"]
            imported = [edge for edge in body["edges"] if edge.get("claim_origin") == "imported"]
            overlay = json.loads((ROOT / "curation/atlas-overlay.json").read_text())
            signed_inferred = {edge["id"] for edge in overlay["edges"]
                               if edge.get("claim_origin") == "inferred"
                               and edge.get("review_status") == "source_checked"}
            require(bool(inferred) and all(edge["review_status"] == "pending"
                    or edge["review_status"] == "source_checked" and edge["id"] in signed_inferred
                    for edge in inferred),
                    "Public graph removed inferred origins or promoted an unsigned candidate.")
            require(bool(imported) and all(edge["review_status"] == "pending" for edge in imported),
                    "Public graph removed or promoted upstream pending claims.")
            require(all(edge.get("source_ids") and edge.get("provenance") for edge in inferred + imported),
                    "Public graph lost pending-claim source provenance.")
            return {"nodes": len(node_ids), "edges": len(body["edges"]), "inferred": len(inferred),
                    "inferred_pending": sum(edge["review_status"] == "pending" for edge in inferred),
                    "inferred_human_source_checked": sum(edge["review_status"] == "source_checked" for edge in inferred),
                    "imported_pending": len(imported)}
        check("graph_pending_provenance", graph_check)
        if args.skip_browser:
            report["checks"].append({"name": "actual_public_export", "passed": False, "reason": "Browser export intentionally skipped; unverified."})
        else:
            check("actual_public_export", lambda: browser_export(client.base, output))
        if args.paid_ai or args.paid_explanation_only:
            require(bool(hidden), "Source-hiding checks failed; no paid explanation was attempted.")
            report["paid_requests_attempted"] += 1
            check("genuine_hidden_source_explanation", lambda: paid_explanation(client, hidden, output))
            if args.paid_ai:
                report["paid_requests_attempted"] += 1
                check("genuine_public_excerpt_extraction", lambda: paid_extraction(client, output))
            # Model output must never modify the public evidence registry.
            def unchanged_check():
                current = client.request("/api/assessments/evaluate", {
                    "assessment_id": "framework-for-syngap1", "withdrawn_source_ids": []})["after"]
                require(current == assessments["framework-for-syngap1"]["after"],
                        "A model request modified the public evidence registry.")
                return {"unchanged": True}
            check("model_requests_leave_registry_unchanged", unchanged_check)
    except (CheckFailure, ValueError, TypeError, KeyError) as exc:
        report["checks"].append({"name": "release_verification", "passed": False,
                                 "reason": str(exc) if isinstance(exc, CheckFailure) else "Verification setup/response failed its contract."})
    report["passed"] = bool(report["checks"]) and all(row["passed"] for row in report["checks"])
    expected_paid = ("genuine_hidden_source_explanation", "genuine_public_excerpt_extraction") if args.paid_ai else ("genuine_hidden_source_explanation",)
    report["paid_ai_verified"] = (args.paid_ai or args.paid_explanation_only) and all(
        any(row["name"] == name and row["passed"] for row in report["checks"]) for name in expected_paid)
    save(output, "summary.json", report)
    print(json.dumps(report, indent=2), flush=True)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
