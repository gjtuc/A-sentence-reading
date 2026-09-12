# 242 — Find-watch after DOI CTA (tree observe)

Version: **0.3.235** · Status: **locked**  
Amends [226](226-pdf-folder-import-browser.md) · [237](237-pdf-import-doi-find-cta.md) · [238](238-pdf-import-open-document-pick.md) · [241](241-saf-tree-write-copy.md) · polish [243](243-pdf-import-remaining-polish.md)

## Locked

- After 「찾아보기」 opens browser, arm watch: window **120s**, next **1** new PDF in **connected tree** (mtime > baseline).
- On hit → confirm dialog → select only (**never delete**). Outside tree = pick path only (no MES).
- Primary path after browser: user uses 「받은 PDF 고르기」(238). Watch is assist when download lands **inside** connected folder.
- [247](247-pdf-import-downloads-bridge.md): on resume while armed (no tree hit) → one 「다운로드에서 가져올까요?」dialog → pick.
- **Pick non-cancel disarms watch** (`disarmFindWatch(reason:'pick')`); ignore copied URIs (`_pdfFindWatchIgnoreUris`); after scan bump baseline.
- Evidence: `pdf_find_watch_disarm` `{reason}` — never URI/DOI.
- **No MANAGE_EXTERNAL_STORAGE** this ship — tree-only observe (226 Exclude MES stays). Sideload MES deferred.

## Version

**0.3.235**

## Amend (design/252)

Find-watch events carry `find_id`; hit may include `file_kind` bucket. Resume Downloads offer evidence: [252](252-find-return-causal-evidence.md).
