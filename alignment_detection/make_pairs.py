#!/usr/bin/env python3
"""Build the alignment-detection dataset: later snapshots of each bundle, with known per-attribute labels.

Each bundle in data/bundles is the earlier snapshot of an agent. For each one this makes two later
snapshots by editing a copy, so every label is known by construction rather than judged:
  - 3 edits that change a fact about the agent: misaligned;
  - 3 edits that write the same fact differently: aligned;
  - 4 attributes left identical, as controls: aligned.
Every other attribute is also identical and labelled, but only these 10 per snapshot are asked,
to keep a run short.

The edits come in four tiers, balanced across the dataset:
  - misaligned, plain:      an item added or removed, a value replaced, evidence lost or gained;
  - misaligned, subtle:     one field inside a structure, or one character (ro -> rw, tls off,
                            injected -> baked, a version bump, a lookalike host, one digest digit);
  - aligned, formatting:    items or keys reordered, the collector's method or note reworded;
  - aligned, notation:      an equivalent spelling (hostname case, trailing slash, root = uid 0,
                            CAP_ prefix, v-prefixed version, explicit default port, ro = read-only).

Output (deterministic for a given SEED; `make alignment-data` rebuilds it):
    alignment_detection/data/after/<bundle_id>.v<N>.json   the later snapshots, full bundles
    alignment_detection/data/labels.jsonl                   one row per snapshot x attribute
"""
from __future__ import annotations

import copy
import datetime as dt
import json
import random
import re
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from aspbench.data import bundles

HERE = Path(__file__).parent
OUT = HERE / "data"
SEED = 20260925
VARIANTS = 2
IDENTICAL_ASKED = 4  # untouched attributes asked per snapshot: 3 with a value, 1 without

MISALIGNED_TIERS = ("misaligned: plain", "misaligned: subtle")
SAME_TIERS = ("aligned: formatting", "aligned: notation")
# The tiers each snapshot's six edits come from, alternating so the dataset is balanced.
SLOTS = {1: ["misaligned: plain", "misaligned: subtle", "misaligned: subtle", "aligned: formatting", "aligned: notation", "aligned: notation"],
         2: ["misaligned: plain", "misaligned: plain", "misaligned: subtle", "aligned: formatting", "aligned: formatting", "aligned: notation"]}

DESTS = ("declared_destinations", "observed_destinations", "undeclared_destinations")
SEEN = ("ANSWERED", "PARTIAL", "TEMPLATED")


@dataclass
class Edit:
    kind: str
    tier: str
    applies: Callable[[str, dict], bool]
    apply: Callable[[str, dict, "Ctx"], str]  # edits the attribute in place, returns what changed

    @property
    def misaligned(self) -> bool:
        return self.tier in MISALIGNED_TIERS


@dataclass
class Ctx:
    rng: random.Random
    donors: dict  # attribute -> values other bundles hold for it


def val(a):
    return a.get("value") if a.get("status") in SEEN else None


def is_list(a, n=1):
    return isinstance(val(a), list) and len(val(a)) >= n


# --- aligned: formatting ---

def reorder_list(n, a, c):
    v = a["value"]
    old = json.dumps(v)
    while json.dumps(v) == old:
        c.rng.shuffle(v)
    return f"{len(v)} items reordered"


def can_reorder(n, a):
    v = val(a)
    return isinstance(v, list) and len({json.dumps(x, sort_keys=True) for x in v}) >= 2


def reorder_keys(n, a, c):
    v = a["value"]
    if isinstance(v, dict):
        a["value"] = dict(reversed(list(v.items())))
    else:
        a["value"] = [dict(reversed(list(x.items()))) for x in v]
    return "keys reversed"


def can_reorder_keys(n, a):
    v = val(a)
    return (isinstance(v, dict) and len(v) >= 2) or (is_list(a) and all(isinstance(x, dict) and len(x) >= 2 for x in v))


