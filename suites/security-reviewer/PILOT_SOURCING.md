# Security reviewer pilot: sourcing notes

30 cases: 21 vulnerable (`cve-0001` to `cve-0021`, source `cvefixes`) and 9 clean (`clean-0001` to `clean-0009`, source `clean`). All code comes from MIT, BSD-3-Clause, ISC or Apache-2.0 projects. No GPL, LGPL, AGPL or MPL code. No model calls were made.

## Method

- Candidates came from the GitHub Advisory Database (`gh api /advisories?cwes=...`), reviewed advisories with a CVE and a fix-commit reference. They were filtered by repo license (GitHub SPDX id), by size (1 or 2 source files, 60 or fewer changed lines), and then read by hand.
- Vulnerable cases: `diff.patch` is `git diff FIX FIX^ -- <source files>`, so the diff goes from the fixed code to the vulnerable code. `context/` holds each touched file in full as of `FIX^` (the vulnerable version). Tests, changelogs, package manifests and docs that the fix commit also touched are left out of the diff and the context.
- Clean cases: `diff.patch` is `git diff C^ C -- <source files>`, and `context/` holds the files as of `C`.
- Labels point at lines in the new side of the diff, which is the `context/` file. Where the fix only added a guard, so the reversed diff is mostly deletions, the label sits on the code left unguarded (for example the `urlopen` call in cve-0017 or the `int(params['i'])` in cve-0021).
- Where the advisory lists several CWEs, the label uses the one that best matches the flaw: next-auth CWE-601 (also CWE-290), swift CWE-611 (also CWE-552), pyjwt CWE-918 (also CWE-200, CWE-345), geopandas CWE-89 (also CWE-202), torchgeo CWE-94 (also CWE-95), mdc CWE-79 (also CWE-184), kafka-python CWE-400 (also CWE-606).
- Largest context file is 511 lines (cve-0012). Largest diff by total changed lines is clean-0004 (+25/-16), then cve-0012 (+13/-23).
- License: the GitHub SPDX id was cross-checked against the LICENSE file in the tree at the pinned revision (`FIX^` for cvefixes, `C` for clean). All 30 match. fonttools also ships a `LICENSE.external` for bundled third-party code, which does not cover `Lib/fontTools/subset/svg.py`.

## Cases

