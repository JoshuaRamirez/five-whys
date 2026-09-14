---
type: llm
weight: 1
---

The run succeeds when all of the following hold:

1. The five-whys skill parsed the invocation with the script's `parse` command, created a run directory under `.five-whys/` with the smoke preset, and dispatched expander agents (one root agent, then three branch agents).
2. `assemble` completed and reported `present_reasons` equal to `total_reasons` equal to 39, with `complete` true.
3. The problem statement is one short sentence with no system details, so `five-whys.json` records at least one stated assumption in its `assumptions` header.
4. The final reply gives the path to `five-whys.json`, the reason count, the approximate token size and the hygiene counts, in a few lines, and does not rank, summarize, interpret or pick root causes.
5. No fragment was hand-written or hand-edited by the orchestrating session; reasons came from the expander agents.
