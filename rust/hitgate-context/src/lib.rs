//! Port of `hitgate/context.py` (plus the slices of `hitgate/run.py` and
//! `hitgate/compare.py` it uses). Behaviour is matched on purpose, down to the
//! operation order of the BM25 arithmetic and Python's `round()`, so that a
//! baseline written by one implementation gates a run of the other.
//!
//! Caveat (ADR-0012): a hit proves the phrase still reaches its own document
//! under this lexical proxy retriever, not that the document is good.

use serde::Serialize;
use serde_json::Value;
use std::collections::{BTreeMap, HashMap, HashSet};
use std::fmt::Write as _;
use std::fs;
use std::path::{Path, PathBuf};

pub const CAVEAT: &str = "context gate measures discoverability under a lexical proxy retriever: \
a hit means the phrase still reaches its own document, not that the document is good.";

pub const SKIP_DIRS: &[&str] = &[".git", "node_modules", "__pycache__", ".venv"];

const STOP: &[&str] = &[
    "the", "a", "an", "and", "or", "to", "for", "of", "in", "on", "use", "when", "with", "this",
    "is", "it", "as", "by", "be", "that", "from", "your", "you",
];

// ---------------------------------------------------------------- python shims

/// Python `round(x, ndigits)`: correctly rounded, ties to even on the exact binary value.
/// Rust's exact float formatting has the same semantics, so format and parse back.
pub fn py_round(x: f64, ndigits: usize) -> f64 {
    format!("{:.*}", ndigits, x).parse::<f64>().unwrap_or(x)
}

/// Python `repr(float)` for the values this tool prints (finite, no exponent range).
pub fn py_float(x: f64) -> String {
    if x.is_finite() && x.fract() == 0.0 && x.abs() < 1e16 {
        format!("{:.1}", x)
    } else {
        format!("{}", x)
    }
}

/// Python `repr(str)`: single quotes unless the text holds a single quote and no double quote.
pub fn py_repr(s: &str) -> String {
    let quote = if s.contains('\'') && !s.contains('"') {
        '"'
    } else {
        '\''
    };
    let mut out = String::with_capacity(s.len() + 2);
    out.push(quote);
    for ch in s.chars() {
        match ch {
            '\\' => out.push_str("\\\\"),
            '\n' => out.push_str("\\n"),
            '\r' => out.push_str("\\r"),
            '\t' => out.push_str("\\t"),
            c if c == quote => {
                out.push('\\');
                out.push(c);
            }
            c if (c as u32) < 0x20 || c as u32 == 0x7f => {
                let _ = write!(out, "\\x{:02x}", c as u32);
            }
            c => out.push(c),
        }
    }
    out.push(quote);
    out
}

/// Python 3.12+ `sum()` over floats: Neumaier compensated summation.
fn py_fsum(items: impl IntoIterator<Item = f64>) -> f64 {
    let mut result = 0.0f64;
    let mut c = 0.0f64;
    for x in items {
        let t = result + x;
        if result.abs() >= x.abs() {
            c += (result - t) + x;
        } else {
            c += (x - t) + result;
        }
        result = t;
    }
    if c != 0.0 && c.is_finite() {
        result += c;
    }
    result
}

/// `Path.read_text(encoding="utf-8", errors="replace")`: lossy decode plus universal newlines.
pub fn read_text(p: &Path) -> String {
    match fs::read(p) {
        Ok(bytes) => String::from_utf8_lossy(&bytes)
            .replace("\r\n", "\n")
            .replace('\r', "\n"),
        Err(_) => String::new(),
    }
}

/// `Path.expanduser()`.
pub fn expanduser(s: &str) -> PathBuf {
    if s == "~" || s.starts_with("~/") || s.starts_with("~\\") {
        if let Some(home) = std::env::var_os("HOME").or_else(|| std::env::var_os("USERPROFILE")) {
            let mut p = PathBuf::from(home);
            if s.len() > 2 {
                p.push(&s[2..]);
            }
            return p;
        }
    }
    PathBuf::from(s)
}

// ------------------------------------------------------------------ tokenizer

/// `[a-z0-9]+` over the lower-cased text, tokens longer than one char, stop words dropped.
pub fn tokenize(text: &str) -> Vec<String> {
    let lower = text.to_lowercase();
    let mut out = Vec::new();
    let mut cur = String::new();
    let flush = |cur: &mut String, out: &mut Vec<String>| {
        if cur.len() > 1 && !STOP.contains(&cur.as_str()) {
            out.push(std::mem::take(cur));
        } else {
            cur.clear();
        }
    };
    for ch in lower.chars() {
        if ch.is_ascii_lowercase() || ch.is_ascii_digit() {
            cur.push(ch);
        } else if !cur.is_empty() {
            flush(&mut cur, &mut out);
        }
    }
    if !cur.is_empty() {
        flush(&mut cur, &mut out);
    }
    out
}