| id | repo | commit | CVE | CWE | license | lines (+/-) | files | patch -R + cmp |
|---|---|---|---|---|---|---|---|---|
| cve-0001 | masci/banks | a215f6d77996 | CVE-2026-71492 | CWE-22 | MIT | +3/-28 | 1 | OK |
| cve-0002 | thumbor/thumbor | 3b986d13677b | CVE-2026-53502 | CWE-22 | MIT | +11/-24 | 1 | OK |
| cve-0003 | elwerene/libreoffice-convert | b78f17df9b91 | CVE-2026-54732 | CWE-22 | MIT | +1/-1 | 1 | OK |
| cve-0004 | argos-ci/argos-javascript | 8355f3af3be3 | CVE-2026-59960 | CWE-78 | MIT | +8/-18 | 1 | OK |
| cve-0005 | cookiecutter/cookiecutter | fdffddb31fd2 | CVE-2022-24065 | CWE-78 | BSD-3-Clause | +5/-9 | 1 | OK |
| cve-0006 | nuxt-content/mdc | 61d636c2983f | CVE-2026-63671 | CWE-79 | MIT | +2/-2 | 1 | OK |
| cve-0007 | mixxorz/slippers | 16cc4ef4fa8a | CVE-2026-34231 | CWE-79 | MIT | +1/-2 | 1 | OK |
| cve-0008 | Parsl/parsl | 013a928461e7 | CVE-2026-21892 | CWE-89 | Apache-2.0 | +6/-8 | 1 | OK |
| cve-0009 | geopandas/geopandas | 6aa8ef14ffde | CVE-2025-69662 | CWE-89 | BSD-3-Clause | +1/-5 | 1 | OK |
| cve-0010 | torchgeo/torchgeo | 1a980788cb70 | CVE-2024-49048 | CWE-94 | MIT | +2/-11 | 1 | OK |
| cve-0011 | andialbrecht/sqlparse | 53ff44b53e27 | CVE-2026-59894 | CWE-94 | BSD-3-Clause | +6/-10 | 1 | OK |
| cve-0012 | WaterFutures/EPyT-Flow | 3fff9151494c | CVE-2026-25632 | CWE-502 | MIT | +13/-23 | 1 | OK |
| cve-0013 | nextauthjs/next-auth | 6e15bdcb2d93 | CVE-2022-24858 | CWE-601 | ISC | +2/-2 | 1 | OK |
| cve-0014 | vgno/koa-remove-trailing-slashes | e7ce4000e9fe | CVE-2021-23384 | CWE-601 | MIT | +2/-6 | 1 | OK |
| cve-0015 | openstack/swift | 12e54391861e | CVE-2022-47950 | CWE-611 | Apache-2.0 | +1/-1 | 1 | OK |
| cve-0016 | fonttools/fonttools | 9f61271dc1ca | CVE-2023-45139 | CWE-611 | MIT | +0/-3 | 1 | OK |
| cve-0017 | jpadilla/pyjwt | 0a795b8e1f6e | CVE-2026-102267 | CWE-918 | MIT | +3/-18 | 1 | OK |
| cve-0018 | moxystudio/node-cross-spawn | 5ff3a07d9add | CVE-2024-21538 | CWE-1333 | MIT | +2/-4 | 1 | OK |
| cve-0019 | pennersr/django-allauth | 8feef46e0e07 | CVE-2025-65431 | CWE-287 | MIT | +2/-4 | 2 | OK |
| cve-0020 | unjs/defu | 3942bfbbcaa7 | CVE-2026-35209 | CWE-1321 | MIT | +1/-1 | 1 | OK |
| cve-0021 | dpkp/kafka-python | 6e4831444f97 | CVE-2026-10143 | CWE-400 | Apache-2.0 | +1/-6 | 1 | OK |
| clean-0001 | jd/tenacity | 3233040287fb | - | - | Apache-2.0 | +9/-7 | 1 | OK |
| clean-0002 | python-humanize/humanize | ffdf407fdfe1 | - | - | MIT | +11/-9 | 1 | OK |
| clean-0003 | cookiecutter/cookiecutter | cd851dd1270e | - | - | BSD-3-Clause | +20/-20 | 2 | OK |
| clean-0004 | mixxorz/slippers | c44fcd127df6 | - | - | MIT | +25/-16 | 2 | OK |
| clean-0005 | torchgeo/torchgeo | eea720cb76dc | - | - | MIT | +21/-3 | 1 | OK |
| clean-0006 | unjs/defu | e458b63653f9 | - | - | MIT | +15/-9 | 1 | OK |
| clean-0007 | unjs/scule | 146ecd076373 | - | - | MIT | +28/-2 | 2 | OK |
| clean-0008 | sindresorhus/p-map | a97778a36cb5 | - | - | MIT | +5/-1 | 1 | OK |
| clean-0009 | unjs/hookable | a4b0b54b9ac0 | - | - | MIT | +10/-0 | 1 | OK |

Commit column is the first 12 characters. `case.yaml` has the full sha. For cvefixes cases it is the upstream fix commit. For clean cases it is the clean commit itself.

CWE spread over the 21 vulnerable cases: CWE-22 x3, CWE-78 x2, CWE-79 x2, CWE-89 x2, CWE-94 x2, CWE-601 x2, CWE-611 x2, CWE-502, CWE-918, CWE-1333, CWE-287, CWE-1321, CWE-400 x1 each. Languages: 14 Python, 7 JavaScript/TypeScript for vulnerable cases, and 5 Python, 4 JS/TS for clean cases. No project has more than 2 cases.

## Verification

For every case, `context/` was copied to a temp dir and `patch -R -p1` was run with `diff.patch`. The resulting files were then compared byte for byte with the upstream pre-diff file (`git show FIX:<path>` for cvefixes, `git show C^:<path>` for clean). All 30 passed. `git apply -R --check` also passed for all 30. Every label range was printed with `sed -n 'START,ENDp' context/<path>` and checked by eye. Each label shows the vulnerable code. `context/` holds exactly the files named in the diff, no more and no fewer.

## Cases I am less sure about

