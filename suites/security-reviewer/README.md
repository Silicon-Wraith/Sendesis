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
  - category: CWE-89
    ranges:
      - {file: app/db.py, start: 42, end: 44}
notes: string-built SQL in lookup_user
```

## Scoring rules (implement in the engine, not by an LLM)

- A finding matches a label when the file is the same and the finding overlaps any of the label's ranges, allowing 3 lines of slack either side. A label counts once, however many findings hit it.
- Recall = matched labels / all labels, over non-clean cases.
- False positives per clean case = findings on clean cases / number of clean cases.
- Category agreement (finding CWE equals label CWE) is reported separately and is not part of the pass bar.
- Schema validity = outputs that validate / outputs returned.
- Schema validity passes on its point value (at least 0.98); recall and false positives per clean case pass on the conservative end of their interval.
- Report Wilson 95 percent intervals per metric and a paired bootstrap for differences between arms.

## Sources

- CVEfixes: pre-fix diffs of real CVE fixes. Use the CVE's changed lines as labels.
- OWASP Benchmark: ships with true and false positive labels.
- Planted: bugs you add fresh to your own code, so no model has trained on them.
- Clean: ordinary changes with no security impact.

Keep case contents out of any public repo if they come from private code.

## Licenses

Cases copied from upstream projects keep that project's license file at the case root (`LICENSE`, plus `NOTICE` where an Apache-2.0 project ships one), fetched at the commit recorded in `case.yaml` `provenance`. Only permissive licenses (MIT, BSD, ISC, Apache-2.0) are used, because this repo is public and MIT licensed. These files sit outside `context/`, so they never reach the model's prompt.
