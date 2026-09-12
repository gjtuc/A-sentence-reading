# 255 — Architecture Technical Debt Refactoring Roadmap

Version: **0.3.254** · Status: **locked**  
Amends [155](155-deploy-live-guard.md) · [168](168-audit-checklist.md) · [169g](169g-causal-handoff-evidence.md) · [173](173-capacity-isolation-roadmap.md)

## Context & Motivation

Through rapid iterative delivery up to `v0.3.253`, the application has achieved robust end-to-end features (bilingual sentence reading, dual-column layout, figure extraction, shadowing practice, Pomodoro focus calendar, and 50-step skill ladder). However, high feature velocity has accumulated structural technical debt across three primary axes:

1. **Monolithic Core Modules**:
   - Backend `src/sentence_reading/api/app.py` (~9,800 lines): combines lifecycle, middleware, in-memory concurrency locks, OAuth, access gating, PDF ingest orchestration, figure hydration, TTS, shadowing, and cloud sync.
   - Mobile `mobile/lib/controllers/library_controller.dart` (~7,500 lines): merges local file I/O, cache management, GCS sync, upload retries, SAF tree traversal, and practice resume state.
   - Mobile `mobile/lib/screens/reader_screen.dart` (~2,550 lines): tightly couples sentence virtualization, figure pinch-zoom gestures, citation accordions, annotation highlights, and TTS playback.

2. **Pipeline Ingest Latency & Cost Redundancy**:
   - Azure Document Intelligence is invoked uniformly across all PDF structures, even for single-column text-only papers that can be reliably parsed via lightweight local extractors (PyMuPDF).
   - Identical sentences across multiple revisions or related literature are repeatedly re-translated via Gemini without a persistent content-addressable cache.

3. **Multi-Script Deployment Guard Friction**:
   - Developers and subagents must coordinate multiple validation scripts (`session_freshness_guard.py`, `pre_deploy_guard.py`, `check_evidence_floor.py`), creating cognitive overhead and potential verification gaps.

---

## 1. Locked Architectural Principles

### 1.1 Backend Router & Context Modularization
- `app.py` remains the single **SoT entrypoint** for FastAPI declaration, lifespan context, global middleware, exception handlers, and router inclusion (`app.include_router(...)`).
- Global in-memory state (`_PAPER_LOCKS`, `_SESSIONS`, `_ACTIVE_INGEST_JOBS`) must reside in an explicit shared context module (`src/sentence_reading/api/context.py`) with thread-safe/asyncio lock primitives to prevent split-brain concurrency.
- Common authentication and authorization dependencies (`_require_auth`, `_require_admin`) move to `src/sentence_reading/api/deps.py`.
- Domain routers are extracted under `src/sentence_reading/api/routes/`:
  - `status.py`: `/api/status`, `/healthz`, `/api/version` (safe canary)
  - `tts.py`: `/api/tts/speak`, voice synthesis, spoken lexicon
  - `auth.py`: OAuth redirects, Kakao/Google tokens, session lifecycle
  - `access.py`: invite code gating, user tier approvals, quota checks
  - `papers.py`: paper metadata listing, reordering, deletion, and local sync
  - `ingest.py`: PDF staging, Azure Layout vs fast-track dispatch, debone, checkpointing
  - `shadowing.py`: chunk builder, audio take upload, evaluation loop
  - `practice.py`: Pomodoro focus calendar sync, 50-step skill ladder cloud sync

### 1.2 Mobile Controller Facade & Screen Decomposition
- **Facade Pattern for `LibraryController`**: Existing public getters and methods (`papers`, `isLoading`, `recordPracticeProgress`, `deletePaper`, `reorderPapers`) must remain 100% backward-compatible.
- Internal responsibilities are delegated to dedicated service modules:
  - `PaperStorageService`: local disk serialization, cache path resolution, TTL cleanup.
  - `PaperSyncService`: GCS cloud sync, lease acquisition, conflict resolution.
  - `PaperUploadService`: chunked background uploads, upload queue state, progress streams.
