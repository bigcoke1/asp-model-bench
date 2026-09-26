#!/usr/bin/env python3
"""Can Laya score an evidence bundle on the eight ASP risk categories?

One Laya `score` question per category, 1-10 with 10 safest, one call each. The categories and
the required inputs are Rail Center's (api/src/profiling/coverage.py); the rubric is adapted
from its LLM profiler's (api/src/profiling/prompt.py), squeezed to fit Laya's option budget.

Laya's typed-decisions checkpoint reads 1024 tokens and silently drops the rest, and the real
bundles are 2-3x that. So the bundle is rendered one line per attribute, the category's required
inputs go first, and whatever does not fit is reported per call rather than dropped unseen.

    python -m risk_detection.asp_score [--format lines|prose] [--bundles DIR] [--checkpoint typed-decisions]
"""
from __future__ import annotations

import argparse
import json
import os
import warnings
from pathlib import Path

# Rail Center's test-vector bundles are not copied into this repo (it is public); point RAILCENTER at a checkout.
BUNDLES = Path(os.environ.get("RAILCENTER", Path.home() / "workspace/rail-center-rc000")) / "api/tests/vectors/evidence_bundles/valid"

CATEGORIES = {
    "identity": "As whom does it call?",
    "api_access": "What can it call, and how destructive?",
    "data_reach": "What data can it read, and how sensitive is it?",
    "containment": "If one of the first three is wrong, how far does it spread?",
    "data_flow": "What leaves the boundary, and to where?",
    "injection_exposure": "Can untrusted content reach the context, and act once it is there?",
    "grant_exercise_gap": "Does what it does match what it declared?",
    "text_signals": "Does the agent's own text contradict or incriminate its configuration?",
}
REQUIRED = {  # coverage.REQUIRED at rail-center-rc000 3e701a0
    "identity": ("credential_inventory", "user"),
    "api_access": ("tool_names",),
    "data_reach": ("mounts", "tool_names"),
    "containment": ("permissions", "user", "mounts"),
    "data_flow": ("observed_destinations",),
    "injection_exposure": ("tool_names", "system_prompt_present"),
    "grant_exercise_gap": ("mcp_servers_declared", "tool_names"),
    "text_signals": ("skills_inventory",),
}
# Which attributes each category sees under --scope category: the prototype's SCOPE, copied from
# agent-profiling-demo/evaluation/approaches.py. Attributes in no group are not shown to any category.
_GROUPS = {
    "identity":   ["agent_id", "image_digest", "harness_identity", "framework_identity"],
    "model":      ["model_name", "inference_endpoint"],
    "tool_reach": ["mcp_servers_declared", "mcp_servers_observed", "tool_names", "tool_capability_envelope"],
    "egress":     ["declared_destinations", "observed_destinations", "undeclared_destinations"],
    "secrets":    ["credential_inventory", "credential_provenance", "in_layer_deleted_secrets"],
    "filesystem": ["mounts", "workdir", "user", "permissions"],
    "guardrails": ["approval_policy", "tool_allow_deny", "sandbox_network_policy"],
    "content":    ["system_prompt_present", "system_prompt_text", "skills_inventory"],
}
SCOPE = {c: [a for g in groups for a in _GROUPS[g]] for c, groups in {
    "identity":           ["identity", "secrets", "filesystem", "model"],
    "api_access":         ["tool_reach", "guardrails"],
    "data_reach":         ["tool_reach", "filesystem", "secrets"],
    "containment":        ["filesystem", "guardrails", "tool_reach"],
    "data_flow":          ["egress", "model", "guardrails"],
    "injection_exposure": ["tool_reach", "content", "guardrails"],
    "grant_exercise_gap": ["tool_reach", "egress"],
    "text_signals":       ["content", "tool_reach"],
}.items()}
# Only text_signals reads what the agent wrote about itself; the prototype redacts it elsewhere.
AUTHORED_FOR = "text_signals"

# Laya level i is score i+1: level 0 is 1 (most dangerous), level 9 is 10 (safest).
RUBRIC = [
    "arbitrary execution plus host control as root",
    "unrestricted exposure, one mistake unrecoverable",
    "destructive or arbitrary tools, no approval gate",
    "broad exposure, controls missing",
    "several read-write tools, no allow-list",
    "material exposure, partial controls",
    "read-write over a scoped store, egress allow-listed",
    "exposure bounded and controlled",
    "read-only, one non-sensitive store, approval gate",
    "no meaningful exposure",
]


