#!/usr/bin/env python3
"""Alignment detection: given two snapshots of one attribute, is the later one misaligned?

The items are alignment_detection/data/labels.jsonl (the rows marked `asked`), built by make_pairs.py:
each bundle in data/bundles as the earlier snapshot, and an edited copy as the later one, so every
label is known. Misaligned means the later snapshot states a different fact about the agent; the same
fact written differently is aligned.

Every system gets the SAME text per item (the attribute's name and both snapshots as JSON) and
the SAME yes/no question:
  - exact-diff:       a baseline; misaligned when the two snapshots differ at all;
  - normalized-diff:  a baseline; misaligned when they differ after generic clean-up (lists and keys
                      sorted, strings lower-cased and trimmed, trailing slashes and the
                      collector's method and note dropped);
  - laya, jevk5:      the question as a typed yes/no; misaligned when P(yes) >= 0.5;
  - qwen, qwen32b:    the question in a prompt, answered as JSON {"drift": true|false};
  - gemini:           the same prompt.

Each system answers each item --runs times (default 1: Laya and JevK5 are deterministic, and the
LLMs run at temperature 0); the prediction is the majority. Results go to
results/alignment_results.json, with every item, every answer and the metrics.

From the repo root (or through the Makefile: `make alignment`, `make alignment-report`):

    python -m alignment_detection.bench [--systems exact-diff normalized-diff laya jevk5 qwen qwen32b gemini]
    python -m alignment_detection.bench --systems qwen --merge    # add one system, keep the rest
    python -m alignment_detection.bench --report                  # print the tables, no calls
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import statistics as st
import time
import urllib.error
from pathlib import Path

from aspbench.clients import gemini_json, jevk5_model, laya_agent, ollama_json
from aspbench.data import DATAGEN_COMMIT, bundles

HERE = Path(__file__).parent
DATA = HERE / "data"

# The text the models see (INSTRUCTIONS, CRITERIA, llm_prompt and Qwen.SCHEMA) still says "drift":
# it is kept exactly as the stored results were run.
INSTRUCTIONS = (
    "Two snapshots of the same attribute from an AI agent's security evidence bundle, collected at "
    "different times. Has the attribute drifted? It has drifted if the later snapshot states a "
    "different fact about the agent: a different value, setting, item or version, or a change in "
    "whether the attribute could be observed. It has not drifted if it states the same fact written "
    "differently, for example with items or keys in another order, different letter case, or "
    "equivalent notation, or if only the collector's method or note is worded differently."
)
CRITERIA = {"true": "drifted: the later snapshot states a different fact",
            "false": "not drifted: the same fact, possibly written differently"}
QUESTION = {"type": "noul", "instructions": INSTRUCTIONS, "criteria": CRITERIA}

TIERS = ["misaligned: plain", "misaligned: subtle", "aligned: formatting", "aligned: notation", "aligned: identical"]


def state(name: str, before: dict, after: dict) -> str:
    dump = lambda a: json.dumps(a, ensure_ascii=False)
    return f"Attribute: {name}\nEarlier snapshot: {dump(before)}\nLater snapshot: {dump(after)}"


def llm_prompt(text: str) -> str:
    return f"{INSTRUCTIONS}\n\n{text}\n\n" 'Answer with JSON only: {"drift": true} or {"drift": false}'


# --- systems: one call answers one item once, returning {"misaligned": bool or None, "p": float?} ---

class ExactDiff:
    key, label = "exact-diff", "exact diff (baseline)"
    name, settings = "exact-diff", {"rule": "misaligned when the two snapshots' JSON differs at all"}

    def __call__(self, item, run):
        return {"misaligned": json.dumps(item["before"]) != json.dumps(item["after"])}


def norm(x):
    if isinstance(x, dict):
        return {str(k).lower(): norm(v) for k, v in sorted(x.items())}
    if isinstance(x, list):
        return sorted((norm(v) for v in x), key=lambda v: json.dumps(v, sort_keys=True))
    if isinstance(x, str):
        s = x.strip().lower()
        return s.rstrip("/") if len(s) > 1 else s
    return x


class NormalizedDiff:
    key, label = "normalized-diff", "normalized diff (baseline)"
    name = "normalized-diff"
    settings = {"rule": "misaligned when status or value differs after sorting lists and keys, lower-casing, "
                        "trimming and dropping trailing slashes; method and note ignored"}

    def __call__(self, item, run):
        k = lambda a: json.dumps({"status": a["status"], "value": norm(a.get("value"))}, sort_keys=True)
        return {"misaligned": k(item["before"]) != k(item["after"])}


class Laya:
    key, label = "laya", "stock Laya"

    def __init__(self, agent):
        self.agent = agent
        self.name = "laya (typed-decisions, stock)"
        self.settings = {"checkpoint": "convaiinnovations/laya typed-decisions", "laya": "0.3.7",
                         "question": "noul", "threshold": 0.5}

    def __call__(self, item, run):
        p = self.agent.predict(item["state"], {"misaligned": QUESTION})["answers"]["misaligned"]["noul"]
        return {"misaligned": p >= 0.5, "p": p}


class JevK5:
    key, label = "jevk5", "JevK5"

    def __init__(self):
        self.model, settings = jevk5_model()
        self.name = "jevk5 (4b v0.3 Q8_0, llama.cpp)"
        self.settings = {**settings, "question": "noul", "threshold": 0.5}

    def __call__(self, item, run):
        p = self.model.decide(item["state"], QUESTION)["noul"]
        return {"misaligned": p >= 0.5, "p": round(p, 4)}


class Qwen:
    key, label = "qwen", "qwen3:14b"
    SCHEMA = {"type": "object", "required": ["drift"], "properties": {"drift": {"type": "boolean"}}}

    def __init__(self, model="qwen3:14b"):
        self.model = model
        self.name = f"{model} (local)"
        self.settings = {"model": model, "temperature": 0, "think": False, "server": "ollama"}

    def __call__(self, item, run):
        r = ollama_json(self.model, llm_prompt(item["state"]), self.SCHEMA)
        d = r.get("drift") if isinstance(r, dict) else None
        return {"misaligned": d if isinstance(d, bool) else None}


class Qwen32(Qwen):
    """qwen3:32b (Q4_K_M), asked exactly as qwen3:14b is."""
    key, label = "qwen32b", "qwen3:32b"

    def __init__(self):
        super().__init__("qwen3:32b")


class Gemini:
    key, label = "gemini", "Gemini"

    def __init__(self, model):
        self.model = model
        self.name = f"gemini ({model})"
        self.settings = {"model": model, "temperature": 0, "output": "JSON"}

    def __call__(self, item, run):
        r = gemini_json(self.model, [{"role": "user", "content": llm_prompt(item["state"])}])
        d = r.get("drift") if isinstance(r, dict) else None
        return {"misaligned": d if isinstance(d, bool) else None}


# --- items and metrics ---

def items():
    before = bundles()
    after = {p.stem: json.loads(p.read_text()) for p in sorted((DATA / "after").glob("*.json"))}
    out = []
    for r in map(json.loads, (DATA / "labels.jsonl").open()):
        if not r["asked"]:
            continue
        b, a = before[r["before"]]["attributes"][r["attribute"]], after[r["after"]]["attributes"][r["attribute"]]
        out.append({**{k: r[k] for k in ("id", "attribute", "misaligned", "tier", "change", "detail")},
                    "before": b, "after": a, "state": state(r["attribute"], b, a)})
    return out


def auroc(scores, labels):
    """Chance that a misaligned item gets a higher P(misaligned) than an aligned one (ties count half)."""
    pos = [s for s, y in zip(scores, labels) if y]
    neg = [s for s, y in zip(scores, labels) if not y]
    if not pos or not neg:
        return None
    wins = sum((p > n) + 0.5 * (p == n) for p in pos for n in neg)
    return round(wins / (len(pos) * len(neg)), 3)


def summarize(its, results):
    truth = {it["id"]: it for it in its}
    out = {}
    for name, rows in results.items():
        tp = fp = fn = tn = bad = 0
        by = {}
        for r in rows:
            it, pred = truth[r["id"]], r["pred"]
            bad += pred is None
            hit = pred is not None and pred == it["misaligned"]
            if it["misaligned"]:
                tp, fn = tp + hit, fn + (not hit)
            else:
                tn, fp = tn + hit, fp + (not hit)
            for k in (it["tier"], it["change"]):
                d = by.setdefault(k, {"n": 0, "right": 0, "misaligned": it["misaligned"]})
                d["n"] += 1
                d["right"] += hit
        prec = tp / (tp + fp) if tp + fp else 0.0
        rec = tp / (tp + fn) if tp + fn else 0.0
        probs = [(r["p"], truth[r["id"]]["misaligned"]) for r in rows if r.get("p") is not None]
        out[name] = {
            "tp": tp, "fp": fp, "fn": fn, "tn": tn, "invalid": bad,
            "precision": round(prec, 3), "recall": round(rec, 3),
            "f1": round(2 * prec * rec / (prec + rec), 3) if prec + rec else 0.0,
            "accuracy": round((tp + tn) / len(rows), 3),
            "auroc": auroc(*zip(*probs)) if len(probs) == len(rows) else None,
            "by": by,
            "median_ms_per_call": round(st.median(ms for r in rows for ms in r["ms"])) if any(r["ms"] for r in rows) else None,
        }
    return out


def verdict(f1: float) -> str:
    return "✓ good" if f1 >= 0.9 else "~ fair" if f1 >= 0.75 else "✗ poor"


def table(doc) -> str:
    s, systems = doc["summary"], doc["meta"]["systems"]
    names = sorted(s, key=lambda n: -s[n]["f1"])
    label = {n: systems[n]["label"] for n in names}
    ms = lambda n: "–" if s[n]["median_ms_per_call"] is None else f"{s[n]['median_ms_per_call']:,} ms"
    out = ["| rank | system | verdict | F1 | precision | recall | accuracy | AUROC | time per call |",
           "|---|---|---|---|---|---|---|---|---|"]
    for i, n in enumerate(names, 1):
        d = s[n]
        auc = "–" if d["auroc"] is None else f"{d['auroc']:.2f}"
        out.append(f"| {i} | {label[n]} | {verdict(d['f1'])} | **{d['f1']:.2f}** | {d['precision']:.2f} | {d['recall']:.2f} | "
                   f"{d['accuracy']:.2f} | {auc} | {ms(n)} |")

    def cell(d, misaligned):
        if misaligned:
            return f"{d['right']} / {d['n']}"
        wrong = d["n"] - d["right"]
        return f"{wrong} / {d['n']}" + (" ✓" if wrong == 0 else "")

    rows = [("Misalignment caught: plain (add, remove, replace, evidence lost or gained)", "misaligned: plain", True),
            ("Misalignment caught: subtle (one field or one character)", "misaligned: subtle", True),
            ("False alarms: reformatted (reordered, note reworded)", "aligned: formatting", False),
            ("False alarms: equivalent notation (case, slash, uid 0, CAP_, v1, :443, read-only)", "aligned: notation", False),
            ("False alarms: identical", "aligned: identical", False)]
    out += ["", "| | " + " | ".join(label[n] for n in names) + " |", "|---|" + "---|" * len(names)]
    out += [f"| {q} | " + " | ".join(cell(s[n]["by"][t], dr) for n in names) + " |" for q, t, dr in rows]

    kinds = sorted({k for n in names for k, d in s[n]["by"].items() if k not in TIERS},
                   key=lambda k: (not s[names[0]]["by"][k]["misaligned"], k))
    out += ["", "| change | label | " + " | ".join(label[n] for n in names) + " |", "|---|---|" + "---|" * len(names)]
    for k in kinds:
        d0 = s[names[0]]["by"][k]
        out.append(f"| `{k}` | {'misaligned: caught' if d0['misaligned'] else 'aligned: false alarms'} | "
                   + " | ".join(cell(s[n]["by"][k], d0["misaligned"]) for n in names) + " |")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--systems", nargs="+", default=["exact-diff", "normalized-diff", "laya", "jevk5", "qwen", "gemini"],
                    choices=["exact-diff", "normalized-diff", "laya", "jevk5", "qwen", "qwen32b", "gemini"])
    ap.add_argument("--runs", type=int, default=1)
    ap.add_argument("--gemini-model", default="gemini-3.5-flash-lite")
    ap.add_argument("--out", default=str(HERE / "results/alignment_results.json"))
    ap.add_argument("--merge", action="store_true", help="keep results already in --out for systems not run now")
    ap.add_argument("--report", action="store_true", help="print the tables from --out without running anything")
    ap.add_argument("--check", action="store_true", help="rebuild the inputs and confirm they match --out, no model calls")
    args = ap.parse_args()
    if args.report:
        print(table(json.loads(Path(args.out).read_text())))
        return

    its = items()
    if args.check:
        stored = json.loads(Path(args.out).read_text())["items"]
        same = [(i["id"], i["misaligned"], i["state"]) for i in stored] == [(i["id"], i["misaligned"], i["state"]) for i in its]
        print("alignment inputs: match the stored results" if same else "alignment inputs: DIFFER from the stored results")
        raise SystemExit(0 if same else 1)
    make = {"exact-diff": ExactDiff, "normalized-diff": NormalizedDiff, "laya": lambda: Laya(laya_agent()),
            "jevk5": JevK5, "qwen": Qwen, "qwen32b": Qwen32, "gemini": lambda: Gemini(args.gemini_model)}
    systems = [make[k]() for k in args.systems]
    results, status, settings = {}, {}, {}
    if args.merge and Path(args.out).exists():
        old = json.loads(Path(args.out).read_text())
        if [(i["id"], i["state"]) for i in old["items"]] != [(i["id"], i["state"]) for i in its]:
            raise SystemExit("--merge refused: the items differ from the ones in --out, so the results would not compare")
        running = {s.name for s in systems}
        results = {k: v for k, v in old["results"].items() if k not in running}
        status = {k: v for k, v in old["meta"]["status"].items() if k not in running}
        settings = {k: v for k, v in old["meta"]["systems"].items() if k not in running}
    for sysm in systems:
        key, rows = sysm.key, []
        try:
            for n, it in enumerate(its):
                runs, ps, ms = [], [], []
                for run in range(args.runs):
                    t = time.perf_counter()
                    r = sysm(it, run)
                    if key not in ("exact-diff", "normalized-diff"):
                        ms.append(round((time.perf_counter() - t) * 1000))
                    runs.append(r["misaligned"])
                    if "p" in r:
                        ps.append(r["p"])
                valid = [x for x in runs if x is not None]
                pred = sum(valid) * 2 > len(valid) if valid else None  # majority; a tie counts as aligned
                rows.append({"id": it["id"], "runs": runs, "pred": pred, "ms": ms,
                             **({"p": round(st.mean(ps), 4)} if ps else {})})
                print(f"  {sysm.name} {n + 1}/{len(its)}", end="\r", flush=True)
            results[sysm.name], status[sysm.name] = rows, "ok"
        except urllib.error.URLError as e:
            status[sysm.name] = f"not run: {e}"
        settings[sysm.name] = {"label": sysm.label, **sysm.settings}
        print(f"{sysm.name}: {status[sysm.name]}          ", flush=True)

    doc = {
        "meta": {
            "run_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            "runs_per_item": args.runs, "aggregate": "majority of the valid runs; an invalid answer counts as wrong",
            "question": QUESTION, "positive_class": "misaligned",
            "input": "the attribute's name and both snapshots as JSON; data/bundles (earlier) and alignment_detection/data/after (later)",
            "asp_datagen_commit": DATAGEN_COMMIT, "systems": settings, "status": status,
        },
        "items": [{k: it[k] for k in ("id", "attribute", "misaligned", "tier", "change", "detail", "state")} for it in its],
        "results": results,
    }
    doc["summary"] = summarize(its, results)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(doc, indent=2, ensure_ascii=False))
    print("\n" + table(doc))
    print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