// ---------------------------------------------------------------- frontmatter

/// A front matter value: `key:` with nothing after it, a scalar, or a list.
#[derive(Clone, Debug, PartialEq)]
pub enum Field {
    Null,
    Str(String),
    List(Vec<String>),
}

pub type Fields = HashMap<String, Field>;

fn unquote(s: &str) -> String {
    let s = s.trim();
    let b = s.as_bytes();
    if b.len() >= 2 && b[0] == b[b.len() - 1] && (b[0] == b'"' || b[0] == b'\'') {
        return s[1..s.len() - 1].to_string();
    }
    s.to_string()
}

/// Minimal YAML front matter: scalars, `- item` lists, `[a, b]` inline lists, `>-` / `|`
/// block scalars and plain scalars continued on indented lines. Nested mappings are ignored.
/// Returns the fields and the body with the front matter stripped.
pub fn parse_frontmatter(text: &str) -> (Fields, &str) {
    if !text.starts_with("---") {
        return (Fields::new(), text);
    }
    let end = match text[3..].find("\n---") {
        Some(i) => i + 3,
        None => return (Fields::new(), text),
    };
    let mut fields = Fields::new();
    let mut key: Option<String> = None;
    let mut block = false;
    for line in text[3..end].split('\n') {
        if line.trim().is_empty() {
            continue;
        }
        let indented = line.starts_with(' ') || line.starts_with('\t');
        if indented {
            if let Some(k) = &key {
                let lstripped = line.trim_start();
                if let Some(item) = lstripped.strip_prefix("- ") {
                    if matches!(fields.get(k), None | Some(Field::Null)) {
                        fields.insert(k.clone(), Field::List(Vec::new()));
                    }
                    if let Some(Field::List(items)) = fields.get_mut(k) {
                        items.push(unquote(item));
                        continue;
                    }
                }
                let cur = fields.get(k);
                let is_none = matches!(cur, None | Some(Field::Null));
                let continued =
                    block || matches!(cur, Some(Field::Str(_))) || (is_none && !line.contains(':'));
                if continued {
                    let base = match cur {
                        Some(Field::Str(s)) => s.as_str(),
                        _ => "",
                    };
                    let joined = format!("{} {}", base, unquote(line.trim()))
                        .trim()
                        .to_string();
                    fields.insert(k.clone(), Field::Str(joined));
                }
            }
            continue; // nested mapping or unknown indentation: ignored
        }
        let Some((k, v)) = line.split_once(':') else {
            continue;
        };
        let k = k.trim().to_string();
        let v = v.trim();
        block = matches!(v, ">" | ">-" | "|" | "|-");
        if block {
            fields.insert(k.clone(), Field::Str(String::new()));
        } else if v.starts_with('[') && v.ends_with(']') {
            let inner = if v.len() >= 2 { &v[1..v.len() - 1] } else { "" };
            let items = inner
                .split(',')
                .filter(|x| !x.trim().is_empty())
                .map(unquote)
                .collect();
            fields.insert(k.clone(), Field::List(items));
        } else if !v.is_empty() {
            fields.insert(k.clone(), Field::Str(unquote(v)));
        } else {
            fields.insert(k.clone(), Field::Null); // a `- item` list may follow
        }
        key = Some(k);
    }
    (fields, text[end + 4..].trim_start_matches('\n'))
}

fn phrases(value: Option<&Field>) -> Vec<String> {
    match value {
        Some(Field::List(items)) => items
            .iter()
            .map(|s| s.trim())
            .filter(|s| !s.is_empty())
            .map(String::from)
            .collect(),
        Some(Field::Str(s)) => s
            .split(',')
            .map(str::trim)
            .filter(|s| !s.is_empty())
            .map(String::from)
            .collect(),
        _ => Vec::new(),
    }
}

/// How Python formats the value in `f"{fields.get('name', ...)} {desc}"`.
fn field_display(value: &Field) -> String {
    match value {
        Field::Null => "None".to_string(),
        Field::Str(s) => s.clone(),
        Field::List(items) => format!(
            "[{}]",
            items
                .iter()
                .map(|s| py_repr(s))
                .collect::<Vec<_>>()
                .join(", ")
        ),
    }
}

// --------------------------------------------------------------------- mining

#[derive(Clone, Debug, PartialEq, Serialize)]
pub struct Case {
    pub query: String,
    pub expect_path_contains: String,
    pub intent: String,
}

/// Mined golden set and its corpus. `docs` keeps insertion order, like the Python dict.
#[derive(Debug, Default)]
pub struct Corpus {
    pub cases: Vec<Case>,
    pub docs: Vec<(String, String)>,
}

struct Entry {
    parts: Vec<String>,
    path: PathBuf,
}

