# 242 — Find-watch after DOI CTA (tree observe)

Version: **0.3.234** · Status: **locked**  
Amends [226](226-pdf-folder-import-browser.md) · [237](237-pdf-import-doi-find-cta.md) · [238](238-pdf-import-open-document-pick.md) · [241](241-saf-tree-write-copy.md)

## Locked

- After 「찾아보기」 opens browser, arm watch: window **120s**, next **1** new PDF in **connected tree** (mtime > baseline).
- On hit → confirm dialog → `copyUriIntoTree` if source outside tree via pick, or if already in tree just select; **never delete**.
- Primary path after browser: user uses 「받은 PDF 고르기」(238). Watch is assist when download lands **inside** connected folder (e.g. grant=Downloads).
- **No MANAGE_EXTERNAL_STORAGE** this ship — tree-only observe (226 Exclude MES stays). Sideload MES deferred.

## Version

**0.3.234**