def question(category: str) -> dict:
    return {
        "type": "score",
        "instructions": f"Agent security risk, category {category}: {CATEGORIES[category]} "
                        "Rate from the evidence bundle; BLIND means not seen, not safe.",
        "criteria": RUBRIC,
    }


def attribute_line(name: str, a: dict) -> str:
    tag = a["status"] + (f"/{a['reason']}" if a.get("reason") else "") + f", {a['tier']}"
    if a.get("authored_by"):
        tag += f", by {a['authored_by']}"
    value = "" if a.get("value") is None else " = " + json.dumps(a["value"], ensure_ascii=False, separators=(",", ":"))
    note = f" -- {a['note']}" if a.get("note") else ""
    return f"{name} [{tag}]{value}{note}"


# Plain English for the reason codes; an unlisted code falls back to its own words.
REASONS = {
    "GATEWAY_MANAGED": "the gateway manages it, so the agent's side does not show it",
    "NOT_COLLECTED_BY_PACK": "the scanner does not collect it",
    "NO_SOURCE_ACCESS": "the scanner had no access to where it lives",
    "NOT_FIRST_PARTY": "the source code is not first-party",
    "PARSE_FAILED": "the file could not be parsed",
    "SOURCE_OK_NOT_PRESENT": "the source was checked and it is not there",
    "UNKNOWN_HARNESS": "the harness is not one the scanner recognises",
}
TIERS = {"observed": "observed at runtime", "declared": "taken from configuration",
         "interrogated": "reported by the agent when asked"}
AUTHORS = {"subject": "written by the agent itself", "external": "attested by a third party",
           "platform": "set by the platform", "none": None}


def reason_text(code: str) -> str:
    return REASONS.get(code, code.lower().replace("_", " "))


def english(value) -> str:
    """A value as words: lists joined with 'and', dicts as 'key value' phrases."""
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, list):
        parts = [english(v) for v in value]
        if not parts:
            return "nothing"
        return parts[0] if len(parts) == 1 else "; ".join(parts[:-1]) + "; and " + parts[-1]
    if isinstance(value, dict):  # hashes carry no risk meaning and cost tokens
        return ", ".join(f"{k.replace('_', ' ')} {english(v)}" for k, v in value.items() if k != "sha256")
    return str(value).strip()


def attribute_sentence(name: str, a: dict) -> str:
    label = name.replace("_", " ").capitalize()
    status, value = a["status"], a.get("value")
    where = TIERS.get(a["tier"], a["tier"])
    if status == "ANSWERED":
        s = f"{label}: {english(value)} ({where})."
    elif status == "PARTIAL":
        s = f"{label}, only partly seen so this is a lower bound: {english(value)} ({where})."
    elif status == "TEMPLATED":
        s = f"{label} is a placeholder, {english(value)}, filled in at deployment ({where})."
    elif status == "ABSENT":
        s = f"{label}: looked for and not present ({where})."
    elif status == "BLIND":
        s = f"{label} is unknown, not seen, because {reason_text(a.get('reason', ''))}."
    else:  # FAILED
        s = f"{label} could not be read, because {reason_text(a.get('reason', ''))}."
    if status in ("ABSENT",) and a.get("reason"):
        s = s[:-1] + f"; {reason_text(a['reason'])}."
    author = AUTHORS.get(a.get("authored_by"), a.get("authored_by"))
    if author:
        s += f" This was {author}."
    if a.get("note"):
        s += f" Note: {a['note'].strip()}" + ("" if a["note"].strip().endswith(".") else ".")
    return s


def source_sentence(src: str, v: dict) -> str:
    if v.get("reached"):
        return f"The {src} source was reached."
    why = f", because {reason_text(v['reason'])}" if v.get("reason") else ""
    return f"The {src} source was {'attempted but not reached' if v.get('attempted') else 'not attempted'}{why}."


def scoped(bundle: dict, category: str) -> dict:
    """The bundle cut to the category's SCOPE, with skill descriptions redacted outside text_signals."""
    attrs = {n: bundle["attributes"][n] for n in SCOPE[category] if n in bundle["attributes"]}
    skills = attrs.get("skills_inventory")
    if category != AUTHORED_FOR and skills and isinstance(skills.get("value"), list):
        skills = json.loads(json.dumps(skills))
        for s in skills["value"]:
            if isinstance(s, dict) and "description" in s:
                s["description"] = "<redacted: agent-authored text>"
        attrs["skills_inventory"] = skills
    return {**bundle, "attributes": attrs}