fn walk(dir: &Path, rel: &mut Vec<String>, out: &mut Vec<Entry>) {
    let Ok(rd) = fs::read_dir(dir) else { return };
    for e in rd.flatten() {
        let name = e.file_name().to_string_lossy().into_owned();
        let path = e.path();
        rel.push(name);
        out.push(Entry {
            parts: rel.clone(),
            path: path.clone(),
        });
        // pathlib's rglob does not descend into symlinked directories.
        if e.file_type().map(|t| t.is_dir()).unwrap_or(false) {
            walk(&path, rel, out);
        }
        rel.pop();
    }
}

/// Sort key matching `sorted()` over `pathlib.Path`: per component, case-folded on Windows.
fn sort_key(parts: &[String]) -> Vec<String> {
    if cfg!(windows) {
        parts.iter().map(|p| p.to_lowercase()).collect()
    } else {
        parts.to_vec()
    }
}

fn name_matches(name: &str, target: &str) -> bool {
    if cfg!(windows) {
        name.eq_ignore_ascii_case(target)
    } else {
        name == target
    }
}

fn ends_with_md(name: &str) -> bool {
    if cfg!(windows) {
        name.len() >= 3 && name[name.len() - 3..].eq_ignore_ascii_case(".md")
    } else {
        name.ends_with(".md")
    }
}

fn skipped(parts: &[String]) -> bool {
    parts.iter().any(|p| SKIP_DIRS.contains(&p.as_str()))
}

fn rel(parts: &[String]) -> String {
    format!("/{}", parts.join("/"))
}

/// Mine cases and documents from a context root.
///
/// Skills: each trigger / auto-invoke phrase is a query; the searchable text is
/// `name + description`. Notes (anything else with a frontmatter description and a body of
/// at least 20 tokens): the description is the query; the searchable text is the body.
pub fn mine(root: &Path) -> Corpus {
    let root = fs::canonicalize(root).unwrap_or_else(|_| root.to_path_buf());
    let mut entries = Vec::new();
    walk(&root, &mut Vec::new(), &mut entries);
    entries.sort_by_key(|e| sort_key(&e.parts));

    let mut corpus = Corpus::default();
    let mut skill_dirs: HashSet<Vec<String>> = HashSet::new();

    for e in entries
        .iter()
        .filter(|e| name_matches(e.parts.last().unwrap(), "SKILL.md"))
    {
        if skipped(&e.parts) {
            continue;
        }
        let text = read_text(&e.path);
        let (fields, _) = parse_frontmatter(&text);
        let Some(Field::Str(desc)) = fields.get("description") else {
            continue;
        };
        if desc.is_empty() {
            continue;
        }
        // pathlib appends the literal pattern spelling for non-wildcard segments, so on Windows
        // a `skill.md` matched case-insensitively is reported as `SKILL.md`.
        let parent = &e.parts[..e.parts.len() - 1];
        let mut spelled = parent.to_vec();
        spelled.push("SKILL.md".to_string());
        let rel = rel(&spelled);
        skill_dirs.insert(sort_key(parent));
        let name = match fields.get("name") {
            Some(f) => field_display(f),
            None => parent.last().cloned().unwrap_or_default(),
        };
        corpus
            .docs
            .push((rel.clone(), format!("{} {}", name, desc)));
        let mut qs = phrases(fields.get("triggers"));
        qs.extend(phrases(fields.get("auto-invoke")));
        for q in qs {
            corpus.cases.push(Case {
                query: q,
                expect_path_contains: rel.clone(),
                intent: "skill-trigger".into(),
            });
        }
    }

    for e in entries
        .iter()
        .filter(|e| ends_with_md(e.parts.last().unwrap()))
    {
        let name = e.parts.last().unwrap();
        let parent = &e.parts[..e.parts.len() - 1];
        if name == "SKILL.md" || skill_dirs.contains(&sort_key(parent)) || skipped(&e.parts) {
            continue;
        }
        let text = read_text(&e.path);
        let (fields, body) = parse_frontmatter(&text);
        let Some(Field::Str(desc)) = fields.get("description") else {
            continue;
        };
        if desc.is_empty() || tokenize(body).len() < 20 {
            continue;
        }
        let rel = rel(&e.parts);
        corpus.docs.push((rel.clone(), body.to_string()));
        corpus.cases.push(Case {
            query: desc.clone(),
            expect_path_contains: rel,
            intent: "note".into(),
        });
    }
    corpus
}

// ----------------------------------------------------------------------- BM25

#[derive(Clone, Debug, PartialEq)]
pub struct Hit {
    pub path: String,
    pub score: f64,
}

/// Plain BM25 over an in-memory corpus. Same constants and arithmetic order as the Python class.
pub struct Bm25 {
    k1: f64,
    b: f64,
    paths: Vec<String>,
    tf: Vec<HashMap<String, usize>>,
    len: Vec<usize>,
    avg: f64,
    idf: HashMap<String, f64>,
}

