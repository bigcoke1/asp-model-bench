# asp-laya-bench

Can a small decision model score agents for ASP (agent security profiling)? This repo tests stock [Laya](https://huggingface.co/convaiinnovations/laya) on the ASP risk categories, and benchmarks it against Gemini, `qwen3:14b` and JevK5 on the same questions.

- **"Stock"** means as published, not tuned on ASP data. Laya's `typed-decisions` checkpoint is already Convai's own fine-tune for general decisions: 0.766 on their benchmark, against 0.362 for the base model. JevK5 was also run as published.
- **The categories and required inputs** come from Rail Center (`api/src/profiling/coverage.py`).
- **The bundles** are Rail Center's test vectors and the synthetic bundles from `~/Desktop/asp-datagen`.
- **Split out of `laya_demo`** on 2026-09-25. The history before that is in `laya_demo`'s git log.

## Benchmark: stock Laya vs Gemini vs qwen3:14b vs JevK5

Can stock Laya score agent evidence bundles on the ASP risk categories, and how does it compare with Gemini, `qwen3:14b` and JevK5?
- **Gemini** is the model Rail Center's LLM profiler uses.
- **`qwen3:14b`** is the best open-weight model that fits this laptop.
- **JevK5** stands in for Jev, which could not be reached. Of the open Jev-class models, it ranks highest on [JevBench](https://benchmarkheaven.com/jev-models) v1.4.2 among those with a documented way to run on a Mac.

Run on 2026-09-25 with `bench.py`. Every number here is in `bench_results.json`.

**Short answer:**
- **Stock Laya does not read the evidence.** Every score lands between 4.8 and 5.7, and it scores empty input safer than any real agent.
- **Gemini with Rail Center's production prompt reads the evidence best:** it passes every check it was given. Its weaknesses:
  - Containment scores stay at 4 or below, so it separates risky agents from very risky ones but calls none of them safe.
  - Even at temperature 0, its three runs gave exactly the same score on only 15 of 32 items; 29 of 32 stayed within 1 point.
- **The prompt matters more than the model.** The same Gemini with a short prompt barely notices baked credentials.
- **qwen3:14b reads identity well but fails the empty-input check:** it gives no evidence at all a perfect 10.
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

| What a good scorer does | stock Laya | Gemini, short prompt | Gemini, production prompt | qwen3:14b | JevK5 |
|---|---|---|---|---|---|
| Scores agents that can reach the host **lower** on containment | ✗ no difference | ✓ 1.3 lower | ✓ 1.5 lower | ✓ 1.5 lower | ✓ 0.9 lower |
| Scores the privileged, root agents **2 or below** on containment | ✗ 0 of 2 | ✓ 2 of 2 | ✓ 2 of 2 | ✗ 0 of 2 | ✗ 0 of 2 |
| Scores agents with a baked credential **lower** on identity | ✗ no difference | ~ 0.3 lower (weak) | ✓ 2.9 lower | ✓ 2.2 lower | ✓ 1.6 lower |
| Scores agents holding no credentials **higher** on identity | ✗ no difference | ✓ 1.3 higher | ✓ 2.6 higher | ✓ 2.2 higher | ✓ 1.6 higher |
| Does **not** score an empty input as safe (identity / containment) | ✗ 6.0 / 6.0: safer than every real bundle | ✓ 1.0 / 1.0 | – not asked (coverage clears nothing) | ✗ 10.0 / 10.0: safer than every real bundle | ~ 7.4 / 6.8: safer than 16 of 20 / 10 of 12 real bundles |
| Range of scores across agents (identity / containment) | 4.8–5.4 / 5.2–5.7 | 1–6 / 1–3 | 1–8 / 0–4 | 1–8 / 3–6 | 1.6–8.1 / 3.0–7.9 |
| Items where the 3 runs agreed: exactly / within 1 point | 34 / 34 of 34 | 30 / 33 of 34 | 15 / 29 of 32 | 33 / 34 of 34 | 34 / 34 of 34 |
| Median time per call | 241 ms | 587 ms | 2,442 ms | 1,272 ms | 2,791 ms |

Notes on the scorecard:
- **Why production was not asked the empty input:** production never calls a model when coverage clears nothing, so this benchmark doesn't either.
- **Why its time per call is longer:** one production call scores all 6–7 categories coverage clears, not one.
- **Why qwen3:14b looks faster than JevK5:** Ollama reuses a prompt it has just seen, so qwen3:14b's first run of an item takes 6.2 s and the two repeats 0.8 s (medians). JevK5's client turns that cache off, so each of its runs takes about 2.8 s for a median of 690 input tokens.
- **What "agreed" means:** "exactly" needs all three runs identical, so 5, 5, 6 does not count; "within 1 point" means the highest and lowest runs are at most 1 apart. The reported score is the median, which absorbs a single stray run: 5, 5, 6 gives 5. A 1-point wobble can still flip an agent's band when a band threshold falls between the two values.

### The averages behind the scorecard

| Average score of … (number of agents) | stock Laya | Gemini, short prompt | Gemini, production prompt | qwen3:14b | JevK5 |
|---|---|---|---|---|---|
| containment, agents that **can** reach the host (6) | 5.4 | 1.0 | 1.0 | 4.5 | 5.7 |
| containment, agents that **cannot** (6) | 5.5 | 2.3 | 2.5 | 6.0 | 6.7 |
| identity, agents **with** a visible baked credential (5) | 5.1 | 2.0 | 3.0 | 4.6 | 4.5 |
| identity, agents **without** one (15) | 5.1 | 2.3 | 5.9 | 6.8 | 6.1 |
| identity, agents holding **no** credentials (4) | 5.1 | 3.2 | 7.2 | 8.0 | 7.0 |
| identity, agents holding **some** (16) | 5.1 | 1.9 | 4.7 | 5.8 | 5.4 |

For example, Gemini with the production prompt gives agents with a baked credential 3.0 on average and agents without one 5.9. That is the "✓ 2.9 lower" in the scorecard.

### Do the systems rank agents alike?

Spearman rank correlation: 1 means the same order, 0 unrelated, negative the opposite order.

| pair | identity | containment |
|---|---|---|
| stock Laya ~ Gemini, short prompt | 0.08 | 0.31 |
| stock Laya ~ Gemini, production prompt | 0.04 | 0.00 |
| stock Laya ~ qwen3:14b | 0.11 | 0.19 |
| stock Laya ~ JevK5 | −0.08 | 0.14 |
| Gemini, short prompt ~ Gemini, production prompt | 0.15 | 0.43 |
| Gemini, short prompt ~ qwen3:14b | 0.36 | 0.49 |
| Gemini, short prompt ~ JevK5 | 0.46 | 0.15 |
| Gemini, production prompt ~ qwen3:14b | 0.43 | 0.65 |
| Gemini, production prompt ~ JevK5 | 0.43 | 0.08 |
| qwen3:14b ~ JevK5 | 0.51 | 0.24 |

Stock Laya's ranking is unrelated to every other system's. Gemini with the production prompt and `qwen3:14b` agree most, but still only moderately. JevK5 ranks identity about as the LLMs do (0.43–0.51), but its containment ranking is nearly unrelated to theirs (0.08–0.24).

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
| Items | The 20 synthetic bundles from `asp-datagen` (pilot 1), on `identity` (20 evaluable) and `containment` (12 evaluable; the other 8 would be `INSUFFICIENT_EVIDENCE`, so production would not ask). Plus one empty input per category: 34 items. |
| Input, every column but the production prompt | The same for every system: the bundle cut to the category's attributes and written as English (`asp_score.py --format prose --scope category`), trimmed to Laya's 1024 tokens so Laya sees all of it. Nothing needed trimming: 0 of 32 items. |
| Question, every column but the production prompt | The same: `asp_score.question()`, 10 levels scored 1–10. Ten, not the design doc's 0–10, because Jev (planned as another column) accepts at most 10 levels. |
| Gemini, production prompt | The whole bundle through Rail Center's own `profiling.prompt.render_prompt` (v7, identical to `origin/master`). One call per bundle asks every category coverage clears; `identity` and `containment` are read from the reply. The score is the model's raw 0–10, before the mixer's clamps. |
| Runs | Every system answers every item 3 times; its score is the median. Production keeps the lowest of three instead. |
| Models | Laya `typed-decisions`, stock, local and deterministic. Gemini `gemini-3.5-flash-lite` through the OpenAI-compatible endpoint, temperature 0, JSON output, as Rail Center calls it. `qwen3:14b` on local Ollama, thinking off, temperature 0. JevK5 v0.3, 4B, as `jevk5-4b-v0.3-Q8_0.gguf` on a local `llama-server` (llama.cpp b11146, Metal), read through JevK5's own client at the file's calibration temperature, 1.22. JevBench ranked v0.2; v0.3 is the current release. |
| Jev | Not run: thejevai.com's upstream provider rejected every request, and TypeSafe is not taking signups. JevK5 stands in for it. `bench.py --systems jev --merge` adds Jev later. |

**Caveats:**
- **No ground truth.** The bundles are synthetic and no one has labelled them by hand. The checks show whether a score moves with a visible fact, not whether it is right.
- **Small numbers.** Each check rests on 2 to 16 agents; the privileged-root check rests on 2.
- **Unequal inputs.** Gemini with the production prompt sees the whole bundle and the production scoring rules; every other column sees only the category's slice and a short question. For Laya that is forced by its 1024 tokens. JevK5, `qwen3:14b` and the short-prompt Gemini could all take more.

### Rerun, or read later

```bash
GOOGLE_API_KEY=... python bench.py                  # all systems, 3 runs each (needs Ollama and llama-server, see Setup)
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

## JevK5: choice, limits and tuning

Written on 2026-09-25. It draws on the run above, token counts taken with `llama-tokenize` on the same model file, and the projects' own pages, which are linked. Unlike the benchmark, these numbers are not in `bench_results.json`.

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
# for JevK5 (`brew install llama.cpp`); the first start downloads the 4.5 GB file.
# bench.py checks the served file's name; set JEVK5_URL for another port.
llama-server --hf-repo alibiserikbay/JevK5-GGUF --hf-file jevk5-4b-v0.3-Q8_0.gguf -c 8192 -ngl 99 --port 8093 &
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
bench.py                stock Laya vs Gemini (short and production prompt) vs qwen3:14b vs JevK5 (vs Jev)
bench_results.json      everything bench.py sent and got back, plus the summary
```
