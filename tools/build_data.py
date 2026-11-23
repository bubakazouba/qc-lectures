"""Build data.json (+ homework images) for the QC lectures site from the exported Drive docs."""
import json, re, os, base64, hashlib, html, urllib.parse, sys
from bs4 import BeautifulSoup, NavigableString

SP = os.path.dirname(os.path.abspath(__file__))
OUT = sys.argv[1]
os.makedirs(f"{OUT}/img", exist_ok=True)
tree = json.load(open(f"{SP}/../qc_tree.json", encoding="utf-8"))

def unwrap(u):
    u = html.unescape(u)
    if "google.com/url" in u:
        u = urllib.parse.parse_qs(urllib.parse.urlparse(u).query).get("q", [u])[0]
    return u

def fix(s):
    return s.replace("�", "'").replace("​", "")

def find(name, items=tree):
    for f in items:
        if f["name"] == name:
            return f
    raise KeyError(name)

# ---------- inline converter (Google Docs HTML -> clean HTML) ----------
def inline(node):
    out = []
    for c in node.children:
        if isinstance(c, NavigableString):
            out.append(html.escape(fix(str(c)), quote=False))
        elif c.name == "a":
            href = c.get("href", "")
            if href.startswith("#cmnt") or href.startswith("#ftnt"):
                continue
            t = inline(c)
            if not t.strip():
                continue
            out.append(f'<a href="{html.escape(unwrap(href))}" target="_blank" rel="noopener">{t}</a>')
        elif c.name == "img":
            src = c.get("src", "")
            if src.startswith("data:image"):
                kind, b64 = src.split(",", 1)
                ext = "png" if "png" in kind else "jpg"
                raw = base64.b64decode(b64)
                fn = f"img/{hashlib.sha1(raw).hexdigest()[:12]}.{ext}"
                open(f"{OUT}/{fn}", "wb").write(raw)
                m = re.search(r"width:\s*([\d.]+)px", c.parent.get("style", "") + c.get("style", ""))
                w = f' style="max-width:{int(float(m.group(1)))}px"' if m else ""
                out.append(f'<img src="{fn}" alt="" loading="lazy"{w}>')
        elif c.name == "span":
            t = inline(c)
            st = c.get("style", "")
            if "font-weight:700" in st and t.strip():
                t = f"<b>{t}</b>"
            if "font-style:italic" in st and t.strip():
                t = f"<i>{t}</i>"
            if "vertical-align:super" in st:
                t = f"<sup>{t}</sup>"
            if "vertical-align:sub" in st:
                t = f"<sub>{t}</sub>"
            out.append(t)
        elif c.name == "sup" and c.find("a", href=re.compile("^#cmnt")):
            continue
        else:
            out.append(inline(c))
    return "".join(out)

def blocks_to_html(nodes):
    """nodes: list of top-level body elements -> clean nested HTML."""
    out, stack = [], []  # stack of (tag, level)
    def close_to(level):
        while stack and stack[-1][1] >= level:
            out.append("</li></%s>" % stack.pop()[0])
    for n in nodes:
        if n.name in ("ul", "ol"):
            cls = " ".join(n.get("class", []))
            m = re.search(r"-(\d+)\b", cls)
            lvl = int(m.group(1)) if m else 0
            tag = n.name
            for li in n.find_all("li", recursive=False):
                body = inline(li).strip()
                if stack and stack[-1][1] > lvl:
                    close_to(lvl + 1)
                if stack and stack[-1][1] == lvl:
                    out.append("</li><li>" + body)
                else:
                    while stack and stack[-1][1] < lvl - 1:  # skipped level
                        out.append(f"<{tag}><li>")
                        stack.append((tag, stack[-1][1] + 1))
                    out.append(f"<{tag}><li>" + body)
                    stack.append((tag, lvl))
        else:
            close_to(0)
            body = inline(n).strip()
            if not body or body in ("&nbsp;",):
                continue
            if n.name in ("h1", "h2", "h3", "h4", "h5", "h6"):
                out.append(f"<h4>{body}</h4>")
            else:
                out.append(f"<p>{body}</p>")
    close_to(0)
    return "".join(out)

