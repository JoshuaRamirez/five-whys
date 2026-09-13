# Releasing five-whys

A version is not bumped until every item below holds. Record the evidence in the
commit message or release notes.

1. **Unit tests pass:** `python3 -m unittest discover tests`
2. **Manifest validates:** `claude plugin validate .`
3. **Smoke run works end to end** in a real session, either by hand or with the eval:
   `/five-whys --smoke --yes <any problem>` assembles 39/39 reasons, writes
   `index.md` and `hygiene.json`, and the reply leaves analysis to the user.
   `claude plugin eval . --allow-tools Bash Write Edit --runs 1`
4. **Changes to prompts or agent instructions** get one smoke run whose tree
   was actually read, not only shape-checked.
5. **Measured numbers in the README** (cost, duration, output size) are updated
   when a full run was done for the release, or left marked with their date.
6. **Version matches** in `.claude-plugin/plugin.json` and the RedJay
   marketplace entry.