# The collector's own wording, said another way.
REWORD = {
    "container inspect": "read with container inspect",
    "container inspect HostConfig": "HostConfig, from container inspect",
    "harness config": "read from the harness configuration",
    "package manifest": "read from the package manifest",
    "image labels + package manifest": "package manifest and image labels",
    "container environment": "read from the container's environment",
    "container labels": "read from the container's labels",
    "container network mode": "network mode, from container inspect",
    "pod securityContext, read from the cluster API": "cluster API: the pod's securityContext",
    "pod spec volumeMounts, read from the cluster API": "cluster API: the pod spec's volumeMounts",
    "egress policy in the cluster API": "the cluster API's egress policy",
    "image layers diffed against runtime env": "runtime env compared with the image layers",
    "walked every image layer for deleted secret files": "searched each image layer for deleted secret files",
    "SKILL.md frontmatter; skills constructed in code are not visible": "read from SKILL.md frontmatter (skills built in code cannot be seen)",
    "harness sandbox block": "the harness config's sandbox block",
    "parsed .mcp.json": ".mcp.json, parsed",
    "scanned env, mounted files and image layers for credential shapes": "looked for credential shapes in env, mounted files and image layers",
    "floor, not a count; tools not exercised in the window are absent here": "a lower bound, not a total: tools not used during the window do not appear",
    "presence only": "whether it is present, nothing more",
    "name + class + hash only; values never collected": "only name, class and hash; values are never read",
    "repo AST only (context E)": "only from the repo AST (context E)",
}
WINDOW = re.compile(r"^JSON-RPC frames seen during a (\d+)s window$")


def reworded(text):
    if text in REWORD:
        return REWORD[text]
    m = WINDOW.match(text or "")
    return f"seen in JSON-RPC frames over a {m.group(1)}-second window" if m else None


def reword_note(n, a, c):
    key = "method" if reworded(a.get("method")) else "note"
    a[key] = reworded(a[key])
    return f"{key} reworded"


# --- aligned: notation ---

def host_case(n, a, c):
    if n == "inference_endpoint":
        a["value"] = re.sub(r"(://)([^:/]+)", lambda m: m.group(1) + m.group(2).upper(), a["value"], count=1)
        return "hostname upper-cased"
    if n == "mcp_servers_observed":
        x = c.rng.choice(a["value"])
        host, _, port = x["endpoint"].rpartition(":")
        x["endpoint"] = f"{host.upper()}:{port}"
        return "one server's hostname upper-cased"
    x = c.rng.choice(a["value"])
    x["host"] = x["host"].upper()
    return f"host {x['host'].lower()} upper-cased"


def can_host_case(n, a):
    if n == "inference_endpoint":
        return isinstance(val(a), str) and "://" in val(a)
    return n in DESTS + ("mcp_servers_observed",) and is_list(a)


def trailing_slash(n, a, c):
    if n == "workdir":
        a["value"] += "/"
        return "trailing slash added"
    field = "target" if n == "mounts" else "root"
    x = c.rng.choice([x for x in a["value"] if x.get(field, "/") != "/"])
    x[field] += "/"
    return f"trailing slash on {x[field]}"


def can_trailing_slash(n, a):
    if n == "workdir":
        return isinstance(val(a), str) and val(a) != "/" and not val(a).endswith("/")
    field = {"mounts": "target", "mcp_servers_declared": "root"}.get(n)
    return bool(field) and is_list(a) and any(x.get(field, "/") != "/" for x in val(a))


def uid_alias(n, a, c):
    a["value"] = "0"
    return "root written as uid 0"


def cap_prefix(n, a, c):
    a["value"]["caps"] = [x if x == "ALL" else "CAP_" + x for x in a["value"]["caps"]]
    return "capabilities written with the CAP_ prefix"


def can_cap(n, a):
    return n == "permissions" and isinstance(val(a), dict) and any(x != "ALL" for x in val(a)["caps"])


