#!/usr/bin/env python3
"""Render the research paper drafts under docs/research/ as a section of the site.

The drafts live in `docs/research/papers/<ID>-<slug>.md`: a small front matter
block and a fixed list of sections (the shape is checked here, not assumed).
`docs/research/research.json` names the collection (author, licence, the repo
snapshot the drafts were written against, the themes). This tool turns them
into plain static pages under `site/research/`:

    site/research/index.html     the collection: papers by theme, their state,
                                 a filter, the planned combined papers
    site/research/<ID>.html      one page per draft

The pages are built at deploy time and NOT committed, for the reason the census
edition and the playground wheel are not (see `tools/publish_census_artifact.py`
and `tools/check_site_wheel.py`): a rendered copy is a function of the tree it
was rendered from, and a committed copy starts rotting at the next merge.
`.github/workflows/pages.yml` runs `--write` before it uploads `site/`.

    python3 tools/publish_research.py --write    render into site/research/
    python3 tools/publish_research.py --check    re-render and diff byte for byte
    python3 tools/publish_research.py --list     one line per draft

The output is deterministic: no timestamp, no absolute path, files in sorted
order. A backticked repository path (`path`, `path:N` or `path:N-M`) whose file
exists at the snapshot commit (read with `git ls-tree`; the working tree only
when that commit is not available) becomes a link to the file at the snapshot,
with the line range as the anchor; anything else stays plain code. Rendering refuses,
naming the file, a draft that lacks a front matter key or a section, that names
an unknown theme, kind or maturity, or whose `fused_with` names a draft that
does not exist. Stdlib only.
"""

from __future__ import annotations

import argparse
import html
import json
import os
import posixpath
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RESEARCH = ROOT / "docs" / "research"
DEST = ROOT / "site" / "research"

# The citation year of the collection. The drafts are a 2026 snapshot; a fixed
# constant keeps the render free of a clock.
YEAR = "2026"

SITE_URL = "https://inso1337.github.io/revl/research/"

KEYS = ("id", "title", "theme", "kind", "maturity", "status", "fused_with")
SECTIONS = ("Pitch", "Abstract", "Problem and claim", "Contributions",
            "Related work", "Evidence on main", "Numbers that exist",
            "Paper outline", "Threats to validity and limits", "Fact-check")
KINDS = ("full", "short", "workshop", "empirical", "benchmark", "journal",
         "position", "experience", "tool-demo", "methods")
# maturity -> (label, badge class from site.css, one line a reader can act on)
MATURITY = {
    "shipped-evidence": ("shipped evidence", "badge-good",
                         "The mechanism is on main and the claim is backed by "
                         "tests or measurements there."),
    "partial": ("partial", "badge-warn",
                "Part of the mechanism is on main; the rest, or the "
                "evaluation, is not."),
    "design-only": ("design only", "badge-violet",
                    "A written design; little or nothing runs yet."),
}
COLLECTION_KEYS = ("snapshot", "author", "license", "license_url", "repo",
                   "themes")

ID_RE = re.compile(r"^P\d{2}$")
FILE_RE = re.compile(r"^(P\d{2})-[a-z0-9][a-z0-9-]*\.md$")
REPO_PATH_RE = re.compile(r"^([A-Za-z0-9_.][A-Za-z0-9_./+-]*?)(?::(\d+)(?:-(\d+))?)?$")


class ResearchError(Exception):
    """A draft or the collection file cannot be rendered. Names the file."""


# --------------------------------------------------------------------------- #
# loading and validation
# --------------------------------------------------------------------------- #
def _rel(path: Path) -> str:
    try:
        return str(Path(path).relative_to(ROOT))
    except ValueError:
        return str(path)


