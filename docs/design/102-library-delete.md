# 102 — Mobile library delete (GCS + user records)

Modules: `library_screen.dart` · `client.dart` · `DELETE /api/cache/papers/{id}` · purge helpers  
받침: [18](18-paper-library.md) · [62](62-mobile-library.md) · [101](101-library-reorder.md)

## 무엇인가

보관 탭 헤더에 **휴지통**을 둔다. 선택 모드에서 문서를 고른 뒤 삭제하면:

1. 로컬 캐시 폴더·index  
2. GCS 논문 객체(session/figures/source)·papers index  
3. **같은 uid**의 사용자 기록 — 노트(`cache:{id}`), 쉐도잉 chunks/takes, takes가 가리키는 voice blob  

을 best-effort로 함께 지운다.

## Product

1. 헤더 휴지통 → 선택 모드 ON/OFF  
2. 하나 이상 선택 → 「삭제」확인 → API DELETE  
3. 열려 있던 문서면 읽기 세션 비움  
4. 기기 library order prefs에서도 id 제거  

## API

`DELETE /api/cache/papers/{cache_id}` — `_paid_access_denied` 적용 · 현재 uid GCS 경로만.

## Version

**0.3.16** · status + pubspec

## Live Enable / IPS

이번 칩에서 불필요함.
