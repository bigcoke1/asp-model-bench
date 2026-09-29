# Risk detection

Can a model score an agent's evidence bundle on the ASP risk categories, the way Rail Center's LLM profiler does? This folder benchmarks stock [Laya](https://huggingface.co/convaiinnovations/laya), Gemini, `qwen3:14b`, `qwen3:32b`, JevK5, DeepSeek V4 Pro, DeepSeek V4 Flash and Kimi K3 on the same questions, over the 20 synthetic bundles in [`../data`](../data).

- **"Stock"** means as published, not tuned on ASP data. Laya's `typed-decisions` checkpoint is already Convai's own fine-tune for general decisions: 0.766 on their benchmark, against 0.362 for the base model. JevK5 was also run as published.
- **The categories and required inputs** come from Rail Center (`api/src/profiling/coverage.py`).
- **Run it:** `make risk` from the repo root, or `make risk-report` to print these tables without calling a model. See [Rerun, or read later](#rerun-or-read-later).

## Benchmark: stock Laya vs Gemini vs open-weight models

Can stock Laya score agent evidence bundles on the ASP risk categories, and how does it compare with Gemini and with open-weight models, local and hosted?
- **Gemini** is the model Rail Center's LLM profiler uses.
- **`qwen3:14b`** is the best open-weight model that fits this laptop.
- **`qwen3:32b`** is the largest dense Qwen3, run on a Mac mini with 48 GB to see whether a bigger open model does better.
- **DeepSeek V4 Pro, DeepSeek V4 Flash and Kimi K3** are popular open-weight models far too big for a Mac (284B to 2.8T parameters). They run through [OpenRouter](https://openrouter.ai) at the precision their makers released: both DeepSeek models on Parasail at fp8, Kimi K3 on Moonshot's own servers at 4-bit.
- **JevK5** stands in for Jev, which could not be reached. Of the open Jev-class models, it ranks highest on [JevBench](https://benchmarkheaven.com/jev-models) v1.4.2 among those with a documented way to run on a Mac.

Run on 2026-09-25 with `bench.py`, on a 16 GB M3 laptop; the qwen3:32b column on 2026-09-28, on a Mac mini (M4 Pro, 48 GB); the DeepSeek and Kimi columns on 2026-09-29, through OpenRouter. Every number here is in [`results/bench_results.json`](results/bench_results.json).

**Short answer:**
- **Stock Laya does not read the evidence.** Every score lands between 4.8 and 5.7, and it scores empty input safer than any real agent.
- **Gemini with Rail Center's production prompt reads the evidence best:** it passes every check it was given. Its weaknesses:
  - Containment scores stay at 4 or below, so it separates risky agents from very risky ones but calls none of them safe.
  - Even at temperature 0, its three runs gave exactly the same score on only 15 of 32 items; 29 of 32 stayed within 1 point.
- **The prompt matters more than the model.** The same Gemini with a short prompt barely notices baked credentials.
- **qwen3:14b reads identity well but fails the empty-input check:** it gives no evidence at all a perfect 10.
- **qwen3:32b does worse than qwen3:14b, not better:** it passes 2 checks to the 14b's 3. Its containment scores stay at 4–6 whether or not an agent can reach the host, and it also gives empty input a 10.
- **Kimi K3 is the best open model here: 4 of 5 checks with only the short prompt.** Host reach lowers its containment score by 2.7 points, more than the production prompt does, and both privileged, root agents score 2 or below. But it gives empty input a 10, and its runs vary more than any other system's.
- **DeepSeek V4 Pro and Flash do no better than `qwen3:14b`.** Pro scores both privileged, root agents 2 or below but barely moves with host reach; Flash reads identity but not containment.
- **The five open LLMs all score empty input a perfect 10:** both `qwen3` models, both DeepSeek models and Kimi K3. Only Gemini, given the same short prompt, scores it as unsafe.
- **JevK5 reads the evidence, unlike stock Laya, but it calls empty input safe.** Its identity scores move 1.6 points with credentials, and its runs are identical every time. But empty input scores safer than most real agents, and one privileged-root agent scores 6.3.

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

| What a good scorer does | stock Laya | Gemini, short prompt | Gemini, production prompt | qwen3:14b | qwen3:32b | JevK5 | DeepSeek V4 Pro | DeepSeek V4 Flash | Kimi K3 |
|---|---|---|---|---|---|---|---|---|---|
| Scores agents that can reach the host **lower** on containment | ✗ no difference | ✓ 1.3 lower | ✓ 1.5 lower | ✓ 1.5 lower | ✗ no difference | ✓ 0.9 lower | ~ 0.7 lower (weak) | ✗ no difference | ✓ 2.7 lower |
| Scores the privileged, root agents **2 or below** on containment | ✗ 0 of 2 | ✓ 2 of 2 | ✓ 2 of 2 | ✗ 0 of 2 | ✗ 0 of 2 | ✗ 0 of 2 | ✓ 2 of 2 | ✗ 0 of 2 | ✓ 2 of 2 |
| Scores agents with a baked credential **lower** on identity | ✗ no difference | ~ 0.3 lower (weak) | ✓ 2.9 lower | ✓ 2.2 lower | ✓ 0.9 lower | ✓ 1.6 lower | ~ 0.9 lower (weak) | ✓ 1.6 lower | ✓ 0.9 lower |
| Scores agents holding no credentials **higher** on identity | ✗ no difference | ✓ 1.3 higher | ✓ 2.6 higher | ✓ 2.2 higher | ✓ 2.9 higher | ✓ 1.6 higher | ✓ 2.6 higher | ✓ 2.8 higher | ✓ 3.8 higher |
| Does **not** score an empty input as safe (identity / containment) | ✗ 6.0 / 6.0: safer than every real bundle | ✓ 1.0 / 1.0 | – not asked (coverage clears nothing) | ✗ 10.0 / 10.0: safer than every real bundle | ✗ 10.0 / 10.0: safer than every real bundle | ~ 7.4 / 6.8: safer than 16 of 20 / 10 of 12 real bundles | ✗ 10.0 / 10.0: safer than every real bundle | ✗ 10.0 / 10.0: safer than every real bundle | ✗ 10.0 / 10.0: safer than every real bundle |
| Range of scores across agents (identity / containment) | 4.8–5.4 / 5.2–5.7 | 1–6 / 1–3 | 1–8 / 0–4 | 1–8 / 3–6 | 2–8 / 4–6 | 1.6–8.1 / 3.0–7.9 | 1–7 / 1–3 | 1–7 / 3–7 | 1–8 / 1–6 |
| Items where the 3 runs agreed: exactly / within 1 point | 34 / 34 of 34 | 30 / 33 of 34 | 15 / 29 of 32 | 33 / 34 of 34 | 34 / 34 of 34 | 34 / 34 of 34 | 26 / 31 of 34 | 26 / 33 of 34 | 18 / 24 of 34 |
| Median time per call | 241 ms | 587 ms | 2,442 ms | 1,272 ms | 642 ms | 2,791 ms | 850 ms | 671 ms | 3,828 ms |

Notes on the scorecard:
- **Why production was not asked the empty input:** production never calls a model when coverage clears nothing, so this benchmark doesn't either.
- **Why its time per call is longer:** one production call scores all 6–7 categories coverage clears, not one.
- **Why qwen3:14b looks faster than JevK5:** Ollama reuses a prompt it has just seen, so qwen3:14b's first run of an item takes 6.2 s and the two repeats 0.8 s (medians). JevK5's client turns that cache off, so each of its runs takes about 2.8 s for a median of 690 input tokens.
- **qwen3:32b shows the same caching, on the Mac mini:** 5.5 s for an item's first run and 0.6 s for each repeat (medians).
- **The DeepSeek and Kimi times include the round trip to OpenRouter** and depend on how busy the provider was.
- **Why Kimi K3's runs disagree:** Moonshot's endpoint takes no temperature, so it answered at Moonshot's default rather than 0. Its three runs agreed exactly on 18 of 34 items and within 1 point on 24.
- **What "agreed" means:** "exactly" needs all three runs identical, so 5, 5, 6 does not count; "within 1 point" means the highest and lowest runs are at most 1 apart. The reported score is the median, which absorbs a single stray run: 5, 5, 6 gives 5. A 1-point wobble can still flip an agent's band when a band threshold falls between the two values.

### The averages behind the scorecard

| Average score of … (number of agents) | stock Laya | Gemini, short prompt | Gemini, production prompt | qwen3:14b | qwen3:32b | JevK5 | DeepSeek V4 Pro | DeepSeek V4 Flash | Kimi K3 |
|---|---|---|---|---|---|---|---|---|---|
| containment, agents that **can** reach the host (6) | 5.4 | 1.0 | 1.0 | 4.5 | 4.8 | 5.7 | 2.3 | 4.5 | 1.5 |
| containment, agents that **cannot** (6) | 5.5 | 2.3 | 2.5 | 6.0 | 5.0 | 6.7 | 3.0 | 4.3 | 4.2 |
| identity, agents **with** a visible baked credential (5) | 5.1 | 2.0 | 3.0 | 4.6 | 4.0 | 4.5 | 2.8 | 2.6 | 2.0 |
| identity, agents **without** one (15) | 5.1 | 2.3 | 5.9 | 6.8 | 4.9 | 6.1 | 3.7 | 4.2 | 2.9 |
| identity, agents holding **no** credentials (4) | 5.1 | 3.2 | 7.2 | 8.0 | 7.0 | 7.0 | 5.5 | 6.0 | 5.8 |
| identity, agents holding **some** (16) | 5.1 | 1.9 | 4.7 | 5.8 | 4.1 | 5.4 | 2.9 | 3.2 | 1.9 |

For example, Gemini with the production prompt gives agents with a baked credential 3.0 on average and agents without one 5.9. That is the "✓ 2.9 lower" in the scorecard.

### Do the systems rank agents alike?

Spearman rank correlation: 1 means the same order, 0 unrelated, negative the opposite order.

| pair | identity | containment |
|---|---|---|
| stock Laya ~ Gemini, short prompt | 0.08 | 0.31 |
| stock Laya ~ Gemini, production prompt | 0.04 | 0.00 |
| stock Laya ~ qwen3:14b | 0.11 | 0.19 |
| stock Laya ~ qwen3:32b | 0.16 | 0.40 |
| stock Laya ~ JevK5 | −0.08 | 0.14 |
| stock Laya ~ DeepSeek V4 Pro | 0.25 | 0.06 |
| stock Laya ~ DeepSeek V4 Flash | 0.02 | 0.28 |
| stock Laya ~ Kimi K3 | −0.02 | −0.11 |
| Gemini, short prompt ~ Gemini, production prompt | 0.15 | 0.43 |
| Gemini, short prompt ~ qwen3:14b | 0.36 | 0.49 |
| Gemini, short prompt ~ qwen3:32b | 0.48 | 0.30 |
| Gemini, short prompt ~ JevK5 | 0.46 | 0.15 |
| Gemini, short prompt ~ DeepSeek V4 Pro | 0.48 | 0.41 |
| Gemini, short prompt ~ DeepSeek V4 Flash | 0.70 | 0.08 |
| Gemini, short prompt ~ Kimi K3 | 0.73 | 0.67 |
| Gemini, production prompt ~ qwen3:14b | 0.43 | 0.65 |
| Gemini, production prompt ~ qwen3:32b | 0.47 | 0.63 |
| Gemini, production prompt ~ JevK5 | 0.43 | 0.08 |
| Gemini, production prompt ~ DeepSeek V4 Pro | 0.38 | 0.49 |
| Gemini, production prompt ~ DeepSeek V4 Flash | 0.43 | 0.18 |
| Gemini, production prompt ~ Kimi K3 | 0.24 | 0.58 |
| qwen3:14b ~ qwen3:32b | 0.63 | 0.42 |
| qwen3:14b ~ JevK5 | 0.51 | 0.24 |
| qwen3:14b ~ DeepSeek V4 Pro | 0.61 | 0.82 |
| qwen3:14b ~ DeepSeek V4 Flash | 0.65 | 0.50 |
| qwen3:14b ~ Kimi K3 | 0.55 | 0.74 |
| qwen3:32b ~ JevK5 | 0.44 | 0.15 |
| qwen3:32b ~ DeepSeek V4 Pro | 0.74 | 0.46 |
| qwen3:32b ~ DeepSeek V4 Flash | 0.74 | 0.55 |
| qwen3:32b ~ Kimi K3 | 0.83 | 0.18 |
| JevK5 ~ DeepSeek V4 Pro | 0.51 | 0.46 |
| JevK5 ~ DeepSeek V4 Flash | 0.75 | 0.38 |
| JevK5 ~ Kimi K3 | 0.54 | 0.09 |
| DeepSeek V4 Pro ~ DeepSeek V4 Flash | 0.82 | 0.61 |
| DeepSeek V4 Pro ~ Kimi K3 | 0.78 | 0.61 |
| DeepSeek V4 Flash ~ Kimi K3 | 0.88 | 0.32 |

Stock Laya's ranking is unrelated, or at most weakly related, to every other system's (0.40 at most). The open LLMs, `qwen3` and the DeepSeek and Kimi models, rank identity much alike (0.55–0.88), but containment far less so (0.18–0.82): `qwen3:14b` and DeepSeek V4 Pro agree closely on it (0.82), while `qwen3:32b` and Kimi K3 barely do (0.18). Gemini with the production prompt agrees with them moderately at best (0.18–0.65). JevK5 ranks identity about as the LLMs do (0.43–0.75), but its containment ranking is at most weakly related to theirs (0.08–0.46).

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
- **qwen3:32b:** more than twice the size of `qwen3:14b` and asked the same way, it does worse.
  - Containment barely moves: every agent scores 4–6, and agents that can reach the host average 4.8 against 5.0 for those that cannot. The two privileged, root agents score 5 and 4.
  - On identity, holding no credentials raises the score by 2.9, the most of any system, but a baked credential lowers it by only 0.9, just over the bar, against 2.2 for `qwen3:14b`.
  - Empty input scores 10, as with `qwen3:14b`.
  - Its three runs were identical on every item.
- **Kimi K3:** with only the short prompt, it passes as many checks as Gemini does with it, and more than any other open model.
  - Host reach lowers containment by 2.7 points (1.5 against 4.2), the largest gap of any system, the production prompt included. Both privileged, root agents score 2 or below.
  - Holding no credentials raises identity by 3.8, also the largest. A baked credential lowers it by 0.93, just over the bar.
  - Empty input scores 10.
  - Its runs are the least settled of any system: identical on only 18 of 34 items, since Moonshot's endpoint runs it at its default temperature rather than 0. The median absorbs a single stray run, but a rerun may move some of its scores.
- **DeepSeek V4 Pro:**
  - Containment stays at 1–3 for every agent, and both privileged, root agents score 2 or below, as with Gemini. But host reach lowers it by only 0.7 (2.3 against 3.0), a weak move.
  - On identity, holding no credentials raises the score by 2.6, but a baked credential lowers it by only 0.87, just under the bar.
  - Empty input scores 10.
- **DeepSeek V4 Flash:** it reads identity (a baked credential lowers it by 1.6, holding no credentials raises it by 2.8) but not containment: agents that can reach the host score 4.5 against 4.3 for those that cannot, and neither privileged, root agent scores 2 or below. Empty input scores 10.
- **JevK5:** it follows the evidence, which stock Laya does not. A baked credential lowers identity by 1.6 points, holding no credentials raises it by 1.6, and host reach lowers containment by 0.95, just over the bar. Its three runs were identical on every item. Its weaknesses:
  - Containment is the weakest of the systems that read evidence. Bundle 0009 is privileged and root, yet it scores 6.3; its most likely level is 7, "read-write over a scoped store, egress allow-listed".
  - Empty input breaks the same rule as `qwen3:14b`, if less blatantly. Its most likely level is 10, "no meaningful exposure", and it scores 7.4 / 6.8, safer than 16 of 20 identity and 10 of 12 containment bundles.
  - The score is the probability-weighted average level, as for Laya, and that blurs its answers. On every item its most likely level is 1 or 7–10, never 2–6, yet the average often lands in between: on 16 of 34 items the two differ by 2 points or more. Bundle 0013, privileged and root, has 1 as its most likely level (p = 0.50) but averages 3.0.
  - Scoring by the most likely level instead is not a free fix. Rescored that way from the saved probabilities, three checks improve and two get worse:
    - host reach lowers containment by 1.5 instead of 0.95;
    - a baked credential lowers identity by 2.6 instead of 1.6;
    - 1 of the 2 privileged, root agents scores 2 or below;
    - but holding no credentials raises identity by only 0.6 instead of 1.6;
    - and empty input becomes a flat 10 / 10.
  - It saw only the category's slice of the bundle, like every column except the production prompt. Its context would hold the whole bundle; see [JevK5: choice, limits and tuning](#jevk5-choice-limits-and-tuning).

### Setup

| | |
|---|---|
| Items | The 20 synthetic bundles in [`../data`](../data) (asp-datagen pilot 1), on `identity` (20 evaluable) and `containment` (12 evaluable; the other 8 would be `INSUFFICIENT_EVIDENCE`, so production would not ask). Plus one empty input per category: 34 items. |
| Input, every column but the production prompt | The same for every system: the bundle cut to the category's attributes and written as English (`asp_score.py --format prose --scope category`), trimmed to Laya's 1024 tokens so Laya sees all of it. Nothing needed trimming: 0 of 32 items. |
| Question, every column but the production prompt | The same: `asp_score.question()`, 10 levels scored 1–10. Ten, not the design doc's 0–10, because Jev (planned as another column) accepts at most 10 levels. |
| Gemini, production prompt | The whole bundle through Rail Center's own `profiling.prompt.render_prompt` (v7, identical to `origin/master`). One call per bundle asks every category coverage clears; `identity` and `containment` are read from the reply. The score is the model's raw 0–10, before the mixer's clamps. |
| Runs | Every system answers every item 3 times; its score is the median. Production keeps the lowest of three instead. |
| Models | Laya `typed-decisions`, stock, local and deterministic. Gemini `gemini-3.5-flash-lite` through the OpenAI-compatible endpoint, temperature 0, JSON output, as Rail Center calls it. `qwen3:14b` on local Ollama, thinking off, temperature 0, and `qwen3:32b` (Q4_K_M) the same way on a Mac mini with 48 GB. DeepSeek V4 Pro (`deepseek/deepseek-v4-pro-0813`) and DeepSeek V4 Flash through OpenRouter on Parasail at fp8, and Kimi K3 through OpenRouter on Moonshot's own servers at its released 4-bit; each pinned to that one provider with no fallback, reasoning off, JSON output, temperature 0 except Kimi K3 (Moonshot's default). JevK5 v0.3, 4B, as `jevk5-4b-v0.3-Q8_0.gguf` on a local `llama-server` (llama.cpp b11146, Metal), read through JevK5's own client at the file's calibration temperature, 1.22. JevBench ranked v0.2; v0.3 is the current release. |
| Jev | Not run: thejevai.com's upstream provider rejected every request, and TypeSafe is not taking signups. JevK5 stands in for it. `bench.py --systems jev --merge` adds Jev later. |

**Caveats:**
- **No ground truth.** The bundles are synthetic and no one has labelled them by hand. The checks show whether a score moves with a visible fact, not whether it is right.
- **Small numbers.** Each check rests on 2 to 16 agents; the privileged-root check rests on 2.
- **Hosted models can change.** The DeepSeek and Kimi columns name the model version and the provider, but a provider can update its serving stack behind the same name, so a later rerun may differ.
- **Unequal inputs.** Gemini with the production prompt sees the whole bundle and the production scoring rules; every other column sees only the category's slice and a short question. For Laya that is forced by its 1024 tokens. JevK5, `qwen3:14b` and the short-prompt Gemini could all take more.

### Rerun, or read later

From the repo root:

```bash
make risk-report                        # print these tables from the stored results, no model calls
make risk                               # rerun laya, gemini, qwen and jevk5, 3 runs each; keeps the rest
make risk SYSTEMS=qwen32b               # rerun qwen3:32b, on a machine with 32 GB or more
make risk SYSTEMS="deepseek-pro deepseek-flash kimi-k3"   # through OpenRouter; needs OPENROUTER_API_KEY
make risk SYSTEMS="qwen" RUNS=3         # rerun one system
RAILCENTER=~/path/to/rail-center make risk SYSTEMS=gemini-prod   # needs a Rail Center checkout
```

What each system needs is in the [root README](../README.md#run-it-yourself). `gemini-prod` builds its prompt with Rail Center's own `profiling` package, so it runs only with a Rail Center checkout; the other systems need nothing outside this repo.

`results/bench_results.json` is self-contained:

| key | holds |
|---|---|
| `meta` | Settings and scale per system, the exact questions, the asp-datagen commit, run status. |
| `items` | Every item: the exact text sent, the facts it shows, and what was cut. |
| `results` | Every run and the median for every system × item, plus which categories production asked. |
| `summary` | The tables above, as data. |

## JevK5: choice, limits and tuning

Written on 2026-09-25. It draws on the run above, token counts taken with `llama-tokenize` on the same model file, and the projects' own pages, which are linked. Unlike the benchmark, these numbers are not in `results/bench_results.json`.

### Why JevK5, and not "OpenJev"

"OpenJev" names several unrelated projects, and none of them suits this task on this laptop:

| Project | What it is | Why not |
|---|---|---|
| [razorback16/openjev](https://github.com/razorback16/openjev) | A server that speaks Jev's API; by default it runs DiffusionGemma 26B-A4B | Its Mac build needs about 16 GB free, which is all of this laptop's memory. Its answers are not deterministic. |
| [openjev/openjev](https://huggingface.co/openjev/openjev) | A 27B model | Licensed CC BY-NC, so commercial use needs permission. About 15 GB even at 4-bit. |
| [AlexWortega/openjev](https://huggingface.co/AlexWortega/openjev) | A Qwen3.5 model for yes/no and entailment questions | It has no 1–10 score question. Its author measures 0.600 accuracy when it reviews shell commands for safety. |
| [OpenJev (Verdict)](https://huggingface.co/heman10x/rlcd-modernbert-151m) | A 151M ModernBERT model | Below stock Laya on JevBench. |
| [SemIf](https://github.com/TheoLeeCJ/SemIf-OpenJev), formerly OpenJev | Stock Qwen3.5-4B | Yes/no questions only. |

On [JevBench](https://benchmarkheaven.com/jev-models) v1.4.2, the open models closest to Jev on its accuracy score ("Intelligence") are:

| Model | Intelligence | Can it run on this Mac? |
|---|---|---|
| Jev 1.13.0, hosted, for reference | 53.1 | – |
| Cygnet, stock Gemma-4-12B | 49.5 | No: its server needs an NVIDIA GPU |
| decider-4b v2 | 49.4 | No: it needs NVIDIA kernels |
| JevK5 v0.2 | 48.9 | Yes, through llama.cpp |
| Stock Laya, for reference | 36.1 | Yes |

Jev and decider-4b v2 each answer only 38% of JevBench's hidden safety-judgement questions, so expect little from any Jev-class model at judging risk.

### What JevK5 was given, and what it can take

Token counts are in JevK5's own tokenizer:

| | tokens |
|---|---|
| JevK5's limit; it refuses longer input | 16,384 |
| The window `llama-server` ran with here (`-c 8192`) | 8,192 |
| What the benchmark sent: the category's slice as English, plus JevK5's wrapper | 291–818, median 690 |
| A whole bundle as English, plus the wrapper | 1,138–1,376, median 1,205 |
| Rail Center's production prompt for one bundle, system and user text | 3,523–4,591, median 4,127 |

- **JevK5 got the same slice as Laya,** because Laya cannot take more.
- **The whole bundle would fit, and so would a prompt the size of production's.** The production prompt itself is written for a model that replies in JSON, so its bundle and scoring rules would need repackaging as a JevK5 question.
- **So the gap between JevK5 and Gemini with the production prompt mixes the model with the input.** A JevK5 column that sees the whole bundle would separate the two.

### Hardware

| Use | Needs |
|---|---|
| Running it through llama.cpp, as here | Model files of 4.48 GB (Q8_0), 3.07 GB (Q5_K_M) or 2.71 GB (Q4_K_M). Runs on Apple, NVIDIA, AMD or Intel GPUs, or on a CPU alone. The [card](https://huggingface.co/alibiserikbay/JevK5-GGUF) recommends a GPU with 6 GB or more for Q8_0. |
| Measured here, M3 with 16 GB | 2.8 s per call at a median of 690 input tokens. |
| Published elsewhere | About 0.6 s per short decision on an M1 Pro. About 13 ms on an H100, or 30 ms for 1–4k-token documents. |
| Running it through PyTorch on NVIDIA | About 9 GB of GPU memory in bf16; JevK5-9B about 19 GB. |
| Fine-tuning | JevK5's training script runs PyTorch on an NVIDIA GPU, and no requirement is published. Estimate: a rented 24 GB+ GPU for 1–4k-token inputs, not this Mac. |

### Tuning: JevK5 or Laya

| | JevK5 (4B) | Laya (`typed-decisions`) |
|---|---|---|
| Zero-shot on this benchmark | Follows 3 of the 5 checks | Follows none |
| Input it can take | 16,384 tokens: the whole bundle and the production rules fit | Trained on 1,024 tokens. It can be stretched to 8,192, but quality there is untested. |
| How to fine-tune | A LoRA training script in the [JevK5 repo](https://github.com/allebee/jevk5) | A [published notebook](https://github.com/NandhaKishorM/laya): two free Kaggle T4 GPUs, 4–5 hours for 4 epochs over about 30k questions |
| Hardware to fine-tune | A rented NVIDIA GPU (estimate above) | Free-tier GPUs |
| Time per call on this M3 | 2.8 s | 241 ms |

**Recommendation: if either is tuned, tune JevK5.**
- **Try the whole bundle first.** It needs no training, so run JevK5 on it before tuning anything.
- **Changing the readout alone does not fix it.** Scoring by the most likely level improves three checks and worsens two; see [What it shows](#what-it-shows).
- **Either tune needs labels this repo does not have.** asp-datagen can generate bundles. The scores would have to come from a teacher, such as Gemini with the production prompt, checked against a hand-labelled holdout.
- **Don't train on asp-datagen's facts.** That would be circular, because the benchmark checks those same facts.

## Earlier: stock Laya on Rail Center's test-vector bundles (`asp_score.py`)

Before the benchmark, [`asp_score.py`](asp_score.py) asked stock Laya (`typed-decisions`) for all eight categories on the three bundles in Rail Center's test vectors (`api/tests/vectors/evidence_bundles/valid`). Those bundles are not copied into this repo, which is public: `python -m risk_detection.asp_score` reads them from a Rail Center checkout (`RAILCENTER`), and its saved results are in [`results/`](results). There was one score question per category, scored 1–10 with 10 safest. It also scored an empty input.

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
