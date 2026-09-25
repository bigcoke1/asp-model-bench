# asp-laya-bench

Can a small decision model score agents for ASP (agent security profiling)? This repo tests stock [Laya](https://huggingface.co/convaiinnovations/laya) on the ASP risk categories, and benchmarks it against Gemini and `qwen3:14b` on the same questions.

- **The categories and required inputs** come from Rail Center (`api/src/profiling/coverage.py`).
- **The bundles** are Rail Center's test vectors and the synthetic bundles from `~/Desktop/asp-datagen`.
- **Split out of `laya_demo`** on 2026-09-25. The history before that is in `laya_demo`'s git log.

## Benchmark: stock Laya vs Gemini vs qwen3:14b

Can stock Laya score agent evidence bundles on the ASP risk categories, and how does it compare with Gemini and with `qwen3:14b`? The Gemini model is the one Rail Center's LLM profiler uses; `qwen3:14b` is the best open-weight model that fits this laptop. Run on 2026-09-25 with `bench.py`. Every number here is in `bench_results.json`.

**Short answer:**
- **Stock Laya does not read the evidence.** Every score lands between 4.8 and 5.7, and it scores empty input safer than any real agent.
- **Gemini with Rail Center's production prompt reads the evidence best:** it passes every check it was given. Its weaknesses:
  - Containment scores stay at 4 or below, so it separates risky agents from very risky ones but calls none of them safe.
  - Even at temperature 0, its three runs gave exactly the same score on only 15 of 32 items; 29 of 32 stayed within 1 point.
- **The prompt matters more than the model.** The same Gemini with a short prompt barely notices baked credentials.
- **qwen3:14b reads identity well but fails the empty-input check:** it gives no evidence at all a perfect 10.

### How to read the tables

Scores run from 1 to 10, **10 safest**. Gemini with the production prompt uses production's 0–10 scale instead.

Each check asks one question: when a bundle shows a risky fact, does the system's score move the right way?

Take host reach: an agent that is privileged, has the Docker socket mounted, or has the host's `/` mounted can reach the host. A good scorer gives those agents a **lower** containment score than agents that cannot.

In the scorecard:
- **✓** means the score moves the right way by at least a tenth of the scale (about 1 point).
- **~** means it moves the right way, but weakly.
- **✗** means no difference, or the wrong way.
- **The number** is the size of the move.

The second table shows the two averages behind each check.

A fact counts only when the bundle actually shows it, meaning the attribute carrying it is `ANSWERED` or `PARTIAL`. A labeller cannot react to a field it could not see.

### Scorecard

| What a good scorer does | stock Laya | Gemini, short prompt | Gemini, production prompt | qwen3:14b |
|---|---|---|---|---|
| Scores agents that can reach the host **lower** on containment | ✗ no difference | ✓ 1.3 lower | ✓ 1.5 lower | ✓ 1.5 lower |
| Scores the privileged, root agents **2 or below** on containment | ✗ 0 of 2 | ✓ 2 of 2 | ✓ 2 of 2 | ✗ 0 of 2 |
| Scores agents with a baked credential **lower** on identity | ✗ no difference | ~ 0.3 lower (weak) | ✓ 2.9 lower | ✓ 2.2 lower |
| Scores agents holding no credentials **higher** on identity | ✗ no difference | ✓ 1.3 higher | ✓ 2.6 higher | ✓ 2.2 higher |
| Does **not** score an empty input as safe (identity / containment) | ✗ 6.0 / 6.0: safer than every real bundle | ✓ 1.0 / 1.0 | – not asked (coverage clears nothing) | ✗ 10.0 / 10.0: safer than every real bundle |
| Range of scores across agents (identity / containment) | 4.8–5.4 / 5.2–5.7 | 1–6 / 1–3 | 1–8 / 0–4 | 1–8 / 3–6 |
| Items where the 3 runs agreed: exactly / within 1 point | 34 / 34 of 34 | 30 / 33 of 34 | 15 / 29 of 32 | 33 / 34 of 34 |
| Median time per call | 241 ms | 587 ms | 2,442 ms | 1,272 ms |

Notes on the scorecard:
- **Why production was not asked the empty input:** production never calls a model when coverage clears nothing, so this benchmark doesn't either.
- **Why its time per call is longer:** one production call scores all 6–7 categories coverage clears, not one.
- **What "agreed" means:** "exactly" needs all three runs identical, so 5, 5, 6 does not count; "within 1 point" means the highest and lowest runs are at most 1 apart. The reported score is the median, which absorbs a single stray run: 5, 5, 6 gives 5. A 1-point wobble can still flip an agent's band when a band threshold falls between the two values.

### The averages behind the scorecard

| Average score of … (number of agents) | stock Laya | Gemini, short prompt | Gemini, production prompt | qwen3:14b |
|---|---|---|---|---|
| containment, agents that **can** reach the host (6) | 5.4 | 1.0 | 1.0 | 4.5 |
| containment, agents that **cannot** (6) | 5.5 | 2.3 | 2.5 | 6.0 |
| identity, agents **with** a visible baked credential (5) | 5.1 | 2.0 | 3.0 | 4.6 |
| identity, agents **without** one (15) | 5.1 | 2.3 | 5.9 | 6.8 |
| identity, agents holding **no** credentials (4) | 5.1 | 3.2 | 7.2 | 8.0 |
| identity, agents holding **some** (16) | 5.1 | 1.9 | 4.7 | 5.8 |

For example, Gemini with the production prompt gives agents with a baked credential 3.0 on average and agents without one 5.9. That is the "✓ 2.9 lower" in the scorecard.

### Do the systems rank agents alike?

Spearman rank correlation: 1 means the same order, 0 unrelated, negative the opposite order.

| pair | identity | containment |
|---|---|---|
| stock Laya ~ Gemini, short prompt | 0.08 | 0.31 |
| stock Laya ~ Gemini, production prompt | 0.04 | 0.00 |
| stock Laya ~ qwen3:14b | 0.11 | 0.19 |
| Gemini, short prompt ~ Gemini, production prompt | 0.15 | 0.43 |
| Gemini, short prompt ~ qwen3:14b | 0.36 | 0.49 |
| Gemini, production prompt ~ qwen3:14b | 0.43 | 0.65 |

Stock Laya's ranking is unrelated to every other system's. Gemini with the production prompt and `qwen3:14b` agree most, but still only moderately.

### What it shows

- **Stock Laya is not usable zero-shot.** It fails every check, its top level never passes 0.20 probability, and empty input comes out safest.
- **Gemini, production prompt:**
  - It is the only system that passes every check it was asked.
  - Baked credentials and credential count move its identity score by nearly 3 points.
  - Containment stays at 0–4 for every agent.
  - Even at temperature 0, its three runs agreed exactly on only 15 of 32 items. Of the 17 that differed, 14 differ by 1 point, two by 2 points, and one by 3 (bundle 0007 identity: 8, 5, 8). This is presumably why production keeps the lowest of three calls rather than one.
- **Gemini, short prompt:** it follows containment but pins nearly everything at 1–3, and it barely notices baked credentials (0.3). The difference from the column beside it is the prompt alone: the production prompt adds the whole bundle, the scoring anchors, the rules for reading `BLIND`, `ABSENT` and `PARTIAL`, and the fence around agent-written text.
- **qwen3:14b:** it reads identity nearly as well as the production prompt (2.2 lower for baked credentials) with only the short prompt. Its weaknesses:
  - Containment is weaker, and neither privileged-root agent scored 2 or below.
  - Empty input scores 10, which breaks the design's rule that nothing unobserved may make an agent look safer.

### Setup

| | |
|---|---|
| Items | The 20 synthetic bundles from `asp-datagen` (pilot 1), on `identity` (20 evaluable) and `containment` (12 evaluable; the other 8 would be `INSUFFICIENT_EVIDENCE`, so production would not ask). Plus one empty input per category: 34 items. |
| Input, first four columns | The same for every system: the bundle cut to the category's attributes and written as English (`asp_score.py --format prose --scope category`), trimmed to Laya's 1024 tokens so Laya sees all of it. |
| Question, first four columns | The same: `asp_score.question()`, 10 levels scored 1–10. Ten, not the design doc's 0–10, because Jev (planned as another column) accepts at most 10 levels. |
| Gemini, production prompt | The whole bundle through Rail Center's own `profiling.prompt.render_prompt` (v7, identical to `origin/master`). One call per bundle asks every category coverage clears; `identity` and `containment` are read from the reply. The score is the model's raw 0–10, before the mixer's clamps. |
| Runs | Every system answers every item 3 times; its score is the median. Production keeps the lowest of three instead. |
| Models | Laya `typed-decisions`, stock, local and deterministic. Gemini `gemini-3.5-flash-lite` through the OpenAI-compatible endpoint, temperature 0, JSON output, as Rail Center calls it. `qwen3:14b` on local Ollama, thinking off, temperature 0. |
| Jev | Not run: thejevai.com's upstream provider rejected every request, and TypeSafe is not taking signups. `bench.py --systems jev --merge` adds it later. |

**Caveats:**
- **No ground truth.** The bundles are synthetic and no one has labelled them by hand. The checks show whether a score moves with a visible fact, not whether it is right.
- **Small numbers.** Each check rests on 2 to 16 agents; the privileged-root check rests on 2.

### Rerun, or read later

```bash
GOOGLE_API_KEY=... python bench.py                  # all systems, 3 runs each (qwen3:14b needs `ollama serve`)
python bench.py --systems gemini-prod --merge       # rerun or add one system, keep the rest
python bench.py --report                            # print these tables from bench_results.json, no calls
```

`bench_results.json` is self-contained:

| key | holds |
|---|---|
| `meta` | Settings and scale per system, the exact questions, the asp-datagen commit, run status. |
| `items` | Every item: the exact text sent, the facts it shows, and what was cut. |
| `results` | Every run and the median for every system × item, plus which categories production asked. |
| `summary` | The tables above, as data. |

## Earlier: stock Laya on Rail Center's test-vector bundles (`asp_score.py`)

Before the benchmark, `asp_score.py` asked stock Laya (`typed-decisions`) for all eight categories on the three bundles in Rail Center's test vectors (`api/tests/vectors/evidence_bundles/valid`). There was one score question per category, scored 1–10 with 10 safest. It also scored an empty input.

It tried three ways of giving Laya the bundle, because a real bundle is 2–3× Laya's 1024-token limit and Laya drops the excess without warning:

| input format (`--format`, `--scope`) | score range on the 3 bundles | empty input | Laya's top-level probability, max | attributes cut per call |
|---|---|---|---|---|
| compact lines, whole bundle (`lines`, `all`) | 4.6–5.5 | 5.9–6.2 | 0.21 | 0–23 |
| English, whole bundle (`prose`, `all`) | 5.0–5.8 | 5.9–6.2 | 0.16 | 0–23 |
| English, scoped per category (`prose`, `category`) | 4.9–5.8 | 5.9–6.2 | 0.18 | 0 |

- **The format made no difference.** Every score sat near 5, and the probabilities were close to an even spread over the ten levels (0.10 each).
- **The empty input scored safest,** above every real bundle.
- **Scoping fixed the length problem but not the scores:**
  - The scoped format uses the prototype's attribute-to-category map (`SCOPE` from `agent-profiling-demo`), and every call fit in 1024 tokens with nothing cut.
  - The containment input for `agt-2c81b4e7` showed a root user and a read-write Docker socket mount, and Laya still scored it 5.4.
- **A positive control, run once and not saved:**
  - One blatantly dangerous sentence scored about 3.7; one blatantly safe sentence, about 6.3.
  - All eight categories scored alike, so stock Laya reacts to how alarming the wording is, not to the category.

## Setup

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
ollama serve &      # for qwen3:14b: `ollama pull qwen3:14b`
```

`bench.py` also reads two other checkouts in place, and changes neither:
- **`~/Desktop/asp-datagen`:** the bundles, and its `datagen.check` and `datagen.contract` modules.
- **`~/workspace/rail-center-rc000`:** its `profiling` package, for the production-prompt column.

`asp_score.py` reads the test-vector bundles from the same Rail Center checkout. Keys come from the environment:
- `GOOGLE_API_KEY` for Gemini.
- `JEV_API_KEY`, plus `JEV_BASE_URL` for thejevai.com, for Jev.

## Files

```
asp_score.py            stock Laya on ASP bundles: --format lines|prose, --scope all|category
asp_score_results*.json the three asp_score.py runs above
bench.py                stock Laya vs Gemini (short and production prompt) vs qwen3:14b (vs Jev)
bench_results.json      everything bench.py sent and got back, plus the summary
```
