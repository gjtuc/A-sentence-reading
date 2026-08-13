# 131 — Full figure captions (UI wrap/scroll + server length)

Modules: `pdf/extract.py` · `docx/extract.py` · Flutter `reader_screen` · status flag  
받침: [02](02-pdf-extract.md) · [63](63-mobile-reader.md) · [128](128-clip-column-width.md) · [129](129-lazy-figure-open.md)

## 무엇인가

모바일 그림 캡션이 `Table 1 Results…`처럼 **2줄 말줄임**으로 끊긴다.  
저장 문자열은 대개 온전하지만, 서버 `_normalize_caption`이 **900자에서 조용히 자른다**.  
이번 칩: **앱은 전체 문장(줄바꿈·스크롤)** · **서버는 안전 상한만 두고 절단 완화**(말줄임 문자 삽입 없음).

| 포함 | 미포함 |
|------|--------|
| Flutter `maxLines:2`+ellipsis 제거 · 스크롤 가능 캡션 | 캡션 추출 품질·Elsevier 블록 이어붙이기 |
| `_normalize_caption` 상한 상향(안전 ceiling) | 표지→그림 #1 · 처리 취소 |
| status `caption_full_text` | 옛 보관본 일괄 재분석 강제 |
| 0.3.47 | |

## Product (locked)

1. 표시: **전체 문장** (줄바꿈 + 필요 시 스크롤) — A  
2. 서버 원문도 손댐 (900자 조용한 절단 완화)  
3. 성공: Ewbank Table 1 캡션이 기기에서 `…` 없이 끝까지(또는 스크롤로) 보임  
4. 이미지 클립 폭(128)과 별개

## Kill / rollback

Revert PR · 클라가 `caption_full_text=false`면 2줄 ellipsis 유지 가능(하위 호환).

## Live Enable / IPS

이번 칩에서 불필요함.

## Version

**0.3.47** · pipeline **rich-v12** (캡션 탐지 로직 불변 · normalize 길이만)