impl Bm25 {
    pub fn new(docs: &[(String, String)]) -> Self {
        Self::with_params(docs, 1.2, 0.75)
    }

    pub fn with_params(docs: &[(String, String)], k1: f64, b: f64) -> Self {
        let paths: Vec<String> = docs.iter().map(|(p, _)| p.clone()).collect();
        let tf: Vec<HashMap<String, usize>> = docs
            .iter()
            .map(|(_, text)| {
                let mut c = HashMap::new();
                for t in tokenize(text) {
                    *c.entry(t).or_insert(0) += 1;
                }
                c
            })
            .collect();
        let len: Vec<usize> = tf.iter().map(|c| c.values().sum()).collect();
        let avg = if len.is_empty() {
            1.0
        } else {
            (len.iter().sum::<usize>() as f64) / (len.len() as f64)
        };
        let mut df: HashMap<&str, usize> = HashMap::new();
        for c in &tf {
            for t in c.keys() {
                *df.entry(t.as_str()).or_insert(0) += 1;
            }
        }
        let n = paths.len();
        let idf = df
            .into_iter()
            .map(|(t, d)| {
                (
                    t.to_string(),
                    (1.0 + (((n - d) as f64) + 0.5) / ((d as f64) + 0.5)).ln(),
                )
            })
            .collect();
        Bm25 {
            k1,
            b,
            paths,
            tf,
            len,
            avg,
            idf,
        }
    }

    pub fn search(&self, query: &str, top: usize) -> Vec<Hit> {
        let q = tokenize(query);
        let mut scored: Vec<Hit> = Vec::new();
        for (i, path) in self.paths.iter().enumerate() {
            let mut s = 0.0f64;
            for t in &q {
                let f = match self.tf[i].get(t) {
                    Some(&f) if f > 0 => f as f64,
                    _ => continue,
                };
                let norm = self.k1 * ((1.0 - self.b) + (self.b * (self.len[i] as f64)) / self.avg);
                s += ((self.idf[t] * f) * (self.k1 + 1.0)) / (f + norm);
            }
            if s > 0.0 {
                scored.push(Hit {
                    path: path.clone(),
                    score: s,
                });
            }
        }
        scored.sort_by(|a, b| {
            b.score
                .partial_cmp(&a.score)
                .unwrap()
                .then_with(|| a.path.cmp(&b.path))
        });
        scored.truncate(top);
        for h in &mut scored {
            h.score = py_round(h.score, 4);
        }
        scored
    }
}

// -------------------------------------------------------------------- metrics

#[derive(Clone, Debug, PartialEq, Serialize)]
pub struct PerCase {
    pub query: String,
    pub expect: String,
    pub scope: String,
    pub intent: String,
    pub hit_rank: Option<usize>,
    pub top_hit: Option<String>,
}

#[derive(Clone, Debug, PartialEq, Serialize)]
pub struct Metrics {
    pub n: usize,
    pub mrr: f64,
    #[serde(rename = "hit@1")]
    pub hit1: f64,
    #[serde(rename = "hit@3")]
    pub hit3: f64,
    #[serde(rename = "hit@5")]
    pub hit5: f64,
}

#[derive(Clone, Debug, PartialEq, Serialize)]
pub struct Shadowed {
    pub query: String,
    pub expect: String,
    pub rank: Option<usize>,
    pub shadowed_by: Option<String>,
}

/// The `context.<label>.json` document, in the Python key order.
#[derive(Clone, Debug, PartialEq, Serialize)]
pub struct RunResult {
    #[serde(flatten)]
    pub agg: Metrics,
    pub by_scope: BTreeMap<String, Metrics>,
    pub by_intent: BTreeMap<String, Metrics>,
    pub per_case: Vec<PerCase>,
    pub docs: usize,
    pub shadowed: Vec<Shadowed>,
}

fn metrics(cases: &[&PerCase]) -> Metrics {
    let n = cases.len().max(1) as f64;
    let hits_at = |k: usize| {
        (cases
            .iter()
            .filter(|c| c.hit_rank.is_some_and(|r| r <= k))
            .count() as f64)
            / n
    };
    let mrr = py_fsum(
        cases
            .iter()
            .map(|c| c.hit_rank.map_or(0.0, |r| 1.0 / (r as f64))),
    ) / n;
    Metrics {
        n: cases.len(),
        mrr: py_round(mrr, 3),
        hit1: py_round(hits_at(1), 3),
        hit3: py_round(hits_at(3), 3),
        hit5: py_round(hits_at(5), 3),
    }
}

