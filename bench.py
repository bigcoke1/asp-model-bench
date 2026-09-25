#!/usr/bin/env python3
"""Stock Laya vs Gemini vs qwen3:14b vs JevK5 (and Jev, when it answers) on the same ASP scoring questions.

Five systems get the SAME text and the SAME question for each item:
  - items: the asp-datagen pilot bundles, `identity` and `containment`, skipping any the coverage
    profiler would mark INSUFFICIENT_EVIDENCE, plus one empty-state null control per category;
  - text: the bundle cut to the category's scope and rendered as English (asp_score.py
    --format prose --scope category), trimmed to fit Laya's 1024 tokens so Laya sees all of it;
  - question: asp_score.question(), ten levels scored 1-10 with 10 safest. Ten, not the design
    doc's eleven, because Jev takes at most ten score levels.

A sixth, `gemini-prod`, is Gemini asked the way Rail Center's LLM profiler asks it: the whole
bundle through rail-center's own `profiling.prompt.render_prompt` (v7), every category coverage
clears in one call, scored 0-10. It never sees the empty-state control, because production never
asks a model when coverage clears nothing.

Each system answers each item --runs times (default 3) and the median is its score. The LLMs run
at temperature 0, as Rail Center's profiler calls its model; Laya and JevK5 generate nothing and
read their answer from the model's probabilities.

There is no ground truth, so the systems are compared on whether their scores follow the facts a
bundle visibly shows (asp-datagen datagen/check.py), on the null control, and on how they rank
the bundles relative to each other.

Results go to bench_results.json: settings, every item with the exact text sent, every run, the
medians, and the summary, so a later reader needs nothing but that file.

Keys come from the environment: GOOGLE_API_KEY for Gemini; JEV_API_KEY (+ JEV_BASE_URL, JEV_MODEL)
for Jev. qwen3:14b is served by a local Ollama; JevK5 by a local llama-server (JEVK5_URL):

    llama-server --hf-repo alibiserikbay/JevK5-GGUF --hf-file jevk5-4b-v0.3-Q8_0.gguf \
        -c 8192 -ngl 99 --port 8093

    python bench.py [--systems laya gemini gemini-prod qwen jevk5] [--runs 3]
    python bench.py --systems gemini-prod --merge     # add one system to the existing results
    python bench.py --report                          # print the tables from bench_results.json
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import statistics as st
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import warnings
from pathlib import Path

import asp_score as A

HERE = Path(__file__).parent
DATAGEN = Path("/Users/easonmeng/Desktop/asp-datagen")
RAILCENTER = Path("/Users/easonmeng/workspace/rail-center-rc000")
sys.path.insert(0, str(DATAGEN))
from datagen.check import facts  # noqa: E402
from datagen.contract import coverage  # noqa: E402

CATS = ["identity", "containment"]
NULL_STATE = "(no evidence bundle)"
GEMINI_OPENAI = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"


class NotAsked(Exception):
    """This system never scores this item, by design rather than by failure."""


def post(url: str, headers: dict, body: dict, timeout: int = 300) -> dict:
    # A User-Agent of our own: thejevai.com's Cloudflare refuses Python's default one (error 1010).
    req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json", "User-Agent": "asp-bench/0.1", **headers})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def llm_prompt(state: str, cat: str) -> str:
    """The same question Laya and Jev get, spelled out for a text model."""
    q = A.question(cat)
    levels = "\n".join(f"  level {i}: {c}" for i, c in enumerate(q["criteria"]))
    return (f"{q['instructions']}\n\nPick exactly one level:\n{levels}\n\nEVIDENCE:\n{state}\n\n"
            'Return ONLY JSON: {"level": <integer 0-9>}')


def level_to_score(lv):
    """A 0-9 level as a 1-10 score, or None when the reply is not a usable level."""
    ok = isinstance(lv, (int, float)) and not isinstance(lv, bool) and 0 <= lv <= 9
    return int(lv) + 1 if ok else None


# --- systems: one call answers one item once, returning {"score": number or None, ...} ---

class Laya:
    key, label = "laya", "stock Laya"

    def __init__(self, agent):
        self.agent = agent
        self.name = "laya (typed-decisions, stock)"
        self.settings = {"checkpoint": "convaiinnovations/laya typed-decisions", "laya": "0.3.7",
                         "deterministic": True, "scale": "1-10", "input": "scoped prose + short question"}

    def __call__(self, item, run):
        a = self.agent.predict(item["state"], {item["category"]: A.question(item["category"])})["answers"][item["category"]]
        probs = [a["probabilities"][str(i)] for i in range(10)]
        return {"score": round(a["score"] + 1, 4), "p_top": max(probs)}


class Gemini:
    """The short question, called the way Rail Center calls a model: OpenAI-compatible, temperature 0, JSON."""
    key, label = "gemini", "Gemini, short prompt"

    def __init__(self, model):
        self.model, self.api_key = model, os.environ.get("GOOGLE_API_KEY")
        self.name = f"gemini ({model})"
        self.settings = {"model": model, "temperature": 0, "scale": "1-10", "input": "scoped prose + short question"}

    def __call__(self, item, run):
        r = post(GEMINI_OPENAI, {"Authorization": f"Bearer {self.api_key}"},
                 {"model": self.model, "temperature": 0, "response_format": {"type": "json_object"},
                  "messages": [{"role": "user", "content": llm_prompt(item["state"], item["category"])}]})
        try:
            return {"score": level_to_score(json.loads(r["choices"][0]["message"]["content"])["level"])}
        except (KeyError, TypeError, json.JSONDecodeError):
            return {"score": None}


class GeminiProd:
    """Gemini with Rail Center's production prompt, built by rail-center's own code.

    One call per bundle per run asks every category coverage clears, as the profiling job does;
    both of the bundle's items read their score from that one reply. The raw model score is used,
    before the mixer's clamps, and it is on production's 0-10 scale.
    """
    key, label = "gemini-prod", "Gemini, production prompt"

    def __init__(self, model):
        sys.path.insert(0, str(RAILCENTER / "api/src"))
        from profiling.bundle import EvidenceBundle
        from profiling.catalogue import load_catalogue
        from profiling.coverage import Outcome, assess_coverage
        from profiling.prompt import PROMPT_VERSION, render_prompt
        self.bundle, self.render, self.cov, self.evaluable = EvidenceBundle, render_prompt, assess_coverage, Outcome.EVALUABLE
        self.catalogue = load_catalogue()
        self.model, self.api_key, self.replies = model, os.environ.get("GOOGLE_API_KEY"), {}
        commit = subprocess.run(["git", "-C", str(RAILCENTER), "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
        self.name = f"gemini ({model}) + production prompt {PROMPT_VERSION}"
        self.settings = {"model": model, "temperature": 0, "scale": "0-10", "prompt": f"rail-center profiling/prompt.py {PROMPT_VERSION}",
                         "rail_center_commit": commit, "input": "whole bundle via render_prompt; all categories coverage clears, one call"}

    def __call__(self, item, run):
        if item["bundle_id"] == "NULL":
            raise NotAsked("production never asks a model when coverage clears nothing")
        key, fresh = (item["bundle_id"], run), (item["bundle_id"], run) not in self.replies
        if fresh:
            b = self.bundle.model_validate_json((DATAGEN / f"data/bundles/{item['bundle_id']}.json").read_bytes())
            asked = [c for c, cov in self.cov(b).items() if cov.outcome is self.evaluable]
            p = self.render(b, asked, self.catalogue)
            t = time.perf_counter()
            r = post(GEMINI_OPENAI, {"Authorization": f"Bearer {self.api_key}"},
                     {"model": self.model, "temperature": 0, "response_format": {"type": "json_object"},
                      "messages": [{"role": "system", "content": p.system}, {"role": "user", "content": p.user}]})
            ms = (time.perf_counter() - t) * 1000
            try:
                cats = json.loads(r["choices"][0]["message"]["content"])["categories"]
            except (KeyError, TypeError, json.JSONDecodeError):
                cats = {}
            self.replies[key] = (cats if isinstance(cats, dict) else {}, asked, ms)
        cats, asked, ms = self.replies[key]
        answer = cats.get(item["category"])
        s = answer.get("score") if isinstance(answer, dict) else None
        ok = isinstance(s, int) and not isinstance(s, bool) and 0 <= s <= 10
        return {"score": s if ok else None, "call_ms": ms if fresh else None, "asked": asked}


class Qwen:
    """qwen3:14b on the local Ollama, thinking off, temperature 0, JSON constrained to {"level": int}."""
    key, label = "qwen", "qwen3:14b"

    def __init__(self, model="qwen3:14b"):
        self.model = model
        self.name = f"{model} (local)"
        self.settings = {"model": model, "temperature": 0, "think": False, "num_ctx": 8192, "server": "ollama",
                         "scale": "1-10", "input": "scoped prose + short question"}

    def __call__(self, item, run):
        r = post("http://localhost:11434/api/chat", {}, {
            "model": self.model, "stream": False, "think": False,
            "messages": [{"role": "user", "content": llm_prompt(item["state"], item["category"])}],
            "format": {"type": "object", "required": ["level"], "properties": {"level": {"type": "integer"}}},
            "options": {"temperature": 0, "num_ctx": 8192}})
        try:
            return {"score": level_to_score(json.loads(r["message"]["content"])["level"])}
        except (KeyError, TypeError, json.JSONDecodeError):
            return {"score": None}


class JevK5:
    """JevK5 v0.3 (4B, Q8_0 GGUF): an open Jev-class model, read through a local llama-server.

    Like Laya it generates nothing: the answer letters' probabilities at one position, under the
    file's calibration temperature, are the answer, and the score is the expected level.
    """
    key, label = "jevk5", "JevK5"
    FILE, SHA256 = "jevk5-4b-v0.3-Q8_0.gguf", "aea433883bc7ed399f2fbd539e53d2eac7caf71a946fe6650995a413979d4a30"
    TEMPERATURE = 1.22  # this file's, from the JevK5-GGUF card; the client's docstring still says 1.367

    def __init__(self):
        import jevk5
        self.url = os.environ.get("JEVK5_URL", "http://127.0.0.1:8093")
        with urllib.request.urlopen(self.url + "/props", timeout=30) as r:
            props = json.loads(r.read())
        if not props.get("model_path", "").endswith(self.FILE):
            sys.exit(f"jevk5: {self.url} serves {props.get('model_path')}, not {self.FILE}")
        self.model = jevk5.JevK5GGUF(self.url, temperature=self.TEMPERATURE)
        self.name = "jevk5 (4b v0.3 Q8_0, llama.cpp)"
        self.settings = {"checkpoint": f"alibiserikbay/JevK5-GGUF {self.FILE}", "sha256": self.SHA256,
                         "client": f"jevk5 {jevk5.__version__}", "server": f"llama.cpp {props.get('build_info')}",
                         "temperature": self.TEMPERATURE, "scale": "1-10", "input": "scoped prose + short question"}

    def __call__(self, item, run):
        a = self.model.decide(item["state"], A.question(item["category"]))
        probs = [a["probabilities"][str(i)] for i in range(10)]
        return {"score": round(a["score"] + 1, 4), "p_top": max(probs), "probs": [round(p, 4) for p in probs]}


class Jev:
    key, label = "jev", "Jev"

    def __init__(self):
        self.url = os.environ.get("JEV_BASE_URL", "https://api.typesafe.ai/v1/systemone")
        self.model = os.environ.get("JEV_MODEL", "jev-latest")
        self.api_key = os.environ.get("JEV_API_KEY")
        self.name = f"jev ({urllib.parse.urlparse(self.url).hostname}, {self.model})"
        self.settings = {"model": self.model, "endpoint": self.url, "scale": "1-10", "input": "scoped prose + short question"}

    def __call__(self, item, run):
        r = post(self.url, {"Authorization": f"Bearer {self.api_key}"},
                 {"model": self.model, "state": item["state"], "questions": {item["category"]: A.question(item["category"])}})
        a = r["answers"][item["category"]]
        p = a["probabilities"]
        probs = [p[str(i)] if isinstance(p, dict) else p[i] for i in range(10)]
        return {"score": round(a["score"] + 1, 4), "p_top": max(probs), "model": r.get("model")}


# --- items ---

def items(agent):
    scen = {r["bundle_id"]: r for r in map(json.loads, (DATAGEN / "data/scenarios.jsonl").open())}
    out = []
    for bid, rec in scen.items():
        b = json.loads((DATAGEN / f"data/bundles/{bid}.json").read_text())
        f = facts(rec["scenario"], b)
        for cat in CATS:
            if coverage(b, cat):
                continue  # INSUFFICIENT_EVIDENCE: production would not ask
            text, _, cut = A.fit(agent, A.render(A.scoped(b, cat), A.REQUIRED[cat], "prose"), A.question(cat))
            out.append({"bundle_id": bid, "category": cat, "facts": f, "cut": cut, "state": text})
    for cat in CATS:
        out.append({"bundle_id": "NULL", "category": cat, "facts": None, "cut": [], "state": NULL_STATE})
    return out


def spearman(x, y):
    def ranks(v):
        order = sorted(range(len(v)), key=lambda i: v[i])
        r, i = [0.0] * len(v), 0
        while i < len(v):
            j = i
            while j + 1 < len(v) and v[order[j + 1]] == v[order[i]]:
                j += 1
            for k in range(i, j + 1):
                r[order[k]] = (i + j) / 2
            i = j + 1
        return r
    rx, ry = ranks(list(x)), ranks(list(y))
    mx, my = st.mean(rx), st.mean(ry)
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den = (sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry)) ** 0.5
    return round(num / den, 3) if den else None


def summarize(its, results):
    """The comparison, as data. Every number is over medians of the runs."""
    F = {(it["bundle_id"], it["category"]): it["facts"] for it in its}
    med = {name: {(r["bundle_id"], r["category"]): r["median"] for r in rows if r["median"] is not None}
           for name, rows in results.items()}
    out = {}
    for name, rows in results.items():
        s = med[name]
        real = lambda c: [v for k, v in s.items() if k[1] == c and k[0] != "NULL"]

        def gap(cat, fact):
            yes = [v for k, v in s.items() if k[1] == cat and F[k] and F[k][fact]]
            no = [v for k, v in s.items() if k[1] == cat and F[k] and not F[k][fact]]
            return {"shown": round(st.mean(yes), 2), "not_shown": round(st.mean(no), 2), "n_shown": len(yes), "n_not": len(no)}

        pr = [v for k, v in s.items() if k[1] == "containment" and F[k] and F[k]["priv_root"]]
        asked = [r for r in rows if r["runs"]]
        out[name] = {
            "containment_host_reach": gap("containment", "host_reach"),
            "containment_priv_root_le2": {"hits": sum(v <= 2 for v in pr), "of": len(pr)},
            "identity_baked_secret": gap("identity", "baked_secret"),
            "identity_no_credentials": gap("identity", "no_creds"),
            "null_control": {c: s.get(("NULL", c)) for c in CATS},
            "mean_real": {c: round(st.mean(real(c)), 2) for c in CATS},
            "range_real": {c: [min(real(c)), max(real(c))] for c in CATS},
            "runs_identical": {"items": sum(len(set(r["runs"])) == 1 for r in asked), "of": len(asked)},
            # A 1-point gap (5, 5, 6) is not identical, but the median absorbs it; a wider one may move a band.
            "runs_within_one": {"items": sum(max(v) - min(v) <= 1 for r in asked if (v := [x for x in r["runs"] if x is not None])),
                                "of": len(asked)},
            "invalid_runs": sum(x is None for r in rows for x in r["runs"]),
            "median_ms_per_call": round(st.median(ms for r in rows for ms in r["ms"])),
        }
    names = list(results)
    pair = lambda a, b, c: [(med[a][k], med[b][k]) for k in med[a] if k in med[b] and k[1] == c and k[0] != "NULL"]
    out["_rank_agreement"] = {f"{a} ~ {b}": {c: spearman(*zip(*pair(a, b, c))) for c in CATS}
                              for i, a in enumerate(names) for b in names[i + 1:]}
    return out


# --- tables ---

def _moves(d, want, scale):
    """How a score moves with a fact: marked as a clear move (>= 10% of the scale), a weak one, none, or the wrong way."""
    diff = d["shown"] - d["not_shown"]
    signed = -diff if want == "lower" else diff
    step = f"{abs(diff):.1f} {'lower' if diff < 0 else 'higher'}"
    if signed >= 0.1 * scale:
        return f"✓ {step}"
    if signed >= 0.03 * scale:
        return f"~ {step} (weak)"
    if signed > -0.03 * scale:
        return "✗ no difference"
    return f"✗ {step} (wrong way)"


def table(doc) -> str:
    summary, systems = doc["summary"], doc["meta"]["systems"]
    names = [n for n in summary if not n.startswith("_")]
    label = {n: systems.get(n, {}).get("label", n) for n in names}
    width = {n: 10 if systems.get(n, {}).get("scale") == "0-10" else 9 for n in names}  # score span

    def null(n):
        v, real = summary[n]["null_control"], summary[n]["range_real"]
        if all(x is None for x in v.values()):
            return "– not asked (coverage clears nothing)"
        top = max(hi for _, hi in real.values())
        worst = max(x for x in v.values() if x is not None)
        vals = " / ".join(f"{x:.1f}" for x in v.values())
        if worst > top:
            return f"✗ {vals}: safer than every real bundle"
        if worst <= min(summary[n]["mean_real"].values()):
            return f"✓ {vals}"
        below = lambda c: [r["median"] < v[c] for r in doc["results"][n]
                           if r["category"] == c and r["bundle_id"] != "NULL" and r["median"] is not None]
        return f"~ {vals}: safer than " + " / ".join(f"{sum(b)} of {len(b)}" for b in map(below, v)) + " real bundles"

    def priv(n):
        d = summary[n]["containment_priv_root_le2"]
        mark = "✓" if d["hits"] == d["of"] else "✗" if d["hits"] == 0 else "~"
        return f"{mark} {d['hits']} of {d['of']}"

    card = [
        ("Scores agents that can reach the host **lower** on containment", lambda n: _moves(summary[n]["containment_host_reach"], "lower", width[n])),
        ("Scores the privileged, root agents **2 or below** on containment", priv),
        ("Scores agents with a baked credential **lower** on identity", lambda n: _moves(summary[n]["identity_baked_secret"], "lower", width[n])),
        ("Scores agents holding no credentials **higher** on identity", lambda n: _moves(summary[n]["identity_no_credentials"], "higher", width[n])),
        ("Does **not** score an empty input as safe (identity / containment)", null),
        ("Range of scores across agents (identity / containment)", lambda n: " / ".join(f"{a:g}–{b:g}" if isinstance(a, int) or a.is_integer() else f"{a:.1f}–{b:.1f}" for a, b in summary[n]["range_real"].values())),
        ("Items where the 3 runs agreed: exactly / within 1 point", lambda n: "{} / {} of {}".format(
            summary[n]["runs_identical"]["items"], summary[n]["runs_within_one"]["items"], summary[n]["runs_identical"]["of"])),
        ("Median time per call", lambda n: f"{summary[n]['median_ms_per_call']:,} ms"),
    ]
    out = ["| What a good scorer does | " + " | ".join(label[n] for n in names) + " |", "|---|" + "---|" * len(names)]
    out += [f"| {q} | " + " | ".join(fn(n) for n in names) + " |" for q, fn in card]

    first = summary[names[0]]
    avg = lambda key, part: lambda n: f"{summary[n][key][part]:.1f}"
    rows = [
        (f"containment, agents that **can** reach the host ({first['containment_host_reach']['n_shown']})", avg("containment_host_reach", "shown")),
        (f"containment, agents that **cannot** ({first['containment_host_reach']['n_not']})", avg("containment_host_reach", "not_shown")),
        (f"identity, agents **with** a visible baked credential ({first['identity_baked_secret']['n_shown']})", avg("identity_baked_secret", "shown")),
        (f"identity, agents **without** one ({first['identity_baked_secret']['n_not']})", avg("identity_baked_secret", "not_shown")),
        (f"identity, agents holding **no** credentials ({first['identity_no_credentials']['n_shown']})", avg("identity_no_credentials", "shown")),
        (f"identity, agents holding **some** ({first['identity_no_credentials']['n_not']})", avg("identity_no_credentials", "not_shown")),
    ]
    out += ["", "| Average score of … (number of agents) | " + " | ".join(label[n] for n in names) + " |", "|---|" + "---|" * len(names)]
    out += [f"| {q} | " + " | ".join(fn(n) for n in names) + " |" for q, fn in rows]

    out += ["", "| Rank agreement (Spearman) | identity | containment |", "|---|---|---|"]
    for p, v in summary["_rank_agreement"].items():
        a, b = p.split(" ~ ")
        out.append(f"| {label.get(a, a)} ~ {label.get(b, b)} | {v['identity']} | {v['containment']} |")
    return "\n".join(out)


def ordered(results, settings):
    """Columns in a fixed order, so the two Gemini columns sit side by side."""
    order = [Laya.label, Gemini.label, GeminiProd.label, Qwen.label, JevK5.label, Jev.label]
    rank = lambda n: order.index(settings[n]["label"]) if settings[n]["label"] in order else len(order)
    return {n: results[n] for n in sorted(results, key=rank)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--systems", nargs="+", default=["laya", "gemini", "gemini-prod", "qwen", "jevk5"],
                    choices=["laya", "gemini", "gemini-prod", "qwen", "jevk5", "jev"])
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--gemini-model", default="gemini-3.5-flash-lite")
    ap.add_argument("--out", default=str(HERE / "bench_results.json"))
    ap.add_argument("--merge", action="store_true", help="keep results already in --out for systems not run now")
    ap.add_argument("--report", action="store_true", help="print the tables from --out without running anything")
    args = ap.parse_args()
    if args.report:
        print(table(json.loads(Path(args.out).read_text())))
        return

    warnings.filterwarnings("ignore")
    import laya
    agent = laya.load(*laya.DEFAULT_MODELS["typed-decisions"][:1], subfolder="typed-decisions")
    its = items(agent)
    make = {"laya": lambda: Laya(agent), "gemini": lambda: Gemini(args.gemini_model),
            "gemini-prod": lambda: GeminiProd(args.gemini_model), "qwen": Qwen, "jevk5": JevK5, "jev": Jev}
    systems = [make[k]() for k in args.systems]

    results, status, settings = {}, {}, {}
    if args.merge and Path(args.out).exists():
        old = json.loads(Path(args.out).read_text())
        same = [(i["bundle_id"], i["category"], i["state"]) for i in old["items"]] == [(i["bundle_id"], i["category"], i["state"]) for i in its]
        if not same:
            sys.exit("--merge refused: the items differ from the ones in --out, so the results would not compare")
        running = {s.name for s in systems}
        results = {k: v for k, v in old["results"].items() if k not in running}
        status = {k: v for k, v in old["meta"]["status"].items() if k not in running}
        settings = {k: v for k, v in old["meta"]["systems"].items() if k not in running}
        # Results saved before systems carried a label and a scale: all three used the 1-10 question.
        legacy = {"laya (typed-decisions, stock)": Laya.label, "gemini (gemini-3.5-flash-lite)": Gemini.label,
                  "qwen3:14b (local)": Qwen.label}
        for k, v in settings.items():
            v.setdefault("label", legacy.get(k, k))
            v.setdefault("scale", "1-10")

    for sysm in systems:
        rows = []
        try:
            for n, it in enumerate(its):
                runs, ms, extra, note = [], [], {}, None
                try:
                    for run in range(args.runs):
                        t = time.perf_counter()
                        r = sysm(it, run)
                        elapsed = (time.perf_counter() - t) * 1000
                        call_ms = r.pop("call_ms", elapsed)
                        if call_ms is not None:
                            ms.append(round(call_ms))
                        runs.append(r.pop("score"))
                        extra = r
                except NotAsked as e:
                    note = str(e)
                valid = [x for x in runs if x is not None]
                rows.append({"bundle_id": it["bundle_id"], "category": it["category"], "runs": runs,
                             "median": st.median(valid) if valid else None, "ms": ms,
                             **({"not_asked": note} if note else {}), **extra})
                print(f"  {sysm.name} {n + 1}/{len(its)}", end="\r", flush=True)
            results[sysm.name], status[sysm.name] = rows, "ok"
        except urllib.error.HTTPError as e:
            status[sysm.name] = f"not run: HTTP {e.code} {e.read()[:200].decode(errors='replace')}"
        settings[sysm.name] = {"label": sysm.label, **sysm.settings}
        print(f"{sysm.name}: {status[sysm.name]}          ", flush=True)

    results = ordered(results, settings)
    doc = {
        "meta": {
            "run_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            "runs_per_item": args.runs, "aggregate": "median of the valid runs",
            "scale": "1-10, 10 safest (Laya level i = score i+1), except systems whose settings say 0-10",
            "question": {c: A.question(c) for c in CATS},
            "input": "asp-datagen pilot bundles, scoped to the category, rendered as prose, fit to Laya's 1024 tokens",
            "asp_datagen_commit": subprocess.run(["git", "-C", str(DATAGEN), "rev-parse", "--short", "HEAD"],
                                                 capture_output=True, text=True).stdout.strip(),
            "systems": settings, "status": status,
        },
        "items": its,
        "results": results,
    }
    doc["summary"] = summarize(its, results)
    Path(args.out).write_text(json.dumps(doc, indent=2, ensure_ascii=False))
    print("\n" + table(doc))
    print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
