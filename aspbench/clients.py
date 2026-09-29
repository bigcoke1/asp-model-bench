"""How each benchmark reaches its models: HTTP for Gemini, OpenRouter, Ollama and llama-server; Laya in-process."""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
import warnings

GEMINI_OPENAI = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
OPENROUTER = "https://openrouter.ai/api/v1/chat/completions"
OLLAMA = os.environ.get("OLLAMA_URL", "http://localhost:11434")
JEVK5_URL = os.environ.get("JEVK5_URL", "http://127.0.0.1:8093")
JEVK5_FILE = "jevk5-4b-v0.3-Q8_0.gguf"
JEVK5_SHA256 = "aea433883bc7ed399f2fbd539e53d2eac7caf71a946fe6650995a413979d4a30"
JEVK5_TEMPERATURE = 1.22  # this file's, from the JevK5-GGUF card; the client's docstring still says 1.367


def post(url: str, headers: dict, body: dict, timeout: int = 300) -> dict:
    # A User-Agent of our own: some Cloudflare fronts refuse Python's default one (error 1010).
    req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json", "User-Agent": "asp-bench/0.1", **headers})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def gemini_json(model: str, messages: list[dict]) -> dict | None:
    """One Gemini call through the OpenAI-compatible endpoint, as Rail Center calls it: temperature
    0, JSON output. The parsed reply, or None when it is not JSON."""
    r = post(GEMINI_OPENAI, {"Authorization": f"Bearer {os.environ.get('GOOGLE_API_KEY')}"},
             {"model": model, "temperature": 0, "response_format": {"type": "json_object"}, "messages": messages})
    try:
        return json.loads(r["choices"][0]["message"]["content"])
    except (KeyError, TypeError, json.JSONDecodeError):
        return None


def openrouter_json(model: str, provider: str, messages: list[dict]) -> dict | None:
    """One call to an open-weight model through OpenRouter, on the one provider named (an endpoint
    tag such as "deepseek" or "deepinfra/fp8"), never a fallback: temperature 0, reasoning off, JSON
    output. Rate limits and server errors are retried, so one busy moment does not end a run. The
    parsed reply, or None when it is not JSON."""
    body = {"model": model, "temperature": 0, "response_format": {"type": "json_object"}, "messages": messages,
            "reasoning": {"enabled": False}, "provider": {"only": [provider], "allow_fallbacks": False}}
    for wait in (2, 4, 8, 16, 32, None):
        try:
            r = post(OPENROUTER, {"Authorization": f"Bearer {os.environ.get('OPENROUTER_API_KEY')}"}, body)
            break
        except urllib.error.HTTPError as e:
            if e.code not in (429, 500, 502, 503, 504) or wait is None:
                raise
            time.sleep(wait)
    try:
        return json.loads(r["choices"][0]["message"]["content"])
    except (KeyError, TypeError, json.JSONDecodeError):
        return None


def ollama_json(model: str, prompt: str, schema: dict, num_ctx: int = 8192) -> dict | None:
    """One Ollama call, thinking off, temperature 0, the reply constrained to `schema`."""
    r = post(f"{OLLAMA}/api/chat", {}, {
        "model": model, "stream": False, "think": False,
        "messages": [{"role": "user", "content": prompt}],
        "format": schema, "options": {"temperature": 0, "num_ctx": num_ctx}})
    try:
        return json.loads(r["message"]["content"])
    except (KeyError, TypeError, json.JSONDecodeError):
        return None


def laya_agent():
    """Stock Laya: the `typed-decisions` checkpoint as published."""
    warnings.filterwarnings("ignore")
    import laya
    return laya.load(*laya.DEFAULT_MODELS["typed-decisions"][:1], subfolder="typed-decisions")


def jevk5_model():
    """JevK5 read through the local llama-server, after checking it serves the expected file.
    Returns the client and the settings to record."""
    import jevk5
    try:
        with urllib.request.urlopen(JEVK5_URL + "/props", timeout=30) as r:
            props = json.loads(r.read())
    except OSError as e:
        sys.exit(f"jevk5: no llama-server at {JEVK5_URL} ({e}); start one with `make serve-jevk5`")
    if not props.get("model_path", "").endswith(JEVK5_FILE):
        sys.exit(f"jevk5: {JEVK5_URL} serves {props.get('model_path')}, not {JEVK5_FILE} (see `make serve-jevk5`)")
    settings = {"checkpoint": f"alibiserikbay/JevK5-GGUF {JEVK5_FILE}", "sha256": JEVK5_SHA256,
                "client": f"jevk5 {jevk5.__version__}", "server": f"llama.cpp {props.get('build_info')}",
                "temperature": JEVK5_TEMPERATURE}
    return jevk5.JevK5GGUF(JEVK5_URL, temperature=JEVK5_TEMPERATURE), settings