def doc_body(name):
    s = BeautifulSoup(open(f"{SP}/{name.replace(' ', '_')}.html", encoding="utf-8").read(), "html.parser")
    return [c for c in s.body.children if getattr(c, "name", None) and not (c.name == "div")]

# ---------- homework: split by "Lecture N" headings ----------
hw_nodes = doc_body("Homeworks")
hw_sections, intro, cur = {}, [], None
for n in hw_nodes:
    t = fix(n.get_text(" ", strip=True))
    m = re.match(r"Lecture\s+(\d+)(?:/(\d+))?", t) if n.name == "h3" else None
    if m:
        cur = {"heading": t, "nodes": [], "nums": [int(m.group(1))] + ([int(m.group(2))] if m.group(2) else [])}
        for k in cur["nums"]:
            hw_sections[k] = cur
        continue
    (cur["nodes"] if cur else intro).append(n)

def dates(h):
    m = re.search(r"assigned on (\d\d/\d\d/\d{4}),? due(?: to)? (\d\d/\d\d/\d{4})", h, re.I)
    return (m.group(1), m.group(2)) if m else (None, None)

# ---------- lecture notes (PDF/doc in Lecture Notes folder) ----------
notes = {}
for f in find("Lecture Notes")["children"]:
    m = re.match(r"QC Lecture\s*(\d+)", f["name"])
    if m:
        kind = "PDF" if f["mimeType"] == "application/pdf" else "Doc"
        notes.setdefault(int(m.group(1)), []).append({"label": f"{kind} notes", "url": f["webViewLink"], "id": f["id"], "kind": kind})

# ---------- recordings ----------
rec_links = json.load(open(f"{SP}/Lecture_Recordings.links.json", encoding="utf-8"))
rec = {}
for text, url in rec_links:
    m = re.match(r"Lecture\s+(\d+)\s*\((.*)\)\s*$", fix(text))
    if m:
        rec[int(m.group(1))] = {"title": m.group(2).strip(), "video": url}
rec_titles_txt = open(f"{SP}/Lecture_Recordings.txt", encoding="utf-8").read()
for m in re.finditer(r"Lecture (\d+) \((.*?)\)\s*$", fix(rec_titles_txt), re.M):  # unrecorded ones (33, 35)
    rec.setdefault(int(m.group(1)), {"title": m.group(2).strip(), "video": None})
rec[33]["title"], rec[35]["title"] = "Quiz", "Mitiq issue kick-off"
rec[33]["note"], rec[35]["note"] = "No recording (quiz)", "No recording (Mitiq issue discussion)"

def yt_id(u):
    if not u:
        return None
    m = re.search(r"(?:youtu\.be/|v=)([\w-]{11})", u)
    return m.group(1) if m else None

# ---------- presenters/dates for the QCAA seminar era (from the Schedule doc) ----------
seminar = {  # lecture -> (date, presenter); matched by topic against the Schedule table
    70: ("2023-07-30", "Preksha"), 69: ("2023-07-23", "Ammar"), 68: ("2023-06-18", "Dariel"),
    67: ("2023-06-04", "Dariel"), 66: ("2023-05-28", "Ammar"), 65: ("2023-05-21", "Ammar"),
    64: ("2023-05-14", "Curtis Bright"), 63: ("2023-05-07", "Ammar"), 62: ("2023-04-30", "Sahmoud"),
    61: ("2023-04-23", "Sahmoud"), 60: ("2023-04-16", "Sahmoud"), 59: ("2023-03-26", "Dariel"),
    58: ("2023-03-19", "Sahmoud"), 57: ("2023-03-05", "Rishi"), 56: ("2023-02-26", "Preksha"),
    55: ("2023-02-19", "Preksha"), 54: ("2023-02-12", "Preksha"), 53: ("2023-02-05", "Dariel"),
    52: ("2023-01-29", "Johnson Qiao"),
}

