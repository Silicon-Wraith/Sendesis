# Security Reviewer suite

Target: about 100 labeled cases, roughly 30 percent clean. Start with a 30-case pilot.

## Case layout

```
suites/security-reviewer/cases/<case-id>/
  case.yaml       # labels and provenance
  diff.patch      # unified diff under review
  context/        # optional: full files the diff touches, same relative paths
```

`case.yaml`:

```yaml
id: planted-0001
source: planted          # cvefixes | owasp | planted | clean
clean: false             # true for a change with no vulnerability
labels:                  # empty when clean is true
  - cwe: CWE-89
    file: app/db.py
    line_start: 42
    line_end: 44
notes: string-built SQL in lookup_user
```

## Scoring rules (implement in the engine, not by an LLM)

- A finding matches a label when the file is the same and the line ranges overlap, allowing 3 lines of slack either side.
- Recall = matched labels / all labels, over non-clean cases.
- False positives per clean case = findings on clean cases / number of clean cases.
- Category agreement (finding CWE equals label CWE) is reported separately and is not part of the pass bar.
- Schema validity = outputs that validate / outputs returned.
- Report Wilson 95 percent intervals per metric and a paired bootstrap for differences between arms.

## Sources

- CVEfixes: pre-fix diffs of real CVE fixes. Use the CVE's changed lines as labels.
- OWASP Benchmark: ships with true and false positive labels.
- Planted: bugs you add fresh to your own code, so no model has trained on them.
- Clean: ordinary changes with no security impact.

Keep case contents out of any public repo if they come from private code.