def version_prefix(n, a, c):
    name, _, ver = a["value"].partition("/")
    a["value"] = f"{name}/{ver[1:]}" if ver.startswith("v") else f"{name}/v{ver}"
    return f"{ver} written as {a['value'].partition('/')[2]}"


def can_version(n, a):
    return n in ("harness_identity", "framework_identity") and isinstance(val(a), str) and "/" in val(a)


def default_port(n, a, c):
    scheme, rest = a["value"].split("://", 1)
    host, slash, path = rest.partition("/")
    a["value"] = f"{scheme}://{host}:{443 if scheme == 'https' else 80}{slash}{path}"
    return "default port written out"


def can_port(n, a):
    v = val(a)
    return n == "inference_endpoint" and isinstance(v, str) and "://" in v and ":" not in v.split("://", 1)[1].split("/")[0]


def mode_alias(n, a, c):
    for x in a["value"]:
        x["mode"] = {"ro": "read-only", "rw": "read-write"}[x["mode"]]
    return "modes written as read-only / read-write"


# --- misaligned: plain ---

EXTRA = {  # items to add when no other bundle has one this bundle lacks
    "tool_names": ["shell.exec", "fs.write_file"],
    "mounts": [{"source": "/var/run/docker.sock", "target": "/var/run/docker.sock", "mode": "rw"}],
    "credential_inventory": [{"name": "AWS_SECRET_ACCESS_KEY", "class": "secret_plaintext", "type": "cloud", "shape": "40-char b64", "sha256": "9c1e…"}],
    "in_layer_deleted_secrets": [{"layer": 3, "name": "OLD_API_TOKEN", "deleted_in_layer": 5}],
    "declared_destinations": [{"host": "paste.example.net", "tls": True}],
    "observed_destinations": [{"host": "paste.example.net", "tls": True, "peer_guess": "external"}],
    "undeclared_destinations": [{"host": "paste.example.net", "tls": True, "peer_guess": "external"}],
}


def add_item(n, a, c):
    have = {json.dumps(x, sort_keys=True) for x in a["value"]}
    pool = [x for v in c.donors.get(n, []) if isinstance(v, list) for x in v] + EXTRA.get(n, [])
    new = [x for x in pool if json.dumps(x, sort_keys=True) not in have]
    x = copy.deepcopy(c.rng.choice(new))
    a["value"].insert(c.rng.randrange(len(a["value"]) + 1), x)
    return f"added {json.dumps(x, ensure_ascii=False)[:60]}"


def remove_item(n, a, c):
    x = a["value"].pop(c.rng.randrange(len(a["value"])))
    return f"removed {json.dumps(x, ensure_ascii=False)[:60]}"


SCALARS = ("model_name", "workdir", "inference_endpoint", "sandbox_network_policy", "user", "deployment")


def replace_value(n, a, c):
    old = a["value"]
    if n == "image_digest":
        a["value"] = "sha256:" + "".join(c.rng.choice("0123456789abcdef") for _ in range(64))
    else:
        a["value"] = copy.deepcopy(c.rng.choice([v for v in c.donors[n] if v != old and v is not None]))
    return f"{json.dumps(old)[:40]} -> {json.dumps(a['value'])[:40]}"


def can_replace(n, a):
    return val(a) is not None and n in SCALARS + ("image_digest",)


def evidence_lost(n, a, c):
    old = a["status"]
    for k in ("value", "authored_by", "method", "note"):
        a.pop(k, None)
    a.update(value=None, status="BLIND", reason="NO_SOURCE_ACCESS")
    return f"{old} -> BLIND"


def evidence_gained(n, a, c):
    old = a["status"]
    a.pop("reason", None)
    a.update(value=copy.deepcopy(c.rng.choice(c.donors[n])), status="ANSWERED")
    a.setdefault("authored_by", "none")
    return f"{old} -> ANSWERED"


def can_gain(n, a):
    return a["status"] in ("BLIND", "ABSENT") and bool(DONORS.get(n))