def load_meta(research: Path) -> dict:
    path = research / "research.json"
    try:
        meta = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ResearchError(f"{_rel(path)}: cannot read: {exc}") from exc
    for key in COLLECTION_KEYS:
        if key not in meta:
            raise ResearchError(f"{_rel(path)}: missing key `{key}`")
    themes = meta["themes"]
    if not themes or any(len(t) != 2 for t in themes):
        raise ResearchError(f"{_rel(path)}: `themes` must be [[key, title], ...]")
    meta["themes"] = [(k, t) for k, t in themes]
    return meta


def _unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        inner = value[1:-1]
        if value[0] == '"':
            inner = inner.replace('\\"', '"').replace("\\\\", "\\")
        return inner
    return value


def split_front_matter(text: str, name: str) -> tuple[dict, str]:
    m = re.match(r"---\n(.*?)\n---\n", text, re.S)
    if not m:
        raise ResearchError(f"{name}: no front matter block")
    fm: dict[str, str] = {}
    for line in m.group(1).split("\n"):
        if not line.strip():
            continue
        key, sep, value = line.partition(":")
        if not sep or not re.fullmatch(r"[a-z_]+", key):
            raise ResearchError(f"{name}: front matter line is not `key: value`: {line!r}")
        fm[key] = _unquote(value)
    return fm, text[m.end():]


def split_sections(body: str) -> list[tuple[str, str]]:
    """The `## ` sections of the body, in file order, as (heading, text)."""
    sections: list[tuple[str, list[str]]] = []
    for line in body.split("\n"):
        if line.startswith("## "):
            sections.append((line[3:].strip(), []))
        elif sections:
            sections[-1][1].append(line)
    return [(h, "\n".join(ls).strip("\n")) for h, ls in sections]


def parse_paper(path: Path, theme_keys: set[str]) -> dict:
    name = _rel(path)
    m = FILE_RE.match(path.name)
    if not m:
        raise ResearchError(f"{name}: file name is not <ID>-<slug>.md")
    fm, body = split_front_matter(path.read_text(encoding="utf-8"), name)
    for key in KEYS:
        if key not in fm:
            raise ResearchError(f"{name}: missing front matter key `{key}`")
    if fm["id"] != m.group(1) or not ID_RE.match(fm["id"]):
        raise ResearchError(f"{name}: front matter id {fm['id']!r} does not match the file name")
    for key in ("title", "status"):
        if not fm[key]:
            raise ResearchError(f"{name}: front matter key `{key}` is empty")
    if fm["theme"] not in theme_keys:
        raise ResearchError(f"{name}: unknown theme {fm['theme']!r}")
    if fm["kind"] not in KINDS:
        raise ResearchError(f"{name}: unknown kind {fm['kind']!r}")
    if fm["maturity"] not in MATURITY:
        raise ResearchError(f"{name}: unknown maturity {fm['maturity']!r}")
    fused = [x.strip() for x in fm["fused_with"].split(",") if x.strip()]
    for other in fused:
        if not ID_RE.match(other) or other == fm["id"]:
            raise ResearchError(f"{name}: bad fused_with entry {other!r}")
    sections = split_sections(body)
    have = {h for h, _ in sections}
    for need in SECTIONS:
        if need not in have:
            raise ResearchError(f"{name}: missing section `## {need}`")
    return {**fm, "fused": fused, "sections": sections, "file": name}


def load_papers(research: Path, theme_keys: set[str]) -> list[dict]:
    files = sorted((research / "papers").glob("*.md"))
    if not files:
        raise ResearchError(f"{_rel(research / 'papers')}: no drafts found")
    papers = [parse_paper(f, theme_keys) for f in files]
    ids: dict[str, str] = {}
    for p in papers:
        if p["id"] in ids:
            raise ResearchError(f"{p['file']}: id {p['id']} is also used by {ids[p['id']]}")
        ids[p["id"]] = p["file"]
    for p in papers:
        for other in p["fused"]:
            if other not in ids:
                raise ResearchError(
                    f"{p['file']}: fused_with names {other}, which has no draft")
    return papers


def load_collection(research: Path = RESEARCH) -> tuple[dict, list[dict]]:
    meta = load_meta(research)
    return meta, load_papers(research, {k for k, _ in meta["themes"]})


