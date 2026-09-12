# 254 - Import screen tab CTA separation

Version: 0.3.247
Amends 226, 248, 251, 253

## Rationale

1. Paper folder tab:
   - Already shows papers in connected folder.
   - Remove redundant '다운로드에서 가져오기' button from paper folder mode.
   - Keep only '파일에서 추가' and '대기열에 추가'.

2. Downloads tab:
   - Sole purpose is getting files from downloads.
   - In empty state, remove '논문 폴더 연결' and '또는 파일에서 추가'.
   - Keep only '다운로드에서 가져오기' as the primary action.

## Locked UI Rules

- Paper folder mode:
  - No '다운로드에서 가져오기' in bottom bar or empty state.
- Downloads mode:
  - In empty state, only '다운로드에서 가져오기' button.
  - Hide bottom bar when no grant connected in downloads mode.

## Version

0.3.247
