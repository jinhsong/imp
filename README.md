# 수입 모델 인증 확인 (전파인증 · 안전인증)

모델명을 입력하면 **전파인증(적합성평가, RRA)** 과 **안전인증(KC, 국가기술표준원)** 의
인증번호를 한 화면에서 조회하는 단일 페이지 도구입니다.

- `index.html` — 화면 + 모든 조회/파싱 로직 (단일 파일)
- `server.py` — 로컬 프록시 서버 (Python 표준 라이브러리만 사용, 설치 불필요)
- `build_db.py` — 전파인증 데이터(.xls) → 검색용 `rra_db.json` 변환기
- `rra_db.json` — 전파인증 로컬 DB (페이지에 번들, 브라우저에서 즉시 검색)
- `data/Device_list.xls` — 원본 데이터 (재생성용)
- `README.md` — 이 문서

> 전파인증의 기본 조회 방식은 **로컬 DB(모델명)** 입니다. 키·서버·외부 호출 없이
> 브라우저에서 바로 검색되며 GitHub Pages 배포 시에도 그대로 동작합니다.

---

## ⚠️ 먼저 알아야 할 것: CORS

data.go.kr / rra.go.kr 의 응답에는 CORS 허용 헤더가 없습니다. 그래서 브라우저가
이 사이트들을 **직접** 호출하면 (로컬에서 열든 GitHub Pages 든) 차단됩니다.
이를 우회하는 두 가지 방식이 있고, 설정 패널의 **연결 방식**에서 고릅니다.

| 방식 | 동작 | 장점 | 단점 |
|------|------|------|------|
| **로컬 프록시** (권장) | `server.py` 가 같은 출처에서 `/fetch` 로 중계 | API 키가 외부로 안 나감, 안정적 | 내 PC에서 서버 실행 필요 |
| **공개 CORS 프록시** | 제3자 공개 프록시 경유 | 파일 하나로 GitHub Pages 배포 시 바로 동작 | 키가 외부 프록시를 지나감(주의), 프록시 불안정 |

---

## 사용법 1 — 로컬에서 (권장, 안전인증 키 사용 시)

```bash
python3 server.py            # 기본 http://localhost:8000
# 또는 포트 지정:  python3 server.py 9000
```

1. 브라우저에서 출력된 주소(예: `http://localhost:8000`) 접속
2. **⚙️ 설정** 열기
   - 연결 방식 → **로컬 프록시**
   - 안전인증 서비스키, 요청 URL, 모델명 파라미터 입력 (아래 "설정값 채우기" 참고)
   - **저장** → **연결 테스트** 로 프록시 정상 확인
3. 모델명 입력 후 **둘 다 조회**

> 키는 브라우저 `localStorage` 에만 저장되며 깃허브에 커밋되지 않습니다.

---

## 사용법 2 — GitHub Pages 배포 (전파인증 위주 공유용)

1. 이 저장소를 푸시하고, **Settings → Pages** 에서 브랜치를 소스로 지정
2. 배포된 페이지에서 **⚙️ 설정 → 연결 방식 → 공개 CORS 프록시** 선택
3. 전파인증은 키 없이 동작합니다. 안전인증은 키를 입력해야 하며,
   **공개 프록시를 거치므로 민감 키 사용은 신중히** 하세요(가능하면 로컬 모드 권장).

`{url}` 자리표시자를 쓰는 공개 프록시 예시(가용성은 그때그때 다름):
- `https://api.allorigins.win/raw?url={url}` (기본값)
- `https://corsproxy.io/?url={url}`

---

## 설정값 채우기

### 안전인증 (SafetyKorea — KC인증정보 Open API)

국가기술표준원 SafetyKorea(제품안전정보센터)에서 발급한 **서비스 ID**를 사용합니다.
data.go.kr 서비스키가 **아니며**, 인증은 쿼리 파라미터가 아니라 **`AuthKey` HTTP 헤더**로
합니다. (이 헤더 인증 때문에 **반드시 '로컬 프록시' 모드**여야 합니다 — 공개 CORS
프록시는 커스텀 헤더를 전달하지 못합니다.)

