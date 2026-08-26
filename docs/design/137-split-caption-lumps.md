# 137 — Split caption lumps (one label per slot)

Modules: `pdf/caption_lumps.py` · `pdf/extract.py` (`_labeled_caption_hits`) · ingest (`api/app.py`) · `llm/typography.py`  
받침: [125](125-caption-anchored-figures.md) · [127](127-caption-word-join.md) · [136](136-strip-adjacent-articles.md)

## 무엇인가

한 줄·한 블록에 **Fig. 1 … Fig. 2 …** 처럼 캡션이 여러 개 붙어 있으면, 지금은 첫 라벨만 보고 나머지가 **한 덩어리**로 남거나 빠진다.  
**라벨마다 별도 캡션·캐러셀 슬롯**으로 쪼갠다. 쪼갤 수 없으면 **업로드 실패**(fail-closed).

| 포함 | 미포함 |
|------|--------|
| 같은 줄 다중 `Fig./Table/Scheme` 분리 | compound 1a/1b 패널 분해 ([44](44-compound-off.md)) |
| 추출 후 덩어리 잔존 검사 → ingest 실패 | DOCX · 로컬 서버 흔적 제거 |
| 킬 `ASR_SPLIT_CAPTION_LUMPS=0` · pipeline `rich-v15` | APK 자체 업데이트 (이번 칩: 빌드·설치만) |
| APK **0.3.55** 빌드·실기 설치 | Live Enable / IPS |

## Product (locked)

1. 한 줄에 **유효한 캡션 라벨이 2개 이상**이면 각각 별도 추출  
2. 라벨은 보이는데 **구분·검증 실패** → 업로드 실패 (통째 성공 금지)  
3. 추출된 figure `caption`에 **서로 다른 키 2개 이상** 남으면 실패  
4. 검증: **pytest + 폰 + Live** (합성 PDF · 가능하면 보관함 PDF)  
5. **APK 0.3.55** 빌드·설치 포함

## Kill / rollback

- `ASR_SPLIT_CAPTION_LUMPS=0` → status `split_caption_lumps=false` · split/validate 끔
- Revert PR · `PIPELINE_VERSION` 되돌림

## Live Enable / IPS

이번 칩에서 불필요함.

## Version

**0.3.55** · pipeline **rich-v15**

## Device / E2E pin

- Live `/api/status`: `version=0.3.55` · `pipeline_version=rich-v15` · `split_caption_lumps=true` · `mobile_split_caption_lumps=true`
- SM-G986N APK **0.3.55** → Live: upload `synthetic_lumped_alpha_beta_nickel_catalysts_drm.pdf` (built from `testdata/caption_lumps/synthetic_lumped_two_figs.pdf`)
  - **WHY long filename/title:** library save needs `normalize_title_key` ≥ 24 (design/108); short adb stems like `zzz_asr_lump137` fail with「제목이 너무 짧…」
  - 보관 **7→8** · entry **Synthetic Paper Alpha: Nickel Catalysts for DRM — Lumped Fig Captions**
  - Reader: **figure 1 / 2** · Fig. 1 Alpha catalyst overview → next → **figure 2 / 2** · Fig. 2 Beta support morphology
- Fail-closed (pytest): `Fig. 1. Valid … Fig. 2` bare label → ingest `CaptionLumpError` (no library entry)
- Kill: `ASR_SPLIT_CAPTION_LUMPS=0` · revert PR · `rich-v14`
- E2E helper: `scripts/lump137_e2e.py` (phone + Live; adb disconnect → retry reader check manually)

Do not paste emails, cookies, tokens, or secrets into chat/PR.
