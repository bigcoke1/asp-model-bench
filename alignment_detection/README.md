# Alignment detection

Given two snapshots of the same agent's evidence bundle, taken at different times, which attributes are no longer aligned? An alignment detector compares them attribute by attribute. It has to catch a real change, such as a new mount, a mount switched from `ro` to `rw`, or a lookalike hostname. It also has to ignore the same fact written differently, such as a reordered list, `root` written as `0`, or a reworded collector note.

Unlike [risk detection](../risk_detection), this task has ground truth. The later snapshots are made by editing copies of the bundles, so every label is known.

**Short answer:**
- **Three models are good at it (F1 of 0.90 or more): qwen3:14b (0.95), Gemini (0.93) and JevK5 (0.90).** All three catch nearly every real change: qwen3:14b misses none of the 120, and Gemini and JevK5 miss one each.
- **Their mistakes are mostly false alarms on equivalent notation.** Every model calls `root` → `0` misaligned in all 7 cases, and trailing slashes trip all three.
- **Two misses matter.** JevK5 passed `db.example.com` → `db.examp1e.com`, a lookalike host, as unchanged. Gemini passed a credential's class changing from `secret_plaintext` to `secret_ref`.
- **Simple rules get most of the way.** Normalized diff uses no model, scores 0.87 and misses nothing. The models beat it only on equivalent notation.
- **Stock Laya is worse than a plain text diff (0.38).** Its probabilities rank misaligned attributes no better than chance (AUROC 0.52).

Run on 2026-09-25 with `bench.py`. Every number here is in [`results/alignment_results.json`](results/alignment_results.json).

## Results