/// `hitgate.run.run` for mined cases (no scope): rank by position, substring match on the path.
pub fn run<R>(cases: &[Case], top: usize, retriever: R) -> RunResult
where
    R: Fn(&str, usize) -> Vec<Hit>,
{
    let mut per_case = Vec::with_capacity(cases.len());
    for case in cases {
        let results = retriever(&case.query, top);
        let hit_rank = results
            .iter()
            .position(|r| r.path.contains(&case.expect_path_contains))
            .map(|i| i + 1);
        let top_hit = results.first().map(|r| format!("{}:?", r.path));
        per_case.push(PerCase {
            query: case.query.clone(),
            expect: case.expect_path_contains.clone(),
            scope: "none".to_string(),
            intent: case.intent.clone(),
            hit_rank,
            top_hit,
        });
    }
    let mut by_scope: BTreeMap<String, Vec<&PerCase>> = BTreeMap::new();
    let mut by_intent: BTreeMap<String, Vec<&PerCase>> = BTreeMap::new();
    for c in &per_case {
        by_scope.entry(c.scope.clone()).or_default().push(c);
        by_intent.entry(c.intent.clone()).or_default().push(c);
    }
    let all: Vec<&PerCase> = per_case.iter().collect();
    RunResult {
        agg: metrics(&all),
        by_scope: by_scope
            .iter()
            .map(|(k, v)| (k.clone(), metrics(v)))
            .collect(),
        by_intent: by_intent
            .iter()
            .map(|(k, v)| (k.clone(), metrics(v)))
            .collect(),
        per_case,
        docs: 0,
        shadowed: Vec::new(),
    }
}

/// Cases whose own document did not rank first, with the document that did.
pub fn shadowed(result: &RunResult) -> Vec<Shadowed> {
    result
        .per_case
        .iter()
        .filter(|c| c.hit_rank != Some(1))
        .map(|c| {
            let top = c.top_hit.as_deref().unwrap_or("");
            let top = top.rsplit_once(':').map(|(a, _)| a).unwrap_or(top);
            Shadowed {
                query: c.query.clone(),
                expect: c.expect.clone(),
                rank: c.hit_rank,
                shadowed_by: if top.is_empty() {
                    None
                } else {
                    Some(top.to_string())
                },
            }
        })
        .collect()
}

#[derive(Clone, Debug, PartialEq, Serialize)]
pub struct Lost {
    pub query: String,
    pub expect: String,
    pub was_rank: Value,
    pub now: Option<String>,
}

/// Cases that hit in the baseline and miss now, keyed by (query, expect).
pub fn lost(result: &RunResult, base: &Value) -> Vec<Lost> {
    let mut was: HashMap<(String, String), Value> = HashMap::new();
    if let Some(cases) = base.get("per_case").and_then(Value::as_array) {
        for c in cases {
            let (Some(q), Some(e)) = (
                c.get("query").and_then(Value::as_str),
                c.get("expect").and_then(Value::as_str),
            ) else {
                continue;
            };
            was.insert(
                (q.to_string(), e.to_string()),
                c.get("hit_rank").cloned().unwrap_or(Value::Null),
            );
        }
    }
    result
        .per_case
        .iter()
        .filter_map(|c| {
            let before = was.get(&(c.query.clone(), c.expect.clone()))?;
            let truthy = before.as_f64().is_some_and(|x| x != 0.0);
            if truthy && c.hit_rank.is_none() {
                Some(Lost {
                    query: c.query.clone(),
                    expect: c.expect.clone(),
                    was_rank: before.clone(),
                    now: c.top_hit.clone(),
                })
            } else {
                None
            }
        })
        .collect()
}

// ----------------------------------------------------------------------- gate

#[derive(Clone, Debug, PartialEq, Serialize)]
pub struct Finding {
    pub metric: String,
    pub scope: String,
    pub delta: f64,
}

#[derive(Clone, Debug, PartialEq, Serialize)]
pub struct Deltas {
    pub mrr: f64,
    #[serde(rename = "hit@1")]
    pub hit1: f64,
    #[serde(rename = "hit@3")]
    pub hit3: f64,
    #[serde(rename = "hit@5")]
    pub hit5: f64,
}

/// The `context.<label>.verdict.json` document, in the Python key order.
#[derive(Clone, Debug, PartialEq, Serialize)]
pub struct Verdict {
    pub verdict: String,
    pub gated_metric: String,
    pub tolerance_pp: f64,
    pub regressions: Vec<Finding>,
    pub improvements: Vec<Finding>,
    pub deltas: Deltas,
    pub refreeze_recommended: bool,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub lost: Option<Vec<Lost>>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub reason: Option<String>,
}

const METRICS: [&str; 4] = ["mrr", "hit@1", "hit@3", "hit@5"];

fn agg_metric(m: &Metrics, name: &str) -> f64 {
    match name {
        "mrr" => m.mrr,
        "hit@1" => m.hit1,
        "hit@3" => m.hit3,
        _ => m.hit5,
    }
}

