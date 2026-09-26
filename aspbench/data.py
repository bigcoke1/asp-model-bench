"""The evidence bundles in data/, and the two asp-datagen helpers the benchmarks need.

The bundles and scenarios are asp-datagen's pilot 1 (commit b4ce3db), copied into this repo so it
runs on its own. `facts` is asp-datagen's datagen/check.py and `coverage` its datagen/contract.py,
copied unchanged apart from the imports.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
BUNDLES = DATA / "bundles"
DATAGEN_COMMIT = "b4ce3db"

# Rail Center's coverage.REQUIRED: a category whose required inputs are BLIND or FAILED is
# INSUFFICIENT_EVIDENCE, and production does not ask a model about it.
REQUIRED = {
    "identity": ("credential_inventory", "user"),
    "api_access": ("tool_names",),
    "data_reach": ("mounts", "tool_names"),
    "containment": ("permissions", "user", "mounts"),
    "data_flow": ("observed_destinations",),
    "injection_exposure": ("tool_names", "system_prompt_present"),
    "grant_exercise_gap": ("mcp_servers_declared", "tool_names"),
    "text_signals": ("skills_inventory",),
}


def bundles() -> dict[str, dict]:
    """Every bundle in data/bundles, by bundle_id, in file order."""
    return {p.stem: json.loads(p.read_text()) for p in sorted(BUNDLES.glob("*.json"))}


def scenarios() -> dict[str, dict]:
    """The sampled facts behind each bundle, by bundle_id. The labeller never sees these."""
    return {r["bundle_id"]: r for r in map(json.loads, (DATA / "scenarios.jsonl").open())}


def coverage(bundle: dict, category: str) -> list[str]:
    """Required inputs that leave the category INSUFFICIENT_EVIDENCE: BLIND or FAILED, or missing."""
    attrs = bundle["attributes"]
    return [a for a in REQUIRED[category] if a not in attrs or attrs[a]["status"] in ("BLIND", "FAILED")]


def shown(b: dict, attribute: str) -> bool:
    return b["attributes"][attribute]["status"] in ("ANSWERED", "PARTIAL")


def facts(s: dict, b: dict) -> dict:
    """The risky facts a bundle visibly shows: from the scenario, but only where the attribute
    carrying the fact is ANSWERED or PARTIAL, since a scorer never sees the scenario."""
    host = (shown(b, "permissions") and s["privileged"]) or \
           (shown(b, "mounts") and bool({"docker_socket", "host_root"} & set(s["mounts"])))
    baked = (not s["gateway_fronted"] and shown(b, "credential_provenance")
             and any(c["provenance"] == "baked" and c["class"] != "secret_ref" for c in s["credentials"]))
    return {
        "host_reach": host,                       # containment: privileged, Docker socket or host /
        "priv_root": shown(b, "permissions") and s["privileged"] and s["run_as"] == "root",
        "baked_secret": baked,                    # identity: the baked_secret hard cap's condition
        "no_creds": b["attributes"]["credential_inventory"]["status"] == "ABSENT",
    }