- cve-0017 (pyjwt, CWE-918): the flaw is that `urllib.request.urlopen` follows redirects by default. A reviewer has to know that default. The label is valid, but the case is hard.
- cve-0020 (defu, CWE-1321): the flaw is only the difference between `{ ...defaults }` and `Object.assign({}, defaults)`: `Object.assign` runs the `__proto__` setter when `defaults` has its own `__proto__` key. The label is valid, but the case is subtle.
- cve-0013 (next-auth, CWE-601): the file is 18 lines. The flaw is `url.startsWith(baseUrl)`, which also accepts `https://site.com.evil.com`.
- cve-0011 (sqlparse, CWE-94): the output filter escapes quotes but not backslashes. It only matters when someone runs the generated Python/PHP code. The advisory classes it as CWE-94. A reviewer could reasonably call it CWE-116.
- cve-0018 (cross-spawn, CWE-1333): the upstream fix swaps `(\\*)"` for a lookahead form that is itself odd. The vulnerable regex is the one the CVE names, but a reviewer may argue about how bad the backtracking really is.
- cve-0016 (fonttools, CWE-611): the reversed diff is 3 deleted lines (`resolve_entities=False` and a comment). No `+` lines exist, so the label spans the whole `etree.XMLParser(...)` call (lines 219-228).
- cve-0021 (kafka-python, CWE-400): the threat model is a malicious or impersonated broker sending a huge SCRAM iteration count.
- cve-0005 (cookiecutter, CWE-78): the fix was a merge commit, and the diff is against its first parent. The reversed diff also carries unrelated f-string to `.format()` changes (lines 110-116). CWE-88 (argument injection) is more precise, but the advisory says CWE-78, and the label uses CWE-78.
- cve-0012 (EPyT-Flow, CWE-502): the diff also removes an allow-list registry at module level. The label covers only the object hook lines (278-281) that import and instantiate the attacker-named class.
- clean-0004 (slippers) touches the same template tag module as cve-0007 and sits near HTML rendering. The change itself only reshapes the arguments to `check_prop_types`. Chosen on purpose as a hard negative.
- clean-0005 (torchgeo) adds `getattr(torchgeo_resnet, backbone)`, but `backbone` is checked against a fixed list a few lines earlier. clean-0006 (defu) rewrites `isPlainObject`, which the merge logic relies on, but the boolean logic is the same (De Morgan). I am confident all three are clean. They are listed here because a reviewer may flag them.
- clean-0007 (scule): the upstream commit subject says "trainCase util", but the diff adds `titleCase`. The content is a pure string helper. The mismatch is only in the upstream message.

## Skipped and why

- Too large (touched file over about 600 lines): raszi/node-tmp CVE-2026-44705 (842), aws/aws-cdk CVE-2026-13760 (756), cstigler/node-xhtml-purifier CVE-2026-61784 (991), miguelgrinberg/flask-httpauth CVE-2026-34531 (669), python-hyper/hpack CVE-2026-59980 (664), webpack/webpack-dev-middleware CVE-2026-76844 (1162), marimo CVE-2026-54386 (733). Clean candidates dropped for size: kafka-python leader-epoch commit (897), pypa/packaging tags refactor (1053), p-queue onError (739), ky retry method case (1308).
- Vulnerable line gives itself away: CycloneDX/cyclonedx-javascript-library CVE-2024-34345. The reversed diff adds `noent: true // prevent https://.../issues/1061`, a comment on the vulnerable line pointing at the XXE issue. Replaced with fonttools.
- No clean line to label: langroid CVE-2026-25481 (the fix only adds a `visit_Attribute` method, so the reversed diff is a pure deletion of a sandbox check).
- Unclear fix semantics: jaredhanson/passport-oauth2 CVE-2021-41580, briancappello/flask-unchained CVE-2021-23393 (the linked commit mostly adds tests, and the one-line change is hard to read as the fix), postcss CVE-2026-45623 (the commit message does not match the path traversal), sunscrapers/djoser CVE-2024-21543 (a rollback commit that mixes in other changes).
- Good but held back for the next batch, to keep 21 and balance CWEs and projects: steveukx/git-js CVE-2026-28291 (CWE-78), pahen/madge CVE-2021-23352 (CWE-78), nuxt/nuxt CVE-2026-56317 (CWE-79), dicebear CVE-2026-68921 (CWE-79), dgtlmoon/changedetection.io CVE-2026-29038 (CWE-79), feathers-sequelize CVE-2022-2422 (CWE-89), scitokens CVE-2026-32714 (CWE-89, 531-line file), PyMySQL CVE-2024-36039 (CWE-89), petl CVE-2020-29128 (CWE-611), lepture/mistune CVE-2022-34749 (CWE-1333), joaonuno/flat-to-nested-js CVE-2026-55091 (CWE-1321), InternLM/lmdeploy CVE-2025-59953 (bind to all interfaces), Kozea/WeasyPrint CVE-2025-68616 (redirects).
- License: OWASP Benchmark (GPL-2.0) and every GPL/LGPL/AGPL/MPL/unknown-license repo in the advisory results were excluded. pypa/packaging reports NOASSERTION on GitHub (it is dual Apache-2.0/BSD-2). It was not used.

## Gaps for the next batch

- No CWE-863 (authorization) case yet. The small candidates found were in very large files (Superset, Flask-AppBuilder, copyparty).
- Many advisories are from 2026, so they are recent. Older, well-known CVEs (cookiecutter, next-auth, koa-remove-trailing-slashes, swift, fonttools, cross-spawn, torchgeo) are more likely to be in model training data. Consider reporting recall separately for the two groups.