def fusion_groups(papers: list[dict]) -> list[list[str]]:
    """The planned combined papers: each draft with its `fused_with`, merged
    where two lists overlap, as sorted id lists in sorted order."""
    groups: list[set[str]] = []
    for p in papers:
        if not p["fused"]:
            continue
        members = {p["id"], *p["fused"]}
        for g in [g for g in groups if g & members]:
            members |= g
            groups.remove(g)
        groups.append(members)
    return sorted(sorted(g) for g in groups)


# --------------------------------------------------------------------------- #
# markdown, only what the drafts use
# --------------------------------------------------------------------------- #
def snapshot_paths(root: Path, snapshot: str) -> tuple[set[str], set[str]] | None:
    """(files, directories) of the tree at `snapshot`, from `git ls-tree`, or
    None when git or that commit is not available in `root`."""
    env = {k: v for k, v in os.environ.items()
           if k not in ("GIT_DIR", "GIT_INDEX_FILE", "GIT_WORK_TREE")}
    try:
        done = subprocess.run(
            ["git", "-C", str(root), "ls-tree", "-r", "--name-only", "-z", snapshot],
            capture_output=True, env=env, check=False)
    except OSError:
        return None
    if done.returncode != 0:
        return None
    files = {n for n in done.stdout.decode("utf-8", "replace").split("\0") if n}
    dirs = {d for n in files for d in _parents(n)}
    return files, dirs


def _parents(path: str) -> list[str]:
    parts = path.split("/")
    return ["/".join(parts[:i]) for i in range(1, len(parts))]


class Ctx:
    """What the inline renderer needs: where repository links go, and which
    files exist at the snapshot the links point to.

    A link is only right if the file exists at the snapshot, and the pages are
    rendered from a later commit, so existence is read from the snapshot's own
    tree. The working tree is the fallback when git or the snapshot is not
    available (`source` says which was used); it is only exact while the
    checkout is the snapshot."""

    def __init__(self, meta: dict, root: Path):
        self.repo = meta["repo"].rstrip("/")
        self.snapshot = meta["snapshot"]
        self.root = root
        self._tree = snapshot_paths(root, self.snapshot)
        self.source = "snapshot" if self._tree else "working tree"

    def kind_of(self, path: str) -> str | None:
        """"blob" for a file, "tree" for a directory, None if neither exists."""
        path = posixpath.normpath(path)
        if self._tree:
            files, dirs = self._tree
            return "blob" if path in files else "tree" if path in dirs else None
        target = self.root / path
        return "blob" if target.is_file() else "tree" if target.is_dir() else None


def esc(text: str) -> str:
    return html.escape(text, quote=True)


def repo_link(span: str, ctx: Ctx) -> str | None:
    """The GitHub URL for a backticked repo path, or None if it is not one."""
    m = REPO_PATH_RE.match(span)
    if not m:
        return None
    path, start, end = m.groups()
    if ".." in path.split("/"):
        return None
    kind = ctx.kind_of(path)
    if kind is None or (kind == "tree" and "/" not in path):
        return None
    url = f"{ctx.repo}/{kind}/{ctx.snapshot}/{posixpath.normpath(path)}"
    if start and kind == "blob":
        url += f"#L{start}" + (f"-L{end}" if end else "")
    return url


_LINK_RE = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)")
_BOLD_RE = re.compile(r"\*\*(?=\S)(.+?)(?<=\S)\*\*")
_ITAL_RE = re.compile(r"(?<![\w*])\*(?=[^\s*])(.+?)(?<=[^\s*])\*(?![\w*])")


def _plain(text: str) -> str:
    text = esc(text)
    text = _LINK_RE.sub(lambda m: f'<a href="{m.group(2)}">{m.group(1)}</a>', text)
    text = _BOLD_RE.sub(r"<strong>\1</strong>", text)
    return _ITAL_RE.sub(r"<em>\1</em>", text)


