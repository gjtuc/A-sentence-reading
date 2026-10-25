# 447 — `&gt;` 가 문장에 그대로 보이던 것 (0.3.472)

## 문제

Pt–Co 논문의 "Pt₇₅Co₂₅/C(500) > Pt₈₀Co₂₀/C(500) > …" 가 `&gt;` 로 보였다.
서버는 아래첨자가 있는 문장을 태그(`<sub>` 등)와 함께 보내고, 그 사이 글자의 `<` `>` `&` 는
`&lt;` `&gt;` `&amp;` 로 적는다 (`richtext.sanitize_sentence_html`). 앱은 태그는 읽었지만 이 글자를 되돌리지 않았다.
태그가 없는 문장은 서버의 `plain_text` 가 이미 풀어 두었으므로 아래첨자가 있는 문장에서만 생겼다.

## 바꾼 것 (`mobile/lib/api/rich_sentence.dart`)

- `decodeTextEntities` 가 `&amp; &lt; &gt; &quot; &apos;` 와 숫자 표기(`&#176;`, `&#xB0;`)를 푼다.
- 태그를 다 찾은 **뒤에** 글자 조각마다 푼다 (`_styledSpan`, 태그 없는 문장). 그래서 풀린 `<` 가 태그를 열지 않는다.
- `plainFromRichHtml` 도 풀어서 낸다. 형광펜·검색이 쓰는 위치는 서버 `plain_text` 와 같은 글자 수가 된다.
- 형광펜 경로는 이미 푼 글자를 그대로 `TextSpan` 으로 낸다. 다시 풀지 않는다.
- 긴 문장 끊어 보기(`richWithClauseBreaks`)는 `&gt;` 를 한 글자로 센다. 태그 없는 문장은 공백을 접지 않는 plain 과 맞춘다.

이 기호가 있는 문장에 예전에 칠한 형광펜은 기호 뒤쪽이 기호 하나당 3글자씩 밀릴 수 있다.

## 시험

`mobile/test/rich_entities_test.dart`
