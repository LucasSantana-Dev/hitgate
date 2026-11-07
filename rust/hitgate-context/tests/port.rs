//! Ports of `tests/test_context.py`. Same fixture corpus, same assertions, plus the
//! Python-compatibility shims (`round`, `repr`) the cross-check depends on.

use hitgate_context::*;
use serde_json::Value;
use std::fs;
use std::path::{Path, PathBuf};
use std::process::Command;
use std::sync::atomic::{AtomicUsize, Ordering};

static COUNTER: AtomicUsize = AtomicUsize::new(0);

struct TempDir(PathBuf);

impl TempDir {
    fn new() -> Self {
        let n = COUNTER.fetch_add(1, Ordering::SeqCst);
        let p =
            std::env::temp_dir().join(format!("hitgate-context-rs-{}-{}", std::process::id(), n));
        let _ = fs::remove_dir_all(&p);
        fs::create_dir_all(&p).unwrap();
        TempDir(p)
    }
    fn path(&self) -> &Path {
        &self.0
    }
}

impl Drop for TempDir {
    fn drop(&mut self) {
        let _ = fs::remove_dir_all(&self.0);
    }
}

fn write(p: &Path, text: &str) {
    fs::create_dir_all(p.parent().unwrap()).unwrap();
    fs::write(p, text).unwrap();
}

/// Mirror of `tests/test_context.py::_corpus`.
fn corpus(root: &Path) {
    write(
        &root.join("skills/ship/SKILL.md"),
        "---
name: ship
description: Version bump, changelog, tag and GitHub release.
triggers:
  - ship
  - cut a release
---
# ship
",
    );
    write(
        &root.join("skills/verify/SKILL.md"),
        "---
name: verify
description: Run the narrowest checks to validate before merge.
auto-invoke: run checks, validate this
---
# verify
",
    );
    write(
        &root.join("skills/nodesc/SKILL.md"),
        "# no front matter
",
    );
    let body = ["postgres connection pool exhausted under load fix pgbouncer"; 5].join(" ");
    write(
        &root.join("memory/pg-pool.md"),
        &format!(
            "---
name: pg-pool
description: postgres pool exhaustion fixed with pgbouncer
metadata:
  type: project
---
{}
",
            body
        ),
    );
    write(
        &root.join("memory/MEMORY.md"),
        "- [pg](pg-pool.md)
",
    );
    write(
        &root.join("memory/short.md"),
        "---
description: too short to index
---
hi
",
    );
}

fn str_field(f: &Fields, k: &str) -> String {
    match f.get(k) {
        Some(Field::Str(s)) => s.clone(),
        other => panic!("{} = {:?}", k, other),
    }
}

fn list_field(f: &Fields, k: &str) -> Vec<String> {
    match f.get(k) {
        Some(Field::List(v)) => v.clone(),
        other => panic!("{} = {:?}", k, other),
    }
}

#[test]
fn frontmatter_lists_and_scalars() {
    let (f, body) = parse_frontmatter(
        "---\nname: x\ntriggers: [a, \"b c\"]\nauto-invoke:\n  - d\n  - 'e f'\n---\nbody\n",
    );
    assert_eq!(str_field(&f, "name"), "x");
    assert_eq!(list_field(&f, "triggers"), vec!["a", "b c"]);
    assert_eq!(list_field(&f, "auto-invoke"), vec!["d", "e f"]);
    assert_eq!(body, "body\n");
}

#[test]
fn frontmatter_folded_scalar() {
    let (f, _) = parse_frontmatter(
        "---\nauto-invoke: >-\n  \"prod is broken\",\n  \"hotfix\", urgency markers\n---\n",
    );
    assert_eq!(
        str_field(&f, "auto-invoke"),
        "\"prod is broken\", \"hotfix\", urgency markers"
    );
    assert_eq!(
        phrases_of(&f, "auto-invoke"),
        vec!["\"prod is broken\"", "\"hotfix\"", "urgency markers"]
    );
}

/// `_phrases` is private in Python too; recompute it the public way via mining a skill.
fn phrases_of(f: &Fields, key: &str) -> Vec<String> {
    match f.get(key) {
        Some(Field::List(v)) => v
            .iter()
            .map(|s| s.trim().to_string())
            .filter(|s| !s.is_empty())
            .collect(),
        Some(Field::Str(s)) => s
            .split(',')
            .map(str::trim)
            .filter(|s| !s.is_empty())
            .map(String::from)
            .collect(),
        _ => vec![],
    }
}

#[test]
fn frontmatter_wrapped_description() {
    let (f, _) = parse_frontmatter(
        "---\nname: x\ndescription: first line\n  continues here\nnext: y\n---\n",
    );
    assert_eq!(str_field(&f, "description"), "first line continues here");
    assert_eq!(str_field(&f, "next"), "y");
}

#[test]
fn frontmatter_no_frontmatter() {
    let (f, body) = parse_frontmatter("# plain\n");
    assert!(f.is_empty());
    assert_eq!(body, "# plain\n");
}

#[test]
fn mine_skills_and_notes() {
    let t = TempDir::new();
    corpus(t.path());
    let c = mine(t.path());
    let skill: Vec<_> = c
        .cases
        .iter()
        .filter(|c| c.intent == "skill-trigger")
        .collect();
    let notes: Vec<_> = c.cases.iter().filter(|c| c.intent == "note").collect();
    let mut queries: Vec<&str> = skill.iter().map(|c| c.query.as_str()).collect();
    queries.sort();
    assert_eq!(
        queries,
        vec!["cut a release", "run checks", "ship", "validate this"]
    );
    assert_eq!(notes.len(), 1);
    assert_eq!(
        notes[0].query,
        "postgres pool exhaustion fixed with pgbouncer"
    );
    assert_eq!(notes[0].expect_path_contains, "/memory/pg-pool.md");
    let paths: Vec<&str> = c.docs.iter().map(|(p, _)| p.as_str()).collect();
    assert_eq!(
        paths,
        vec![
            "/skills/ship/SKILL.md",
            "/skills/verify/SKILL.md",
            "/memory/pg-pool.md"
        ]
    );
    assert!(skill
        .iter()
        .all(|c| c.expect_path_contains.starts_with('/')));
}

