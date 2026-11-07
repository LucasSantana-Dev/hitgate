"""Context gate: mining, the stdlib BM25 proxy, the shadowing report and the gate exit code."""
import json

from hitgate.context import BM25, lost, main, mine, parse_frontmatter, shadowed
from hitgate.run import run


def _corpus(root):
    (root / "skills" / "ship").mkdir(parents=True)
    (root / "skills" / "ship" / "SKILL.md").write_text(
        "---\nname: ship\ndescription: Version bump, changelog, tag and GitHub release.\n"
        "triggers:\n  - ship\n  - cut a release\n---\n# ship\n"
    )
    (root / "skills" / "verify").mkdir(parents=True)
    (root / "skills" / "verify" / "SKILL.md").write_text(
        "---\nname: verify\ndescription: Run the narrowest checks to validate before merge.\n"
        "auto-invoke: run checks, validate this\n---\n# verify\n"
    )
    (root / "skills" / "nodesc").mkdir(parents=True)
    (root / "skills" / "nodesc" / "SKILL.md").write_text("# no front matter\n")
    (root / "memory").mkdir()
    body = " ".join(["postgres connection pool exhausted under load fix pgbouncer"] * 5)
    (root / "memory" / "pg-pool.md").write_text(
        "---\nname: pg-pool\ndescription: postgres pool exhaustion fixed with pgbouncer\n"
        f"metadata:\n  type: project\n---\n{body}\n"
    )
    (root / "memory" / "MEMORY.md").write_text("- [pg](pg-pool.md)\n")
    (root / "memory" / "short.md").write_text("---\ndescription: too short to index\n---\nhi\n")


def test_parse_frontmatter_lists_and_scalars():
    text = (
        "---\nname: x\ndescription: \"quoted\"\ntriggers:\n  - a\n  - b\n"
        "tags: [c, d]\nmetadata:\n  type: y\n---\nbody"
    )
    f, body = parse_frontmatter(text)
    assert f["description"] == "quoted"
    assert f["triggers"] == ["a", "b"]
    assert f["tags"] == ["c", "d"]
    assert "type" not in f
    assert body == "body"
    assert parse_frontmatter("no front matter") == ({}, "no front matter")
    folded = "---\nauto-invoke: >-\n  \"prod is broken\", \"hotfix\",\n  urgency markers\n---\n"
    f, _ = parse_frontmatter(folded)
    assert f["auto-invoke"] == '"prod is broken", "hotfix", urgency markers'
    wrapped = "---\ndescription: Coordinate sessions for parallel implementation, review,\n  and synthesis.\nnext:\n  on the next line\n---\n"
    f, _ = parse_frontmatter(wrapped)
    assert f["description"] == "Coordinate sessions for parallel implementation, review, and synthesis."
    assert f["next"] == "on the next line"


def test_mine_skills_and_memory(tmp_path):
    _corpus(tmp_path)
    cases, docs = mine(tmp_path)
    assert set(docs) == {"/skills/ship/SKILL.md", "/skills/verify/SKILL.md", "/memory/pg-pool.md"}
    assert not docs["/memory/pg-pool.md"].startswith("---")  # body only, front matter stripped
    assert {c["intent"] for c in cases} == {"skill-trigger", "note"}
    triggers = {c["query"] for c in cases if c["intent"] == "skill-trigger"}
    assert triggers == {"ship", "cut a release", "run checks", "validate this"}


def test_bm25_ranks_own_document_first_and_reports_shadowing(tmp_path):
    _corpus(tmp_path)
    cases, docs = mine(tmp_path)
    r = BM25(docs)
    assert r("cut a release", 5)[0]["path"] == "/skills/ship/SKILL.md"
    assert r("zzz nothing", 5) == []
    out = run(cases, top=5, retriever=r)
    assert out["hit@5"] == 1.0
    stub = lambda q, top, scope: [{"path": "/skills/verify/SKILL.md"}, {"path": "/skills/ship/SKILL.md"}]
    out = run(cases[:1], top=5, retriever=stub)
    assert shadowed(out) == [
        {"query": cases[0]["query"], "expect": "/skills/ship/SKILL.md", "rank": 2, "shadowed_by": "/skills/verify/SKILL.md"}
    ]


def test_anchored_paths_do_not_collide(tmp_path):
    # "review/SKILL.md" is a substring of "code-review/SKILL.md"; the anchored form is not.
    for name, desc in (("review", "Review a diff for defects."), ("code-review", "Review code for style.")):
        (tmp_path / name).mkdir()
        (tmp_path / name / "SKILL.md").write_text(f"---\nname: {name}\ndescription: {desc}\ntriggers: [review]\n---\n")
    cases, docs = mine(tmp_path)
    stub = lambda q, top, scope: [{"path": "/code-review/SKILL.md"}]
    out = run([c for c in cases if c["expect_path_contains"] == "/review/SKILL.md"], top=5, retriever=stub)
    assert out["hit@5"] == 0.0


def test_lost_flags_one_broken_skill_under_the_aggregate_tolerance():
    base = {"per_case": [{"query": f"q{i}", "expect": f"/s{i}", "hit_rank": 1} for i in range(100)]}
    cur = {"per_case": [dict(c, hit_rank=(None if c["query"] == "q7" else 1), top_hit="/other:1") for c in base["per_case"]]}
    assert lost(cur, base) == [{"query": "q7", "expect": "/s7", "was_rank": 1, "now": "/other:1"}]


def test_main_gates_against_baseline(tmp_path, capsys):
    _corpus(tmp_path)
    out = tmp_path / "out"
    assert main([str(tmp_path), "--label", "base", "--out", str(out)]) == 0
    base = out / "context.base.json"
    assert json.loads(base.read_text())["hit@5"] == 1.0
    # Break ship's description and let verify steal its trigger phrase.
    (tmp_path / "skills" / "ship" / "SKILL.md").write_text(
        "---\nname: ship\ndescription: Nothing relevant here.\ntriggers:\n  - ship\n  - cut a release\n---\n"
    )
    (tmp_path / "skills" / "verify" / "SKILL.md").write_text(
        "---\nname: verify\ndescription: cut a release and ship it.\nauto-invoke: run checks, validate this\n---\n"
    )
    assert main([str(tmp_path), "--label", "cur", "--out", str(out), "--baseline", str(base)]) == 1
    v = json.loads((out / "context.cur.verdict.json").read_text())
    assert v["verdict"] == "regression"
    assert "Shadowed" in capsys.readouterr().out


def test_main_rejects_missing_or_empty_root(tmp_path):
    assert main([str(tmp_path / "nope")]) == 2
    (tmp_path / "empty").mkdir()
    assert main([str(tmp_path / "empty")]) == 2
