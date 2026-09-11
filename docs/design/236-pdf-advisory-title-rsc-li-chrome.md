# 236 — Skip journal short-link lines (`rsc.li/…`) in advisory titles

Version: **0.3.233** · Status: **locked**  
Amends [233](233-pdf-advisory-title-chrome-skip.md)

## Problem

RSC Catal. Sci. Technol. covers put `rsc.li/catalysis` after DOI, before the real title.  
233 skipped Cite this / DOI / masthead, but not bare journal short-links → phone showed `rsc.li/catalysis` for `d3cy01612a`.

## Locked

In `isAdvisoryTitleChrome` / `_prefixChrome` (Dart):

- Reject lines starting with `rsc.li/`
- Also reject bare `host.tld/path` (no scheme, no spaces) e.g. `rsc.li/catalysis`

True titles stay (multi-word prose). Bump advisory cache **v=5**.

## Tests

Extend RSC fixture + `tests/test_pdf_import_ux_232_233.py` · flutter smoke

## Version

**0.3.233**