def inline(text: str, ctx: Ctx) -> str:
    out = []
    for i, part in enumerate(re.split(r"(`[^`\n]+`)", text)):
        if i % 2 == 0:
            out.append(_plain(part))
            continue
        span = part[1:-1]
        url = repo_link(span, ctx)
        code = f"<code>{esc(span)}</code>"
        out.append(f'<a class="repo" href="{esc(url)}">{code}</a>' if url else code)
    return "".join(out)


def split_row(line: str) -> list[str]:
    """Cells of a pipe-table row; a `|` inside backticks or after `\\` is text."""
    cells, cur, in_code, i = [], [], False, 0
    line = line.strip()
    if line.startswith("|"):
        line = line[1:]
    if line.endswith("|") and not line.endswith("\\|"):
        line = line[:-1]
    while i < len(line):
        ch = line[i]
        if ch == "\\" and i + 1 < len(line) and line[i + 1] == "|":
            cur.append("|")
            i += 2
            continue
        if ch == "`":
            in_code = not in_code
        if ch == "|" and not in_code:
            cells.append("".join(cur).strip())
            cur = []
        else:
            cur.append(ch)
        i += 1
    cells.append("".join(cur).strip())
    return cells


_BULLET = re.compile(r"^[-*] +(.*)$")
_NUMBER = re.compile(r"^\d+[.)] +(.*)$")
_SEPARATOR = re.compile(r"^\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)*\|?\s*$")


def _table(lines: list[str], ctx: Ctx) -> str:
    head = split_row(lines[0])
    rows = [split_row(ln) for ln in lines[2:]]
    out = ['<div class="tablewrap"><table>', "<thead><tr>"]
    out += [f"<th>{inline(c, ctx)}</th>" for c in head]
    out.append("</tr></thead><tbody>")
    for row in rows:
        row = (row + [""] * len(head))[:len(head)]
        out.append("<tr>" + "".join(f"<td>{inline(c, ctx)}</td>" for c in row) + "</tr>")
    out.append("</tbody></table></div>")
    return "".join(out)


def _list(lines: list[str], ordered: bool, ctx: Ctx) -> str:
    pat = _NUMBER if ordered else _BULLET
    items: list[list[str]] = []
    for ln in lines:
        m = pat.match(ln)
        if m:
            items.append([m.group(1)])
        else:
            items[-1].append(ln.strip())
    tag = "ol" if ordered else "ul"
    body = "".join(f"<li>{inline(' '.join(it), ctx)}</li>" for it in items)
    return f"<{tag}>{body}</{tag}>"


def _continues_list(line: str, pat: re.Pattern) -> bool:
    """A line belongs to the open list: another item of the same kind, or text
    that continues the last item (not a blank, heading, table or other list)."""
    if not line.strip() or re.match(r"^#{1,6} ", line) or line.lstrip().startswith("|"):
        return False
    return bool(pat.match(line)) or not (_BULLET.match(line) or _NUMBER.match(line))


def render_markdown(text: str, ctx: Ctx, base_level: int = 3) -> str:
    """Headings, paragraphs, bullet and numbered lists, pipe tables."""
    lines = text.split("\n")
    out: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            i += 1
            continue
        m = re.match(r"^(#{1,6}) +(.*)$", line)
        if m:
            level = min(6, max(base_level, len(m.group(1))))
            out.append(f"<h{level}>{inline(m.group(2), ctx)}</h{level}>")
            i += 1
        elif line.lstrip().startswith("|") and i + 1 < len(lines) and _SEPARATOR.match(lines[i + 1]):
            j = i + 2
            while j < len(lines) and lines[j].lstrip().startswith("|"):
                j += 1
            out.append(_table(lines[i:j], ctx))
            i = j
        elif _BULLET.match(line) or _NUMBER.match(line):
            ordered = bool(_NUMBER.match(line))
            pat = _NUMBER if ordered else _BULLET
            j = i + 1
            while j < len(lines) and _continues_list(lines[j], pat):
                j += 1
            out.append(_list(lines[i:j], ordered, ctx))
            i = j
        else:
            j = i + 1
            while j < len(lines) and lines[j].strip() and not re.match(r"^#{1,6} ", lines[j]) \
                    and not lines[j].lstrip().startswith("|") \
                    and not _BULLET.match(lines[j]) and not _NUMBER.match(lines[j]):
                j += 1
            out.append(f"<p>{inline(' '.join(s.strip() for s in lines[i:j]), ctx)}</p>")
            i = j
    return "\n".join(out)


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


