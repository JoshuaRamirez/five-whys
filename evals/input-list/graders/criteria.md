---
type: llm
weight: 1
---

The run succeeds when all of the following hold:

1. The five-whys skill parsed the invocation with the script's `parse` command, which returned three inputs with their list numbers removed, and passed those three inputs to `init` one per line with depth 1.
2. The run dispatched one expander agent, covering all three inputs, and no branch agents.
3. `assemble` completed and reported `inputs` equal to 3, `present_reasons` equal to `total_reasons` equal to 15, with `complete` true.
4. In `five-whys.json`, `inputs` holds the three problems in order, each with exactly 5 reasons whose ids start with that input's number (1.1 to 1.5, 2.1 to 2.5, 3.1 to 3.5).
5. The final reply gives the path to `five-whys.json`, the input count, the reason count, the approximate token size and the hygiene counts, in a few lines, and does not rank, summarize, interpret or pick root causes.
6. No fragment was hand-written or hand-edited by the orchestrating session; reasons came from the expander agent.
