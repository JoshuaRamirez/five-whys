---
type: llm
weight: 1
---

The run succeeds when all of the following hold:

1. The five-whys skill parsed the invocation with the script's `parse` command and ran the smoke preset: a run directory under `.five-whys/` was created and expander agents were dispatched (one root agent, then three branch agents).
2. `assemble` completed and reported `present_reasons` equal to `total_reasons` equal to 39, with `complete` true.
3. The final reply gives the path to `five-whys.json`, the reason count, the approximate token size and the hygiene counts, in a few lines.
4. The final reply does not rank, summarize, interpret or pick root causes from the tree; it leaves analysis to the user.
5. No fragment was hand-written or hand-edited by the orchestrating session; reasons came from the expander agents.
