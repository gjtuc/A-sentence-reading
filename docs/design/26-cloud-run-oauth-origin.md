# 26 — Cloud Run Google OAuth 원본

모듈: Google Cloud Console OAuth 클라이언트 · `/api/status` `cloud_url`

## 무엇을

Cloud Run URL에서 **Google 로그인**이 되도록, OAuth 웹 클라이언트에  
**승인된 JavaScript 원본**을 추가한다. (이메일 로그인은 원본 없이도 동작)

## URL

`https://asr-sentence-reading-984608876300.asia-northeast3.run.app`

(별칭 `https://asr-sentence-reading-viifumy7qq-du.a.run.app` 가 있으면 둘 다 넣어도 됨)

## 콘솔 (사람 1회)

1. [사용자 인증 정보](https://console.cloud.google.com/apis/credentials?project=peaceful-basis-503207-t4)
2. OAuth 2.0 클라이언트 ID (웹 · `….apps.googleusercontent.com`) 열기
3. **승인된 JavaScript 원본** → **URI 추가**  
   `https://asr-sentence-reading-984608876300.asia-northeast3.run.app`  
   (이미 있는 `http://127.0.0.1:8770` 은 유지)
4. 저장

## 합격

- Run URL 에서 **구글로 계속하기** → 계정 선택 → 로그인됨
- `/api/status` `cloud_url` 이 위 주소

## 버전

0.2.23