#[test]
fn bm25_ranks_own_doc_first_and_shadowed_is_empty() {
    let t = TempDir::new();
    corpus(t.path());
    let c = mine(t.path());
    let bm = Bm25::new(&c.docs);
    let hits = bm.search("cut a release", 5);
    assert_eq!(hits[0].path, "/skills/ship/SKILL.md");
    let mut r = run(&c.cases, 5, |q, top| bm.search(q, top));
    assert_eq!(r.agg.hit1, 1.0);
    assert_eq!(r.agg.mrr, 1.0);
    r.shadowed = shadowed(&r);
    assert!(r.shadowed.is_empty());
}

#[test]
fn lost_reports_cases_that_hit_before_and_miss_now() {
    let t = TempDir::new();
    corpus(t.path());
    let c = mine(t.path());
    let bm = Bm25::new(&c.docs);
    let good = run(&c.cases, 5, |q, top| bm.search(q, top));
    let base: Value = serde_json::to_value(&good).unwrap();
    let broken = run(&c.cases, 5, |_q, _top| Vec::<Hit>::new());
    let l = lost(&broken, &base);
    assert_eq!(l.len(), c.cases.len());
    assert!(l
        .iter()
        .all(|x| x.was_rank.as_u64() == Some(1) && x.now.is_none()));
}

fn bin() -> Command {
    Command::new(env!("CARGO_BIN_EXE_hitgate-context"))
}

#[test]
fn main_gates_a_regression_with_exit_1() {
    let t = TempDir::new();
    let root = t.path().join("ctx");
    corpus(&root);
    let out = t.path().join("out");
    let ok = bin()
        .args([root.to_str().unwrap(), "--out", out.to_str().unwrap()])
        .output()
        .unwrap();
    assert_eq!(
        ok.status.code(),
        Some(0),
        "{}",
        String::from_utf8_lossy(&ok.stderr)
    );
    let baseline = out.join("context.context.json");
    assert!(baseline.is_file());

    // Break ship: its description no longer mentions releases, and verify steals the phrase.
    write(
        &root.join("skills/ship/SKILL.md"),
        "---\nname: ship\ndescription: Do the thing.\ntriggers:\n  - ship\n  - \"cut a release\"\n---\n",
    );
    write(
        &root.join("skills/verify/SKILL.md"),
        "---\nname: verify\ndescription: Cut a release and ship validated work to production with a release tag.\nauto-invoke: run checks, validate this\n---\n",
    );
    let bad = bin()
        .args([
            root.to_str().unwrap(),
            "--out",
            out.to_str().unwrap(),
            "--label",
            "after",
            "--baseline",
            baseline.to_str().unwrap(),
        ])
        .output()
        .unwrap();
    let stdout = String::from_utf8_lossy(&bad.stdout);
    assert_eq!(bad.status.code(), Some(1), "{}", stdout);
    let verdict: Value =
        serde_json::from_slice(&fs::read(out.join("context.after.verdict.json")).unwrap()).unwrap();
    assert_eq!(verdict["verdict"], "regression");
    assert!(stdout.contains("Shadowed"), "{}", stdout);
    assert!(
        stdout.contains("Newly unreachable") || stdout.contains("REGRESSION"),
        "{}",
        stdout
    );
}

#[test]
fn main_exit_2_on_missing_or_empty_root() {
    let t = TempDir::new();
    let missing = bin()
        .arg(t.path().join("nope").to_str().unwrap())
        .output()
        .unwrap();
    assert_eq!(missing.status.code(), Some(2));
    let empty = t.path().join("empty");
    fs::create_dir_all(&empty).unwrap();
    let e = bin().arg(empty.to_str().unwrap()).output().unwrap();
    assert_eq!(e.status.code(), Some(2));
    let args = bin()
        .args(["--tol", "x", empty.to_str().unwrap()])
        .output()
        .unwrap();
    assert_eq!(args.status.code(), Some(2));
}

#[test]
fn py_round_matches_python() {
    // Python: round(0.0625, 3) == 0.062 (ties to even on the exact binary value),
    // round(2.675, 2) == 2.67 (2.675 is below the tie in binary), round(0.5, 0) == 0.0.
    assert_eq!(py_round(0.0625, 3), 0.062);
    assert_eq!(py_round(2.675, 2), 2.67);
    assert_eq!(py_round(0.5, 0), 0.0);
    assert_eq!(py_round(1.0 / 3.0, 3), 0.333);
    assert_eq!(py_round(2.0 / 3.0, 3), 0.667);
}

#[test]
fn py_repr_and_float() {
    assert_eq!(py_repr("ship"), "'ship'");
    assert_eq!(py_repr("don't"), "\"don't\"");
    assert_eq!(py_repr("a\\b\n"), "'a\\\\b\\n'");
    assert_eq!(py_float(1.0), "1.0");
    assert_eq!(py_float(0.5), "0.5");
    assert_eq!(py_float(0.333), "0.333");
}

#[test]
fn tokenizer_matches_python() {
    assert_eq!(
        tokenize("Cut a release, NOW! v2.0"),
        vec!["cut", "release", "now", "v2"]
    );
    assert_eq!(tokenize("the a an"), Vec::<String>::new());
}