# --------------------------------------------------------------------------- #
# pages
# --------------------------------------------------------------------------- #
def _nav(prefix: str) -> str:
    return f"""<nav class="nav">
  <div class="wrap nav-inner">
    <a class="brand" href="{prefix}index.html">revl<span class="cursor"></span></a>
    <div class="nav-links">
      <a href="{prefix}index.html">Home</a>
      <a href="{prefix}research/">Research</a>
      <a href="{prefix}playground.html">Playground</a>
    </div>
    <span class="spacer"></span>
    <div class="nav-cta">
      <a class="btn btn-ghost btn-sm" href="https://github.com/inso1337/revl">GitHub</a>
      <a class="btn btn-primary btn-sm" href="{prefix}playground.html">Playground</a>
    </div>
  </div>
</nav>"""


def _footer(meta: dict) -> str:
    return f"""<footer>
  <div class="wrap foot-inner">
    <div>
      <span style="font-family:var(--mono); color:var(--text)">revl</span> research drafts
      · text © {YEAR} {esc(meta['author'])}, <a href="{esc(meta['license_url'])}">{esc(meta['license'])}</a>
      · not peer reviewed
    </div>
    <div class="foot-links">
      <a href="{esc(meta['repo'])}">GitHub</a>
      <a href="{esc(meta['repo'])}/tree/main/docs/research">Sources</a>
      <a href="./">All drafts</a>
      <a href="../index.html">revl.dev</a>
    </div>
  </div>
</footer>"""


def _page(title: str, description: str, body: str, meta: dict, prefix: str, script: str = "") -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{esc(title)}</title>
  <meta name="description" content="{esc(description)}" />
  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600;700&display=swap" rel="stylesheet" />
  <link rel="stylesheet" href="{prefix}css/site.css" />
  <link rel="stylesheet" href="{prefix}css/research.css" />
  <link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><rect width='100' height='100' rx='18' fill='%2306080e'/><text x='50' y='68' font-size='52' font-family='monospace' font-weight='700' fill='%232dd4bf' text-anchor='middle'>r</text></svg>" />
</head>
<body class="research">

{_nav(prefix)}

{body}