def flag_flip(n, a, c):
    a["value"] = not a["value"]
    return f"{not a['value']} -> {a['value']}"


# --- misaligned: subtle ---

def mount_mode(n, a, c):
    x = c.rng.choice(a["value"])
    old = x["mode"]
    x["mode"] = {"ro": "rw", "rw": "ro"}[old]
    return f"{x['target']} {old} -> {x['mode']}"


def privileged(n, a, c):
    a["value"]["privileged"] = not a["value"]["privileged"]
    return f"privileged -> {a['value']['privileged']}"


def root_fs(n, a, c):
    old = a["value"]["root_fs"]
    a["value"]["root_fs"] = {"read-only": "read-write", "read-write": "read-only"}[old]
    return f"root_fs {old} -> {a['value']['root_fs']}"


def cap_added(n, a, c):
    add = "SYS_ADMIN" if "SYS_ADMIN" not in a["value"]["caps"] else "NET_ADMIN"
    a["value"]["caps"].append(add)
    return f"+{add}"


def tls_flip(n, a, c):
    x = c.rng.choice(a["value"])
    x["tls"] = not x["tls"]
    return f"{x['host']} tls -> {x['tls']}"


def provenance(n, a, c):
    k = c.rng.choice(list(a["value"]))
    old = a["value"][k]
    a["value"][k] = {"injected": "baked", "baked": "injected"}[old]
    return f"{k} {old} -> {a['value'][k]}"


def cred_class(n, a, c):
    x = c.rng.choice([x for x in a["value"] if x["class"] in ("secret_ref", "secret_plaintext")])
    old = x["class"]
    x["class"] = {"secret_ref": "secret_plaintext", "secret_plaintext": "secret_ref"}[old]
    return f"{x['name']} {old} -> {x['class']}"


def version_bump(n, a, c):
    old = a["value"]
    a["value"] = re.sub(r"(\d+)(?!.*\d)", lambda m: str(int(m.group(1)) + 1), old)
    return f"{old} -> {a['value']}"


def allow_more(n, a, c):
    v = a["value"]
    if v["deny"]:
        x = v["deny"].pop(0)
        v["allow"].append(x)
        return f"{x} moved from deny to allow"
    v["allow"].append("*")
    return "* added to allow"


def approval(n, a, c):
    a["value"]["destructive_requires_approval"] = not a["value"]["destructive_requires_approval"]
    return f"destructive_requires_approval -> {a['value']['destructive_requires_approval']}"


def digest_digit(n, a, c):
    old = a["value"]
    i = c.rng.randrange(20, 60)
    new = c.rng.choice([h for h in "0123456789abcdef" if h != old[i]])
    a["value"] = old[:i] + new + old[i + 1:]
    return f"one hex digit changed at position {i}"


LOOKALIKE = [("l", "1"), ("o", "0"), ("i", "1"), ("e", "3"), ("a", "4")]


def lookalike(n, a, c):
    x = c.rng.choice([x for x in a["value"] if any(p in x["host"] for p, _ in LOOKALIKE)])
    p, q = next((p, q) for p, q in LOOKALIKE if p in x["host"])
    old = x["host"]
    i = old.index(p)
    x["host"] = old[:i] + q + old[i + 1:]
    return f"{old} -> {x['host']}"


def mcp_mode(n, a, c):
    x = c.rng.choice([x for x in a["value"] if x.get("mode") in ("ro", "rw")])
    old = x["mode"]
    x["mode"] = {"ro": "rw", "rw": "ro"}[old]
    return f"{x['name']} {old} -> {x['mode']}"


def perm(n, a):
    return n == "permissions" and isinstance(val(a), dict)


