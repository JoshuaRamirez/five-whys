# Reason quality rubric

Used with `quality.py` to score a sample of reasons from a five-whys tree. It
is development measurement only: scores are never written into a run or shown
by one (see the README's design decisions). The criteria restate the rules in
`agents/why-expander.md`, so a score measures how well agents followed them.

Each packet item gives the problem, the chain of reasons above the item (from
the top), the item's reason and its siblings: the other reasons answering the
same why. Score every item on all three criteria. Judge the reason as a
hypothesis; don't check whether it is true.

## Causal

Does the reason explain why the last reason in the chain happens? For level 1,
the question is why the problem occurs. For five-ws trees that ask what, when,
where or how (the packet item's `question`), score whether the answer answers
that question about the item above it: a fact or component, a time or
condition, a place, or a mechanism. The key stays `causal`.

- **0:** Not a cause. It restates the parent, describes a symptom or effect,
  proposes a fix, or gives an opinion.
- **1:** Related to the parent, but the link is loose. It is a background
  condition, a correlation, or a cause of something next to the parent.
- **2:** A direct cause. If it were not so, the parent would plausibly not
  happen, or would happen differently.

## Specific

Does the reason name concrete things from the problem, context or chain?

- **0:** It would fit any project unchanged, for example "the team lacked
  time" or "communication was poor".
- **1:** Tied to this domain, but it names no concrete component, decision,
  actor, event or constraint from the chain.
- **2:** It names something concrete from the problem, context or chain, such
  as a file, a step, a setting, a date, a decision or a person's role.

## Distinct

Does it differ in mechanism from its siblings and from every reason in its
chain?

- **0:** It restates a sibling or an ancestor in other words, or loops back to
  a cause named higher in the chain.
- **1:** A different wording, but the same mechanism as a sibling, only
  narrower or broader.
- **2:** A separate mechanism from every sibling and every ancestor.

## Score file

```json
{"scorer": "<who scored; model or person, and what they could see>",
 "independent": true,
 "scores": [{"n": 1, "causal": 2, "specific": 1, "distinct": 2, "note": "optional"}]}
```

`independent` is true when the scorer did not write the code, prompts or tree
being measured and has not seen the other scorer's file. Check the file with
`quality.py score <packet> <file>`.