{_footer(meta)}
{script}</body>
</html>
"""


def maturity_badge(key: str) -> str:
    label, cls, _ = MATURITY[key]
    return f'<span class="badge {cls}">{esc(label)}</span>'


def bibtex(key: str, title: str, meta: dict, note: str, url: str = SITE_URL) -> str:
    return (f"@misc{{{key},\n"
            f"  author       = {{{meta['author']}}},\n"
            f"  title        = {{{title}}},\n"
            f"  year         = {{{YEAR}}},\n"
            f"  howpublished = {{\\url{{{url}}}}},\n"
            f"  note         = {{{note}}}\n"
            f"}}")


def paper_bibtex(p: dict, meta: dict) -> str:
    note = (f"Research draft, not peer reviewed. Written against revl commit "
            f"{meta['snapshot']}. Licensed {meta['license']}.")
    return bibtex(f"revl{p['id'].lower()}", p["title"], meta, note,
                  f"{SITE_URL}{p['id']}.html")


def render_paper(p: dict, by_id: dict[str, dict], meta: dict, ctx: Ctx) -> str:
    themes = dict(meta["themes"])
    fused = ""
    if p["fused"]:
        links = ", ".join(
            f'<a href="{o}.html">{o}</a> ({esc(by_id[o]["title"])})' for o in p["fused"])
        fused = (f'<p class="fused">Planned to be combined with {links} into a '
                 "single paper.</p>")
    toc = "".join(f'<li><a href="#{slug(h)}">{esc(h)}</a></li>' for h, _ in p["sections"])
    sections = "\n".join(
        f'<section id="{slug(h)}">\n<h2>{esc(h)}</h2>\n{render_markdown(t, ctx)}\n</section>'
        for h, t in p["sections"])
    cite = paper_bibtex(p, meta)
    body = f"""<main class="wrap paper-page">
  <p class="crumbs"><a href="./">Research</a> / {esc(themes[p['theme']])}</p>
  <p class="eyebrow">{esc(p['id'])} · {esc(p['kind'])} · draft</p>
  <h1>{esc(p['title'])}</h1>
  <p class="badges">{maturity_badge(p['maturity'])} <span class="badge badge-plain">{esc(p['kind'])}</span> <span class="badge badge-plain">{esc(themes[p['theme']])}</span></p>
  <div class="state">
    <p><strong>State of the work.</strong> {inline(p['status'], ctx)}</p>
    <p class="muted">This is a draft, not peer reviewed. Repository references link to
    revl at commit <a href="{esc(ctx.repo)}/commit/{esc(ctx.snapshot)}"><code>{esc(ctx.snapshot)}</code></a>.</p>
    {fused}
  </div>
  <nav class="toc" aria-label="Sections"><ol>{toc}</ol></nav>
{sections}
  <section id="cite">
    <h2>Cite this draft</h2>
    <pre class="cite"><code>{esc(cite)}</code></pre>
    <p class="muted">Text licensed <a href="{esc(meta['license_url'])}">{esc(meta['license'])}</a>, author {esc(meta['author'])}.</p>
  </section>
  <p class="back"><a href="./">&larr; All research drafts</a></p>
</main>"""
    return _page(f"{p['id']}: {p['title']} | revl research", p["status"], body, meta, "../")


FILTER_JS = """<script>
(function () {
  var form = document.getElementById("filters");
  if (!form) return;
  form.hidden = false;
  var cards = [].slice.call(document.querySelectorAll("article.paper"));
  var groups = [].slice.call(document.querySelectorAll("section.theme"));
  var count = document.getElementById("shown");
  function apply() {
    var want = {}, shown = 0;
    ["theme", "maturity", "kind"].forEach(function (k) { want[k] = form.elements[k].value; });
    cards.forEach(function (c) {
      var ok = ["theme", "maturity", "kind"].every(function (k) {
        return !want[k] || c.getAttribute("data-" + k) === want[k];
      });
      c.hidden = !ok;
      if (ok) shown += 1;
    });
    groups.forEach(function (g) {
      g.hidden = !g.querySelector("article.paper:not([hidden])");
    });
    count.textContent = shown + " of " + cards.length + " drafts shown";
  }
  form.addEventListener("change", apply);
  form.addEventListener("reset", function () { setTimeout(apply, 0); });
  apply();
})();
</script>
"""


def _options(values: list[tuple[str, str]], label: str) -> str:
    opts = "".join(f'<option value="{esc(v)}">{esc(t)}</option>' for v, t in values)
    return f'<option value="">{esc(label)}</option>{opts}'


def _card(p: dict, ctx: Ctx) -> str:
    return f"""<article class="paper" data-theme="{esc(p['theme'])}" data-maturity="{esc(p['maturity'])}" data-kind="{esc(p['kind'])}">
  <div class="paper-head"><a class="paper-id" href="{p['id']}.html">{esc(p['id'])}</a> {maturity_badge(p['maturity'])} <span class="badge badge-plain">{esc(p['kind'])}</span></div>
  <h3><a href="{p['id']}.html">{esc(p['title'])}</a></h3>
  <p class="status">{inline(p['status'], ctx)}</p>
