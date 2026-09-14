"""Mechanical similarity flags for Five Whys trees. Standard library only.

Flags annotate reasons; nothing is removed, rewritten, ranked or summarized.
Similarity is word overlap (Jaccard) on stemmed words minus stopwords, so it
catches copies, close rewordings and word variants, and misses paraphrases that
use different words.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict

SIMILARITY = 0.6  # near-duplicates, restatements and check warnings
CROSS_BRANCH_SIMILARITY = 0.45  # leads between reasons under different level-1 reasons
LONG_REASON_WORDS = 25
MIN_SHARED_TOKENS = 2  # candidate pairs share at least this many indexed tokens
COMMON_TOKEN_SHARE = 0.05  # tokens in more than this share of reasons are not indexed

STOPWORDS = frozenset(
    "a an and are as at be because been but by can for from has have how in into is it its "
    "not no of on or so than that the their them then there they this to was were what when "
    "which while who why will with without".split()
)


def stem(word: str) -> str:
    """Strip common inflections so estimate, estimates and estimated compare equal."""
    if len(word) <= 4 or not word.isalpha():
        return word
    if word.endswith("ies"):
        word = word[:-3] + "y"
    elif word.endswith(("sses", "ches", "shes", "xes")):
        word = word[:-2]
    elif word.endswith("s") and not word.endswith(("ss", "us", "is")):
        word = word[:-1]
    elif word.endswith("ing") and len(word) > 6:
        word = word[:-3]
    elif word.endswith("ed") and len(word) > 5:
        word = word[:-2]
    return word[:-1] if word.endswith("e") and len(word) > 4 else word


def tokens(text: str) -> set[str]:
    words = re.findall(r"[a-z0-9]+(?:['-][a-z0-9]+)*", text.lower())
    return {stem(w) for w in words if w not in STOPWORDS}


def jaccard(a: set, b: set) -> float:
    return len(a & b) / len(a | b) if a and b else 0.0


def similarity(a: str, b: str) -> float:
    return jaccard(tokens(a), tokens(b))


def branch_of(node_id: str, level: int = 1) -> str:
    return ".".join(node_id.split(".")[:level])


def hygiene(flat: list[dict], report=None, branch_level: int = 1) -> dict:
    """Flag every reason in `flat` ({id, depth, parent, reason}).

    With `report`, only flags touching those ids are returned; the other entries
    still serve as ancestors and comparison text (check uses this for branch
    fragments, passing the root's reasons as context).

    `branch_level` is how many id segments name a level-1 reason: 1 for trees
    assembled before 0.3.0, 2 when ids start with the input number. Pairs from
    different inputs are then leads too, marked across_inputs.
    """
    by_id = {r["id"]: r for r in flat}
    toks = {r["id"]: tokens(r["reason"]) for r in flat}
    text = {r["id"]: r["reason"] for r in flat}
    wanted = (lambda *ids: any(i in report for i in ids)) if report is not None else (lambda *ids: True)

    groups = defaultdict(list)
    for r in flat:
        groups[" ".join(re.findall(r"[a-z0-9]+", r["reason"].lower()))].append(r["id"])
    exact = [{"ids": ids, "text": text[ids[0]]} for ids in groups.values() if len(ids) > 1 and wanted(*ids)]
    exact_pairs = {frozenset((a, b)) for ids in groups.values() for a in ids for b in ids if a != b}

    df = Counter(t for s in toks.values() for t in s)
    common = max(5, int(len(flat) * COMMON_TOKEN_SHARE))
    index = defaultdict(list)
    for r in flat:
        for t in toks[r["id"]]:
            if df[t] <= common:
                index[t].append(r["id"])
    shared = Counter()
    for ids in index.values():
        for i in range(len(ids)):
            for j in range(i + 1, len(ids)):
                shared[(ids[i], ids[j])] += 1

    near, cross = [], []
    for (a, b), count in shared.items():
        if count < MIN_SHARED_TOKENS or frozenset((a, b)) in exact_pairs or not wanted(a, b):
            continue
        ta, tb = toks[a], toks[b]
        parent = by_id[a]["parent"]
        if parent and parent == by_id[b]["parent"]:  # siblings share their parent's topic words
            ta, tb = ta - toks[parent], tb - toks[parent]
        score = jaccard(ta, tb)
        pair = {"a": a, "b": b, "similarity": round(score, 2), "texts": [text[a], text[b]]}
        if score >= SIMILARITY:
            near.append(pair)
        elif score >= CROSS_BRANCH_SIMILARITY and branch_of(a, branch_level) != branch_of(b, branch_level):
            if branch_level > 1:
                pair["across_inputs"] = branch_of(a) != branch_of(b)
            cross.append(pair)
    near.sort(key=lambda p: -p["similarity"])
    cross.sort(key=lambda p: -p["similarity"])

    restates_parent, restates_ancestor = [], []
    for r in flat:
        if not wanted(r["id"]):
            continue
        ancestor, k = r["parent"], 0
        while ancestor:
            score = jaccard(toks[r["id"]], toks[ancestor])
            if score >= SIMILARITY:
                flag = {"id": r["id"], "of": ancestor, "similarity": round(score, 2),
                        "texts": [text[r["id"]], text[ancestor]]}
                (restates_parent if k == 0 else restates_ancestor).append(flag)
                break
            ancestor, k = by_id[ancestor]["parent"], k + 1

    over_length = [{"id": r["id"], "words": len(r["reason"].split())}
                   for r in flat if wanted(r["id"]) and len(r["reason"].split()) > LONG_REASON_WORDS]
    flags = {"exact_duplicates": exact, "near_duplicates": near, "restates_parent": restates_parent,
             "restates_ancestor": restates_ancestor, "cross_branch": cross, "over_length": over_length}
    return {
        "note": "Mechanical flags only. Nothing was removed, rewritten, ranked or summarized; "
                "whether a flag matters is the reader's call.",
        "method": "Word overlap (Jaccard) on lowercased, stemmed words minus stopwords; sibling pairs ignore "
                  "their parent's words. Candidate pairs must share min_shared_tokens words that each appear "
                  "in at most common_token_share of reasons. cross_branch lists pairs under different level-1 "
                  "reasons, including pairs from different inputs (across_inputs), scoring between cross_branch_similarity and similarity, as leads for convergence. "
                  "Catches copies, close rewordings and word variants; misses paraphrases in different words.",
        "thresholds": {"similarity": SIMILARITY, "cross_branch_similarity": CROSS_BRANCH_SIMILARITY,
                       "long_reason_words": LONG_REASON_WORDS, "min_shared_tokens": MIN_SHARED_TOKENS,
                       "common_token_share": COMMON_TOKEN_SHARE},
        "counts": {name: len(items) for name, items in flags.items()},
        **flags,
    }
