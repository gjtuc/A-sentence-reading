# 467 — 짝과 합치기가 서버 목록에도 남게

## 증상

메인과 보충(SI)을 둘 다 올려 짝은 잡혔는데, "짝과 합치기"를 눌러도 보관함이 그대로였다.
SI가 계속 따로 보이고 합치기 버튼도 다시 나왔다. 두 번 누른 논문은 SI 문장과 그림이
두 번 붙었다(187 → 189 → 191 문장, 8 → 10 → 12 그림).

## 원인

1. 앱 `mergeSupplementary`는 기기 안 합치기(`_mergeSupplementaryLocal`, design/263)가 되면
   서버 합치기를 부르지 않았다. 기기 세션과 목록만 바꿨다.
2. 바로 뒤 `refresh()`는 서버 목록을 기기 목록에 덮어쓴다. 서버는 합친 적이 없으므로
   SI가 다시 나타나고 메인 역할도 `main`, 합치기 가능도 참으로 돌아왔다.
3. 기기 합치기는 이미 합친 메인에도 SI를 한 번 더 이어 붙였다.

## 고침

- 기기 합치기가 끝나면 refresh 전에 `POST /api/cache/papers/{id}/merge-supplementary`를
  기다린다. 실패해도 기기 합치기는 성공으로 둔다. 결과는 `paper_merge_done`의
  `server_sync`(ok | http_NNN | error | none)에 남는다.
- `_mergeSupplementaryLocal`: 메인 세션에 `supplementary_merged`가 이미 있으면
  `section == supplementary` 문장과 `si-` 그림을 먼저 빼고 다시 붙인다.
  `paper_merge_local_done`에 `prior_merge`, `stripped_sent_n`, `stripped_fig_n`.

## 이미 두 번 붙은 논문

새 앱에서 그 논문의 "짝과 합치기"를 한 번 더 누르면 겹친 SI가 빠지고 한 번만 붙은 뒤
서버에도 합쳐진다.

## 시험

- `mobile/test/merge_server_sync_467_test.dart`
