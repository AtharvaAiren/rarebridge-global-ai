"""Public collaborator routes for a disease or an assessment.

Rules:
- Curated overlay contacts are preferred; they carry their own review status.
- A paper author is a potential contact, not the confirmed asset owner.
- Public routes listed on an asset record (public_researcher_routes) are merged
  into a matching curated contact (by URL, then by name) or exposed as a derived
  contact with review_status 'pending' and last_checked null.
- Only public page URLs are served; email addresses are rejected at load time.
"""

from __future__ import annotations

import copy
import re

KIND_ORDER = {"organization": 0, "study_team": 1, "researcher": 2}
DEGREE_WORDS = {"md", "phd", "mph", "msc", "ms", "bsc", "dr", "prof", "rn", "do", "mbbs", "frcp"}
ORG_WORDS = {"foundation", "association", "society", "alliance", "cure", "network", "federation", "trust"}
TEAM_WORDS = {"team", "center", "centre", "lab", "laboratory", "consortium", "group", "page", "study",
              "clinic", "program", "programme", "institute", "registry", "hospital", "department"}


def _name_tokens(name):
    tokens = re.sub(r"[^0-9a-z]+", " ", name.casefold()).split()
    return [t for t in tokens if t not in DEGREE_WORDS]


def _names_match(a, b):
    ta, tb = _name_tokens(a), _name_tokens(b)
    if not ta or not tb:
        return False
    short, long_ = (ta, tb) if len(ta) <= len(tb) else (tb, ta)
    return len(short) >= 2 and long_[:len(short)] == short


def _slug(name):
    return re.sub(r"[^0-9a-z.]+", "-", name.casefold()).strip("-")


def _route_kind(name):
    tokens = set(_name_tokens(name))
    if tokens & ORG_WORDS:
        return "organization"
    if tokens & TEAM_WORDS:
        return "study_team"
    return "researcher"


def sort_contacts(contacts):
    return sorted(contacts, key=lambda c: (KIND_ORDER.get(c["kind"], 9), c["label"].casefold(), c["id"]))


class ContactService:
    def __init__(self, registry):
        self.reg = registry

    def _contact_diseases(self, contact):
        return set(contact.get("disease_ids") or self.reg.associated_diseases(contact["id"]))

    def for_disease(self, disease_id, kinds=None):
        out = []
        for contact in self.reg.contacts.values():
            if kinds and contact["kind"] not in kinds:
                continue
            if disease_id in self._contact_diseases(contact):
                item = copy.deepcopy(contact)
                item["relevance"] = "Recorded as working on this disease in the curated slice."
                out.append(item)
        return sort_contacts(out)

    def _match_route(self, route):
        """Name match first. A URL alone matches only when it is unambiguous, because a
        paper DOI or an organization page can be listed for several people."""
        contacts = list(self.reg.contacts.values())
        by_name = [c for c in contacts if _names_match(route["name"], c["label"])]
        if len(by_name) == 1:
            return by_name[0]
        url = route.get("url")
        by_url = [c for c in contacts if url and c.get("url") == url]
        if len(by_url) > 1:
            kind = _route_kind(route["name"])
            by_url = [c for c in by_url if c["kind"] == kind]
        return by_url[0] if len(by_url) == 1 else None

    def for_bundle(self, bundle):
        """Contacts who could resolve this assessment's open checks."""
        reg = self.reg
        target = bundle["target_disease"]["id"]
        asset = bundle["asset"]
        asset_record = reg.assets.get(asset["id"], {})
        bundle_sources = {reg.canonical_source(sid) or sid for sid in bundle.get("sources", {})}
        asset_sources = {reg.canonical_source(sid) or sid for sid in asset_record.get("source_ids", [])}
        routes = list(asset.get("public_researcher_routes", []))
        selected = {}

        for contact in reg.contacts.values():
            contact_sources = {reg.canonical_source(sid) or sid for sid in contact.get("source_ids", [])}
            on_target = target in self._contact_diseases(contact)
            shares_source = bool(contact_sources & (bundle_sources | asset_sources))
            if on_target and shares_source:
                item = copy.deepcopy(contact)
                item["relevance"] = ("Works on the target disease and is documented by a source this "
                                     "assessment cites.")
                selected[contact["id"]] = item

        for route in routes:
            match = self._match_route(route)
            if match is not None:
                item = selected.get(match["id"]) or copy.deepcopy(match)
                item.setdefault("relevance", "Listed as a public route on this assessment's asset record.")
                if route.get("url") and route["url"] != item.get("url"):
                    extra = item.setdefault("additional_routes", [])
                    if not any(r["url"] == route["url"] for r in extra):
                        extra.append({"name": route["name"], "url": route["url"],
                                      "listed_by": f"asset record in assessment {bundle['id']}",
                                      "review_status": "pending"})
                selected[match["id"]] = item
                continue
            kind = _route_kind(route["name"])
            prefix = {"organization": "org", "study_team": "team", "researcher": "researcher"}[kind]
            contact_id = f"{prefix}:{_slug(route['name'])}"
            if contact_id in selected:
                continue
            source_ids = sorted(asset_sources or bundle_sources)
            selected[contact_id] = {
                "id": contact_id,
                "label": route["name"],
                "kind": kind,
                "url": route.get("url", ""),
                "role": ("Public route listed on the asset record. "
                         + ("Published study investigator; " if kind == "researcher" else "")
                         + "current ownership or availability not established."),
                "source_ids": source_ids,
                "review_status": "pending",
                "last_checked": None,
                "derived_from": "asset.public_researcher_routes",
                "relevance": "Listed as a public route on this assessment's asset record.",
            }
        return sort_contacts(selected.values())
