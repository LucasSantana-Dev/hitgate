"""The code-aware tokenizer is what lets BM25 match natural-language queries against
identifiers. These assert the actual splitting behaviour, not trivial properties."""
from ragcore.retrieval import _tokenize


def test_camelcase_splits_into_subtokens():
    toks = _tokenize("getUserProfile")
    # whole identifier (lowercased) is kept AND split into pieces
    assert "getuserprofile" in toks
    assert {"get", "user", "profile"} <= set(toks)


def test_snake_case_splits_into_subtokens():
    toks = _tokenize("get_user_profile")
    assert {"get", "user", "profile"} <= set(toks)


def test_single_word_is_not_exploded():
    # a plain word yields just itself — no spurious sub-tokens
    assert _tokenize("fusion") == ["fusion"]


def test_natural_language_query_overlaps_identifier_tokens():
    # the whole point: "get user profile" and "getUserProfile" share sub-tokens
    nl = set(_tokenize("get user profile"))
    ident = set(_tokenize("getUserProfile"))
    assert {"get", "user", "profile"} <= (nl & ident)


def test_short_fragments_are_dropped():
    # sub-tokens shorter than 2 chars are not emitted (avoids noise like "a"/"x")
    toks = _tokenize("aXbY")
    assert "a" not in toks and "x" not in toks
