---
type: llm
weight: 1
---

The run succeeds when all of the following hold:

1. The five-whys skill parsed the invocation with the script's `parse` command, which returned three inputs with their list numbers removed and the default question `why`, and passed those three inputs to `init` one per line with depth 1.
2. The run dispatched one expander agent, covering all three trees, and no branch agents.
3. `assemble` completed and reported `inputs` equal to 3, `present_answers` equal to `total_answers` equal to 15, with `complete` true.
4. In `five-whys.json`, `inputs` holds the three problems in order, each with one `why` tree of exactly 5 answers whose ids start with that input's number and the question (1.why.1 to 1.why.5, 2.why.1 to 2.why.5, 3.why.1 to 3.why.5).
5. The final reply gives the path to `five-whys.json`, the input count, the answer count, the approximate token size and the hygiene counts, in a few lines, and does not rank, summarize, interpret or pick answers.
6. No fragment was hand-written or hand-edited by the orchestrating session; answers came from the expander agent.
