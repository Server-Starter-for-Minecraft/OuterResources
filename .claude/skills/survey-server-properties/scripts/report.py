"""Compare data/surveyed.json with serverProperties.json using the app's version logic.

usage: python -I report.py [--work DIR] [--since VERSION]

--since limits the report to versions newer than VERSION (e.g. the newest version of the previous survey).

Sections:
  HIDDEN BUT EXISTS   the app hides a property that the server has            -> must fix (widen the range)
  DEFAULT MISMATCH    the selected definition's default differs from the file the server wrote -> fix or explain
  SHOWN BUT ABSENT    the app shows a property the server does not have       -> fine if it is a short gap
  NOT IN JSON         keys the servers have that serverProperties.json lacks   -> add if worth showing
  TRANSITIONS         where presence/default changes between surveyed versions; "unsurveyed N" means
                      N manifest versions in between were not surveyed -> survey the middle to bisect
"""
import argparse, math, os, sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--work", default=os.path.join(os.getcwd(), ".survey-work"))
ap.add_argument("--since")
args = ap.parse_args()

m = common.manifest(args.work)
order = common.order(m)  # newest first
rank = {v: i for i, v in enumerate(order)}
P = common.load_props()["properties"]
VS = common.load_data()["versions"]

# versions whose data is not representative (April Fools forks etc.): version -> reason
IGNORE = {
    "22w13oneblockatatime": "April Fools snapshot forked from 1.18.2",
}
# values that are not defaults
RANDOM = {"management-server-secret"}

for k, e in P.items():
    for d in e["definitions"]:
        for x in d.get("minecraftVersion", {}).values():
            if x not in rank:
                print(f"WARNING {k}: version '{x}' is not in the manifest (the app treats it as unknown)")


# ---- app logic (ServerStarter2 src/components/World/Property/propertyDefinitions.ts) ----
def upper(r):  # rank of `to` (smaller rank = newer); no `to` = unbounded
    return -math.inf if not r or "to" not in r else rank.get(r["to"], -math.inf)


def lower(r):
    return math.inf if not r or "from" not in r else rank.get(r["from"], math.inf)


def unavailable(e, v):
    r, ds = rank[v], e["definitions"]
    return all(r > lower(d.get("minecraftVersion")) for d in ds) or all(r < upper(d.get("minecraftVersion")) for d in ds)


def select(e, v):
    r, ds = rank[v], e["definitions"]
    for d in ds:
        mv = d.get("minecraftVersion")
        if upper(mv) <= r <= lower(mv):
            return d
    ended = sorted([d for d in ds if r < upper(d.get("minecraftVersion"))], key=lambda d: upper(d.get("minecraftVersion")))
    if ended:
        return ended[0]
    return sorted(ds, key=lambda d: -lower(d.get("minecraftVersion")))[0]


def fmt(x):
    return str(x).lower() if isinstance(x, bool) else str(x)


# ---- data ----
sup = set(common.supported(m))
limit = rank[args.since] if args.since else math.inf
vers = [v for v in order if v in VS and v in sup and v not in IGNORE and VS[v]["keys"] is not None]
in_scope = [v for v in vers if rank[v] < limit]


# 1.17-1.18.1 servers do not write these keys although they read them; presence comes from the jar scan
COMPLETE_FROM = rank["18w48a"]
# old names the jar keeps reading only to migrate old files after the server stopped writing them;
# presence is decided by the launched file alone
MIGRATION_ONLY = {"announce-player-achievements", "resource-pack-hash"}
NOT_WRITTEN = {"generate-structures", "generator-settings", "level-seed", "level-type"}


def present(v, k):
    """From 18w48a (1.14) a launched server writes every property, so its file is authoritative
    (the jar scan also matches unrelated strings, e.g. the 'pvp' game rule in 26.4).
    Older servers write a key only when it is read (rcon.* only with RCON enabled, ...), so the jar scan counts too."""
    rec = VS[v]
    if k in MIGRATION_ONLY:
        return k in (rec["launch"] or {})
    if rec["launch"] and rank[v] <= COMPLETE_FROM:
        return k in rec["launch"] or (k in NOT_WRITTEN and k in (rec["keys"] or []))
    return k in (rec["keys"] or []) or k in (rec["launch"] or {})


hidden, absent, mism = defaultdict(list), defaultdict(list), defaultdict(list)
for v in in_scope:
    L = VS[v]["launch"]
    for k, e in P.items():
        ex, shown = present(v, k), not unavailable(e, v)
        if ex and not shown:
            hidden[k].append(v)
        elif shown and not ex:
            absent[k].append(v)
        if L and k in L and k not in RANDOM:
            want = fmt(select(e, v)["default"])
            if want != L[k]:
                mism[(k, want, L[k])].append(v)


def span(vs):
    vs = sorted(vs, key=lambda v: -rank[v])
    return f"{vs[0]} .. {vs[-1]} ({len(vs)} surveyed)" if len(vs) > 1 else vs[0]


print(f"surveyed versions in scope: {len(in_scope)}  ({in_scope[-1] if in_scope else '-'} .. {in_scope[0] if in_scope else '-'})")
print("\n== HIDDEN BUT EXISTS (must fix) ==")
for k, vs in sorted(hidden.items()):
    print(f"  {k}: {span(vs)}")
print("\n== DEFAULT MISMATCH ==")
for (k, want, got), vs in sorted(mism.items()):
    print(f"  {k}: json={want!r} server={got!r}  {span(vs)}")
print("\n== SHOWN BUT ABSENT (acceptable if short) ==")
for k, vs in sorted(absent.items()):
    print(f"  {k}: {span(vs)}")

print("\n== NOT IN JSON ==")
extra = defaultdict(list)
for v in in_scope:
    for k in set(VS[v]["launch"] or {}) | set(VS[v]["keys"] or []):
        if k not in P and present(v, k):
            extra[k].append(v)
for k, vs in sorted(extra.items()):
    written = [v for v in vs if k in (VS[v]["launch"] or {})]
    tag = f"written by server: {span(written)}" if written else "jar scan only (check it is a real property)"
    print(f"  {k}: {span(vs)}  [{tag}]")

print("\n== TRANSITIONS (older -> newer) ==")
chron = list(reversed(vers))
keys = sorted(set(P) | set(extra))
for k in keys:
    out = []
    for a, b in zip(chron, chron[1:]):
        if rank[b] >= limit:
            continue
        pa, pb = present(a, k), present(b, k)
        La, Lb = VS[a]["launch"] or {}, VS[b]["launch"] or {}
        gap = rank[a] - rank[b] - 1
        note = f" (unsurveyed {gap}, try {order[(rank[a] + rank[b]) // 2]})" if gap else ""
        if pa != pb:
            # --initSettings in 1.17-1.18.1 omits world-generation keys; presence then comes from the jar scan
            out.append(f"{'+' if pb else '-'} {a} -> {b}{note}")
        elif pa and k in La and k in Lb and La[k] != Lb[k] and k not in RANDOM:
            out.append(f"default {La[k]!r} -> {Lb[k]!r}: {a} -> {b}{note}")
    if out:
        print(f"  {k}")
        for x in out:
            print("    " + x)