- 엔드포인트: `http://www.safetykorea.kr/openapi/api/cert/certificationList.json`
- 인증: 헤더 `AuthKey: <서비스 ID>` (대소문자 구분)
- 파라미터: `conditionKey`(검색구분) + `conditionValue`(검색어)
  - `conditionKey` 값: `all` / `certNum` / `productName` / `modelName` / `certDate` / `signDate`
- 응답: `{ "resultCode":"2000", "resultMsg":"Success", "resultData":[ … ] }`
  - 레코드 필드: `certNum`(인증번호) `certState`(인증상태) `modelName`(모델명)
    `productName`(제품명) `certDiv`(인증구분) `makerName`(제조사) `importerName`(수입사)
    `makerCntryName`(제조국) `certDate`(인증일자) 등
  - 결과코드 `2000` = 성공. 그 외는 화면에 코드·메시지를 표시합니다.

설정:

1. **연결 방식 → 로컬 프록시** 로 두고 `python3 server.py` 실행.
2. *안전인증 AuthKey* 에 발급받은 서비스 ID 입력 (localStorage 에만 저장).
3. *검색 구분* 은 기본 `modelName`(모델명). *요청 URL* 은 기본값 그대로 두면 됩니다.
4. 모델명을 입력하고 조회 → 인증번호·인증상태 등이 표시됩니다.

> 최대 1,000건까지 반환됩니다. 응답이 안 맞으면 **디버그 표시**로 원본 JSON 을 확인하고
> `index.html` 의 `normalizeSafety()` 필드 매핑을 조정하세요.

### 전파인증 ① 로컬 DB (기본, 모델명 검색 — 키 불필요) ★권장

5년치 적합성평가 데이터를 번들해 브라우저에서 바로 검색합니다. 전파인증 카드의
**조회 기준 → 모델명·로컬DB** 에서 동작하며, 모델명/파생모델명 부분일치로
인증번호·인증상태·상호·기자재명·제조국·제조자·인증연월일을 보여줍니다.

데이터 갱신(새 .xls 를 받았을 때):

```bash
python3 build_db.py                 # data/Device_list.xls → rra_db.json
python3 build_db.py 새파일.xls       # 다른 파일로 갱신
```

> 입력 파일은 RRA 검색결과 다운로드본(.xls = euc-kr HTML 표)이며, 헤더는
> `번호/상호/기자재명칭/모델명/제조국가/인증 연월일/인증 상태/인증번호/제조자/파생모델명`
> 순서입니다. 파생모델명의 `<br>`(엔터) 다중값은 각각 검색되도록 펼쳐집니다.
> `rra_db.json` 은 `index.html` 과 같은 위치에 있어야 합니다(설정에서 경로 변경 가능).
> file:// 로 직접 열면 로드가 막힐 수 있으니 `server.py` 또는 GitHub Pages 로 여세요.

### 전파인증 ② RRA 무료 Open API (인증번호 조회 — 키 불필요)

RRA가 `emsit.go.kr` 에서 무료 Open API를 제공합니다(별도 서비스키 없음). 단,
**모델명이 아니라 인증번호(`mtlCefNo`)로 조회**합니다.

- 인증여부: `http://emsit.go.kr/openapi/service/AuthenticationInfoService/getAuthStatus.do?mtlCefNo=<인증번호>`
  → 응답 `<authYn>Y/N</authYn>`
- 상세정보: `http://emsit.go.kr/openapi/service/AuthenticationInfoService/getAuthInfo.do?mtlCefNo=<인증번호>`
  → `bsmNm`(업체명) `mtlNm`(기자재명칭) `matlBscMdlNm`(기본모델) `matlDerivMdlNm`(파생모델)
     `matlMfrNm`(제조자) `dttlInfCdNm`(제조국) `cvaPcsYmd`(인증일) 등
- 인증번호 상세 페이지: `A_b_popup_keyno.do?key_no=<인증번호>`

응답코드: `0000` 정상 / `0001` 조회내역없음 / `0098` 요청 파라미터 누락.

