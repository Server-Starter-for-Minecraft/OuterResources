"""Survey vanilla server jars: which server.properties keys exist and what defaults a real server writes.

usage:
  python -I survey.py [options] --new            # every supported version not yet in data/surveyed.json
  python -I survey.py [options] <version id>...  # specific versions (re-surveys them)

options:
  --work DIR      scratch directory for downloads (default: ./.survey-work under the cwd)
  --eula          the user has agreed to the Minecraft EULA: write eula=true and fully start servers
                  that cannot use --initSettings (before 1.14), then send "stop"
  --full-start    with --eula, always fully start the server instead of --initSettings
                  (1.17-1.18.1 --initSettings omits world-generation keys such as generator-settings)
  --no-launch     only scan the jar (no server is started)
  --runtime DIR   Mojang java runtimes (default: ServerStarter2's cache)
  --limit N       survey at most N versions this run

Each version records:
  keys    property keys found in the jar's class constants
  launch  {key: value} of the server.properties the server wrote (null if not launched / failed)
  mode    "initSettings" | "eula" | null
"""
import argparse, io, json, os, re, shutil, struct, subprocess, sys, threading, time, zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("versions", nargs="*")
ap.add_argument("--new", action="store_true")
ap.add_argument("--work", default=os.path.join(os.getcwd(), ".survey-work"))
ap.add_argument("--eula", action="store_true")
ap.add_argument("--full-start", action="store_true")
ap.add_argument("--no-launch", action="store_true")
ap.add_argument("--runtime", default=os.path.expanduser("~/AppData/Roaming/ServerStarter2/serverstarter/cache/bin/runtime"))
ap.add_argument("--limit", type=int)
args = ap.parse_args()
if args.full_start and not args.eula:
    sys.exit("--full-start needs --eula (the user must agree to the Minecraft EULA)")

m = common.manifest(args.work)
by_id = {v["id"]: v for v in m["versions"]}
rank = {v: i for i, v in enumerate(common.order(m))}
data = common.load_data()
VS = data["versions"]

if args.new:
    # versions released after the newest surveyed one (older unsurveyed snapshots were covered by bisection)
    sup = common.supported(m)
    newest = min((rank[v] for v in VS if v in rank), default=len(sup))
    targets = list(reversed(sup[:newest]))  # oldest first
else:
    unknown = [v for v in args.versions if v not in by_id]
    if unknown:
        sys.exit(f"not in manifest: {unknown}")
    targets = args.versions
if args.limit:
    targets = targets[: args.limit]
print(f"{len(targets)} version(s) to survey", flush=True)

# ---- jar scan -------------------------------------------------------------
# Keys read by the class that reads server-port/view-distance, plus keys found anywhere
# that are already known property names (properties moved to other classes in some versions).
PROP_KEY = re.compile(r"^[a-z][a-z0-9]*(?:[-.][a-z0-9]+)+$|^(?:motd|pvp|hardcore|difficulty|gamemode)$")
NOISE = re.compile(r"\.(txt|log|json|properties)$|^(java|os)\.")  # file names / system properties
known = set(common.load_props()["properties"])
for rec in VS.values():
    known.update(rec.get("keys") or [])
    known.update((rec.get("launch") or {}).keys())


def utf8_consts(b):
    if b[:4] != b"\xca\xfe\xba\xbe":
        return []
    n = struct.unpack(">H", b[8:10])[0]
    i, k, out = 10, 1, []
    while k < n:
        t = b[i]
        if t == 1:
            ln = struct.unpack(">H", b[i + 1 : i + 3])[0]
            out.append(b[i + 3 : i + 3 + ln].decode("utf-8", "replace"))
            i += 3 + ln
        elif t in (3, 4, 9, 10, 11, 12, 17, 18):
            i += 5
        elif t in (5, 6):
            i += 9
            k += 1
        elif t in (7, 8, 16, 19, 20):
            i += 3
        elif t == 15:
            i += 4
        else:
            raise ValueError(t)
        k += 1
    return out


def scan_zip(z):
    for name in z.namelist():  # 1.18+ bundles the real server jar
        if name.startswith("META-INF/versions/") and name.endswith(".jar"):
            return scan_zip(zipfile.ZipFile(io.BytesIO(z.read(name))))
    keys = set()
    for name in z.namelist():
        if not name.endswith(".class"):
            continue
        b = z.read(name)
        prop = b"server-port" in b or b"view-distance" in b
        for s in utf8_consts(b):
            if ((prop and PROP_KEY.match(s)) or s in known) and not NOISE.search(s):
                keys.add(s)
    return sorted(keys)