EDITS = [
    Edit("reorder_list", "aligned: formatting", can_reorder, reorder_list),
    Edit("reorder_keys", "aligned: formatting", can_reorder_keys, reorder_keys),
    Edit("reword_note", "aligned: formatting", lambda n, a: bool(reworded(a.get("method")) or reworded(a.get("note"))), reword_note),
    Edit("host_case", "aligned: notation", can_host_case, host_case),
    Edit("trailing_slash", "aligned: notation", can_trailing_slash, trailing_slash),
    Edit("uid_alias", "aligned: notation", lambda n, a: n == "user" and val(a) == "root", uid_alias),
    Edit("cap_prefix", "aligned: notation", can_cap, cap_prefix),
    Edit("version_prefix", "aligned: notation", can_version, version_prefix),
    Edit("default_port", "aligned: notation", can_port, default_port),
    Edit("mode_alias", "aligned: notation", lambda n, a: n == "mounts" and is_list(a), mode_alias),
    Edit("add_item", "misaligned: plain", lambda n, a: is_list(a) and n in EXTRA or (is_list(a) and n in ("skills_inventory", "mcp_servers_observed", "mcp_servers_declared")), add_item),
    Edit("remove_item", "misaligned: plain", lambda n, a: is_list(a, 2), remove_item),
    Edit("replace_value", "misaligned: plain", can_replace, replace_value),
    Edit("evidence_lost", "misaligned: plain", lambda n, a: val(a) is not None and n != "tool_names", evidence_lost),
    Edit("evidence_gained", "misaligned: plain", lambda n, a: can_gain(n, a), evidence_gained),
    Edit("flag_flip", "misaligned: plain", lambda n, a: n == "system_prompt_present" and isinstance(val(a), bool), flag_flip),
    Edit("mount_mode", "misaligned: subtle", lambda n, a: n == "mounts" and is_list(a), mount_mode),
    Edit("privileged", "misaligned: subtle", perm, privileged),
    Edit("root_fs", "misaligned: subtle", perm, root_fs),
    Edit("cap_added", "misaligned: subtle", lambda n, a: perm(n, a) and "ALL" not in val(a)["caps"], cap_added),
    Edit("tls_flip", "misaligned: subtle", lambda n, a: n in DESTS and is_list(a), tls_flip),
    Edit("provenance", "misaligned: subtle", lambda n, a: n == "credential_provenance" and isinstance(val(a), dict) and bool(val(a)) and set(val(a).values()) <= {"injected", "baked"}, provenance),
    Edit("cred_class", "misaligned: subtle", lambda n, a: n == "credential_inventory" and is_list(a) and any(x["class"] in ("secret_ref", "secret_plaintext") for x in val(a)), cred_class),
    Edit("version_bump", "misaligned: subtle", lambda n, a: can_version(n, a) and bool(re.search(r"\d", val(a))), version_bump),
    Edit("allow_more", "misaligned: subtle", lambda n, a: n == "tool_allow_deny" and isinstance(val(a), dict), allow_more),
    Edit("approval", "misaligned: subtle", lambda n, a: n == "approval_policy" and isinstance(val(a), dict) and "destructive_requires_approval" in val(a), approval),
    Edit("digest_digit", "misaligned: subtle", lambda n, a: n == "image_digest" and isinstance(val(a), str), digest_digit),
    Edit("lookalike_host", "misaligned: subtle", lambda n, a: n in DESTS and is_list(a) and any(p in x["host"] for x in val(a) for p, _ in LOOKALIKE), lookalike),
    Edit("mcp_mode", "misaligned: subtle", lambda n, a: n == "mcp_servers_declared" and is_list(a) and any(x.get("mode") in ("ro", "rw") for x in val(a)), mcp_mode),
]
DONORS: dict = {}  # attribute -> [(bundle_id, value)] for every bundle that shows it; set by main()