Ranked by F1. The verdict is explained in [How to read the tables](#how-to-read-the-tables).

| rank | system | verdict | F1 | precision | recall | accuracy | AUROC | time per call |
|---|---|---|---|---|---|---|---|---|
| 1 | qwen3:14b | ✓ good | **0.95** | 0.91 | 1.00 | 0.97 | – | 4,350 ms |
| 2 | Gemini | ✓ good | **0.93** | 0.88 | 0.99 | 0.95 | – | 586 ms |
| 3 | JevK5 | ✓ good | **0.90** | 0.83 | 0.99 | 0.94 | 0.99 | 2,327 ms |
| 4 | normalized diff (baseline) | ~ fair | **0.87** | 0.77 | 1.00 | 0.91 | – | – |
| 5 | exact diff (baseline) | ✗ poor | **0.67** | 0.50 | 1.00 | 0.70 | – | – |
| 6 | stock Laya | ✗ poor | **0.38** | 0.33 | 0.44 | 0.56 | 0.52 | 119 ms |

### Where each system goes wrong

Each misalignment row counts changes caught, so higher is better; each false-alarm row counts attributes wrongly flagged, so lower is better.

| | qwen3:14b | Gemini | JevK5 | normalized diff (baseline) | exact diff (baseline) | stock Laya |
|---|---|---|---|---|---|---|
| Misalignment caught: plain (add, remove, replace, evidence lost or gained) | 60 / 60 | 60 / 60 | 60 / 60 | 60 / 60 | 60 / 60 | 15 / 60 |
| Misalignment caught: subtle (one field or one character) | 60 / 60 | 59 / 60 | 59 / 60 | 60 / 60 | 60 / 60 | 38 / 60 |
| False alarms: reformatted (reordered, note reworded) | 0 / 60 ✓ | 0 / 60 ✓ | 1 / 60 | 0 / 60 ✓ | 60 / 60 | 34 / 60 |
| False alarms: equivalent notation (case, slash, uid 0, CAP_, v1, :443, read-only) | 12 / 60 | 17 / 60 | 24 / 60 | 36 / 60 | 60 / 60 | 34 / 60 |
| False alarms: identical | 0 / 160 ✓ | 0 / 160 ✓ | 0 / 160 ✓ | 0 / 160 ✓ | 0 / 160 ✓ | 41 / 160 |

<details>
<summary>By kind of change</summary>

| change | label | qwen3:14b | Gemini | JevK5 | normalized diff (baseline) | exact diff (baseline) | stock Laya |
|---|---|---|---|---|---|---|---|
| `add_item` | misaligned: caught | 10 / 10 | 10 / 10 | 10 / 10 | 10 / 10 | 10 / 10 | 3 / 10 |
| `allow_more` | misaligned: caught | 5 / 5 | 5 / 5 | 5 / 5 | 5 / 5 | 5 / 5 | 5 / 5 |
| `approval` | misaligned: caught | 5 / 5 | 5 / 5 | 5 / 5 | 5 / 5 | 5 / 5 | 2 / 5 |
| `cap_added` | misaligned: caught | 4 / 4 | 4 / 4 | 4 / 4 | 4 / 4 | 4 / 4 | 1 / 4 |
| `cred_class` | misaligned: caught | 5 / 5 | 4 / 5 | 5 / 5 | 5 / 5 | 5 / 5 | 5 / 5 |
| `digest_digit` | misaligned: caught | 5 / 5 | 5 / 5 | 5 / 5 | 5 / 5 | 5 / 5 | 5 / 5 |
| `evidence_gained` | misaligned: caught | 10 / 10 | 10 / 10 | 10 / 10 | 10 / 10 | 10 / 10 | 3 / 10 |
| `evidence_lost` | misaligned: caught | 10 / 10 | 10 / 10 | 10 / 10 | 10 / 10 | 10 / 10 | 0 / 10 |
| `flag_flip` | misaligned: caught | 10 / 10 | 10 / 10 | 10 / 10 | 10 / 10 | 10 / 10 | 0 / 10 |
| `lookalike_host` | misaligned: caught | 5 / 5 | 5 / 5 | 4 / 5 | 5 / 5 | 5 / 5 | 3 / 5 |
| `mcp_mode` | misaligned: caught | 4 / 4 | 4 / 4 | 4 / 4 | 4 / 4 | 4 / 4 | 2 / 4 |
| `mount_mode` | misaligned: caught | 4 / 4 | 4 / 4 | 4 / 4 | 4 / 4 | 4 / 4 | 2 / 4 |
| `privileged` | misaligned: caught | 5 / 5 | 5 / 5 | 5 / 5 | 5 / 5 | 5 / 5 | 0 / 5 |
| `provenance` | misaligned: caught | 3 / 3 | 3 / 3 | 3 / 3 | 3 / 3 | 3 / 3 | 3 / 3 |
| `remove_item` | misaligned: caught | 10 / 10 | 10 / 10 | 10 / 10 | 10 / 10 | 10 / 10 | 5 / 10 |
| `replace_value` | misaligned: caught | 10 / 10 | 10 / 10 | 10 / 10 | 10 / 10 | 10 / 10 | 4 / 10 |
| `root_fs` | misaligned: caught | 5 / 5 | 5 / 5 | 5 / 5 | 5 / 5 | 5 / 5 | 5 / 5 |
| `tls_flip` | misaligned: caught | 5 / 5 | 5 / 5 | 5 / 5 | 5 / 5 | 5 / 5 | 2 / 5 |
| `version_bump` | misaligned: caught | 5 / 5 | 5 / 5 | 5 / 5 | 5 / 5 | 5 / 5 | 3 / 5 |
| `cap_prefix` | aligned: false alarms | 0 / 3 ✓ | 2 / 3 | 0 / 3 ✓ | 3 / 3 | 3 / 3 | 1 / 3 |
| `default_port` | aligned: false alarms | 0 / 6 ✓ | 1 / 6 | 6 / 6 | 6 / 6 | 6 / 6 | 6 / 6 |
| `host_case` | aligned: false alarms | 0 / 12 ✓ | 0 / 12 ✓ | 0 / 12 ✓ | 0 / 12 ✓ | 12 / 12 | 9 / 12 |
| `identical` | aligned: false alarms | 0 / 160 ✓ | 0 / 160 ✓ | 0 / 160 ✓ | 0 / 160 ✓ | 0 / 160 ✓ | 41 / 160 |
| `mode_alias` | aligned: false alarms | 0 / 10 ✓ | 4 / 10 | 0 / 10 ✓ | 10 / 10 | 10 / 10 | 5 / 10 |
| `reorder_keys` | aligned: false alarms | 0 / 20 ✓ | 0 / 20 ✓ | 0 / 20 ✓ | 0 / 20 ✓ | 20 / 20 | 13 / 20 |
| `reorder_list` | aligned: false alarms | 0 / 20 ✓ | 0 / 20 ✓ | 1 / 20 | 0 / 20 ✓ | 20 / 20 | 16 / 20 |
| `reword_note` | aligned: false alarms | 0 / 20 ✓ | 0 / 20 ✓ | 0 / 20 ✓ | 0 / 20 ✓ | 20 / 20 | 5 / 20 |
| `trailing_slash` | aligned: false alarms | 5 / 12 | 3 / 12 | 4 / 12 | 0 / 12 ✓ | 12 / 12 | 7 / 12 |
| `uid_alias` | aligned: false alarms | 7 / 7 | 7 / 7 | 7 / 7 | 7 / 7 | 7 / 7 | 0 / 7 ✓ |
| `version_prefix` | aligned: false alarms | 0 / 10 ✓ | 0 / 10 ✓ | 7 / 10 | 10 / 10 | 10 / 10 | 6 / 10 |

</details>

### What it shows

- **qwen3:14b is the best alignment detector here.**
  - It caught all 120 real changes, including every lookalike host and the one-digit changes to image digests.
  - Its 12 false alarms are all equivalent notation: trailing slashes (5 of 12) and `root` → `0` (7 of 7).
  - It took 4.4 s per call because this 16 GB laptop was swapping during the run. Its first 50 items took 3.4 s each.
- **Gemini is nearly as good, and the fastest model at 0.6 s per call.**
  - It missed one change: `QUIZ_MTLS_CERT` going from `secret_plaintext` to `secret_ref`.
  - Its 17 false alarms: `root` → `0` (7 of 7), `ro` → `read-only` (4 of 10), trailing slashes (3 of 12), `CAP_` prefixes (2 of 3) and one explicit `:443`.
- **JevK5 is good, and the lightest model that is (4B, local).**
  - Its one miss is a lookalike host, `db.example.com` → `db.examp1e.com`, exactly the kind of change an alignment detector exists to catch.
  - Its 25 false alarms:
    - `root` → `0` (7 of 7);
    - an explicit `:443` (6 of 6);
    - `v`-prefixed versions (7 of 10);
    - trailing slashes (4 of 12);
    - one reordered list.
  - Its AUROC of 0.99 means its probabilities nearly separate misaligned from aligned. A threshold of 0.55 instead of 0.5 would give F1 0.93 on these items, but that threshold was picked on the same items, so treat it as optimistic.
- **Normalized diff is the line a model has to beat.** It catches every change and raises no false alarms on formatting or on identical attributes. All 36 of its false alarms are equivalent notation it has no rule for: `root` = `0`, `CAP_`, `v`-prefixes, `:443` and `read-only`.
- **Exact diff flags every reformatting,** so half of what it flags is noise (precision 0.50).
- **Stock Laya is unusable here.**
  - It misses 67 of the 120 changes, including every `evidence_lost` and every `privileged` flip.
  - It raises false alarms on 41 of the 160 identical attributes.
  - With an AUROC of 0.52, no threshold rescues it: its best F1 at any threshold on these items is 0.46.


## How to read the tables

Each item is one attribute in one pair of snapshots, and the question is whether it is misaligned. **Misaligned is the positive class.**

| metric | what it answers |
|---|---|
| **F1** (the ranking) | One number that balances precision and recall; it is high only when both are. |
| precision | Of the attributes a system flagged, how many were really misaligned? False alarms lower it. |
| recall | Of the misaligned attributes, how many did it flag? Misses lower it. |
| accuracy | Share of all items answered right. It flatters a lazy system: 70% of items are aligned, so always answering "aligned" scores 0.70. |
| AUROC | Only for Laya and JevK5, which output a probability of misalignment: the chance that a misaligned attribute gets a higher probability than an aligned one. 1.0 means the probabilities separate the two perfectly, and 0.5 means no better than chance. |

**Verdict:**
- **✓ good:** F1 of 0.90 or more.
- **~ fair:** 0.75 to 0.90.
- **✗ poor:** below 0.75.

Exact diff scores 0.67, so anything below it does worse than comparing the two snapshots as text.

## The dataset

| | |
|---|---|
| Earlier snapshots | The 20 bundles in [`../data/bundles`](../data/bundles). |
| Later snapshots | 2 per bundle, 40 in all, in [`data/after`](data/after): full bundles, each `collected_at` 7 or 14 days later. |
| Edits per later snapshot | 3 that change a fact (misaligned), 3 that write the same fact differently (aligned), each on a different attribute. |
| Labels | [`data/labels.jsonl`](data/labels.jsonl): all 26 attributes of every later snapshot, 1,040 rows, each with its label, tier, kind of change, and what changed. |
| Asked | The 6 edited attributes plus 4 untouched ones per snapshot (3 with a value, 1 without): 400 items. 120 are misaligned and 280 aligned. |
| Built by | [`make_pairs.py`](make_pairs.py), seeded, so it is deterministic. `make alignment-data` rebuilds it, and `make check` confirms the files match a fresh build. |

The question every system gets, exactly as run. Its wording predates the rename to alignment, so it says "drifted":

> Two snapshots of the same attribute from an AI agent's security evidence bundle, collected at different times. Has the attribute drifted? It has drifted if the later snapshot states a different fact about the agent: a different value, setting, item or version, or a change in whether the attribute could be observed. It has not drifted if it states the same fact written differently, for example with items or keys in another order, different letter case, or equivalent notation, or if only the collector's method or note is worded differently.

The input is the attribute's name, then each snapshot as JSON:

```
Attribute: mounts
Earlier snapshot: {"value": [{"source": "/var/run/secrets/…", "target": "/var/run/secrets/…", "mode": "ro"}, …], "status": "ANSWERED", …}
Later snapshot: {"value": [{"source": "/var/run/secrets/…", "target": "/var/run/secrets/…", "mode": "rw"}, …], "status": "ANSWERED", …}
```

The kinds of change, balanced across the dataset:

| tier | label | kinds, with an example |
|---|---|---|
| plain | misaligned | `add_item` (a tool, mount, host, credential or skill added), `remove_item`, `replace_value` (a different model, workdir, endpoint, user or network policy; a new image digest), `evidence_lost` (`ANSWERED` → `BLIND`), `evidence_gained` (`ABSENT` or `BLIND` → `ANSWERED`), `flag_flip` (`system_prompt_present` true → false) |
| subtle | misaligned | `mount_mode` (`ro` → `rw`), `privileged`, `root_fs`, `cap_added` (`+SYS_ADMIN`), `tls_flip`, `provenance` (`injected` → `baked`), `cred_class` (`secret_ref` → `secret_plaintext`), `version_bump` (`crewai/0.86.0` → `0.86.1`), `allow_more` (`*` added to the allow list), `approval`, `digest_digit` (one hex digit of the image digest), `lookalike_host` (`github-123` → `g1thub-123`), `mcp_mode` |
| formatting | aligned | `reorder_list`, `reorder_keys`, `reword_note` (the collector's `method` or `note` said another way) |
| notation | aligned | `host_case` (hostnames are case-insensitive), `trailing_slash` (`/app/x` → `/app/x/`), `uid_alias` (`root` → `0`), `cap_prefix` (`NET_BIND_SERVICE` → `CAP_NET_BIND_SERVICE`), `version_prefix` (`0.86.0` → `v0.86.0`), `default_port` (`https://host` → `https://host:443`), `mode_alias` (`ro` → `read-only`) |
| identical | aligned | untouched attributes, as controls |

## The systems

| system | how it answers |
|---|---|
| exact diff (baseline) | Misaligned whenever the two snapshots' JSON differs at all. |
| normalized diff (baseline) | Misaligned when `status` or `value` differs after generic clean-up: lists and keys sorted, strings lower-cased and trimmed, trailing slashes dropped, `method` and `note` ignored. It knows no per-attribute equivalences such as `root` = `0`. |
| stock Laya | `typed-decisions` checkpoint, the question as a yes/no; misaligned when P(yes) ≥ 0.5. Every input fits its 1,024 tokens (the longest is 492). |
| JevK5 | v0.3 4B, `jevk5-4b-v0.3-Q8_0.gguf` on a local `llama-server`, the question as a yes/no at the file's calibration temperature, 1.22; misaligned when P(yes) ≥ 0.5. |
| qwen3:14b | Local Ollama, thinking off, temperature 0, reply constrained to `{"drift": true/false}` (the prompt's wording, as run). |
| Gemini | `gemini-3.5-flash-lite` through the OpenAI-compatible endpoint, temperature 0, JSON output. |

Every system answered every item once. Laya and JevK5 are deterministic, and the LLMs run at temperature 0. `RUNS=3` takes a majority of three instead.

## Caveats

- **The edits are synthetic.** The kinds of change are ones chosen to cover real ASP misalignment. Real misalignment can look different, for example two changes in one attribute, or a collector upgrade that rewrites every note at once.
- **"Equivalent notation" is a judgement.** `root` and `0` are the same user, and `/app/x/` is the same directory as `/app/x`, but a reader may disagree with a kind. The per-kind table shows each one separately, so it can be discounted.
- **Normalized diff overlaps the formatting edits by design.** Its rules (sorting, case, trailing slashes, ignoring notes) are the generic ones anyone would write first, and they happen to cover formatting fully. It stands for what simple rules get you. Adding per-attribute rules, such as `root` = `0`, `ro` = `read-only` and dropping `:443`, would raise it further.
- **Small counts per kind:** 3 to 20 items each, and 160 identical controls.
- **One run per item.** In the risk benchmark, Gemini at temperature 0 was not fully deterministic.

## Rerun, or read later

From the repo root:

```bash
make alignment-report                  # print these tables from the stored results, no model calls
make alignment-quick                   # rerun the two diff baselines, no model, a few seconds
make alignment                         # rerun all six systems (about an hour on an M3; see the root README for servers and keys)
make alignment SYSTEMS="gemini laya"   # rerun some; the other systems' stored results are kept
make alignment-data                    # rebuild the dataset (then rerun, since the items change)
```

[`results/alignment_results.json`](results/alignment_results.json) is self-contained:

| key | holds |
|---|---|
| `meta` | The question, each system's settings, run status. |
| `items` | Every item: its label, tier, kind of change, what changed, and the exact text sent. |
| `results` | Every system's answer per item, with P(misaligned) for Laya and JevK5 and the time per call. |
| `summary` | The tables above, as data, including the per-kind counts. |