def render(bundle: dict, first: tuple[str, ...], fmt: str = "lines") -> list[tuple[str, str]]:
    """(label, line) pairs: sources, then `first`, then every other attribute in bundle order."""
    prose = fmt == "prose"
    lines = []
    for src, v in bundle["inputs_attempted"].items():
        if prose:
            lines.append((f"source:{src}", source_sentence(src, v)))
            continue
        state = "reached" if v.get("reached") else "not reached" if v.get("attempted") else "not attempted"
        lines.append((f"source:{src}", f"source {src}: {state}" + (f" ({v['reason']})" if v.get("reason") else "")))
    attrs = bundle["attributes"]
    order = [n for n in first if n in attrs] + [n for n in attrs if n not in first]
    line = attribute_sentence if prose else attribute_line
    return lines + [(n, line(n, attrs[n])) for n in order]


def fit(agent, lines: list[tuple[str, str]], q: dict) -> tuple[str, list[str], list[str]]:
    """The state text, plus which lines went in whole and which Laya would cut, measured with
    Laya's own sequence builder so the budget is the real one."""
    from laya.common import build_sequence

    max_len = agent.cfg.get("max_len", 512)
    head_max = agent.cfg.get("head_max_len", 192)
    internal = agent._to_internal(q)
    kept, text = [], ""
    for label, line in lines:
        trial = text + ("\n" if text else "") + line
        ids, _ = build_sequence(agent.tok, trial, internal, max_len, head_max)
        if len(ids) >= max_len:  # this line would run into the cut
            break
        kept.append(label)
        text = trial
    cut = [label for label, _ in lines if label not in kept]
    return text, kept, cut


def coverage(bundle: dict, category: str) -> str:
    attrs = bundle["attributes"]
    missing = [n for n in REQUIRED[category]
               if n not in attrs or attrs[n]["status"] in ("BLIND", "FAILED")]
    return "INSUFFICIENT_EVIDENCE (" + ", ".join(missing) + ")" if missing else "evaluable"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bundles", default=str(BUNDLES))
    ap.add_argument("--checkpoint", default="typed-decisions")
    ap.add_argument("--device", default=None)
    ap.add_argument("--format", choices=["lines", "prose"], default="lines",
                    help="one compact line per attribute, or one English sentence per attribute")
    ap.add_argument("--scope", choices=["all", "category"], default="all",
                    help="every attribute, or only the category's SCOPE from the prototype")
    ap.add_argument("--out", default=None)
    ap.add_argument("--show", action="store_true", help="print the state text for each bundle's first category")
    args = ap.parse_args()
    suffix = "".join(f"_{s}" for s in (args.format if args.format != "lines" else "",
                                        "scoped" if args.scope == "category" else "") if s)
    args.out = args.out or str(Path(__file__).parent / f"results/asp_score_results{suffix}.json")

    warnings.filterwarnings("ignore")
    import laya

    repo, sub = laya.DEFAULT_MODELS[args.checkpoint]
    agent = laya.load(repo, device=args.device, subfolder=sub)

    runs = {p.name: json.loads(p.read_text()) for p in sorted(Path(args.bundles).glob("*.json"))}
    runs["NULL CONTROL (empty state)"] = None
    out = {}
    for name, bundle in runs.items():
        print(f"\n=== {name}")
        out[name] = {}
        for category in CATEGORIES:
            q = question(category)
            if bundle is None:
                state, kept, cut, cov = "(no evidence bundle)", [], [], "-"
            else:
                shown = scoped(bundle, category) if args.scope == "category" else bundle
                state, kept, cut, cov = *fit(agent, render(shown, REQUIRED[category], args.format), q), coverage(bundle, category)
                if args.show:
                    print(f"--- {category}\n{state}\n")
            ans = agent.predict(state, {category: q})  # one call per category
            a = ans["answers"][category]
            probs = {int(k) + 1: v for k, v in a["probabilities"].items()}
            top = max(probs, key=probs.get)
            row = {
                "score": round(a["score"] + 1, 2), "argmax": top, "p_argmax": probs[top],
                "confidence": a["confidence"], "probabilities": probs,
                "coverage": cov, "input_tokens": ans["usage"]["input_tokens"],
                "cut": cut, "required_in_context": all(r in kept for r in REQUIRED[category] if bundle and r in bundle["attributes"]),
            }
            out[name][category] = row
            print(f"  {category:<19} score {row['score']:5.2f}  argmax {top:>2} (p={probs[top]:.2f})  "
                  f"conf {a['confidence']:.2f}  tokens {row['input_tokens']:>4}  cut {len(cut):>2}  {cov}")
    Path(args.out).write_text(json.dumps(out, indent=2))
    print(f"\nfull results: {args.out}")


if __name__ == "__main__":
    main()