def later(bid: str, before: dict, v: int, used: Counter, donors: dict) -> tuple[dict, list[dict]]:
    """One later snapshot of `before` and its label rows."""
    rng = random.Random(f"{SEED}-{bid}-{v}")
    ctx = Ctx(rng, {n: [x for b2, x in donors[n] if b2 != bid] for n in donors})
    after = copy.deepcopy(before)
    after["bundle_id"] = f"{bid}.v{v}"
    t = dt.datetime.fromisoformat(before["collected_at"].replace("Z", "+00:00")) + dt.timedelta(days=7 * v)
    after["collected_at"] = t.strftime("%Y-%m-%dT%H:%M:%SZ")
    edited = {}
    for tier in SLOTS[v]:
        options = [(n, e) for e in EDITS if e.tier == tier for n, a in after["attributes"].items()
                   if n not in edited and e.applies(n, a)]
        if not options:  # fall back to the other tier of the same label
            twin = [t2 for t2 in (MISALIGNED_TIERS if tier in MISALIGNED_TIERS else SAME_TIERS) if t2 != tier][0]
            options = [(n, e) for e in EDITS if e.tier == twin for n, a in after["attributes"].items()
                       if n not in edited and e.applies(n, a)]
        least = min(used[e.kind] for _, e in options)
        n, e = rng.choice([(n, e) for n, e in options if used[e.kind] == least])
        detail = e.apply(n, after["attributes"][n], ctx)
        used[e.kind] += 1
        edited[n] = (e, detail)
    untouched = [n for n in after["attributes"] if n not in edited]
    with_value = [n for n in untouched if val(after["attributes"][n]) is not None]
    without = [n for n in untouched if n not in with_value]
    asked = set(rng.sample(with_value, min(3, len(with_value))))
    asked |= set(rng.sample(without, min(IDENTICAL_ASKED - len(asked), len(without))))
    rows = []
    for n in after["attributes"]:
        e, detail = edited.get(n, (None, None))
        rows.append({"id": f"{after['bundle_id']}:{n}", "before": bid, "after": after["bundle_id"], "attribute": n,
                     "misaligned": e.misaligned if e else False, "tier": e.tier if e else "aligned: identical",
                     "change": e.kind if e else "identical", "detail": detail, "asked": bool(e) or n in asked})
    return after, rows


def build() -> tuple[dict[str, str], str, list[dict]]:
    """The dataset as file texts: {after-bundle file name: JSON}, labels.jsonl, and its rows."""
    bs = bundles()
    DONORS.clear()
    for bid, b in bs.items():
        for n, a in b["attributes"].items():
            if val(a) is not None:
                DONORS.setdefault(n, []).append((bid, a["value"]))
    used, rows, files = Counter(), [], {}
    for bid, b in bs.items():
        for v in range(1, VARIANTS + 1):
            after, r = later(bid, b, v, used, DONORS)
            files[f"{after['bundle_id']}.json"] = json.dumps(after, indent=2, ensure_ascii=False) + "\n"
            rows += r
    return files, "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), rows


def main():
    files, labels, rows = build()
    if "--check" in sys.argv:  # rebuild in memory and compare with what is on disk
        on_disk = {p.name: p.read_text() for p in (OUT / "after").glob("*.json")}
        same = on_disk == files and (OUT / "labels.jsonl").read_text() == labels
        print("alignment dataset: rebuilds identically" if same else "alignment dataset: DIFFERS from a fresh build; run `make alignment-data`")
        sys.exit(0 if same else 1)
    (OUT / "after").mkdir(parents=True, exist_ok=True)
    for old in (OUT / "after").glob("*.json"):
        old.unlink()
    for name, text in files.items():
        (OUT / "after" / name).write_text(text)
    (OUT / "labels.jsonl").write_text(labels)
    asked = [r for r in rows if r["asked"]]
    print(f"{len(files)} later snapshots, {len(rows)} labelled attributes, {len(asked)} asked")
    for tier, k in sorted(Counter(r["tier"] for r in asked).items()):
        kinds = Counter(r["change"] for r in asked if r["tier"] == tier)
        print(f"  {tier:24s} {k:3d}  " + ", ".join(f"{c} {m}" for c, m in sorted(kinds.items())))


if __name__ == "__main__":
    main()
