---
type: llm
weight: 1
---

The run succeeds when all of the following hold:

1. The `/five-whys` shortcut ran the five-ws skill with `--ask why`: the script's `parse` command handled the invocation and returned the question `why`, and the smoke preset ran, creating a run directory under `.five-ws/` and dispatching expander agents (one root agent, then three branch agents).
2. `assemble` completed and reported `present_answers` equal to `total_answers` equal to 39, with `complete` true.
3. The final reply gives the path to `five-ws.json`, the answer count, the approximate token size and the hygiene counts, in a few lines.
4. The final reply does not rank, summarize, interpret or pick answers from the tree; it leaves analysis to the user.
5. No fragment was hand-written or hand-edited by the orchestrating session; answers came from the expander agents.