TRACKS = [
    ("foundations", "Foundations", "Qubits, gates as matrices, superdense coding, teleportation", [1, 2, 3, 4]),
    ("oracles", "Oracle algorithms", "Deutsch, Deutsch-Jozsa, Simon", [5, 6, 7]),
    ("nonlocality", "Entanglement and nonlocality", "EPR pairs, Bell and CHSH", [8, 10, 14]),
    ("grover", "Grover and circuits", "Search, oracles, no-cloning, gate decomposition, Qiskit", [9, 12, 13, 15]),
    ("measurement", "Measurement", "POVMs and measuring compatible operators", [11, 34, 58]),
    ("shor", "Shor, QFT and phase estimation", "Period finding, QFT, Draper adder, quantum counting", [16, 17, 18, 24, 25]),
    ("hardware", "Hardware", "Superconducting qubits, with a guest lecture by Daniel Sank", ["H1", "H2", "H3", "H4", "H5", 52]),
    ("optimization", "Optimization and linear systems", "Adiabatic QC, QAOA, HHL", [27, 28, 29]),
    ("challenges", "Challenges and practice", "QOSF and IBM challenge walk-throughs, the quiz", [26, 31, 32, 33]),
    ("crypto", "Cryptography and lattices", "BB84, hidden subgroup problem, SVP, Kuperberg", [30, 60, 61, 62]),
    ("qec", "Error correction", "Shor code, Hamming, stabilizers, toric and surface codes, Mitiq", [35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 45, 46, 47, 48, 50]),
    ("complexity", "Complexity and verification", "Interactive proofs, nonlocal games, Grilo, MIP* = RE", [49, 54, 55, 56]),
    ("ml", "Learning and ML", "Autoencoders, barren plateaus, online learning, learning states", [53, 57, 59, 70]),
    ("manybody", "Many-body physics", "Kitaev models, spin chains, AKLT, MPS, ergodicity breaking, KS systems", [51, 63, 64, 65, 66, 67, 68, 69]),
]
track_of = {k: t[0] for t in TRACKS for k in t[3]}

def to_iso(d):
    if not d:
        return None
    m, dd, y = d.split("/")
    return f"{y}-{m}-{dd}"

lectures = []
for n in sorted(rec):
    r = rec[n]
    sec = hw_sections.get(n)
    a, due = dates(sec["heading"]) if sec else (None, None)
    hw_html = blocks_to_html(sec["nodes"]) if sec else ""
    shared = sec and len(sec["nums"]) > 1
    date, presenter = seminar.get(n, (to_iso(a), None))
    lectures.append({
        "id": str(n), "num": n, "title": fix(r["title"]), "video": r["video"], "yt": yt_id(r["video"]),
        "note": r.get("note"), "notes": notes.get(n, []), "homework": hw_html,
        "homework_shared_with": [k for k in sec["nums"] if k != n] if shared else [],
        "assigned": to_iso(a), "due": to_iso(due), "date": date, "presenter": presenter,
        "track": track_of.get(n, "other"),
    })

# ---------- hardware series ----------
dl = find("Daniel's Lecture")
prep_notes = {i + 1: f for i, f in enumerate(sorted(find("Lecture Notes", dl["children"])["children"], key=lambda f: f["name"]))}
outline = find("Quantum Computing Hardware Lectures Outline", dl["children"])
hw_links = {fix(t): u for t, u in rec_links}
for i in range(1, 5):
    f = prep_notes[i]
    u = hw_links[f"Quantum Computing Hardware Prep Lecture {i}/4"]
    lectures.append({"id": f"H{i}", "num": None, "title": f"Hardware prep {i}/4", "video": u, "yt": yt_id(u),
                     "notes": [{"label": ("PDF" if f['mimeType'].endswith('pdf') else "Doc") + " notes", "url": f["webViewLink"], "id": f["id"],
                                "kind": "PDF" if f['mimeType'].endswith('pdf') else "Doc"},
                               {"label": "Series outline", "url": outline["webViewLink"], "id": outline["id"], "kind": "Doc"}],
                     "homework": "", "homework_shared_with": [], "track": "hardware", "date": None, "presenter": None,
                     "assigned": None, "due": None, "note": None})
