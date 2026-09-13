# five-whys

A Claude Code plugin that runs an **exhaustive** Five Whys. It asks "why?" five
levels deep, and every answer is five reasons. Each of those reasons is asked
"why?" again, and so on:

```
5 + 25 + 125 + 625 + 3,125 = 3,905 reasons
```

The whole tree goes into one JSON file that you can read into context in full.
The plugin only generates the tree. Analysis is up to you.

## Install

```
/plugin marketplace add JoshuaRamirez/claude-code-plugins
/plugin install five-whys@RedJay
```

## Use

```
/five-whys Our deploys keep failing on Friday afternoons
```

The skill creates a run under `.five-whys/<timestamp>-<slug>/` in the current
directory, then fans the work out to sub-agents:

| Round | Agents | Produces                                         |
|-------|--------|--------------------------------------------------|
| 1     | 1      | levels 1-2 (30 reasons)                          |
| 2     | 25     | levels 3-5 under each level-2 reason (155 each)  |

Every fragment is shape-checked (exactly 5 reasons per node, exactly 5 levels).
Invalid or missing fragments are re-dispatched on their own, so an interrupted
run resumes with `plan`.

## Output

`.five-whys/<run>/five-whys.json`, with one reason per line:

```json
{"schema":"five-whys/1","problem":"...","branching":5,"depth":5,"total_reasons":3905,"reading":"...","whys":[
 {"id":"1","depth":1,"reason":"...","whys":[
  {"id":"1.1","depth":2,"reason":"...","whys":[
   {"id":"1.1.1","depth":3,"reason":"...","whys":[
    {"id":"1.1.1.1","depth":4,"reason":"...","whys":[
     {"id":"1.1.1.1.1","depth":5,"reason":"..."},
```

- Top-level `whys` answer "Why does the problem occur?"
- A node's `whys` answer "Why <that node's reason>?"
- `id` is the dotted path from the top. `2.4.1` is the 1st reason for `2.4`.

The file is about 150k tokens. To load it, ask Claude to read the
`five-whys.json` whole. The skill pages through it in 400-line windows.

## Script

`scripts/fivewhys.py` (Python 3.9+, stdlib only) does all the deterministic
work:

| Command                           | Does                                                   |
|-----------------------------------|--------------------------------------------------------|
| `init` (problem on stdin)         | create a run directory                                 |
| `plan <run>`                      | list missing or invalid fragments, with agent prompts  |
| `check <fragment> --depth N`      | validate one fragment                                  |
| `assemble <run>`                  | merge all fragments into `five-whys.json`              |

## License

MIT