</article>"""


def _theme_sections(papers: list[dict], meta: dict, ctx: Ctx) -> str:
    out = []
    for key, title in meta["themes"]:
        mine = [p for p in papers if p["theme"] == key]
        if not mine:
            continue
        out.append(f'<section class="theme" id="theme-{esc(key)}">\n'
                   f'<h2>{esc(title)} <span class="count">{len(mine)}</span></h2>\n'
                   + "\n".join(_card(p, ctx) for p in mine) + "\n</section>")
    return "\n".join(out)


def _groups_section(papers: list[dict]) -> str:
    by_id = {p["id"]: p for p in papers}
    groups = fusion_groups(papers)
    if not groups:
        return ""
    items = "".join(
        "<li>" + " + ".join(f'<a href="{i}.html">{i}</a>' for i in g) + ": "
        + esc("; ".join(by_id[i]["title"] for i in g)) + "</li>"
        for g in groups)
    return f"""<section id="combined">
<h2>Planned combined papers</h2>
<p>Some drafts cover one argument from several sides. These groups are planned to
become a single paper each; until then they are published as separate drafts.</p>
<ul class="groups">{items}</ul>
</section>"""


def render_index(papers: list[dict], meta: dict, ctx: Ctx) -> str:
    counts = {k: sum(1 for p in papers if p["maturity"] == k) for k in MATURITY}
    maturity_rows = "".join(
        f"<li>{maturity_badge(k)} {counts[k]} drafts. {esc(MATURITY[k][2])}</li>"
        for k in MATURITY)
    kinds = sorted({p["kind"] for p in papers})
    form = f"""<form id="filters" class="filters" hidden>
  <label>Theme <select name="theme">{_options(meta['themes'], 'all themes')}</select></label>
  <label>State <select name="maturity">{_options([(k, v[0]) for k, v in MATURITY.items()], 'any state')}</select></label>
  <label>Kind <select name="kind">{_options([(k, k) for k in kinds], 'any kind')}</select></label>
  <button type="reset" class="btn btn-ghost btn-sm">Reset</button>
  <span id="shown" class="muted" aria-live="polite"></span>
</form>"""
    cite = bibtex("revlresearch", "Research drafts about revl", meta,
                  f"Collection of research drafts, not peer reviewed. Written against "
                  f"revl commit {meta['snapshot']}. Licensed {meta['license']}.")
    body = f"""<main class="wrap">
  <header class="research-hero">
    <p class="eyebrow">Research</p>
    <h1>Research drafts about revl</h1>
    <p class="lede">{len(papers)} papers about the language, its checker, its runtime and the
    way agents use it. Each page says what exists on main today and what kind of
    result is still missing, so you can tell a measured claim from a design.</p>
  </header>

  <section id="state">
    <h2>State of the collection</h2>
    <p><strong>Every paper here is a draft.</strong> None has been peer reviewed.
    The drafts were written against revl commit
    <a href="{esc(ctx.repo)}/commit/{esc(ctx.snapshot)}"><code>{esc(ctx.snapshot)}</code></a>,
    and the repository references in them link to that commit, so a reference keeps
    meaning what it meant when it was written even as main moves. A citation
    that still has to be checked is marked in the text.</p>
    <ul class="maturity">{maturity_rows}</ul>
    <p>Author: {esc(meta['author'])}. Text licensed
    <a href="{esc(meta['license_url'])}">{esc(meta['license'])}</a>. The sources are
    <a href="{esc(ctx.repo)}/tree/main/docs/research">in the repository</a>.</p>
  </section>

  <section id="papers">
    <h2>Drafts</h2>
    {form}
    {_theme_sections(papers, meta, ctx)}
  </section>

  {_groups_section(papers)}

  <section id="cite">
    <h2>How to cite</h2>
    <p>Cite the collection, or a single draft from the cite block at the end of its
    page. A draft is a work in progress: cite the page, not a result as settled.</p>
    <pre class="cite"><code>{esc(cite)}</code></pre>
  </section>
