"""Shared helpers for the server.properties survey scripts."""
import json, os, urllib.request

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO_DIR = os.path.dirname(os.path.dirname(os.path.dirname(SKILL_DIR)))
DATA_PATH = os.path.join(SKILL_DIR, "data", "surveyed.json")
PROPS_PATH = os.path.join(REPO_DIR, "serverstarter2", "v1", "serverProperties.json")
MANIFEST_URL = "https://piston-meta.mojang.com/mc/game/version_manifest_v2.json"
# ServerStarter2 supports every version newer than this one
OLDEST_UNSUPPORTED = "1.2.5"


def fetch(url, timeout=120):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return r.read()


def manifest(work):
    """Fetch the Mojang manifest (cached per work dir for one run)."""
    p = os.path.join(work, "manifest.json")
    if not os.path.exists(p):
        os.makedirs(work, exist_ok=True)
        open(p, "wb").write(fetch(MANIFEST_URL))
    return json.load(open(p, encoding="utf-8"))


def order(m):
    """Version ids newest first (the order the app uses)."""
    return [v["id"] for v in m["versions"]]


def supported(m):
    o = order(m)
    return o[: o.index(OLDEST_UNSUPPORTED)]


def load_data():
    if not os.path.exists(DATA_PATH):
        return {"versions": {}}
    return json.load(open(DATA_PATH, encoding="utf-8"))


def save_data(data, m):
    """One version per line, newest first, so diffs stay small."""
    rank = {v: i for i, v in enumerate(order(m))}
    vs = data["versions"]
    lines = []
    for v in sorted(vs, key=lambda x: rank.get(x, -1)):
        lines.append("    " + json.dumps(v, ensure_ascii=False) + ": " + json.dumps(vs[v], ensure_ascii=False, sort_keys=True))
    body = ",\n".join(lines)
    os.makedirs(os.path.dirname(DATA_PATH), exist_ok=True)
    with open(DATA_PATH, "w", encoding="utf-8", newline="\n") as f:
        f.write('{\n  "versions": {\n' + body + "\n  }\n}\n")


def load_props():
    return json.load(open(PROPS_PATH, encoding="utf-8"))
