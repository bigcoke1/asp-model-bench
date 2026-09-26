# asp-model-bench

Benchmarks for the models behind **agent security profiling (ASP)**. Each task asks whether a model can read an AI agent's evidence bundle and make a call a profiler needs. A bundle records what the agent runs as, what it can reach, and which credentials and tools it holds. Every task runs on the same 20 synthetic bundles in [`data/`](data), so anyone can rerun them: see [Run it yourself](#run-it-yourself).

| task | the question | ground truth | folder |
|---|---|---|---|
| **Risk detection** | How risky is this agent in one category, scored 1–10? | None. The checks ask whether a score follows risky facts the bundle shows. | [`risk_detection/`](risk_detection) |
| **Alignment detection** | Between two snapshots of the same agent, which attributes changed? | Yes. The later snapshots are made by known edits. | [`alignment_detection/`](alignment_detection) |

## Which model is good

| system | where it runs | risk detection: checks passed | alignment detection: F1 |
|---|---|---|---|
| Gemini, Rail Center's production prompt | Google API | ✓ **4 of 4** asked | – not run; the prompt is written for risk |
| Gemini, short prompt | Google API | ~ 4 of 5; the fifth only weakly | ✓ **0.93** |
| qwen3:14b (open) | this laptop, Ollama | ~ 3 of 5 | ✓ **0.95**, best |
| JevK5 (open, 4B) | this laptop, llama.cpp | ~ 3 of 5 | ✓ **0.90** |
| stock Laya (open, 0.4B) | this laptop, CPU | ✗ **0 of 5** | ✗ **0.38**, worse than a text diff |
| normalized diff (rules, no model) | anywhere | – | ~ 0.87 |
| exact diff (rules, no model) | anywhere | – | ✗ 0.67 |

The model is `gemini-3.5-flash-lite` in both Gemini rows.

- **For risk detection, use Gemini with Rail Center's production prompt.** It is the only system that passes every risk check.
- **For alignment detection, qwen3:14b, Gemini and JevK5 are all good (F1 0.90–0.95).** qwen3:14b is best and runs locally. All three catch nearly every real change. Their mistakes are mostly false alarms on equivalent notation, such as `root` written as `0`.
- **JevK5 is the lightest model that does well (4B, local).** It is good on alignment. On risk it follows credentials and host reach, but it scores empty input as safe, and neither privileged, root agent scores 2 or below; one scores 6.3.
- **Stock Laya is not usable for either task.** On alignment, its probabilities rank misaligned attributes no better than chance (AUROC 0.52). On risk, every score lands near 5.
- **Simple rules make a strong alignment baseline.** Normalized diff sorts lists and keys, ignores case and trailing slashes, and scores 0.87 with no model. The models beat it only by recognising equivalent notation, and even there they raise false alarms.
- **Neither task's results carry over to real agents yet.** The bundles are synthetic and risk detection has no ground truth; each folder's README lists its caveats.

Each folder's README has the full tables, the method and the caveats.

## Run it yourself

You need Python 3.12 and `make`. Each model has its own extra requirement:

| system | needs | time for a full run on an M3 laptop with 16 GB |
|---|---|---|
| exact diff, normalized diff | nothing | seconds |
| stock Laya | nothing; downloads its checkpoint on first use | about 1 minute per task |
| Gemini | `GOOGLE_API_KEY` in the environment | about 4 minutes for alignment |
| qwen3:14b | [Ollama](https://ollama.com): `make models`, then `ollama serve` | about 25–35 minutes for alignment |
| JevK5 | [llama.cpp](https://github.com/ggml-org/llama.cpp) (`brew install llama.cpp`): `make models`, then `make serve-jevk5` | about 16 minutes for alignment |
| Gemini, production prompt (risk only) | a Rail Center checkout, at `RAILCENTER` (default `~/workspace/rail-center-rc000`) | about 2 minutes |

```bash
make setup           # .venv and the Python dependencies
make report          # both benchmarks' tables from the stored results, no model calls
make check           # confirm the data and the inputs rebuild exactly as stored
make alignment-quick # the two diff baselines on alignment: no model, a few seconds

make models          # qwen3:14b and JevK5's weights, about 14 GB
ollama serve         # in a second terminal, for qwen3:14b
make serve-jevk5     # in a third terminal, for JevK5
export GOOGLE_API_KEY=...

make alignment       # all six systems on alignment detection
make risk            # laya, gemini, qwen and jevk5 on risk detection, 3 runs each
make alignment SYSTEMS="laya gemini" RUNS=3   # some systems; the others' stored results are kept
```

- **Missing servers or keys:** a system whose server or key is missing is recorded as "not run", and the rest carry on.
- **Memory:** qwen3:14b and JevK5 together need about 14 GB. On a 16 GB machine, stop one server before running the other. `make help` lists every target.

## Layout

```
data/                  the 20 evidence bundles and the facts behind them (data/README.md)
aspbench/              shared code: loading the bundles, reaching each model
risk_detection/        bench.py, asp_score.py (an earlier experiment), results/, README.md
alignment_detection/   make_pairs.py (builds the dataset), data/ (later snapshots, labels),
                       bench.py, results/, README.md
Makefile               every way to run it
```

## Data

The bundles are synthetic and were generated by `asp-datagen`. No real agent, host or credential is behind any of them. [`data/README.md`](data/README.md) covers where they come from, their format, and what is deliberately left out. Rail Center's own test-vector bundles are not included, because this repository is public.

This repository was called `asp-laya-bench` until 2026-09-25, when it only tested Laya.