</main>"""
    return _page("Research drafts | revl",
                 f"{len(papers)} research drafts about revl and the state of each.",
                 body, meta, "../", FILTER_JS)


def render(research: Path = RESEARCH, root: Path = ROOT,
           require_snapshot: bool = False) -> dict[str, str]:
    """Every page of the section, as {file name: text}, in sorted name order.

    Repository links are decided by the tree at the snapshot commit. When that
    commit is not in `root` the working tree decides instead and a note is
    printed; `require_snapshot` makes that a refusal (the deploy uses it, so a
    shallow checkout cannot publish links judged against the wrong tree)."""
    meta, papers = load_collection(research)
    ctx = Ctx(meta, root)
    if ctx.source != "snapshot":
        if require_snapshot:
            raise ResearchError(
                f"snapshot commit {ctx.snapshot} is not available in {root}; "
                "fetch full history (actions/checkout fetch-depth: 0)")
        print(f"publish_research: snapshot {ctx.snapshot} not available; "
              "repository links are judged against the working tree", file=sys.stderr)
    by_id = {p["id"]: p for p in papers}
    files = {"index.html": render_index(papers, meta, ctx)}
    for p in papers:
        files[f"{p['id']}.html"] = render_paper(p, by_id, meta, ctx)
    return dict(sorted(files.items()))


# --------------------------------------------------------------------------- #
# write / check / list
# --------------------------------------------------------------------------- #
def write(files: dict[str, str], dest: Path) -> None:
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    for stale in dest.glob("*.html"):
        if stale.name not in files:
            stale.unlink()
    for name, text in files.items():
        (dest / name).write_text(text, encoding="utf-8")


def check(files: dict[str, str], dest: Path) -> int:
    """Re-render into a temp dir and diff it against `dest`, byte for byte."""
    dest = Path(dest)
    if not dest.is_dir():
        print(f"publish_research: {dest} does not exist; render it with --write")
        return 1
    with tempfile.TemporaryDirectory() as tmp:
        fresh = Path(tmp)
        write(files, fresh)
        want = {p.name: p.read_bytes() for p in fresh.iterdir()}
    have = {p.name: p.read_bytes() for p in dest.iterdir() if p.is_file()}
    problems = [f"{n} is missing" for n in sorted(want.keys() - have.keys())]
    problems += [f"{n} is not rendered by this tree" for n in sorted(have.keys() - want.keys())]
    problems += [f"{n} differs from a fresh render" for n in sorted(want.keys() & have.keys())
                 if want[n] != have[n]]
    if problems:
        print("publish_research: site/research has drifted; re-render with --write")
        for line in problems:
            print(f"  {line}")
        return 1
    print(f"publish_research: {len(want)} files match a fresh render")
    return 0


def list_papers(papers: list[dict]) -> str:
    return "\n".join(f"{p['id']}\t{p['theme']}\t{p['maturity']}\t{p['kind']}\t{p['title']}"
                     for p in papers)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true", help=f"render into --dest (default {DEST})")
    mode.add_argument("--check", action="store_true", help="re-render and diff against --dest")
    mode.add_argument("--list", action="store_true", help="one line per draft")
    ap.add_argument("--dest", type=Path, default=DEST)
    ap.add_argument("--require-snapshot", action="store_true",
                    help="refuse to render unless the snapshot commit is in this checkout")
    ap.add_argument("--research", type=Path, default=RESEARCH,
                    help="the docs/research directory to read")
    args = ap.parse_args(argv)
    try:
        if args.list:
            print(list_papers(load_collection(args.research)[1]))
            return 0
        files = render(args.research, require_snapshot=args.require_snapshot)
    except ResearchError as exc:
        print(f"publish_research: {exc}", file=sys.stderr)
        return 1
    if args.check:
        return check(files, args.dest)
    write(files, args.dest)
    print(f"publish_research: wrote {len(files)} files to {_rel(args.dest)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