fn base_metric(base: &Value, name: &str) -> Result<f64, String> {
    base.get(name)
        .and_then(Value::as_f64)
        .ok_or_else(|| format!("'{}'", name))
}

/// Sorted (name, hit@5) pairs of a `by_scope` / `by_intent` group in the baseline.
fn base_groups(base: &Value, key: &str) -> Vec<(String, Option<f64>)> {
    let mut out: Vec<(String, Option<f64>)> = base
        .get(key)
        .and_then(Value::as_object)
        .map(|m| {
            m.iter()
                .map(|(k, v)| (k.clone(), v.get("hit@5").and_then(Value::as_f64)))
                .collect()
        })
        .unwrap_or_default();
    out.sort_by(|a, b| a.0.cmp(&b.0));
    out
}

/// `hitgate.compare.compare`. Errors name the missing baseline key (an unusable baseline).
pub fn compare(cur: &RunResult, base: &Value, tol_pp: f64) -> Result<Verdict, String> {
    let tol = tol_pp / 100.0;
    let mut regressions = Vec::new();
    let mut improvements = Vec::new();
    let mut deltas = [0.0f64; 4];
    for (i, m) in METRICS.iter().enumerate() {
        let delta = py_round(agg_metric(&cur.agg, m) - base_metric(base, m)?, 4);
        deltas[i] = delta;
        if delta < -tol {
            regressions.push(Finding {
                metric: m.to_string(),
                scope: "aggregate".into(),
                delta,
            });
        } else if delta > tol {
            improvements.push(Finding {
                metric: m.to_string(),
                scope: "aggregate".into(),
                delta,
            });
        }
    }
    for (key, cur_groups, prefix) in [
        ("by_scope", &cur.by_scope, "scope:"),
        ("by_intent", &cur.by_intent, "intent:"),
    ] {
        for (name, b5) in base_groups(base, key) {
            let (Some(b5), Some(c5)) = (b5, cur_groups.get(&name).map(|m| m.hit5)) else {
                continue;
            };
            let delta = py_round(c5 - b5, 4);
            let scope = format!("{}{}", prefix, name);
            if delta < -tol {
                regressions.push(Finding {
                    metric: "hit@5".into(),
                    scope,
                    delta,
                });
            } else if delta > tol {
                improvements.push(Finding {
                    metric: "hit@5".into(),
                    scope,
                    delta,
                });
            }
        }
    }
    let refreeze = improvements
        .iter()
        .any(|r| r.metric == "hit@5" && r.scope == "aggregate");
    let verdict = if !regressions.is_empty() {
        "regression"
    } else if refreeze {
        "improvement"
    } else {
        "pass"
    };
    Ok(Verdict {
        verdict: verdict.to_string(),
        gated_metric: "hit@5".to_string(),
        tolerance_pp: tol_pp,
        regressions,
        improvements,
        deltas: Deltas {
            mrr: deltas[0],
            hit1: deltas[1],
            hit3: deltas[2],
            hit5: deltas[3],
        },
        refreeze_recommended: refreeze,
        lost: None,
        reason: None,
    })
}

fn arrow(delta: f64) -> &'static str {
    if delta > 0.0 {
        "↑"
    } else if delta < 0.0 {
        "↓"
    } else {
        "·"
    }
}

/// `hitgate.compare.print_table`, rendered to a string.
pub fn render_table(cur: &RunResult, base: &Value, v: &Verdict, tol_pp: f64) -> String {
    let mut out = String::new();
    let _ = writeln!(
        out,
        "\nDelta vs baseline (tolerance ±{}pp):",
        py_float(tol_pp)
    );
    for m in METRICS {
        let b = base.get(m).and_then(Value::as_f64).unwrap_or(0.0);
        let c = agg_metric(&cur.agg, m);
        let delta = c - b;
        let flag = if v
            .regressions
            .iter()
            .any(|r| r.metric == m && r.scope == "aggregate")
        {
            "  ⚠ REGRESSION"
        } else {
            ""
        };
        let _ = writeln!(
            out,
            "  {:<8} {:.3} → {:.3}  {}{:+.3}{}",
            m,
            b,
            c,
            arrow(delta),
            delta.abs(),
            flag
        );
    }
    for (key, cur_groups, prefix, title) in [
        ("by_scope", &cur.by_scope, "scope:", "Per-scope"),
        ("by_intent", &cur.by_intent, "intent:", "Per-intent"),
    ] {
        let groups = base_groups(base, key);
        if groups.is_empty() || cur_groups.is_empty() {
            continue;
        }
        let _ = writeln!(
            out,
            "\n{} Hit@5 (tolerance ±{}pp):",
            title,
            py_float(tol_pp)
        );
        for (name, b5) in groups {
            let (Some(b5), Some(cm)) = (b5, cur_groups.get(&name)) else {
                continue;
            };
            let delta = cm.hit5 - b5;
            let scope = format!("{}{}", prefix, name);
            let flag = if v.regressions.iter().any(|r| r.scope == scope) {
                "  ⚠ REGRESSION"
            } else {
                ""
            };
            let _ = writeln!(
                out,
                "  {:<16} n={}  {:.3} → {:.3}  {}{:+.3}{}",
                name,
                cm.n,
                b5,
                cm.hit5,
                arrow(delta),
                delta.abs(),
                flag
            );
        }
    }
    if !v.regressions.is_empty() {
        let names: Vec<&str> = v
            .regressions
            .iter()
            .map(|r| {
                if r.scope == "aggregate" {
                    r.metric.as_str()
                } else {
                    r.scope.as_str()
                }
            })
            .collect();
        let _ = writeln!(
            out,
            "\nRegressed: {}. Investigate before shipping retrieval changes.",
            names.join(", ")
        );
    } else if v.refreeze_recommended {
        let _ = writeln!(
            out,
            "\n✓ within tolerance. Hit@5 improved. Consider re-freezing the baseline."
        );
    } else {
        let _ = writeln!(out, "\n✓ within tolerance.");
    }
    out
}