u = hw_links["Daniel Sank Quantum Computing Hardware Guest Lecture"]
lectures.append({"id": "H5", "num": None, "title": "Guest lecture: Daniel Sank on quantum computing hardware", "video": u, "yt": yt_id(u),
                 "notes": [{"label": "Audience Q&A (Dory)", "url": hw_links["Dory Q&A"], "kind": "Link"},
                           {"label": "Daniel Sank's PhD thesis", "url": "https://web.physics.ucsb.edu/~martinisgroup/theses/Sank2014.pdf", "kind": "PDF"}],
                 "homework": "", "homework_shared_with": [], "track": "hardware", "date": None, "presenter": "Daniel Sank",
                 "assigned": None, "due": None, "note": None})

# ---------- seminar schedule table ----------
sch = BeautifulSoup(open(f"{SP}/Schedule.html", encoding="utf-8").read(), "html.parser")
talks = []
for tr in sch.find_all("tr")[1:]:
    tds = tr.find_all("td")
    if len(tds) < 3:
        continue
    d, who, topic = (fix(td.get_text(" ", strip=True)) for td in tds[:3])
    if who in ("NA", "") or topic.strip("* ") == "NA":
        continue
    links = [{"text": fix(a.get_text(" ", strip=True)), "url": unwrap(a["href"])} for a in tds[2].find_all("a") if not a["href"].startswith("#")]
    first = next((fix(x.get_text(" ", strip=True)) for x in tds[2].find_all(["p", "li"]) if x.get_text(strip=True)), topic)
    talks.append({"date": d, "presenter": who, "topic": first.replace(" ", " ").strip(), "links": links})
sch_nodes = [c for c in sch.body.children if getattr(c, "name", None) and c.name in ("ul", "ol", "p", "h1", "h2", "h3", "h4")]
pi = next(i for i, c in enumerate(sch_nodes) if "Potential Topics" in c.get_text())
potential = blocks_to_html(sch_nodes[pi + 1:])

# ---------- syllabus, resources, homework-resources ----------
syl_nodes = doc_body("Syllabus")
pend = next(i for i, c in enumerate(syl_nodes) if c.get_text(strip=True).startswith("Pending"))
syllabus = blocks_to_html(syl_nodes[1:pend])
syllabus_pending = blocks_to_html(syl_nodes[pend + 1:])
resources = blocks_to_html(doc_body("More Resources"))
hw_intro = blocks_to_html(intro)

# ---------- projects + write-ups ----------
def flat(items, prefix=""):
    out = []
    for f in items:
        if "children" in f:
            out.append({"group": f["name"], "items": [{"name": c["name"], "url": c["webViewLink"]} for c in f["children"] if "children" not in c]})
        else:
            out.append({"name": f["name"], "url": f["webViewLink"]})
    return out
projects = flat(find("Projects")["children"])
writeups = [{"name": c["name"], "url": c["webViewLink"]} for c in find("Write-ups")["children"]]

data = {
    "title": "A Gentle Introduction to Quantum Computing",
    "drive": "https://drive.google.com/drive/folders/1OMa3SzBhIBtOJjCh2wKxCrW_yH9ujOjq",
    "github": "https://github.com/bubakazouba/spiny-quantum",
    "tracks": [{"id": t[0], "name": t[1], "blurb": t[2], "items": [str(x) for x in t[3]]} for t in TRACKS],
    "lectures": lectures, "talks": talks, "potential_topics": potential,
    "syllabus": syllabus, "syllabus_pending": syllabus_pending,
    "resources": resources, "homework_resources": hw_intro,
    "projects": projects, "writeups": writeups,
}
json.dump(data, open(f"{OUT}/data.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("lectures", len(lectures), "with video", sum(1 for l in lectures if l["video"]),
      "with notes", sum(1 for l in lectures if l["notes"]), "with hw", sum(1 for l in lectures if l["homework"]),
      "talks", len(talks), "imgs", len(os.listdir(f"{OUT}/img")))
missing = [l["id"] for l in lectures if l["track"] == "other"]
print("untracked", missing)