- **Componentization of `ReaderScreen`**:
  - `SentenceViewport`: virtualized sentence list with dual-language rendering and font scale tokens.
  - `FigureOverlayPanel`: horizontal figure carousel, pinch-to-zoom isolation, caption chip jumps.
  - `ReaderAnnotationToolbar`: 4-color highlighter, note creation, and AI inquiry bottom sheet.
  - `ReferenceAccordionView`: citation list with auto-expand defaults and DOI jump handlers.

### 1.3 Lightweight Fast-Track Ingestion & Translation Cache
- **Hybrid Ingestion Dispatcher**:
  - Run fast layout heuristics (single-column detector via PyMuPDF bounding box variance).
  - Clean single-column papers bypass Azure Layout to use local fast-track extraction (<1.5s latency, 0 external API cost).
  - Multi-column, table-heavy, or complex formula papers route through Azure Document Intelligence.
- **Sentence-Level Translation Hash Cache**:
  - Cache key: `sha256(domain + "::" + raw_english_sentence.strip())`.
  - Stored in GCS / local SQLite cache. Cache hits immediately return validated Korean translations, reducing Gemini token costs and rate limit pressure.

### 1.4 Unified Guard CLI (`scripts/guard.py`)
- Combine all verification steps into a single CLI tool:
  - `python scripts/guard.py freshness`: runs `session_freshness_guard.py` logic.
  - `python scripts/guard.py floor`: runs `check_evidence_floor.py` logic.
  - `python scripts/guard.py pre-deploy`: runs `pre_deploy_guard.py` checks.
  - `python scripts/guard.py all`: runs all guards sequentially with strict fail-closed exit codes.

---

## 2. Invariants & Guardrails (Non-Negotiable)

1. **Atomic 4-File Version Bump**:
   - `pre_deploy_guard.py` regex requires exact matches in:
     - `src/sentence_reading/api/app.py`: `version="X.Y.Z"` and `"/api/status": {"version": "X.Y.Z"}`
     - `mobile/pubspec.yaml`: `version: X.Y.Z+build`
     - `mobile/lib/config.dart`: `kAppVersionLabel = 'X.Y.Z'`
   - Router extractions must **never** move version declarations out of `app.py`.

2. **Evidence Floor Preservation (Design 169g)**:
   - All entries in `FROZEN_KINDS` (`src/sentence_reading/llm/evidence_floor.py`) are immutable and strictly **add-only**.
   - Event sensors (`_google_batch_timed`, `translate_call_start/done`, `reanalyze_pref_snapshot`, etc.) must not be removed during router refactoring.

3. **In-Memory Lock Concurrency Integrity**:
   - Never duplicate lock dicts across modules. `context.py` must be the sole holder of `_PAPER_LOCKS` and `_INGEST_JOB_LOCKS`.

4. **UI Stealth Interaction Integrity (Design 253 / 254)**:
   - 2-second hold for edit mode vs 500ms stealth hold for reorder must maintain the motion-triggered lift highlight (`isLifted: ValueListenable<bool>`) to decouple static press from drag activation.

---

## 3. Four-Phase Execution Roadmap

| Phase | Target Scope | Key Deliverables | Risk Level |
|---|---|---|---|
| **Phase 1** | Unified Guard & Canary Routers | `scripts/guard.py`, extract `routes/status.py` and `routes/tts.py` | Low |
| **Phase 2** | Auth, Access & Concurrency Context | `context.py` (locks), `deps.py` (auth), `routes/auth.py`, `routes/access.py` | Medium |
| **Phase 3** | Ingest Pipeline & Translation Cache | Hybrid layout router (PyMuPDF fast-track), SHA-256 translation cache | High |
| **Phase 4** | Mobile Facade & Reader Componentization | `LibraryController` services, `ReaderScreen` modular widgets | Medium |

---

## 4. Verification

- `python scripts/check_evidence_floor.py` -> exit 0
- `python scripts/pre_deploy_guard.py` -> exit 0
- `flutter test` -> all tests pass
- Cloud Run verification: `python scripts/verify_live_status.py --require-azure-layout --min-pipeline rich-v20 --expect 0.3.254`

## Version

**0.3.254**
