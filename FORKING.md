# Forking protocol

A **fork** is a new `.mini` contract. The whole point of `.mini` is that it
adapts to the project: instead of bending a general-purpose format to your
records, you declare *your* records once and every tool follows.

## 1. Decide what a record is

A `.mini` record is one line of scalar fields, lists, marked lists and
one-level tuples. If your data is a list of things with the same shape —
items, cards, rows, events, criteria, cases, annotations — it fits. If a
record needs deep hierarchy, split it into two families related by an
identifier (the relational pattern: `card` records point to `a` items).

## 2. Start from the closest parent, or blank

```bash
mini new-fork quiz2 --from a --add "feedback:str" "level:enum{easy|hard}"
mini new-fork ticket --add "id:str" "title:str" "labels:list<str>" "priority:enum{low|high}"
```

With `--from`, the child's core is the parent's full field list (core +
extensions) and your new fields become extensions. Without it you define
the core yourself.

## 3. Edit `forks/<prefix>/contract.json`

* `prefix` — short, unique, `[A-Za-z][A-Za-z0-9_-]*`; it is the first token of
  every document of the family.
* `header.keys` — typed metadata (`n` is implicit and mandatory). Use a
  **count key** (`"count_key": "k"` on a list field, `k` declared in the header)
  whenever a list has a fixed length: it turns delimiter collisions into
  detectable errors.
* `core` — ordered required fields. Types: `str`, `int`, `float`, `bool`,
  `enum` (+`values`), `list` (+`item`, `min`, `max`), `mlist` (+`marker`:
  `exactly_one` | `at_least_one` | `at_most_one` | `any`, and `json`
  `{items, selected}` names), `tuple` (+`items`).
* `extensions` — optional trailing fields; parsers of older versions ignore them.
* `list_separator` — `,` by default; choose `;` for text-heavy lists if your
  content is full of commas (inherited forks must keep the parent's).

## 4. Add fixtures

`fixtures/valid.mini` and `fixtures/canonical.json` must round-trip in both
directions byte for byte (`dumps(canonical) == valid.mini`). Add
`escaping.mini` (+`escaping.json`) with every reserved character, and
negative cases `bad_count.mini`, `bad_arity.mini`, `bad_type.mini`
(`bad_marker.mini` when you use a marked list). `benchmark/make_forks.py`
shows how the shipped forks generate them.

## 5. Check the invariants

```bash
mini check-forks
```

| # | Invariant | Checked by |
|---|---|---|
| I1 | one line = one independently valid record | parser |
| I2 | header with prefix and `n`; parent's required header keys stay required | registry |
| I3 | inherited fields: same names, order, types, list separator | registry (`E21`) |
| I4 | new fields appended after the inherited ones, optional | registry |
| I5 | fixtures round-trip, negatives rejected | `check-forks` |

A change that reorders, retypes or removes an inherited field is a **new
prefix**, never a new version of the same prefix. Compatible growth
(appending fields, adding optional header keys) increments `version`.

## 6. Teach it to a model

```bash
mini prompt <prefix> --lang en   # or --lang es
```

The block is generated from the contract and is what you paste into the
system prompt. It states the header, the field order, escaping and quoting
rules, the marker rule and a one-record example. In our validation, models
that had never seen a fork produced 100 % parseable, 100 % round-trip
documents from this block alone (36/36 across three unseen forks and two
models), and models asked to *write a parser* from it passed all fixtures in
15 of 16 attempts.

## 7. Publish

Open a pull request adding `forks/<prefix>/` (contract, README, fixtures).
CI runs `mini check-forks`, the Python suite and the JS conformance test.