// ------------------------------------------------------------------------ CLI

pub const USAGE: &str = "usage: hitgate-context [-h] [--label LABEL] [--baseline BASELINE] [--tol TOL] [--top TOP] [--out OUT] [--show SHOW] root

Context gate: label-free regression gate for agent context (skills, memory notes).

positional arguments:
  root                 context root (e.g. ~/.claude or a repo's .claude/)

options:
  -h, --help           show this help message and exit
  --label LABEL        result label (default: context)
  --baseline BASELINE  previous context.<label>.json to gate against
  --tol TOL            tolerance in percentage points (default: 5.0)
  --top TOP            results per query (default: 5)
  --out OUT            directory for context.<label>.json (default: cwd)
  --show SHOW          shadowed cases to print (default: 15)

exit codes: 0 pass, 1 regression, 2 bad root, no cases, unusable baseline or bad arguments";

#[derive(Debug, Clone, PartialEq)]
pub struct Args {
    pub root: PathBuf,
    pub label: String,
    pub baseline: Option<PathBuf>,
    pub tol: f64,
    pub top: usize,
    pub out: PathBuf,
    pub show: usize,
}

pub enum Parsed {
    Run(Args),
    Help,
}

pub fn parse_args(argv: &[String]) -> Result<Parsed, String> {
    let mut root: Option<PathBuf> = None;
    let mut label = "context".to_string();
    let mut baseline = None;
    let mut tol = 5.0f64;
    let mut top = 5usize;
    let mut out: Option<PathBuf> = None;
    let mut show = 15usize;
    let mut i = 0;
    while i < argv.len() {
        let arg = &argv[i];
        if arg == "-h" || arg == "--help" {
            return Ok(Parsed::Help);
        }
        let (name, inline) = match arg.split_once('=') {
            Some((n, v)) if n.starts_with("--") => (n.to_string(), Some(v.to_string())),
            _ => (arg.clone(), None),
        };
        if name.starts_with("--") {
            let value = match inline {
                Some(v) => v,
                None => {
                    i += 1;
                    argv.get(i)
                        .cloned()
                        .ok_or_else(|| format!("argument {}: expected one argument", name))?
                }
            };
            match name.as_str() {
                "--label" => label = value,
                "--baseline" => baseline = Some(expanduser(&value)),
                "--tol" => tol = value.parse().map_err(|_| format!("argument --tol: invalid float value: {}", py_repr(&value)))?,
                "--top" => top = value.parse().map_err(|_| format!("argument --top: invalid int value: {}", py_repr(&value)))?,
                "--out" => out = Some(expanduser(&value)),
                "--show" => show = value.parse().map_err(|_| format!("argument --show: invalid int value: {}", py_repr(&value)))?,
                "--retriever" => return Err("argument --retriever: not supported by the Rust binary (Python only); the stdlib BM25 is always used".into()),
                _ => return Err(format!("unrecognized arguments: {}", name)),
            }
        } else if root.is_none() {
            root = Some(expanduser(arg));
        } else {
            return Err(format!("unrecognized arguments: {}", arg));
        }
        i += 1;
    }
    let root = root.ok_or_else(|| "the following arguments are required: root".to_string())?;
    let out = out.unwrap_or_else(|| std::env::current_dir().unwrap_or_else(|_| PathBuf::from(".")));
    Ok(Parsed::Run(Args {
        root,
        label,
        baseline,
        tol,
        top,
        out,
        show,
    }))
}

/// Entry point shared by `main` and the integration tests. Returns the exit code.
pub fn cli(argv: &[String]) -> i32 {
    let a = match parse_args(argv) {
        Ok(Parsed::Run(a)) => a,
        Ok(Parsed::Help) => {
            println!("{}", USAGE);
            return 0;
        }
        Err(e) => {
            eprintln!(
                "{}\nhitgate-context: error: {}",
                USAGE.lines().next().unwrap_or(""),
                e
            );
            return 2;
        }
    };
    if !a.root.is_dir() {
        eprintln!("hitgate-context: not a directory: {}", a.root.display());
        return 2;
    }
    let corpus = mine(&a.root);
    if corpus.cases.is_empty() {
        eprintln!(
            "hitgate-context: no skills with triggers or notes with a description under {}",
            a.root.display()
        );
        return 2;
    }
    let retriever = Bm25::new(&corpus.docs);
    let mut result = run(&corpus.cases, a.top, |q, top| retriever.search(q, top));
    result.docs = corpus.docs.len();
    result.shadowed = shadowed(&result);

    println!(
        "[context:{}]  docs={}  n={}  MRR={}  hit@1={}  hit@3={}  hit@5={}",
        a.label,
        result.docs,
        result.agg.n,
        py_float(result.agg.mrr),
        py_float(result.agg.hit1),
        py_float(result.agg.hit3),
        py_float(result.agg.hit5)
    );
    for (intent, m) in &result.by_intent {
        println!(
            "  {:<14} n={:<4} hit@1={}  hit@5={}",
            intent,
            m.n,
            py_float(m.hit1),
            py_float(m.hit5)
        );
    }
    if !result.shadowed.is_empty() {
        let shown = a.show.min(result.shadowed.len());
        println!(
            "\nShadowed ({} of {}; showing {}):",
            result.shadowed.len(),
            result.agg.n,
            shown
        );
        for s in &result.shadowed[..shown] {
            let rank = s.rank.map_or(format!(">{}", a.top), |r| r.to_string());
            println!(
                "  {:<48} -> {}  rank={}  first={}",
                py_repr(&s.query),
                s.expect,
                rank,
                s.shadowed_by.as_deref().unwrap_or("None")
            );
        }
    }
    println!("\n{}", CAVEAT);

    if let Err(e) = fs::create_dir_all(&a.out) {
        eprintln!("hitgate-context: cannot create {}: {}", a.out.display(), e);
        return 2;
    }
    let out_path = a.out.join(format!("context.{}.json", a.label));
    let json = serde_json::to_string_pretty(&result).expect("result serializes");
    if let Err(e) = fs::write(&out_path, json) {
        eprintln!(
            "hitgate-context: cannot write {}: {}",
            out_path.display(),
            e
        );
        return 2;
    }
    println!("wrote {}", out_path.display());

    let Some(baseline) = &a.baseline else {
        return 0;
    };
    let base: Value = match fs::read(baseline)
        .map_err(|e| e.to_string())
        .and_then(|b| serde_json::from_slice(&b).map_err(|e| e.to_string()))
    {
        Ok(v) => v,
        Err(e) => {
            eprintln!(
                "hitgate-context: unusable baseline {}: {}",
                baseline.display(),
                e
            );
            return 2;
        }
    };
    let mut v = match compare(&result, &base, a.tol) {
        Ok(v) => v,
        Err(e) => {
            eprintln!(
                "hitgate-context: unusable baseline {}: {}",
                baseline.display(),
                e
            );
            return 2;
        }
    };
    print!("{}", render_table(&result, &base, &v, a.tol));
    let base_n = base.get("n").cloned().unwrap_or(Value::Null);
    if base_n.as_u64() != Some(result.agg.n as u64) {
        println!(
            "note: case set changed, baseline n={} current n={}",
            base_n, result.agg.n
        );
    }
    let lost_cases = lost(&result, &base);
    if !lost_cases.is_empty() {
        println!(
            "\nNewly unreachable ({}): cases that hit in the baseline and miss now",
            lost_cases.len()
        );
        for c in lost_cases.iter().take(a.show) {
            println!(
                "  {:<48} -> {}  was rank {}  first={}",
                py_repr(&c.query),
                c.expect,
                c.was_rank,
                c.now.as_deref().unwrap_or("None")
            );
        }
        if v.verdict != "regression" {
            v.verdict = "regression".to_string();
            v.reason = Some("newly unreachable cases".to_string());
        }
    }
    v.lost = Some(lost_cases);
    let verdict_path = a.out.join(format!("context.{}.verdict.json", a.label));
    let json = serde_json::to_string_pretty(&v).expect("verdict serializes");
    if let Err(e) = fs::write(&verdict_path, json) {
        eprintln!(
            "hitgate-context: cannot write {}: {}",
            verdict_path.display(),
            e
        );
        return 2;
    }
    if v.verdict == "regression" {
        1
    } else {
        0
    }
}
