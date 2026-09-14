---
type: llm
weight: 1
---

The run succeeds when all of the following hold:

1. The five-ws skill parsed the invocation with the script's `parse` command, which returned the questions `what` and `how` and one input, and passed `--ask what,how` and depth 1 to `init`.
2. The run dispatched one expander agent, covering both trees, and no branch agents.
3. `assemble` completed and reported `questions` of `what` and `how`, and `present_answers` equal to `total_answers` equal to 10, with `complete` true.
4. In `five-ws.json`, the input holds two trees, `1.what` and `1.how`, each with exactly 5 answers (1.what.1 to 1.what.5 and 1.how.1 to 1.how.5). The what-answers name facts or components of the backup problem, and the how-answers describe mechanisms or steps by which runs are skipped or go unnoticed.
5. The final reply gives the path to `five-ws.json`, the questions, the answer count, the approximate token size and the hygiene counts, in a few lines, and does not rank, summarize, interpret or pick answers.
6. No fragment was hand-written or hand-edited by the orchestrating session; answers came from the expander agent.
