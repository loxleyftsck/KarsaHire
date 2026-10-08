# Dependency advisory review — 2026-09-30

## Scope and result

Reviewed the five exact Python package pins in `requirements.txt` against the packages' upstream GitHub security-advisory pages and release notes on 2026-09-30. The pinned versions meet or exceed the published fixed versions found in that review. No dependency changes were needed for this advisory snapshot.

| Package pin | Upstream advisory review | Result |
| --- | --- | --- |
| `pypdf==6.19.0` | The upstream advisory index listed ten advisories on the review date. The fixes span 6.16.1, 6.17.0, 6.18.0, 6.18.1, and 6.19.0. The Roman page-label issue was fixed in 6.17.0; the latest listed fixes for appearance streams, alphabetical page labels, and embedded files are in 6.19.0. | Pin meets the latest listed fixed version. [Advisory index](https://github.com/py-pdf/pypdf/security/advisories), [release history](https://github.com/py-pdf/pypdf/releases) |
| `Pillow==12.3.0` | Upstream 12.3.0 release notes record the security fixes included in that release, including 2026 vulnerabilities. | Pin includes those published fixes. [12.3.0 security release notes](https://github.com/python-pillow/Pillow/blob/main/docs/releasenotes/12.3.0.rst) |
| `lxml==6.1.3` | GHSA-vfmq-68hx-4jfw affects versions below 6.1.0 and lists 6.1.0 as patched. | Pin is above the fixed version. [Upstream advisory](https://github.com/lxml/lxml/security/advisories/GHSA-vfmq-68hx-4jfw) |
| `python-docx==1.2.0` | The upstream GitHub security page showed no published advisories. It also showed that the project has no `SECURITY.md` policy. | No published upstream advisory was found; this is not evidence that the package has no vulnerabilities. [Upstream security page](https://github.com/python-openxml/python-docx/security) |
| `typing-extensions==4.16.0` | The upstream GitHub security page showed no published advisories. | No published upstream advisory was found. [Upstream security page](https://github.com/python/typing_extensions/security) |

## Limits

This is a dated check of public upstream advisory pages for the five pins in `requirements.txt`. It did not inspect the installed Python environment, resolve or validate an SBOM, query OS/distribution advisories, verify package artifact provenance, or assess exploitability in the application. The optional local Tesseract executable and language data are not part of these Python pins; inventory and review their exact versions separately before using them in a controlled build. Public advisory pages can change after this review. Recheck before staging and production, and use an approved dependency/SBOM scanner against the exact build environment.

This review adds advisory evidence to the 2026-09-30 static source review; it does not replace that scan, formal security review, SSO/RBAC work, or M3 approval. M3 remains open.
