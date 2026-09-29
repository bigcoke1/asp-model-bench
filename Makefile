# asp-model-bench: run the benchmarks yourself. `make help` lists the targets.
#
#   make setup                     once: .venv and the Python dependencies
#   make report                    print both benchmarks' tables from the stored results (no models)
#   make alignment SYSTEMS="laya"  rerun one system on one benchmark; the other systems' results are kept
#
# Local models need their servers running first, each in its own terminal:
#   qwen3:14b   `ollama serve`         (after `make models`)
#   JevK5       `make serve-jevk5`     (needs llama.cpp: `brew install llama.cpp`)
# Gemini needs GOOGLE_API_KEY in the environment. A system whose server or key is missing is
# recorded as "not run" and the rest carry on.

PY       ?= .venv/bin/python
SYSTEMS  ?=
RUNS     ?=
JEVK5_PORT ?= 8093

RISK_SYSTEMS      = $(or $(SYSTEMS),laya gemini qwen jevk5)
ALIGNMENT_SYSTEMS = $(or $(SYSTEMS),exact-diff normalized-diff laya jevk5 qwen gemini)
RUNS_FLAG         = $(if $(RUNS),--runs $(RUNS))

.PHONY: help setup models serve-jevk5 risk risk-report alignment-data alignment alignment-report alignment-quick report check clean

help:  ## list the targets
	@grep -E '^[a-z0-9-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  make %-17s %s\n", $$1, $$2}'

setup:  ## create .venv and install the Python dependencies
	python3 -m venv .venv
	$(PY) -m pip install -r requirements.txt

models:  ## download the local models: qwen3:14b (9.3 GB, Ollama) and JevK5 (4.5 GB)
	ollama pull qwen3:14b
	$(PY) -c "from huggingface_hub import hf_hub_download as d; print(d('alibiserikbay/JevK5-GGUF', 'jevk5-4b-v0.3-Q8_0.gguf'))"

serve-jevk5:  ## serve JevK5 with llama.cpp on port 8093 (JEVK5_PORT); stays in the foreground
	llama-server --hf-repo alibiserikbay/JevK5-GGUF --hf-file jevk5-4b-v0.3-Q8_0.gguf \
		-c 8192 -ngl 99 --host 127.0.0.1 --port $(JEVK5_PORT)

risk:  ## run risk detection (SYSTEMS default: laya gemini qwen jevk5; RUNS default 3; qwen32b and the OpenRouter models only by name)
	$(PY) -m risk_detection.bench --merge --systems $(RISK_SYSTEMS) $(RUNS_FLAG)

risk-report:  ## print the risk-detection tables from the stored results
	$(PY) -m risk_detection.bench --report

alignment-data:  ## rebuild the alignment dataset in alignment_detection/data (deterministic)
	$(PY) -m alignment_detection.make_pairs

alignment:  ## run alignment detection (SYSTEMS default: all but qwen32b and the OpenRouter models; RUNS default 1)
	$(PY) -m alignment_detection.bench --merge --systems $(ALIGNMENT_SYSTEMS) $(RUNS_FLAG)

alignment-quick:  ## alignment detection with no model at all: the two diff baselines, in seconds
	$(PY) -m alignment_detection.bench --merge --systems exact-diff normalized-diff

alignment-report:  ## print the alignment-detection tables from the stored results
	$(PY) -m alignment_detection.bench --report

report: risk-report alignment-report  ## print both benchmarks' tables

check:  ## confirm the data and inputs rebuild exactly as stored (no model calls)
	$(PY) -m alignment_detection.make_pairs --check
	$(PY) -m alignment_detection.bench --check
	$(PY) -m risk_detection.bench --check

clean:  ## remove Python caches
	find . -name __pycache__ -not -path './.venv/*' -prune -exec rm -rf {} +