XML 파싱/필드 매핑은 `index.html` 의 `parseRraInfo()` 에서 조정합니다.

### 전파인증 ③ 모델명 실시간 조회 (RRA 사이트 직접 — 키 불필요)

로컬DB는 번들된 스냅샷이라 최신 건이 빠질 수 있습니다. **최신 데이터를 모델명으로**
찾으려면 전파인증 카드에서 **조회 기준 → 모델명·실시간조회** 를 선택하세요. RRA 검색
화면이 쓰는 요청을 그대로 보냅니다(키 불필요, **로컬 프록시 모드 필요**).

- 요청: `POST https://www.rra.go.kr/ko/license/A_c_search_view.do`
  (`application/x-www-form-urlencoded`)
- 본문: `category=&fromdate=<YYYYMMDD>&todate=<YYYYMMDD>&firm=&equip=&model_no=<모델명>&app_no=&maker=&nation=`
  - **`model_no`** 가 모델명, **`fromdate`/`todate`** 가 인증일자 기간
- 응답(euc-kr HTML 결과표; server.py 가 UTF-8 로 변환)에서 각 결과 행(상호·기자재명칭·
  모델명·제조국·인증일·인증상태·상세링크 `app_no`)을 파싱합니다. 결과표에는 인증번호가
  없으므로, 각 행의 상세팝업(`A_b_popup.do?app_no=`)을 받아 **인증번호(R-…)를 보충 추출**해
  표시합니다(처음엔 "인증번호 조회중…" 후 채워짐).

설정의 *인증일자 시작/종료* 로 기간을 바꿀 수 있습니다(기본 2000-01-01 ~ 오늘).

> 결과표 열 구조가 바뀌면 **디버그 표시**로 원본 HTML 을 확인하고 `index.html` 의
> `parseRraLive()` / 인증번호 정규식 `RRA_CERT_RE` 을 조정하세요. RRA 페이지 인코딩이
> euc-kr 이라 한글이 깨져 보이면 인증번호(영문)는 정상이며, 필요 시 알려주시면 변환을 넣겠습니다.

---

## 여러 모델 일괄 조회

화면의 **📋 여러 모델 일괄 조회** 를 펼친 뒤:

1. 모델명을 **한 줄에 하나씩(또는 쉼표 구분)** 붙여넣기
2. **전파인증 / 안전인증** 중 조회할 항목 체크
   - 전파인증은 위 카드의 *조회 기준*(로컬DB/실시간)을 그대로 사용
   - 안전인증은 AuthKey + 로컬 프록시 필요
3. **일괄 조회** → 모델별 결과 표(인증번호·인증상태·건수·상세링크) 표시
4. **CSV 다운로드** 로 결과 저장(엑셀 호환, UTF-8 BOM)

> 로컬DB 전파인증은 즉시 처리됩니다. 실시간/안전인증은 모델마다 네트워크 요청이
> 있어 모델 수에 비례해 시간이 걸립니다(순차 처리, 진행률 표시).

## 보안 메모

- 안전인증 키는 **로컬 프록시 모드**에서 사용하길 권장합니다 (외부로 전송되지 않음).
- 키를 코드/저장소에 하드코딩하지 마세요. 입력값은 `localStorage` 에만 저장됩니다.
- `server.py` 는 `ALLOWED_HOSTS` 에 등록된 정부 도메인으로만 중계합니다(오픈 프록시 아님).

## 문제 해결

| 증상 | 확인 |
|------|------|
| "host not allowed" | 대상 도메인을 `server.py` 의 `ALLOWED_HOSTS` 에 추가 |
| 안전인증 결과 0건인데 키는 정상 | 모델명 파라미터명/요청 URL이 상세페이지와 일치하는지, 디버그로 원본 확인 |
| 전파인증 "미인증/내역없음" | 모델명이 아니라 **인증번호**(예: KCC-REM-MJT-MJT)를 입력했는지 확인 |
| 공개 프록시 실패 | 다른 공개 CORS 프록시 템플릿으로 교체하거나 로컬 모드 사용 |
