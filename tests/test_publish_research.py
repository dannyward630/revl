"""The research drafts reach a reader, and the deploy is what puts them there.

`docs/research/papers/*.md` are research paper drafts; `tools/publish_research.py`
renders them into `site/research/`, and `.github/workflows/pages.yml` runs it.
The pages are built at deploy time and NOT committed, for the census edition's
reason (see `tests/test_publish_census_artifact.py`): a rendered copy is only
right for the tree it was rendered from.

What can go wrong, and what holds it:

1. The deploy stops building the pages, or builds them after the upload (a 404
   where the research section should be). Read statically from the workflow.
2. The rendered pages get committed and start rotting. `.gitignore` is read.
3. A draft is malformed and the section silently renders without it. Every draft
   is parsed here, and the generator is shown to refuse a bad one by name.
4. The text leaks something private (a local path, a downstream repo name, a
   sweep row id, a `[verify]` marker, an em-dash, an attribution). A gate over
   `docs/research/**`, with a positive control so it cannot pass vacuously.
5. Two renders of one tree differ, which would make `--check` meaningless.

Cited repository paths are deliberately NOT checked against HEAD: the drafts pin
them to the snapshot commit, and HEAD moves.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

from _load_by_path import load_by_path

ROOT = Path(__file__).resolve().parents[1]
TOOL = "tools/publish_research.py"
PAGES = ROOT / ".github" / "workflows" / "pages.yml"
GITIGNORE = ROOT / ".gitignore"
RESEARCH = ROOT / "docs" / "research"
SITE_INDEX = ROOT / "site" / "index.html"


def _tool():
    return load_by_path("test_publish_research_under_test", ROOT / TOOL)


@pytest.fixture(scope="module")
def tool():
    return _tool()


@pytest.fixture(scope="module")
def collection(tool):
    return tool.load_collection(RESEARCH)


@pytest.fixture(scope="module")
def rendered(tool):
    return tool.render(RESEARCH, ROOT)


def _uncommented(path: Path) -> str:
    """The workflow without comment-only lines: its header explains the
    arrangements it replaced and names this tool, which is not the step."""
    return "\n".join(ln for ln in path.read_text(encoding="utf-8").splitlines()
                     if not ln.lstrip().startswith("#"))


# --- anti-vacuity ---------------------------------------------------------- #
def test_the_tool_and_the_drafts_exist(collection):
    meta, papers = collection
    assert (ROOT / TOOL).is_file(), f"{TOOL} is gone"
    src = (ROOT / TOOL).read_text(encoding="utf-8")
    for flag in ("--write", "--check", "--list"):
        assert flag in src, f"{TOOL} no longer offers {flag}"
    assert len(papers) >= 1, "no drafts were found under docs/research/papers"
    assert meta["snapshot"] and meta["author"] and meta["license"]


# --- 1: the deploy builds the pages, before the upload --------------------- #
def test_the_deploy_renders_the_research_pages_before_it_uploads():
    text = _uncommented(PAGES)
    builder = f"{TOOL} --write"
    assert builder in text, (
        f"{PAGES.name} no longer runs `{builder}`, so the deploy publishes a site "
        "whose research/ section is a 404 while the home page still links to it"
    )
    upload = "actions/upload-pages-artifact@"
    assert upload in text, f"{PAGES.name} no longer uploads the artifact"
    assert text.index(builder) < text.index(upload), (
        f"`{builder}` runs AFTER the upload in {PAGES.name}: the upload would "
        "publish the checkout, which has no research pages in it"
    )


def test_the_home_page_links_to_the_research_section():
    nav = SITE_INDEX.read_text(encoding="utf-8").split("</nav>")[0]
    assert re.search(r'<a href="research/">Research</a>', nav), (
        "site/index.html no longer links to research/ from its nav"
    )


# --- 2: the pages are not committed ---------------------------------------- #
def test_the_rendered_pages_are_not_committed():
    ignored = GITIGNORE.read_text(encoding="utf-8")
    assert re.search(r"^site/research/?$", ignored, re.M), (
        ".gitignore no longer ignores site/research/, so the rendered pages can "
        "be committed and rot"
    )
    tracked = subprocess.run(["git", "ls-files", "--", "site/research"],
                             cwd=ROOT, capture_output=True, text=True)
    if tracked.returncode == 0:
        assert not tracked.stdout.strip(), (
            f"the rendered research pages are committed at {tracked.stdout.split()}"
        )


# --- 3: every draft parses, and the generator refuses a bad one ------------- #
def test_every_draft_has_its_keys_sections_theme_and_resolvable_fusion(
        tool, collection):
    meta, papers = collection
    themes = {k for k, _ in meta["themes"]}
    ids = {p["id"] for p in papers}
    assert len(ids) == len(papers), "two drafts share an id"
    for p in papers:
        for key in tool.KEYS:
            assert key in p, f"{p['file']}: missing `{key}`"
        assert p["theme"] in themes, f"{p['file']}: unknown theme {p['theme']}"
        assert p["kind"] in tool.KINDS, f"{p['file']}: unknown kind {p['kind']}"
        assert p["maturity"] in tool.MATURITY, f"{p['file']}: bad maturity"
        have = [h for h, _ in p["sections"]]
        for need in tool.SECTIONS:
            assert need in have, f"{p['file']}: missing section {need}"
        for other in p["fused"]:
            assert other in ids, f"{p['file']}: fused_with {other} has no draft"
        assert p["status"].strip(), f"{p['file']}: empty status"


def test_the_collection_file_carries_what_the_pages_state():
    import json
    meta = json.loads((RESEARCH / "research.json").read_text(encoding="utf-8"))
    assert meta["license"] == "CC BY 4.0"
    assert meta["license_url"] == "https://creativecommons.org/licenses/by/4.0/"
    assert meta["author"] == "Thomas Moussajee"
    assert meta["repo"] == "https://github.com/inso1337/revl"
    assert re.fullmatch(r"[0-9a-f]{7,40}", meta["snapshot"])
    assert all(len(t) == 2 for t in meta["themes"])


def _fixture(tmp_path: Path, name: str = "P90-fixture-paper.md",
             drop_key: str | None = None, drop_section: str | None = None,
             theme: str = "formal-pl", fused: str = "", extra_paper: bool = False):
    """A one-paper research directory in tmp_path, optionally malformed."""
    research = tmp_path / "research"
    (research / "papers").mkdir(parents=True)
    (research / "research.json").write_text(
        '{"snapshot": "abc1234", "author": "A. Author", "license": "CC BY 4.0", '
        '"license_url": "https://example.org/l", "repo": "https://example.org/r", '
        '"themes": [["formal-pl", "Formal"], ["methods", "Methods"]]}',
        encoding="utf-8")
    fm = {"id": name[:3], "title": '"A title: with a colon"', "theme": theme,
          "kind": "full", "maturity": "partial", "status": "Something exists.",
          "fused_with": fused}
    if drop_key:
        del fm[drop_key]
    sections = [
        "Pitch", "Abstract", "Problem and claim", "Contributions", "Related work",
        "Evidence on main", "Numbers that exist", "Paper outline",
        "Threats to validity and limits", "Fact-check"]
    if drop_section:
        sections.remove(drop_section)
    text = ("---\n" + "\n".join(f"{k}: {v}" for k, v in fm.items()) + "\n---\n\n"
            + "\n\n".join(f"## {s}\n\nText of {s}." for s in sections) + "\n")
    (research / "papers" / name).write_text(text, encoding="utf-8")
    if extra_paper:
        other = text.replace("id: P90", "id: P91")
        (research / "papers" / "P91-other.md").write_text(other, encoding="utf-8")
    return research


def test_a_well_formed_fixture_renders(tool, tmp_path):
    files = tool.render(_fixture(tmp_path), tmp_path)
    assert set(files) == {"index.html", "P90.html"}
    assert "A title: with a colon" in files["P90.html"]


@pytest.mark.parametrize("kwargs, needle", [
    ({"drop_key": "maturity"}, "missing front matter key `maturity`"),
    ({"drop_key": "fused_with"}, "missing front matter key `fused_with`"),
    ({"drop_section": "Evidence on main"}, "missing section `## Evidence on main`"),
    ({"drop_section": "Fact-check"}, "missing section `## Fact-check`"),
    ({"theme": "no-such-theme"}, "unknown theme 'no-such-theme'"),
    ({"fused": "P77"}, "fused_with names P77, which has no draft"),
])
def test_the_generator_refuses_a_malformed_draft_and_names_the_file(
        tool, tmp_path, capsys, kwargs, needle):
    research = _fixture(tmp_path, **kwargs)
    with pytest.raises(tool.ResearchError) as raised:
        tool.render(research, tmp_path)
    assert "P90-fixture-paper.md" in str(raised.value)
    assert needle in str(raised.value)

    dest = tmp_path / "out"
    code = tool.main(["--write", "--research", str(research), "--dest", str(dest)])
    assert code != 0, "main wrote pages for a malformed draft"
    assert not dest.exists(), "pages were written for a malformed draft"
    assert "P90-fixture-paper.md" in capsys.readouterr().err


def test_a_duplicate_id_is_refused(tool, tmp_path):
    research = _fixture(tmp_path)
    other = (research / "papers" / "P90-fixture-paper.md").read_text(encoding="utf-8")
    (research / "papers" / "P90-second.md").write_text(other, encoding="utf-8")
    with pytest.raises(tool.ResearchError) as raised:
        tool.render(research, tmp_path)
    message = str(raised.value)
    assert "P90-second.md" in message, "the error does not name the draft that repeats the id"
    assert "P90-fixture-paper.md" in message, "the error does not name the draft it repeats"
    assert "P90" in message


# --- the repo path links --------------------------------------------------- #
def test_a_backticked_path_that_exists_links_to_the_snapshot(tool, tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_text("x\n", encoding="utf-8")
    ctx = tool.Ctx({"repo": "https://example.org/r/", "snapshot": "abc1234"}, tmp_path)
    one = tool.inline("see `src/a.py:7`", ctx)
    assert 'href="https://example.org/r/blob/abc1234/src/a.py#L7"' in one
    span = tool.inline("`src/a.py:7-12`", ctx)
    assert "blob/abc1234/src/a.py#L7-L12" in span
    plain = tool.inline("`src/a.py`", ctx)
    assert 'href="https://example.org/r/blob/abc1234/src/a.py"' in plain
    assert "#L" not in plain


def _git(repo: Path, *args: str) -> str:
    import os
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(GIT_AUTHOR_NAME="T", GIT_AUTHOR_EMAIL="t@example.org",
               GIT_COMMITTER_NAME="T", GIT_COMMITTER_EMAIL="t@example.org")
    done = subprocess.run(["git", "-C", str(repo), *args], capture_output=True,
                          text=True, env=env, check=True)
    return done.stdout.strip()


def test_links_follow_the_snapshot_tree_not_the_working_tree(tool, tmp_path):
    """The pages are rendered from a later commit than the one the links point
    at. A file that was there at the snapshot and is gone now still links, and
    one that only exists now does not."""
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    _git(repo, "init", "-q")
    (repo / "src" / "old.py").write_text("x\n", encoding="utf-8")
    (repo / "src" / "kept.py").write_text("x\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "snapshot")
    snapshot = _git(repo, "rev-parse", "HEAD")
    (repo / "src" / "old.py").unlink()
    (repo / "src" / "new.py").write_text("x\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "later")

    ctx = tool.Ctx({"repo": "https://example.org/r", "snapshot": snapshot}, repo)
    assert ctx.source == "snapshot"
    assert f"blob/{snapshot}/src/old.py" in tool.inline("`src/old.py:3`", ctx)
    assert f"blob/{snapshot}/src/kept.py" in tool.inline("`src/kept.py`", ctx)
    assert f"tree/{snapshot}/src" in tool.inline("`src/`", ctx)
    assert "<a " not in tool.inline("`src/new.py`", ctx), (
        "a file that did not exist at the snapshot was linked"
    )


def test_a_missing_snapshot_falls_back_to_the_working_tree_or_is_refused(
        tool, tmp_path, capsys):
    research = _fixture(tmp_path)   # snapshot abc1234 is in no repository here
    ctx = tool.Ctx({"repo": "https://example.org/r", "snapshot": "abc1234"}, tmp_path)
    assert ctx.source == "working tree"
    assert tool.render(research, tmp_path), "the fallback did not render"
    assert "not available" in capsys.readouterr().err
    with pytest.raises(tool.ResearchError) as raised:
        tool.render(research, tmp_path, require_snapshot=True)
    assert "abc1234" in str(raised.value)


def test_the_deploy_checks_out_history_and_requires_the_snapshot():
    text = _uncommented(PAGES)
    assert "--require-snapshot" in text.split(f"{TOOL} --write")[1].splitlines()[0]
    checkout = text.split("actions/checkout@")[1].split("actions/setup-python")[0]
    assert re.search(r"fetch-depth:\s*0\b", checkout), (
        "the deploy checkout is shallow, so the snapshot commit may be missing"
    )


def test_source_links_go_to_main_and_code_links_stay_on_the_snapshot(
        tool, rendered, collection):
    meta, papers = collection
    for name, text in rendered.items():
        assert f"/tree/{meta['snapshot']}/docs/research" not in text, (
            f"{name} links the sources to a commit that does not hold them"
        )
        assert f"{meta['repo']}/tree/main/docs/research" in text
    assert any(f"/blob/{meta['snapshot']}/" in t for t in rendered.values())


def test_index_cards_render_inline_markup_in_the_status(tool, tmp_path):
    research = _fixture(tmp_path)
    paper = research / "papers" / "P90-fixture-paper.md"
    paper.write_text(paper.read_text(encoding="utf-8").replace(
        "status: Something exists.", "status: A **bold** claim in `code <b>`."),
        encoding="utf-8")
    index = tool.render(research, tmp_path)["index.html"]
    assert '<p class="status">A <strong>bold</strong> claim in <code>code &lt;b&gt;</code>.</p>' in index


def test_anything_else_in_backticks_stays_plain_code(tool, tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_text("x\n", encoding="utf-8")
    ctx = tool.Ctx({"repo": "https://example.org/r", "snapshot": "abc1234"}, tmp_path)
    for span in ("src/missing.py:3", "Session.fork", "../etc/passwd", "/etc/passwd",
                 "src/a.py::test_name", "a < b"):
        out = tool.inline(f"`{span}`", ctx)
        assert "<a " not in out, f"`{span}` was linked: {out}"
        assert "<code>" in out


def test_markdown_the_drafts_use_renders_and_everything_else_is_escaped(
        tool, tmp_path):
    ctx = tool.Ctx({"repo": "https://example.org/r", "snapshot": "abc1234"}, tmp_path)
    md = ("A **bold** and *italic* and [link](https://example.org/x) and "
          "<script>alert(1)</script> & `code <b>`.\n\n"
          "- one\n- two\n  continues\n\n"
          "1. first\n2. second\n\n"
          "| h1 | h2 |\n|---|---|\n| `a|b` | x \\| y |\n")
    out = tool.render_markdown(md, ctx)
    assert "<strong>bold</strong>" in out and "<em>italic</em>" in out
    assert '<a href="https://example.org/x">link</a>' in out
    assert "<script>" not in out and "&lt;script&gt;" in out
    assert "<code>code &lt;b&gt;</code>" in out
    assert "<ul><li>one</li><li>two continues</li></ul>" in out
    assert "<ol><li>first</li><li>second</li></ol>" in out
    assert out.count("<tr>") == 2 and "<td><code>a|b</code></td><td>x | y</td>" in out
    assert "<a " not in tool.inline("[x](javascript:alert(1))", ctx)


def test_fusion_groups_merge_overlapping_lists(tool):
    papers = [{"id": "P01", "fused": ["P23"]}, {"id": "P23", "fused": ["P01"]},
              {"id": "P10", "fused": ["P12", "P11"]}, {"id": "P12", "fused": ["P10"]},
              {"id": "P05", "fused": []}]
    assert tool.fusion_groups(papers) == [["P01", "P23"], ["P10", "P11", "P12"]]


# --- 5: determinism, and check is exact ------------------------------------ #
def test_two_renders_of_one_tree_are_byte_identical(tool, rendered, collection):
    _, papers = collection
    assert tool.render(RESEARCH, ROOT) == rendered
    assert set(rendered) == {"index.html", *(f"{p['id']}.html" for p in papers)}
    for name, text in rendered.items():
        assert str(ROOT) not in text, f"{name} embeds this checkout's path"
        assert "/Users/" not in text, f"{name} embeds an absolute path"
        assert not re.search(r"\b20\d\d-\d\d-\d\dT", text), f"{name} embeds a timestamp"
        assert "—" not in text, f"{name} contains an em-dash"


def test_the_pages_carry_what_a_reader_needs(rendered, collection):
    meta, papers = collection
    index = rendered["index.html"]
    for needle in (meta["author"], meta["license"], meta["license_url"],
                   meta["snapshot"], "@misc{revlresearch", "Planned combined papers",
                   "not peer reviewed", 'id="filters"'):
        assert needle in index, f"index.html lacks {needle!r}"
    for p in papers:
        page = rendered[f"{p['id']}.html"]
        assert p["title"].split(":")[0][:20] in page
        assert "Cite this draft" in page and "@misc{revl" in page
        assert 'href="./"' in page, f"{p['id']}.html has no way back to the index"
        assert f'href="{p["id"]}.html"' in index, f"index.html does not list {p['id']}"
        for other in p["fused"]:
            assert f'href="{other}.html"' in page


def test_the_filter_degrades_to_the_full_list_without_js(rendered, collection):
    """The controls are `hidden` until a script un-hides them, and no card is
    hidden in the markup, so a reader without JS sees every draft."""
    _, papers = collection
    index = rendered["index.html"]
    assert re.search(r'<form id="filters"[^>]*\bhidden\b', index)
    assert index.count('<article class="paper"') == len(papers)
    assert not re.search(r'<article class="paper"[^>]*\bhidden\b', index)


def test_check_is_exact_in_both_directions(tool, rendered, tmp_path):
    dest = tmp_path / "research"
    tool.write(rendered, dest)
    assert tool.check(rendered, dest) == 0

    page = dest / "index.html"
    page.write_text(page.read_text(encoding="utf-8") + "extra", encoding="utf-8")
    assert tool.check(rendered, dest) == 1, "a mutated page passed --check"

    page.write_text(rendered["index.html"], encoding="utf-8")
    (dest / "P01.html").unlink()
    assert tool.check(rendered, dest) == 1, "a missing page passed --check"

    tool.write(rendered, dest)
    (dest / "P99.html").write_text("stale", encoding="utf-8")
    assert tool.check(rendered, dest) == 1, "a stale extra page passed --check"
    tool.write(rendered, dest)
    assert not (dest / "P99.html").exists(), "--write left a stale page behind"
    assert tool.check(rendered, dest) == 0


# --- 4: the leak gate over docs/research/** -------------------------------- #
# Product names that appear as the subject of a related-work row, of a
# provider adapter or of a benchmarked tool, never as an author or helper. Each
# is an exact phrase in an exact file, so a new occurrence anywhere else is
# still a red.
THIRD_PARTY = {
    "P55-approval-as-type-judgment.md": ["Claude Code permission modes",
                                         "OpenAI Agents SDK"],
    "P60-self-extending-runtime-propose-swap.md": ["Copilot Workspace"],
    "P62-typed-model-boundary-constrained-decoding.md": [
        "Anthropic tool use", "anthropic and gemini read",
        "Anthropic and Gemini adapters", "OpenAI Structured Outputs",
        "Gemini responseSchema"],
    "P66-agent-compiler-boundary-roles.md": ["Copilot Workspace", "Apple M1 Max"],
    "P44-embeddable-failclosed-admission-gate.md": ["Apple M1 Max"],
    "P69-lifecycle-residue-empirical-study.md": ["OpenAI agents SDK"],
}

LEAKS = [
    ("an absolute local path", re.compile(r"/Users/")),
    ("the private worktree name", re.compile(r"wt-papers")),
    ("the private lanes directory", re.compile(r"revl-lanes")),
    ("a private downstream repo", re.compile(r"revl-harness|revl-sp")),
    ("a downstream item id", re.compile(r"\b[HM][0-9]{1,3}\b")),
    ("a sweep row id", re.compile(r"\br[0-9]{4}\b")),
    ("a [verify] marker", re.compile(r"\[verify\]")),
    ("an em-dash", re.compile("—")),
    ("a private draft heading", re.compile(
        r"^\s*#+\s*(Scorecard|Target venues|What is missing|Needs downstream material)\b",
        re.I)),
    ("an assistant or vendor name", re.compile(r"Claude|Anthropic|Co-Authored", re.I)),
    ("another vendor or model name", re.compile(r"OpenAI|\bGPT|Gemini|Copilot")),
]


def leaks(name: str, text: str) -> list[str]:
    """Every leak in `text`, as `line N: what`. Allowed third-party phrases are
    removed from their own file before the words are looked for."""
    for phrase in THIRD_PARTY.get(name, []):
        text = text.replace(phrase, "")
    found = []
    for n, line in enumerate(text.splitlines(), 1):
        for what, pat in LEAKS:
            if pat.search(line):
                found.append(f"line {n}: {what}")
    return found


def test_the_leak_gate_catches_each_leak_it_names():
    """Positive control: a gate that finds nothing in the drafts proves nothing
    until it is shown finding something."""
    samples = {
        "an absolute local path": "see /Users/x/y",
        "the private worktree name": "in wt-papers",
        "a private downstream repo": "the revl-harness engine",
        "a sweep row id": "record r0123 says",
        "a [verify] marker": "Smith 2020 [verify]",
        "an em-dash": "a — b",
        "an assistant or vendor name": "drafted by Claude",
        "the private lanes directory": "see revl-lanes/orchestration",
        "a downstream item id": "tracked as M78 downstream",
        "a private draft heading": "## Needs downstream material",
        "another vendor or model name": "scored with GPT-4",
    }
    assert set(samples) == {what for what, _ in LEAKS}
    for what, line in samples.items():
        assert any(what in hit for hit in leaks("P00-x.md", line)), what
    assert leaks("P00-x.md", "Co-Authored-By: someone"), "Co-Authored is not caught"
    for line in ("item H12 is open", "milestone M5", "run by OpenAI", "asked Gemini",
                 "Copilot wrote it", "## Scorecard", "### Target venues",
                 "## What is missing"):
        assert leaks("P00-x.md", line), f"not caught: {line!r}"
    assert not leaks("P44-embeddable-failclosed-admission-gate.md", "Apple M1 Max")
    assert leaks("P00-x.md", "Apple M1 Max"), "the hardware allowance is not per file"
    for line in ("the word scorecard in a sentence", "H123456",
                 "what is missing from the table"):
        assert not leaks("P00-x.md", line), f"false positive: {line!r}"
    assert leaks("P55-approval-as-type-judgment.md", "Claude Code permission modes") == []
    assert leaks("P56-other.md", "Claude Code permission modes"), (
        "the third-party allowance leaked into a file it was not written for"
    )
    assert leaks("P56-other.md", "Copilot Workspace"), (
        "the Copilot allowance leaked into a file it was not written for"
    )
    assert leaks("P66-agent-compiler-boundary-roles.md", "OpenAI Agents SDK"), (
        "an allowance is wider than the phrase it was written for"
    )
    assert leaks("P66-agent-compiler-boundary-roles.md", "Copilot Workspace and Gemini")


def test_the_research_text_leaks_nothing_private():
    files = sorted(p for p in RESEARCH.rglob("*") if p.is_file())
    assert files, "docs/research/ holds no files"
    problems = []
    for f in files:
        for hit in leaks(f.name, f.read_text(encoding="utf-8")):
            problems.append(f"{f.relative_to(ROOT)}: {hit}")
    assert not problems, "private or attributing text in docs/research:\n" + "\n".join(problems)