# ---- launch ---------------------------------------------------------------
def find_java(base):
    for root, _, files in os.walk(base):
        if os.path.basename(root) == "bin" and ("java.exe" in files or "java" in files):
            return os.path.join(root, "java.exe" if "java.exe" in files else "java")
    return None


def runtime_major(base):
    for root, _, files in os.walk(base):
        if "release" in files:
            m_ = re.search(r'JAVA_VERSION="(?:1\.)?(\d+)', open(os.path.join(root, "release"), errors="replace").read())
            if m_:
                return int(m_.group(1))
    return None


def java_for(meta):
    jv = meta.get("javaVersion", {})
    comp, need = jv.get("component", "jre-legacy"), jv.get("majorVersion", 8)
    java = find_java(os.path.join(args.runtime, comp))
    if java:
        return java
    # fall back to the closest installed runtime that is at least as new (e.g. Java 17 for Java 16)
    cands = []
    for name in os.listdir(args.runtime) if os.path.isdir(args.runtime) else []:
        base = os.path.join(args.runtime, name)
        major, j = runtime_major(base), find_java(base)
        if major and j and major >= need and not name.endswith("-snapshot"):
            cands.append((major, j))
    if cands:
        return min(cands)[1]
    raise RuntimeError(f"Java runtime '{comp}' (Java {need}+) not found under {args.runtime} (start this version once in ServerStarter2, or pass --runtime)")


RANDOM_VALUES = {"management-server-secret"}  # generated per server; not a default


def read_props(d):
    p = os.path.join(d, "server.properties")
    res = {}
    if os.path.exists(p):
        for line in open(p, encoding="utf-8", errors="replace"):
            line = line.rstrip("\r\n")
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                res[k] = "<random>" if k in RANDOM_VALUES else v.replace("\\", "")
    return res


def run_init_settings(java, d):
    try:
        subprocess.run([java, "-jar", "server.jar", "--initSettings", "--nogui", "nogui"], cwd=d, capture_output=True,
                       timeout=240, stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        pass
    return read_props(d)


def run_eula(java, d):
    """Fully start the server (EULA accepted by the user), wait until it is ready, then stop it."""
    open(os.path.join(d, "eula.txt"), "w").write("eula=true\n")
    p = subprocess.Popen([java, "-Xmx2G", "-jar", "server.jar", "nogui"], cwd=d, stdin=subprocess.PIPE,
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    done = threading.Event()

    def reader():
        for line in iter(p.stdout.readline, b""):
            if b"Done (" in line or b"For help, type" in line:
                done.set()
        done.set()

    threading.Thread(target=reader, daemon=True).start()
    done.wait(600)
    try:
        p.stdin.write(b"stop\n")
        p.stdin.flush()
    except OSError:
        pass
    try:
        p.wait(120)
    except subprocess.TimeoutExpired:
        p.kill()
        p.wait()
    return read_props(d)


INIT_SETTINGS_FROM = rank.get("18w43a")  # --initSettings exists from the 1.14 snapshots

for vid in targets:
    t0 = time.time()
    meta = json.loads(common.fetch(by_id[vid]["url"]))
    srv = meta.get("downloads", {}).get("server")
    if not srv:
        VS[vid] = {"keys": None, "launch": None, "mode": None}
        common.save_data(data, m)
        print(vid, "no server jar", flush=True)
        continue
    d = os.path.join(args.work, "srv", vid)
    shutil.rmtree(d, ignore_errors=True)
    os.makedirs(d)
    jar = os.path.join(d, "server.jar")
    open(jar, "wb").write(common.fetch(srv["url"]))
    keys = scan_zip(zipfile.ZipFile(jar))
    launch, mode = None, None
    if not args.no_launch:
        java = java_for(meta)
        if INIT_SETTINGS_FROM is not None and rank[vid] <= INIT_SETTINGS_FROM and not args.full_start:
            launch, mode = run_init_settings(java, d), "initSettings"
        if not launch and args.eula:
            for f in os.listdir(d):
                if f != "server.jar":
                    shutil.rmtree(os.path.join(d, f), ignore_errors=True) if os.path.isdir(os.path.join(d, f)) else os.remove(os.path.join(d, f))
            launch, mode = run_eula(java, d), "eula"
        if not launch:
            launch, mode = None, None
    VS[vid] = {"keys": keys, "launch": launch, "mode": mode}
    common.save_data(data, m)
    shutil.rmtree(d, ignore_errors=True)
    print(f"{vid}: {len(keys)} keys, launch={mode or '-'} ({len(launch or {})} keys), {time.time() - t0:.0f}s", flush=True)
