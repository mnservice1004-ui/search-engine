# 동탄구보건소 보건민원 검색엔진

## VS Code·Codex 기준 구현 매뉴얼

> 문서 목적: 동탄구보건소 보건민원 정보검색 서비스 구현 기준
> 기준일: 2026-08-28
> 대상 환경: Windows 10/11, VS Code, Python 3.12
> 주 사용자: 웹사이트를 직접 이용하는 **65세 이상 노년층 민원인**
> 부 사용자: 노년층 민원인을 안내하는 보호자와 보건소 직원
> 개발기한: 남은 일주일
> 현재 단계: 노년층 민원인용 검색결과 문구와 안내정보 전환
> 디자인 상태: **현재 디자인 최종 확정 및 변경 금지**
> 공식 출처: [화성특례시 보건소](https://www.hscity.go.kr/health/index.do)
> Codex 사용 기준: [OpenAI 공식 Codex IDE 확장 문서](https://developers.openai.com/codex/ide)

---

## 0. 기준 문서와 적용 우선순위

이 파일은 프로젝트의 유일한 VS Code 구현 기준 문서다. 과거 구현기록 중 현재 코드·DB와 충돌하는 내용은 이 기준일의 검증 결과로 대체하며, 완료된 기능을 다시 개발하지 않는다.

적용 우선순위는 다음과 같다.

1. 2026-08-28에 확인된 현재 코드·DB·자동시험 결과
2. 기관이 확정한 공식자료와 출처
3. 이 문서의 노년층 민원인용 문구·데이터 전환 원칙
4. 보류목록과 운영 전 승인사항

예시 전화번호·장소·업무정보는 실제 값으로 사용하지 않는다. 기관명은 현재 서비스 문구에서 `동탄구보건소`로 사용하고, 과거 명칭은 역사적 원문과 출처 기록에만 보존한다.

### 0.1 이번 기준 갱신의 범위

이번 기준 갱신은 문서 정리만 수행한다. 대표 업무의 실제 공개문구 작성, 화면 적용, 데이터 적재, 코드 구현은 포함하지 않는다. 이후 작업에서도 업무 원문·연락처 원본·출처를 덮어쓰지 않고 별도의 공개 안내정보로 연결한다.

## 1. 서비스 목적과 사용자

### 1.1 목적 전환

기존 목적은 보건소 직원이 업무명, 담당 부서, 위치와 연락처를 검색해 민원인에게 설명하는 내부 안내도구였다.

현재 목적은 **노년층 민원인이 행정조직이나 공식 업무명을 알지 못해도 일상적인 말로 필요한 보건민원을 검색하고, 자신이 해야 할 일과 방문장소 및 연락처를 직접 이해할 수 있는 공개 안내서비스**를 만드는 것이다.

서비스는 다음을 제공해야 한다.

- 노년층 민원인이 말하듯 검색
- 공식 행정용어를 몰라도 검색 가능
- 자신이 이용할 수 있는 서비스인지 확인
- 준비물·비용·운영시간 확인
- 방문할 장소와 찾아가는 방법 확인
- 위치 안내 아이콘으로 내부 위치 확인
- 잘 모르겠을 때 대표 연락처로 바로 문의
- 복수 연락처가 있을 때 용도별 번호 확인
- 확인되지 않은 내용을 확정정보로 제공하지 않음

### 1.2 대표 이용 흐름

1. 민원인이 평소 쓰는 짧은 말로 검색한다.
2. 검색결과에서 자신에게 맞는 업무를 고른다.
3. 첫 안내문에서 가장 먼저 할 일을 확인한다.
4. 이용대상·준비물·비용·운영시간을 확인한다.
5. 방문 위치와 위치 안내 아이콘을 확인한다.
6. 더 확인할 내용은 대표 또는 용도별 연락처로 문의한다.

### 1.3 현재 문제

일부 원문은 민원인이 직접 읽는 문장이 아니라 직원이 검색 후 설명하기 위한 내부 안내 형식이다. 다음 표현은 내부 원문정보로는 보존하되 공개 화면에 그대로 노출하지 않는다.

- 담당
- 담당부서
- 담당자·직위
- 운영 상태
- 원문 기준
- 확인 질문
- 안내 멘트
- 공식 업무전화
- 특이사항 없음
- 복수 전화번호의 단순 나열

이 문제는 원본을 삭제하거나 덮어쓰는 방식으로 해결하지 않는다. 업무 원문과 검증상태는 내부 데이터에 보존하고, 같은 뜻을 노년층 민원인이 이해할 수 있는 별도 공개문장으로 제공한다.

### 1.4 2026-08-28 완료 기준선

| 항목 | 확인된 상태 |
|---|---:|
| 검색 대상 업무 | 63건 |
| 검색 별칭 | 316건 |
| `task_contacts` | 93행 |
| 연락처 연결 업무 | 51개 |
| primary 연락처 | 45행 |
| 실제 복수 연락처 업무 | 20개 |
| 보류 업무 | 12개 |
| 보류 업무의 활성 연락처 | 0행 |
| 전체 자동시험 | 64 passed |
| `git diff --check` | 통과 |

연락처 연결 업무 51개와 보류 업무 12개를 합하면 전체 업무 63개다. primary 45행은 연결 업무 수와 다른 지표이며, 연락처 93행과 복수 연락처 업무 20개도 서로 같은 개념이 아니다.

완료된 연락처·API·화면 연결 상태는 다음과 같다.

- 검색 API에 `primary_contact`와 `contacts`가 구현되어 있다.
- `contacts`에는 primary 연락처가 포함된다.
- 검색 결과 최대 10개 업무의 연락처를 SQL 한 번으로 조회하여 N+1 조회를 피한다.
- 상세 안내는 대표번호·용도·조건을 기존 영역에 표시하고, 전화번호는 `tel:` 링크로 제공한다.
- 화면 표시값은 `display_phone`을 우선 사용한다.
- SMS 안내는 `primary_contact`만 사용한다.
- A011 결핵 상담·관리의 대표번호는 `031-5189-4364`다.
- A012 결핵 검사는 용도별 연락처 5개를 보존한다.
- F101 결핵실 위치 안내의 대표번호는 `031-5189-4364`다.
- A011·A012·F101의 활성 연락처에는 `031-5189-4354`가 없다.
- 위치 안내 아이콘 이동, 검색, 추천어, 상세 안내와 SMS 기능을 유지한다.
- 연락처 화면 연결 작업에서 `public/index.html`과 `public/css/style.css`는 변경하지 않았다.

기준일 당시 운영 DB 스냅샷은 다음과 같다.

| 테이블·항목 | 수량·값 |
|---|---:|
| `tasks` | 63 |
| `aliases` | 316 |
| `event_logs` | 116 |
| `task_contacts` | 93 |
| 당시 DB SHA-256 | `5629c524f5052100ba1c8b78ed2268e4bc3a18b4427e280c2bba1a7e16f3a896` |

`event_logs`는 실제 검색 때마다 증가하므로 DB 파일의 물리 SHA-256도 달라질 수 있다. 위 해시는 영구 고정값이 아니라 2026-08-28 당시 상태의 스냅샷이다. 앞으로는 파일 해시 하나만으로 데이터 무결성을 판단하지 않고 다음을 함께 검사한다.

- `tasks`, `aliases`, `task_contacts`, primary 수량
- 업무·전화번호·용도의 자연키 중복
- 활성 primary 중복
- 고아 `task_id`
- `PRAGMA foreign_key_check`
- `PRAGMA integrity_check`
- A011·A012·F101 핵심 연락처

### 1.5 완료와 예정 구분

| 구분 | 상태 |
|---|---|
| 기존 63개 업무·316개 별칭 검색 | 완료·회귀보존 |
| `task_contacts` 1:N 구조와 검증 연락처 적용 | 완료 |
| 검색 API 연락처 일괄조회 | 완료 |
| 기존 상세 안내의 연락처 표시 | 완료 |
| SMS의 primary 연락처 사용 | 완료 |
| 위치 안내 아이콘 이동 | 완료·회귀보존 |
| 현재 프런트엔드 디자인 | 최종 확정·변경 금지 |
| 대표 업무 3건 선정과 공식 근거 연결 | 완료: A011·A012·R002 |
| 63개 업무의 노년층 민원인용 공개문구 | 예정 |
| 공개용 안내정보 별도 구조와 API 연결 | 예정 |
| 공식자료와 공개문구 전수 대조 | 예정 |
| 공개 운영 승인·KWCAG·사용성 인수시험 | 운영 전 필수 |

### 1.6 확인 필요와 보류

- `[확인 필요]` 63개 업무의 공개 제목·요약·첫 행동 문구와 공식 근거 연결
- `[확인 필요]` 이용대상·준비물·비용·운영시간의 업무별 공식 근거
- `[확인 필요]` `catalog_items`, `source_documents`, `document_chunks`와 각 FTS의 현재 운영 DB 수량
- 보류: 우편번호 등 공식 페이지 간 값이 충돌하는 기관정보
- 보류: H004, F105, F109, F111, F202, F203, F205, F206, F301, F302, F303, F304의 연락처

---

## 2. 수집 자료와 사용 방법

### 2.1 수집 결과

| 항목 | 수량·상태 |
|---|---|
| 첨부 표시 공식 게시물 | 507건 |
| 정상 완료 게시물 | 502건 |
| 본문 이미지 원본 예외가 있는 게시물 | 5건 |
| 공식 첨부파일 | 819개, 크기·SHA-256 검증 완료 |
| 본문 삽입 이미지 URL | 59개 |
| 유효 이미지 | 54개 |
| 전체 추출 레코드 | 889개 |
| 본문 추출 성공 | 888개 |
| 글자가 없는 이미지 | 1개 |
| 추출 실패 | 0개 |
| 엑셀 검수용 검색본문_청크 | 1,493개 |

통합 엑셀에는 현행 서비스 96행, 서비스 조사기록 187행, 기관정보 147행, 직원 업무 82행, 보건소식 920건, 고시공고 46건, 입찰공고 13건, 의료기관·약국 108건, 산후조리원 4건, 기타자료 8건도 정리되어 있다. 다만 서로 다른 자료유형을 한 테이블에 무리하게 합치지 않는다.

검색에 직접 쓰는 구조화 행은 1,424건이다.

| 구조화 검색 구역 | 수량 |
|---|---:|
| 현행 서비스·직원업무·시설·기타자료 및 기관 조사기록 | 445건 |
| 보건소식·고시공고·입찰공고 전체 제목 | 979건 |
| 합계 | 1,424건 |

서비스_원문기록 187행, 현행검색_24, 데이터오류_검증은 감사·검수용으로 보존하되 민원인 검색결과에 확정 정보처럼 직접 노출하지 않는다.

최종 원본 ZIP을 검색엔진용으로 다시 나누면 다음 수량이 된다.

| 검색 DB 대상 | 수량 |
|---|---|
| 게시글 문서 | 507개 |
| 첨부·삽입이미지·압축내부 문서 | 889개 |
| source_documents 전체 | 1,396개 |
| 검색 가능한 문서 | 1,360개 |
| 3,000자 검색 청크 | 2,075개 |

게시글 본문 중 유효한 값은 472개다. 빈 본문 27개와 문자열 undefined 8개는 메타데이터만 보존하고 검색에서는 제외한다. 추출 레코드는 889개 중 888개가 검색 가능하며, 글자가 없는 이미지 1개는 검색에서 제외한다.

본문 이미지 예외 5건은 공식 서버가 HTML 오류 응답을 반환한 4건과 이전 CMS가 HTTP 502를 반환한 1건이다. 해당 게시글과 공식 첨부파일은 보존되어 있으므로 전체 수집 실패와 혼동하지 않는다.

### 2.2 프로젝트에 사용할 파일

| 파일 | 용도 |
|---|---|
| 보건민원_검색엔진_MVP.zip | 실행 가능한 기본 코드 |
| 동탄구보건소_공식정보_수집본_2026-08-26.xlsx | 구조화 데이터와 검색용 청크 |
| 동탄구보건소_첨부파일_2차수집_2026-08-26.zip | 원본 첨부·추출본문·매니페스트 |
| data/source/동탄구보건소_검색업무별_공식연락처_확정대조_2026-08-28.xlsx | 연락처 93행의 최종 검증자료, SHA-256 `95862ee7a5bfdf7e349208ae6eeafe19353a1ff8bf97f975d9fd18937a7a253e` |
| 동탄구보건소_검색업무별_공식연락처_매칭검토_2026-08-27.xlsx | 확정 전 후보·대조 이력 보존용 |
| 20260826_175705.jpg | 현재 `hero-dongtan.jpg`의 원본 근거. 확정 배경은 교체·재복사하지 않음 |
| 프로젝트기획서_보건민원 정보 검색 사이트.pdf | 최초 요구사항 기준 |
| 노강우_보건소정보검색서비스_수정PRD.docx의 사본.docx | 고령층 UX·접근성·전화/QR·운영 기준 |
| index(1).html | 63개 업무·별칭·층별 지도 원본 |
| index(3).html | 선택 결과에 따라 위치 아이콘을 이동시키는 JavaScript 참고자료 |

`index(1).html`은 63개 업무·별칭·층별 위치자료의 역사적 기준이고, `index(3).html`은 위치 마커 동작의 구현 근거다. 현재 `public/js/app.js`에 결과별 마커 이동이 반영되어 있으므로 두 HTML을 다시 옮기거나 덮어쓰지 않는다.

### 2.3 검색엔진에 넣을 것과 넣지 않을 것

| 자료 | 처리 |
|---|---|
| 서비스_현행 96행 | 현행 서비스 검색의 최우선 자료 |
| 기관정보_전수 147행 | 기관·조직·시설 안내 검색. 오류 경고는 별도 보존 |
| 직원_업무_82 82행 | 소속·직위·업무·공식 업무전화 검색. 성명 추측 금지 |
| 의료기관약국_108·산후조리원_4 | 시설명·주소·전화 검색 |
| 보건소식_920·고시공고_46·입찰공고_13 | 첨부가 없는 게시물까지 포함하는 전체 제목 색인 |
| 기타자료_8 | 감염병·교육·사진자료 검색 |
| posts_manifest.json | 게시글 507건의 메타데이터와 게시글 본문 |
| extraction_manifest.json | 첨부·이미지·압축내부 추출 레코드 889건 |
| extracted_text 폴더 | 검색할 전체 추출본문 |
| collection_summary.json·extraction_summary.json | 적재 전후 수량 검증 |
| 검색본문_청크 시트 | 엑셀 검수·표본검색·교차검증용 |
| 첨부게시물_507 시트 | 관리자 검수와 게시물 메타데이터 확인 |
| 첨부본문_추출 시트 | 추출 방식·OCR 상태·SHA-256 검증 |
| 데이터오류_검증 시트 | 관리자만 확인, 민원인에게 확정 사실처럼 표시 금지 |
| 게시글HTML_청크 시트 | 검색 DB에 넣지 않음. HTML 노이즈와 XSS 위험 방지 |
| 176MB 원본 ZIP | 감사·재추출용으로 보존하고 웹에서 직접 배포하지 않음 |
| OCR 본문 | 검색 보조값으로 사용하되 공식 원문 확인 문구 표시 |

실제 런타임 적재는 최종 JSON 매니페스트와 extracted_text를 사용한다. 이렇게 해야 게시물·첨부·OCR·SHA-256·추출방법을 잃지 않고 Windows에서도 상대경로로 원문을 추적할 수 있다. 엑셀의 검색본문_청크 1,493행은 적재 결과를 교차검증하는 자료로 사용한다. HWP·PDF 파일을 사용자 PC에서 다시 OCR할 필요는 없다.

단, 현행 서비스·기관·직원업무·시설과 첨부 없는 게시물 제목은 JSON ZIP에 모두 들어 있지 않으므로 통합 엑셀에서 별도로 적재한다. 즉 “구조화 엑셀 색인”과 “원본 JSON·TXT 본문 색인”을 함께 사용한다.

---

## 3. 구현 구조와 디자인 고정 기준

~~~mermaid
flowchart LR
    U[노년층 민원인 브라우저] --> F[현재 HTML CSS JavaScript]
    F --> A[Flask API]
    A --> T[업무 63건과 별칭 316건]
    A --> C[연락처 93행]
    A --> D[공식 수집자료]
    T --> S[(SQLite FTS5)]
    C --> S
    D --> S
    A -. 기본 OFF .-> L[선택적 LLM 검색어 확장]
    A -. mock .-> M[문자 서비스]
~~~

### 3.1 사용기술의 현재 역할

| 기술 | 역할 | 상태 |
|---|---|---|
| Python 3.12·Flask | 검색·연락처·위치·SMS API | 사용 |
| SQLite·FTS5 | 업무·별칭·연락처·공식자료 저장과 검색 | 사용 |
| HTML·CSS·JavaScript | 현재 확정 화면과 데이터 바인딩 | 사용·디자인 고정 |
| pytest | 임시 DB 기반 회귀시험 | 사용 |
| Streamlit | 내부 읽기 전용 검수 | 필요 시 사용 |
| OpenAI API | 결과 0건의 선택적 검색어 확장 | 기본 OFF |
| 실제 문자 발송 | 기관 승인 전 사용하지 않음 | mock 유지 |
| 공개 배포 | 보안·개인정보·운영승인 후 별도 판단 | 보류 |

### 3.2 디자인 완전 고정 원칙

현재 `http://127.0.0.1:5000`에서 보이는 화면을 최종 디자인으로 확정한다. 사용자 승인 여부와 관계없이 다음 항목을 변경하지 않는다.

- 전체 레이아웃과 헤더
- 화성특례시 로고와 동탄구보건소 표기
- 배경사진, crop, 확대율, 위치와 어두운 overlay
- 구름과 나뭇가지 애니메이션을 포함한 기존 애니메이션 방식
- Hero 문구, 검색창의 위치와 형태, 추천 검색어 영역
- 검색 결과·상세 안내·위치 안내 패널
- 층별 배치도, 위치 아이콘과 이동 방식
- SMS 창
- 색상, 글꼴, 글자 크기와 두께
- 여백, 간격, 테두리와 그림자
- 버튼 모양·위치와 아이콘
- 반응형 기준과 줄바꿈
- 기존 DOM 구조와 기존 CSS class

`public/index.html`, `public/css/style.css`, 배경·이미지·글꼴 파일은 디자인 목적으로 수정하지 않는다. 새로운 카드, 박스, 버튼, 탭, 제목, 아이콘, 팝업 또는 화면 구역을 만들지 않는다. 기존 요소를 삭제하거나 이동하거나 순서를 바꾸지 않는다. 현재 모션은 보존 대상이며 추가·교체·조정 대상이 아니다.

### 3.3 허용되는 콘텐츠 변경

다음만 기존 화면 안에서 허용한다.

- 기존 영역의 문구와 라벨 교체
- 기존 필드에 표시되는 검증 데이터 교체
- 기존 `전화로 문의하기` 영역의 확정 연락처 표시
- 기존 위치 안내의 확정 위치 표시
- 검증된 검색 별칭 추가
- 기존 상세 안내 영역의 민원인용 문장 표시
- 시각적 결과를 바꾸지 않는 접근성 속성 보완

향후 `public/js/app.js`를 수정할 때도 기존 DOM과 CSS class를 그대로 두고 텍스트·데이터 바인딩만 최소 변경한다.

내용이 현재 영역에 맞지 않으면 다음 순서로 처리한다.

1. 문장을 더 짧게 쓴다.
2. 중복 설명을 없앤다.
3. 가장 중요한 행동을 먼저 알린다.
4. 그래도 표시하기 어려운 정보는 보류목록에 기록한다.

패널 크기 변경, 글자 크기 축소, 여백 축소, 임의 스크롤 추가, 새 상세영역 추가, CSS 수정 또는 화면 재배치로 정보량 문제를 해결하지 않는다.

### 3.4 공개 라벨 전환표

| 내부 원문 표현 | 공개 화면 기본 표현 |
|---|---|
| 담당 | 문의하는 곳 |
| 담당부서 | 담당하는 곳 |
| 담당자·직위 | 문의 안내 |
| 운영 상태 | 최근 확인일 |
| 확인 질문 | 이런 경우 이용하세요 |
| 안내 멘트 | 이렇게 이용하세요 |
| 공식 업무전화 | 전화로 문의하기 |
| 주의사항 | 방문 전 확인사항 |

업무 내용에 맞게 자연스러운 쉬운 한국어로 다듬되 뜻을 바꾸지 않는다. 확인되지 않은 정보는 `방문 전에 전화로 확인해 주세요.` 또는 `현재 공식자료를 확인하고 있습니다.`라고 안내한다.

다음 내부 상태 표현은 공개 화면에 사용하지 않는다.

- 원문 기준
- 내부 검토 중
- 담당자 미확정
- 데이터 없음
- `conflict`
- `ambiguous`
- `unmatched`
- `probable_review`
- `[공식 확인 필요]`

내부 상태값은 DB와 관리자용 검토자료에만 보존한다.

### 3.5 노년층 민원인용 문장 원칙

- 쉬운 한국어와 존댓말을 쓴다.
- 한 문장에는 한 가지 행동만 안내한다.
- 행정용어를 설명 없이 단독으로 쓰지 않는다.
- 65세 이상 사용자가 실제로 쓰는 말과 검색어를 반영한다.
- 결과 첫 문장에서 다음 행동을 알 수 있게 한다.
- 담당하는 곳보다 민원인이 해야 할 일을 먼저 설명한다.
- 대표전화부터 표시하고 추가 번호는 용도별로 나눈다.
- 이용대상·준비물·비용·운영시간을 추측하지 않는다.
- 공식자료로 확인되지 않은 정보를 확정적으로 쓰지 않는다.
- 내부 검증정보를 공개하지 않는다.
- 빈 항목에 의미 없는 문구를 반복하지 않는다.
- 길고 복합적인 문장보다 짧고 직접적인 문장을 쓴다.
- 전화 문의와 방문 위치를 분명히 구분한다.

### 3.6 정보의 논리적 우선순위

1. 어떤 민원을 처리할 수 있는지
2. 가장 먼저 무엇을 해야 하는지
3. 전화로 어디에 문의하는지
4. 어디로 방문하는지
5. 이용 대상
6. 준비물
7. 비용
8. 운영시간
9. 방문 전 확인사항
10. 추가 연락처와 담당하는 곳
11. 최근 공식 확인일

이 순서는 화면 요소를 재배치한다는 뜻이 아니다. 현재 디자인과 기존 항목 순서를 그대로 유지하면서 각 문장의 앞부분에 더 중요한 정보를 둔다는 뜻이다.

### 3.7 내부 원문과 공개 안내정보 분리

기존 `tasks`와 `task_contacts`는 원문·연락처 근거로 보존한다. 직원용 원문정보와 공개문장을 같은 필드에 덮어쓰지 않는다.

향후 공개 안내정보는 다음 별도 필드로 관리하는 설계를 사용한다.

| 공개 필드 | 의미 |
|---|---|
| `public_title` | 노년층 민원인이 이해하기 쉬운 업무명 |
| `public_summary` | 핵심 행동을 먼저 알리는 짧은 설명 |
| `eligibility` | 이용 대상 |
| `documents` | 준비할 서류·물품 |
| `fee` | 공식 확인된 비용 |
| `operating_hours` | 업무별 운영시간 |
| `visit_steps` | 방문·이용 순서 |
| `public_caution` | 방문 전 확인사항 |
| `primary_action` | 가장 먼저 해야 할 행동 |
| `verified_date` | 공개내용의 공식 확인일 |

이 필드는 설계안이며 이번 문서 갱신에서는 DB나 코드로 구현하지 않는다. 모든 공개 데이터는 원문 `task_id`와 공식 출처에 연결하여 출처를 추적할 수 있어야 한다. 연락처는 별도 `task_contacts` 1:N 구조를 계속 사용하며 공개 안내 필드에 중복 저장하지 않는다.

---

## 4. Windows에서 자료 배치하기

### 4.1 권장 프로젝트 경로

현재 사용 중인 경로를 그대로 사용한다.

~~~text
C:\Users\corle\OneDrive\바탕 화면\보건민원_검색엔진_MVP
~~~

경로에 한글과 공백이 있으므로 PowerShell에서는 항상 Set-Location -LiteralPath와 따옴표를 사용한다.

### 4.2 파일 배치

1. 보건민원_검색엔진_MVP.zip의 내용을 위 폴더에 푼다.
2. 프로젝트 안에 source_data 폴더를 만든다.
3. 공식정보 엑셀을 source_data 폴더에 복사한다.
4. 2차 수집 ZIP은 source_data 폴더 아래에 풀어 둔다.
5. 현재 `public\images\hero-dongtan.jpg`와 다른 디자인 자산은 그대로 보존한다.

PowerShell 예시:

~~~powershell
Set-Location -LiteralPath 'C:\Users\corle\OneDrive\바탕 화면\보건민원_검색엔진_MVP'
New-Item -ItemType Directory -Force source_data

Copy-Item -LiteralPath 'C:\Users\corle\Downloads\동탄구보건소_공식정보_수집본_2026-08-26.xlsx' -Destination '.\source_data\' -ErrorAction Stop
~~~

배경 원본의 확인된 SHA-256은 `ec53099e0e40ace51ab9c384bd93cd4318f749a67613e5786323eff7b5aa4c6e`다. 이 값은 현재 디자인 자산의 이력 확인용이며, 배경을 다시 복사하거나 교체하는 명령으로 사용하지 않는다.

압축을 풀기 전에는 수집자료 ZIP이 전송 중 손상되지 않았는지 다음 명령으로 확인한다.

~~~powershell
(Get-FileHash -Algorithm SHA256 -LiteralPath 'C:\Users\corle\Downloads\동탄구보건소_첨부파일_2차수집_2026-08-26.zip').Hash.ToLower()
~~~

정상값은 다음과 정확히 같아야 한다.

~~~text
51e63be7421d4c66072a87a9eca98704453badc62a6f40d1eba163ea2d6f92cb
~~~

다르면 압축을 풀지 말고 파일을 다시 내려받는다.

정상값을 확인했으면 압축을 풀고 핵심 파일이 있는지 확인한다.

~~~powershell
if (Test-Path '.\source_data\attachments_second_pass') { throw '기존 attachments_second_pass 폴더가 있습니다. 삭제하지 말고 이름을 바꾼 뒤 다시 실행하십시오.' }
Expand-Archive -LiteralPath 'C:\Users\corle\Downloads\동탄구보건소_첨부파일_2차수집_2026-08-26.zip' -DestinationPath '.\source_data\'

Test-Path '.\source_data\attachments_second_pass\manifests\posts_manifest.json'
Test-Path '.\source_data\attachments_second_pass\manifests\extraction_manifest.json'
~~~

두 Test-Path 결과가 모두 True여야 한다.

### 4.3 완료 후 폴더 구조

~~~text
보건민원_검색엔진_MVP/
├─ .venv/
├─ admin/
├─ data/
│  ├─ health_search.db
│  ├─ home_shortcuts.json
│  ├─ map_points.json
│  ├─ tasks.json
│  └─ source/
│     └─ 동탄구보건소_검색업무별_공식연락처_확정대조_2026-08-28.xlsx
├─ public/
│  ├─ css/style.css
│  ├─ js/app.js
│  ├─ images/hero-dongtan.jpg
│  ├─ images/floor-1.jpg
│  ├─ images/floor-2.jpg
│  └─ images/floor-3.jpg
├─ scripts/
├─ source_data/
│  ├─ 동탄구보건소_공식정보_수집본_2026-08-26.xlsx
│  └─ attachments_second_pass/
├─ sql/
├─ tests/
├─ app.py
├─ db.py
├─ search_engine.py
└─ requirements-dev.txt
~~~

### 4.4 Git 제외 항목

176MB 원본과 비밀키를 GitHub에 올리지 않는다. .gitignore 끝에 다음을 추가한다.

~~~gitignore
.env
.venv/
.tools/
source_data/
data/*.db
data/backups/
reports/private/
__pycache__/
.pytest_cache/
~~~

`.env.example`은 설치 안내용이므로 Git에 남긴다. `*.env*`처럼 범위가 넓은 규칙을 사용해 `.env.example`까지 숨기지 않는다.

---

## 5. VS Code와 Codex 열기

### 5.1 VS Code에서 프로젝트 열기

1. VS Code를 실행한다.
2. 파일 → 폴더 열기를 누른다.
3. 보건민원_검색엔진_MVP 폴더를 선택한다.
4. 왼쪽 탐색기에 app.py, db.py, public, data가 보이는지 확인한다.

### 5.2 Python 인터프리터 선택

1. Ctrl+Shift+P를 누른다.
2. Python: Select Interpreter를 입력한다.
3. 다음 파일을 선택한다.

~~~text
.\.venv\Scripts\python.exe
~~~

목록에 없다면 Enter interpreter path를 눌러 직접 선택한다.

### 5.3 Codex 열기

VS Code 왼쪽의 Codex 아이콘을 누른다. 아이콘이 보이지 않으면 Ctrl+Shift+P를 누르고 Codex: Open Codex Sidebar를 실행한다.

OpenAI 공식 문서도 “프로젝트를 먼저 열고, 관련 파일을 문맥으로 제공하며, 변경 전후 Git 체크포인트를 만들고, 편집 결과의 diff를 검토할 것”을 권장한다.

### 5.4 Codex 사용 원칙

- 한 번에 한 단계만 요청한다.
- 먼저 관련 파일을 읽고 계획을 말하게 한다.
- 변경할 파일 범위를 명시한다.
- 변경 후 자동시험을 실행하게 한다.
- 테스트가 실패하면 다음 단계로 넘어가지 못하게 한다.
- .env의 실제 API 키를 채팅에 붙여 넣지 않는다.
- Codex가 바꾼 파일은 VS Code의 변경 비교 화면에서 확인한다.
- React·Next.js로 재작성하지 않고 현재 HTML·CSS·JavaScript·Flask 구조를 유지한다.
- 수정 PRD의 JSON 초기안을 이유로 현재 SQLite·FTS·수집자료를 제거하지 않는다.
- 요구사항, 현재 구현상태, 향후 선택기능을 서로 다른 문장으로 보고하게 한다.
- 운영 DB를 바꾸기 전에 Flask 서버를 종료하고 날짜·시각이 포함된 새 백업을 만든다.
- 테스트는 실제 `data\health_search.db`가 아닌 임시 DB를 사용하게 한다.
- 프런트의 문구·데이터 바인딩은 360/390/768/1440px, 키보드, 고대비와 현재 반응형 상태를 함께 확인한다.
- 공식 연락처·위치를 추측하지 않고 출처 URL과 확인일을 함께 보존한다.

모든 프롬프트 마지막에는 다음 문장을 붙인다.

~~~text
이 단계 밖의 기능은 변경하지 마라.
완료 후 변경 파일, 실행 명령, 테스트 결과, 남은 위험을 보고하고 멈춰라.
~~~

### 5.5 각 단계가 끝난 뒤 확인

~~~powershell
git status
git diff --check
git diff --stat
~~~

VS Code 왼쪽 소스 제어에서 Codex가 변경한 파일만 열어 비교한다. 테스트가 통과하면 해당 단계 파일만 선택해 커밋한다. .env, source_data, data\*.db는 선택하면 안 된다. git status가 “not a git repository”라고 하면 소스 제어의 리포지토리 초기화를 한 번 누른 뒤 다시 확인한다.

---

## 6. 실행 환경과 현재 서비스 확인

### 6.0 실행 확인 목적

코드를 고치기 전에 현재 상태가 실행되는지 확인한다.

### 6.1 PowerShell 실행

VS Code 메뉴에서 터미널 → 새 터미널을 연다.

~~~powershell
Set-Location -LiteralPath 'C:\Users\corle\OneDrive\바탕 화면\보건민원_검색엔진_MVP'
Test-Path '.\.venv\Scripts\python.exe'
.\.venv\Scripts\python.exe --version
~~~

예상 결과:

~~~text
True
Python 3.12.10
~~~

### 6.2 PowerShell 활성화 오류를 피하는 방법

Activate.ps1을 실행하지 않아도 된다. 아래처럼 가상환경 안의 python.exe를 직접 사용하면 실행정책 오류가 발생하지 않는다.

~~~powershell
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
~~~

이 방법을 이 매뉴얼의 기본 방식으로 사용한다.

활성화를 꼭 하고 싶다면 현재 PowerShell 창에만 다음 설정을 적용한다.

~~~powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force
.\.venv\Scripts\Activate.ps1
~~~

### 6.3 환경파일과 운영 DB 보호

현재 `data/health_search.db`에는 업무·별칭·검증 연락처가 반영되어 있으므로 `scripts/init_db.py`로 다시 초기화하지 않는다. 기준일 수량은 `tasks` 63건, `aliases` 316건, `task_contacts` 93행이다.

DB를 변경하는 후속 작업은 반드시 다음 순서를 지킨다.

1. Flask 서버를 정상 종료한다.
2. 운영 DB의 물리 해시와 논리 수량을 기록한다.
3. SQLite backup API로 시각이 포함된 복구본을 만든다.
4. 같은 코드를 임시 DB에 먼저 적용한다.
5. 변경예정 내용을 사용자에게 보고하고 별도 승인을 받는다.
6. 단일 트랜잭션으로 적용하고 commit 전 무결성 검사를 통과한다.

`scripts/init_db.py`는 운영 DB가 없는 새 환경에서만 사용한다. 연락처가 없는 과거 초기 DB 상태를 현재 정상 상태로 해석하지 않는다.

### 6.4 자동시험

~~~powershell
.\.venv\Scripts\python.exe -m pytest -q
~~~

테스트 개수는 기능 추가에 따라 달라지므로 특정 `passed` 숫자를 완료조건으로 고정하지 않는다. 최신 전체 시험에서 실패가 0이어야 하며, 실패가 있으면 전체 오류 문장을 Codex에 붙여 넣고 다음 단계로 넘어가지 않는다.

### 6.5 서버 실행

~~~powershell
.\.venv\Scripts\python.exe app.py
~~~

브라우저에서 다음 주소를 연다.

~~~text
http://127.0.0.1:5000
~~~

종료할 때는 터미널에서 Ctrl+C를 누른다.

### 6.6 상태 API 확인

새 PowerShell 터미널에서 실행한다.

~~~powershell
Invoke-RestMethod -Uri 'http://127.0.0.1:5000/api/health'
~~~

task_count가 63, data_backend가 sqlite, llm_enabled가 False, sms_mode가 mock이면 정상이다.

### 6.7 이 단계의 Codex 프롬프트

~~~text
현재 보건민원_검색엔진_MVP 프로젝트를 읽기 전용으로 점검해라.
Python 3.12와 .venv를 사용한다.
아직 코드는 수정하지 마라.

1. 프로젝트 구조와 실행 진입점을 설명하라.
2. requirements-dev.txt 설치 여부를 확인하라.
3. data/health_search.db가 있으면 다시 초기화하지 말고 업무 63건과 별칭 316건을 조회하라. DB가 없을 때만 scripts/init_db.py를 실행하라.
4. pytest 전체를 실행하라.
5. app.py를 실행하기 전 발생 가능한 오류를 보고하라.

검사 결과와 정확한 다음 명령만 보고하고 멈춰라.
~~~

### 6.8 실행 확인 완료 기준

- Python 3.12.10이 확인된다.
- 가상환경 python.exe를 직접 실행할 수 있다.
- SQLite 업무 63건이 생성된다.
- 자동시험이 모두 통과한다.
- http://127.0.0.1:5000이 열린다.

---

## 7. 확정된 화면의 보존 기준

이 절은 새 화면을 만드는 단계가 아니다. 현재 화면을 회귀검사할 때 사용할 고정 기준이다.

### 7.1 고정할 화면

| 영역 | 고정 기준 |
|---|---|
| 배경 | 현재 하늘 사진, crop, 확대율, 위치, 밝기와 어두운 overlay |
| 상단 | 화성특례시 로고, 동탄구보건소 표기, 구분선, 배치와 여백 |
| Hero | 현재 서비스 표식, 큰 제목, 움직이는 설명문, 글꼴·두께·행간·정렬·간격 |
| 검색 | 검색창, 검색 버튼, 추천어, 유리 질감, 위치와 크기 |
| 결과 | 빈 상태, 결과 카드, 상세 안내, 연락처, 위치 안내와 배치도 |
| 모션 | 현재 구름·나뭇가지·설명문·위치 아이콘 움직임과 모션 감소 동작 |
| 반응형 | 현재 1440·768·390·360px 배치와 줄바꿈 |

빨간색·노란색 테두리나 흐릿한 사각형은 과거 설명 이미지의 가이드일 뿐 실제 화면 요소가 아니다.

### 7.2 회귀 확인 항목

- 검색·Enter 입력·추천어·지우기가 이전과 같다.
- 결과 선택과 상세 dialog가 이전과 같다.
- 층 선택과 위치 아이콘 이동이 이전과 같다.
- 연락처와 SMS 동작이 이전과 같다.
- 데스크톱·태블릿·모바일에서 가로 넘침과 새 겹침이 없다.
- 콘솔 오류와 정적 자산 404가 없다.
- `prefers-reduced-motion`에서 현재 정의된 모션 감소 동작이 유지된다.

화면이 고정 기준과 다르면 문구·데이터 바인딩 변경에서 생긴 회귀인지 확인한다. 디자인 속성을 조정하여 해결하지 않는다.

### 7.3 디자인 검증 기록 원칙

기준 화면을 캡처하거나 DOM 계산값을 측정하는 것은 허용되지만, 검증 과정에서 운영 검색 API를 호출해 `event_logs`를 늘리지 않는다. 기능시험은 임시 DB 또는 이미 승인된 비기록 방식으로 수행한다.

화면 검증 보고에는 다음만 기록한다.

- 1440·768·390·360px의 가로 넘침과 겹침 여부
- 현재 글꼴·두께·간격·배경 crop·overlay 유지 여부
- 검색·상세·위치·연락처·SMS 회귀 결과
- 콘솔 오류와 정적 자산 404 여부
- 모션 감소 설정의 현재 동작 유지 여부

검증에서 발견된 문구 문제는 제3.3절의 콘텐츠 변경 절차로 해결한다. 디자인 차이는 수정하지 않고 고정 기준과의 회귀로 분류한다.

---

## 8. 수집자료·SQLite FTS 기술 기록

### 8.0 수집자료 적재 목적

이 절은 수집자료와 FTS importer의 유효한 기술 기록을 보존한다. 구조화 정보 1,424건, 게시글 507건, 추출 레코드 889건, 검색 가능 문서 1,360개와 3,000자 단위 청크 2,075개는 원본·적재 목표 수량이다. 운영 DB의 현재 테이블 수량과 동일하다고 자동 간주하지 말고 후속 작업 전 읽기 전용으로 다시 확인한다. 이 적재 작업은 제18절의 남은 일주일 일정에 포함하지 않는다.

### 8.A 구조화 엑셀 1,424건 적재

#### 8.A.1 직접 색인할 시트

| 시트 | item_type | 행 수 | 검색 역할 |
|---|---|---:|---|
| 서비스_현행 | service | 96 | 현행 대상·시간·비용·준비물·절차·연락처 |
| 기관정보_전수 | institution | 147 | 조직·시설·주소·운영 안내 |
| 직원_업무_82 | staff | 82 | 소속·직위·업무·공식 업무전화 |
| 보건소식_920 | news | 920 | 첨부 없는 글까지 포함한 전체 게시물 제목 |
| 고시공고_46 | notice | 46 | 전체 고시공고 제목 |
| 입찰공고_13 | bid | 13 | 전체 입찰공고 제목 |
| 의료기관약국_108 | medical_pharmacy | 108 | 시설명·종류·주소·전화 |
| 산후조리원_4 | postpartum | 4 | 시설명·주소·전화·공식 표시 이용료 |
| 기타자료_8 | other | 8 | 감염병·교육·사진자료 |
| 합계 |  | 1,424 |  |

서비스_원문기록, 현행검색_24, 데이터오류_검증과 2차 수집 검수 시트는 원본 엑셀에 그대로 보존한다. 이들은 감사·품질검사용이며 민원인 결과의 확정 답변으로 직접 색인하지 않는다.

#### 8.A.2 의존성 추가

scripts/import_catalog.py에서만 엑셀을 읽는다. Codex가 requirements-dev.txt에 다음 한 줄을 추가하게 한다.

~~~text
openpyxl>=3.1,<4
~~~

웹서버는 적재가 끝난 SQLite만 읽으므로 운영 중 매 요청마다 엑셀을 열지 않는다.

스키마를 만들기 전에 Python에 포함된 SQLite가 trigram FTS5를 지원하는지 확인한다.

~~~powershell
.\.venv\Scripts\python.exe -c "import sqlite3; c=sqlite3.connect(':memory:'); c.execute(\"CREATE VIRTUAL TABLE temp.fts_probe USING fts5(x, tokenize='trigram')\"); print(sqlite3.sqlite_version, 'FTS5 trigram OK')"
~~~

오류가 나면 그대로 진행하지 않는다. Codex에 오류 전문을 주고 catalog_items_fts와 document_chunks_fts를 unicode61로 만들되, 한국어 부분일치는 파라미터화된 LIKE로 보완하게 한다.

#### 8.A.3 구조화 테이블

sql/sqlite_schema.sql에 다음 구조를 추가한다.

~~~sql
CREATE TABLE IF NOT EXISTS catalog_items (
    id TEXT PRIMARY KEY,
    item_type TEXT NOT NULL CHECK(item_type IN (
        'service','institution','staff','news','notice','bid',
        'medical_pharmacy','postpartum','other'
    )),
    source_sheet TEXT NOT NULL,
    source_row INTEGER NOT NULL,
    title TEXT NOT NULL,
    category TEXT,
    body TEXT NOT NULL,
    plain_description TEXT,
    preparation TEXT,
    department TEXT,
    location_text TEXT,
    phone TEXT,
    address TEXT,
    posted_at TEXT,
    source_url TEXT NOT NULL,
    checked_at TEXT,
    warning TEXT,
    imported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(source_sheet, source_row)
);

CREATE INDEX IF NOT EXISTS idx_catalog_items_type
ON catalog_items(item_type);

CREATE INDEX IF NOT EXISTS idx_catalog_items_date
ON catalog_items(posted_at);

CREATE VIRTUAL TABLE IF NOT EXISTS catalog_items_fts USING fts5(
    title,
    category,
    body,
    item_id UNINDEXED,
    tokenize='trigram'
);
~~~

`catalog_items`와 공개 안내 필드의 실제 적재 상태는 후속 작업 전에 다시 확인한다. 공개문장은 기존 `tasks` 원문 필드에 덮어쓰지 않고 제3.7절의 별도 구조를 사용한다.

업무별 연락처는 다음 1:N 구조로 구현되어 있으며 기준일 현재 93행이다.

~~~sql
CREATE TABLE IF NOT EXISTS task_contacts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    phone TEXT NOT NULL CHECK(length(trim(phone)) > 0),
    display_phone TEXT NOT NULL CHECK(length(trim(display_phone)) > 0),
    label TEXT NOT NULL CHECK(length(trim(label)) > 0),
    note TEXT,
    contact_role TEXT,
    condition_text TEXT,
    is_primary INTEGER NOT NULL DEFAULT 0 CHECK(is_primary IN (0, 1)),
    source_url TEXT NOT NULL CHECK(length(trim(source_url)) > 0),
    source_urls_json TEXT NOT NULL DEFAULT '[]',
    source_sheet TEXT NOT NULL CHECK(length(trim(source_sheet)) > 0),
    source_row INTEGER NOT NULL CHECK(source_row >= 2),
    verified_at TEXT NOT NULL CHECK(length(trim(verified_at)) > 0),
    match_status TEXT NOT NULL CHECK(match_status IN (
        'confirmed', 'confirmed_multiple', 'conditional'
    )),
    active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0, 1)),
    UNIQUE(task_id, phone, label)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_task_contacts_one_active_primary
ON task_contacts(task_id)
WHERE is_primary = 1 AND active = 1;

CREATE INDEX IF NOT EXISTS idx_task_contacts_task_active
ON task_contacts(task_id, active);
~~~

DB 연결을 열 때마다 `PRAGMA foreign_keys = ON`을 실행한다. 자연키 중복, 활성 primary 중복과 존재하지 않는 `task_id`는 DB 제약 및 임시 DB 시험으로 차단한다.

#### 8.A.4 매핑 원칙

- 각 시트의 첫 행 헤더가 이 매뉴얼의 헤더와 다르면 즉시 중단한다.
- id는 sheet 이름과 해당 행의 업무키를 SHA-256으로 해시한 안정적인 문자열을 사용한다.
- service의 title은 서비스명, body는 적용상태·대상·시간·비용·준비물·절차·장소·주의사항을 줄바꿈으로 결합한다.
- institution의 title은 구분, body는 공식 페이지 표시내용이다.
- institution은 과거 표현·페이지 충돌도 포함하므로 warning에 “기관 조사기록 — 현재 적용 여부와 공식 원문 확인”을 항상 넣고, 본문 속 전화번호를 현재 연락처 필드로 추출하지 않는다.
- staff의 title은 소속과 직위, body는 업무다. 공식 페이지에 없는 직원 성명은 만들지 않는다.
- staff의 행에는 URL 열이 없으므로 공식 직원안내 URL https://www.hscity.go.kr/health/organ/BD_selectHealthOrganList.do?q_healthNm=dongtan 를 공통 출처로 사용한다.
- news·notice·bid의 title은 제목, posted_at은 표시일, source_url은 원문 URL이다.
- medical_pharmacy와 postpartum의 title은 명칭, body는 유형·주소·전화·공식 표시정보다.
- phone은 서비스·직원업무·시설 시트의 전용 열에서만 가져오고, 서술형 본문에서 정규식으로 전화번호를 추측하지 않는다. `--`는 빈값으로 저장한다.
- 모든 외부 URL은 `https:`이며 hostname이 정확히 `hscity.go.kr`이거나 `.hscity.go.kr`로 끝나는지 검사한다.
- 행별 URL이 비어 있으면 요약 시트에 기록된 해당 시트의 대표 공식 원문만 대체 출처로 사용하고, 대표 원문도 없으면 실패한다.
- 빈 셀은 빈 문자열로 다루고 문자열 None이나 nan을 본문에 넣지 않는다.
- 수집본 원본 셀을 수정하지 않는다.
- 데이터오류_검증의 충돌 항목은 별도 관리자 경고로 보존하고, 안전한 적용 기준이 정해지기 전에는 확정 표시하지 않는다.

PRD 필드에 쓰는 원본 헤더는 다음처럼 고정한다. 없는 값을 다른 문장에서 추측하지 않는다.

| 시트 | `plain_description` | `preparation` | `department` | `location_text` |
|---|---|---|---|---|
| 서비스_현행 | 별도 검수 전 빈값 | `준비물` | 공식 부서 열이 없어 빈값 | `주소·장소` |
| 직원_업무_82 | 빈값 | 빈값 | `소속` | 빈값 |
| 의료기관약국_108 | 빈값 | 빈값 | 빈값 | `주소` |
| 산후조리원_4 | 빈값 | 빈값 | 빈값 | `주소` |
| 기관정보_전수·게시판·기타자료 | 빈값 | 빈값 | 빈값 | 명시적 위치 열이 있을 때만 사용 |

`서비스_현행`의 연락처 셀에 번호가 하나만 있으면 검증 후 `phone`에 넣을 수 있다. 번호가 여러 개거나 조건문이 섞이면 원문을 `body`에 보존하고 `phone`은 비워 `tel:` 링크를 만들지 않으며 `warning`에 “복수·조건부 연락처 검수 필요”를 남긴다.

#### 8.A.5 수정 PRD 업무정보 필드 매핑

PRD의 업무표를 별도 중복 DB로 만들지 않고 기존 `tasks`, `aliases`, `catalog_items`와 연락처 구조에 연결한다.

| PRD 항목 | 현재 저장 위치·처리 |
|---|---|
| 업무명 | `tasks.name` 또는 `catalog_items.title` |
| 쉬운 설명 | 검수된 `tasks.plain_description` 또는 `catalog_items.plain_description`. 기존 `script`는 검수 후 1회 이관 |
| 준비물 | `tasks.preparation` 또는 `catalog_items.preparation`. 현행 서비스 자료의 검증값만 이관하고 없으면 빈값 |
| 소관 부서 | `tasks.department` 또는 구조화 서비스의 공식 부서 필드 |
| 대표전화 | `task_contacts`의 활성 primary를 사용하고 출처·확인일을 함께 보존 |
| 위치 | `floor`, `place`, `route`를 이용해 `층·방향·장소` 텍스트로 표시 |
| 동의어 | 기존 `aliases` 테이블. 실제 민원 표현 50개를 수집해 검수 후 추가 |

복수·조건별 연락처를 `031-... / 031-...`처럼 한 문자열에 합치지 않는다. `task_contacts`에 번호별 용도·조건·공식 출처·확인일·매칭상태를 저장하고 화면은 번호마다 별도의 전화 링크를 사용한다. 기준일의 검증 연락처 93행은 완료된 데이터이므로 공개문구 작업에서 다시 적재하거나 변경하지 않는다.

기존 63개 업무의 쉬운 설명·준비물은 `reports/private/task_content_approvals.json`에서만 이관한다. 이 파일에는 `source_tasks_sha256`, `reviewed_by_role`, `reviewed_at`, 그리고 `items`의 `task_id`, `plain_description`, `preparation`, `department`, `location_text`, `source_urls`, `checked_at`을 둔다. Codex는 내용을 만들지 않는다. `scripts/apply_task_content.py --dry-run`이 원본 해시·업무 ID·빈 필수값·공식 URL·중복을 확인하고, 승인 후 DB 백업과 한 트랜잭션으로 적용한다. 승인 파일이 없으면 이 필드는 빈값이며 화면은 항목을 숨기되 기존 공식정보·검색 기능은 유지한다.

여기서 `source_tasks_sha256`도 변환된 DB가 아니라 `data/tasks.json` 원본 바이트의 SHA-256이다.

~~~json
{
  "source_tasks_sha256": "",
  "reviewed_by_role": "",
  "reviewed_at": "",
  "items": []
}
~~~

#### 8.A.6 구조화 importer 검증 기준

~~~text
통합 엑셀의 구조화 공식정보를 SQLite FTS5에 적재하는 기능만 구현해라.

입력:
source_data/동탄구보건소_공식정보_수집본_2026-08-26.xlsx

구현:
1. requirements-dev.txt에 openpyxl>=3.1,<4를 추가한다.
2. sql/sqlite_schema.sql의 catalog_items·catalog_items_fts 구조를 확인하되 이미 완료된 task_contacts 구조와 데이터를 변경하지 않는다.
3. scripts/migrate_schema.py와 scripts/import_catalog.py 및 테스트를 만든다.
4. load_workbook(data_only=True, read_only=True)로 읽는다.
5. 직접 색인할 시트와 행 수는 service 96, institution 147, staff 82, news 920, notice 46, bid 13, medical_pharmacy 108, postpartum 4, other 8이다.
6. 합계 catalog_items와 FTS는 각각 정확히 1,424행이어야 한다.
7. 헤더 이름과 행 수가 다르면 DB를 변경하기 전에 실패하라.
8. --check 옵션은 헤더·수량·URL·필수값만 검사하고 DB를 변경하지 않는다.
9. 실제 import는 한 transaction에서 catalog_items와 FTS만 비운 뒤 다시 넣는다.
10. 기존 tasks의 행·기존 업무값, aliases, event_logs, 승인된 연락처와 source_documents는 변경하지 않는다. 스키마 마이그레이션으로 새 빈 열을 추가하는 것만 허용한다.
11. 서비스_원문기록, 현행검색_24, 데이터오류_검증, HTML·첨부 검수시트는 민원인 검색 FTS에 넣지 않는다.
12. 직원 성명은 추측하지 않는다.
13. source_url은 HTTPS이고 hostname이 hscity.go.kr과 정확히 같거나 .hscity.go.kr로 끝날 때만 허용한다.
14. 빈 셀은 빈 문자열로 다루고 None 또는 nan이라는 글자를 저장하지 않는다.
15. institution에는 항상 원문확인 warning을 넣고 서술형 본문의 전화번호를 phone으로 승격하지 않는다.
16. 전화번호는 전용 열만 사용하며 --는 빈값으로 바꾼다.
17. plain_description·preparation·department·location_text를 전용 필드로 적재하고 API가 구조적으로 반환할 수 있게 한다.
18. 서비스 연락처가 단일 검증번호가 아니면 phone을 비우고 warning을 남겨 하나의 tel: 링크로 만들지 않는다.
19. scripts/apply_task_content.py는 reports/private/task_content_approvals.json을 입력으로 --dry-run까지만 구현하며 승인 파일을 만들거나 내용을 추측하지 않는다.
20. 테스트는 작은 임시 XLSX와 임시 DB를 사용한다.

전체 테스트를 실행하라.

이 단계 밖의 기능은 변경하지 마라.
완료 후 변경 파일, 실행 명령, 9개 유형별 적재 수량, 테스트 결과를 보고하고 멈춰라.
~~~

#### 8.A.7 별도 승인 시 참고 실행

Flask 서버가 실행 중이면 먼저 터미널에서 Ctrl+C로 종료한다. 같은 이름의 이전 백업을 덮어쓰지 않도록 시각이 포함된 새 파일을 만든다.

~~~powershell
New-Item -ItemType Directory -Force '.\data\backups' | Out-Null
$backupStamp = Get-Date -Format 'yyyyMMdd-HHmmss'
Copy-Item -LiteralPath '.\data\health_search.db' -Destination ".\data\backups\health_search.before_catalog.$backupStamp.db" -ErrorAction Stop
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe scripts\migrate_schema.py
.\.venv\Scripts\python.exe scripts\import_catalog.py --check
.\.venv\Scripts\python.exe scripts\import_catalog.py
.\.venv\Scripts\python.exe -c "import sqlite3; c=sqlite3.connect(r'data\health_search.db'); print('catalog',c.execute('select count(*) from catalog_items').fetchone()[0]); print('catalog_fts',c.execute('select count(*) from catalog_items_fts').fetchone()[0])"
~~~

예상 출력의 마지막 두 값은 모두 1424다. 한 번 더 import를 실행해도 같은 수여야 한다.

### 8.B 최종 매니페스트와 추출본문 적재

#### 8.B.1 원문 본문은 왜 JSON·TXT를 적재하는가

- 게시글, 첨부, 삽입이미지, 압축내부 문서 유형을 정확히 구분할 수 있다.
- 추출방법과 OCR 여부를 결과에 표시할 수 있다.
- 원본·부모 SHA-256을 보존할 수 있다.
- Windows에서 무효인 수집 당시 Linux 절대경로를 버리고 상대경로만 사용할 수 있다.
- Python 표준 라이브러리만으로 처리할 수 있어 추가 패키지가 필요 없다.

엑셀의 검색본문_청크 1,493행은 적재 결과의 표본검사와 교차검증에 사용한다.

#### 8.B.2 입력 파일

~~~text
source_data/attachments_second_pass/
├─ manifests/posts_manifest.json
├─ manifests/collection_summary.json
├─ manifests/extraction_manifest.json
├─ manifests/extraction_summary.json
├─ posts/
└─ extracted_text/
~~~

다음 파일은 사용하지 않는다.

- manifests/posts_manifest.partial.json
- saved_path 같은 수집 당시 Linux 절대경로
- article_html
- container_text
- failed_inline_responses의 HTML 오류 본문

#### 8.B.3 FTS5 trigram 지원 확인

한국어 합성어의 중간 부분을 찾으려면 trigram 토크나이저가 유리하다.

8.A 단계에서 이미 FTS5 trigram OK를 확인했다면 이 검사는 건너뛰어도 된다.

~~~powershell
.\.venv\Scripts\python.exe -c "import sqlite3; c=sqlite3.connect(':memory:'); c.execute(\"CREATE VIRTUAL TABLE temp.fts_probe USING fts5(x, tokenize='trigram')\"); print(sqlite3.sqlite_version, 'FTS5 trigram OK')"
~~~

FTS5 trigram OK가 나오면 다음으로 진행한다. 오류가 나면 Codex에 오류 전문을 전달하고, unicode61 FTS와 파라미터화된 LIKE 보조검색을 함께 구현하게 한다.

#### 8.B.4 SQLite 테이블

sql/sqlite_schema.sql에 다음 세 구조를 추가한다.

~~~sql
CREATE TABLE IF NOT EXISTS source_documents (
    id TEXT PRIMARY KEY,
    source_type TEXT NOT NULL
        CHECK(source_type IN ('post','attachment','inline_image','archive_member')),
    board TEXT NOT NULL CHECK(board IN ('news','notice','bid')),
    post_sn TEXT NOT NULL,
    title TEXT NOT NULL,
    posted_at TEXT,
    source_name TEXT,
    page_url TEXT NOT NULL,
    asset_url TEXT,
    local_relative_path TEXT,
    extracted_text_path TEXT,
    sha256 TEXT,
    parent_sha256 TEXT,
    collection_status TEXT,
    extraction_status TEXT,
    extraction_method TEXT,
    is_ocr INTEGER NOT NULL DEFAULT 0 CHECK(is_ocr IN (0,1)),
    searchable INTEGER NOT NULL DEFAULT 0 CHECK(searchable IN (0,1)),
    imported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_source_documents_post
ON source_documents(board, post_sn);

CREATE INDEX IF NOT EXISTS idx_source_documents_date
ON source_documents(posted_at);

CREATE INDEX IF NOT EXISTS idx_source_documents_sha
ON source_documents(sha256);

CREATE TABLE IF NOT EXISTS document_chunks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id TEXT NOT NULL
        REFERENCES source_documents(id) ON DELETE CASCADE,
    chunk_no INTEGER NOT NULL,
    body TEXT NOT NULL,
    UNIQUE(document_id, chunk_no)
);

CREATE VIRTUAL TABLE IF NOT EXISTS document_chunks_fts USING fts5(
    title,
    source_name,
    body,
    document_id UNINDEXED,
    tokenize='trigram'
);
~~~

trigger보다 importer가 document_chunks와 document_chunks_fts를 같은 트랜잭션에서 함께 적재하게 한다. 초보자가 오류 위치를 확인하기 쉽다.

#### 8.B.5 정확한 데이터 매핑

게시글 507건:

- id: post:{board}:{post_sn}
- title: title 또는 list_title
- posted_at: registered_at 또는 list_date
- source_name: 게시글 본문
- page_url: page_url
- local_relative_path: posts/{board}/{post_sn}.json
- collection_status: status
- 검색본문: article_text
- 공백, 빈값, 문자열 undefined는 searchable=0

추출 레코드 889건:

- extraction_manifest.json의 files 배열 873건과 archive_members 배열 16건을 모두 읽음
- files의 id: asset:{record_type}:{board}:{post_sn}:{attachment_sequence}:{sha256}
- archive_members의 id: asset:archive_member:{board}:{post_sn}:{record_token}:{sha256}
- source_type: attachment, inline_image, archive_member 중 하나
- title: post_title
- posted_at: post_date
- source_name: archive_member_path 또는 original_name
- page_url: 공식 게시물 page_url
- asset_url: 원본 source_url
- 경로: relative_path와 extracted_text_path만 사용
- SHA: sha256와 parent_sha256
- extraction_status: status
- extraction_method: method
- 본문: source_data\attachments_second_pass 아래의 extracted_text_path 파일을 UTF-8로 읽음
- is_ocr: method에 OCR이 포함되면 1
- empty 1건은 searchable=0

post_sn은 14~17자리이므로 항상 TEXT로 처리한다.

#### 8.B.6 importer의 필수 동작

새 파일 scripts/import_second_pass.py는 다음을 모두 만족해야 한다.

1. 시작 전에 게시물 507, files 873, archive_members 16, 세부유형 819·54·16을 확인한다.
2. article_text의 빈값·문자열 undefined를 검색에서 제외한다.
3. 본문에서 NUL만 제거하고 줄바꿈은 보존한다.
4. 원본 본문 자체를 정규화한 값으로 덮어쓰지 않는다.
5. 본문을 3,000자 고정 길이로 나누고 겹치지 않게 한다.
6. 모든 경로를 resolve한 뒤 source_data\attachments_second_pass 하위인지 검사한다.
7. 하나라도 경로가 밖으로 벗어나거나 파일이 없으면 전체 rollback한다.
8. SQL은 전부 파라미터 바인딩을 사용한다.
9. 한 트랜잭션에서 source_documents, document_chunks, FTS를 적재한다.
10. 재실행할 때 이 세 검색 테이블만 비우고 다시 넣는다.
11. tasks, aliases, event_logs와 공식 연락처는 절대로 건드리지 않는다.
12. 정상 종료 수량이 다르면 실패로 끝낸다.
13. --check 옵션은 원본 수량·경로·본문·예상 청크 수만 검사하고 DB는 변경하지 않는다.

정상 수량:

~~~text
source_documents: 1396
searchable documents: 1360
document_chunks: 2075
document_chunks_fts: 2075
~~~

#### 8.B.7 문서 importer 검증 기준

~~~text
최종 2차 수집 JSON 매니페스트와 extracted_text를 SQLite FTS5에 적재하는 기능만 구현해라.

입력 루트:
source_data/attachments_second_pass

읽을 자료:
- manifests/posts_manifest.json
- manifests/extraction_manifest.json
- manifests/collection_summary.json
- manifests/extraction_summary.json
- extracted_text 하위 TXT

중요: extraction_manifest.json의 files 배열 873건뿐 아니라 archive_members 배열 16건도 반드시 읽어 총 889건을 만든다.

확정 수량:
- 게시글 507
- 추출 레코드 889 = attachment 819 + inline_image 54 + archive_member 16
- source_documents 1,396
- searchable 1,360
- 3,000자 document_chunks 2,075
- FTS 행 2,075

구현:
1. sql/sqlite_schema.sql에 source_documents, document_chunks, document_chunks_fts를 추가한다.
2. trigram FTS5를 사용하되 현재 SQLite가 지원하지 않으면 명확한 오류를 내라.
3. scripts/import_second_pass.py를 만들고 DB를 바꾸지 않는 --check 옵션을 제공한다.
4. 게시글 article_text와 extracted_text_path의 TXT만 본문으로 사용한다.
5. article_html, container_text, failed HTML 응답, partial manifest는 적재하지 않는다.
6. 문자열 undefined, 빈 게시글 27건, empty 이미지 1건은 metadata만 넣고 searchable=0으로 둔다.
7. post_sn은 항상 TEXT다.
8. saved_path 절대경로는 사용하지 말고 상대경로만 사용한다.
9. 상대경로의 path traversal을 막고 입력 루트 하위인지 확인한다.
10. 본문은 NUL만 제거하고 3,000자씩 겹침 없이 나눈다.
11. 한 SQLite transaction에서 문서·청크·FTS를 함께 적재하고 실패 시 rollback한다.
12. 재실행해도 같은 수량이 되게 한다.
13. 기존 tasks, aliases, event_logs, 연락처는 변경하지 않는다.
14. 테스트는 작은 임시 매니페스트·TXT·DB fixture로 작성한다.

전체 테스트를 실행하라.

이 단계 밖의 기능은 변경하지 마라.
완료 후 변경 파일, 실행 명령, 실제 적재 수량, 테스트 결과, 남은 위험을 보고하고 멈춰라.
~~~

#### 8.B.8 별도 승인 시 참고 실행

Flask 서버를 종료한 뒤 DB를 시각이 포함된 새 파일명으로 백업한다.

~~~powershell
New-Item -ItemType Directory -Force '.\data\backups' | Out-Null
$secondPassBackupStamp = Get-Date -Format 'yyyyMMdd-HHmmss'
Copy-Item -LiteralPath '.\data\health_search.db' -Destination ".\data\backups\health_search.before_second_pass.$secondPassBackupStamp.db" -ErrorAction Stop
.\.venv\Scripts\python.exe scripts\migrate_schema.py
.\.venv\Scripts\python.exe scripts\import_second_pass.py --check
.\.venv\Scripts\python.exe scripts\import_second_pass.py
~~~

적재 수량 확인:

~~~powershell
.\.venv\Scripts\python.exe -c "import sqlite3; c=sqlite3.connect(r'data\health_search.db'); print('tasks',c.execute('select count(*) from tasks where active=1').fetchone()[0]); print('docs',c.execute('select count(*) from source_documents').fetchone()[0]); print('searchable',c.execute('select count(*) from source_documents where searchable=1').fetchone()[0]); print('chunks',c.execute('select count(*) from document_chunks').fetchone()[0]); print('fts',c.execute('select count(*) from document_chunks_fts').fetchone()[0])"
~~~

예상 출력:

~~~text
tasks 63
docs 1396
searchable 1360
chunks 2075
fts 2075
~~~

### 8.C 수집자료 적재 완료 기준

- catalog_items와 catalog_items_fts가 각각 1,424행이다.
- 현행 서비스·직원업무·시설·기관 조사기록 445건과 게시판 제목 979건이 유형별로 분리된다.
- 게시글·첨부·OCR 자료가 source_type별로 분리된다.
- 두 번 실행해도 1,396 / 1,360 / 2,075 / 2,075가 유지된다.
- 기존 위치안내 시범 63건과 별칭 316건이 그대로다.
- 빈값·undefined·오류 HTML이 검색되지 않는다.
- 수집 당시 절대경로가 DB에 들어가지 않는다.
- tasks와 공식 연락처가 변경되지 않는다.

---

## 9. API 계약과 공개 안내정보 연결 기준

연락처 API 연결은 완료됐다. 이 절은 완료된 계약을 고정하고, 향후 공개 안내정보를 같은 검색 결과에 추가할 때 지킬 기준을 정한다. 기존 검색 순위·결과 수·위치·SMS 필드는 변경하지 않는다.

### 9.1 검색 규칙

두 API에 다음 공통 규칙을 적용한다.

1. 입력은 2~80자다.
2. 정규식으로 2자 이상의 한글·영문·숫자 토큰만 뽑고 사용자의 원문을 MATCH에 직접 넣지 않는다.
3. 3자 이상 토큰은 trigram FTS5로 찾는다.
4. 금연·난임 같은 2자 토큰은 파라미터화된 LIKE 보조검색을 사용한다.
5. FTS 점수는 제목 8, 분류·파일명 3, 본문 1의 비중으로 시작한다.
6. /api/catalog-search는 service·institution·staff·medical_pharmacy·postpartum·other 445건만 검색하고 institution에는 원문확인 경고를 붙인다.
7. /api/content-search는 news·notice·bid 제목 979건과 source_documents·청크를 함께 검색한다.
8. 같은 게시물의 제목행·게시글본문·여러 첨부청크는 page_url과 post_sn 기준으로 한 카드에 묶는다.
9. 가장 점수가 높은 청크를 미리보기로 사용하되, 현행 구조화 정보와 과거 게시글의 의미를 섞지 않는다.
10. 현행정보는 서비스·기관·직원업무·시설 순으로 명시적 유형 가중치를 둘 수 있다.
11. 게시물 동점이면 최신 등록일을 먼저 표시한다.
12. 각 API는 최대 20개 결과를 반환한다.
13. 전체 결과 수는 100에서 잘리지 않게 실제 전체 수를 계산한다.
14. OCR 결과는 “OCR 추출 참고” 배지를 표시할 수 있게 추출방법을 반환한다.
15. 답을 생성하거나 의료판단을 하지 않고 공식 원문을 연결한다.

### 9.2 API 계약

기존 `POST /api/search`의 각 업무 결과에는 `primary_contact`와 `contacts`가 구현되어 있다. `contacts`는 primary를 포함한 활성 연락처 전체이며, primary 우선 뒤 용도·전화번호의 안정적인 순서로 반환한다. 최대 10개 검색결과의 연락처는 task ID 전체를 모아 SQL 한 번으로 조회한다.

~~~json
{
  "id": "A011",
  "name": "DB의 실제 업무명",
  "primary_contact": {
    "phone": "031-5189-4364",
    "display_phone": "031-5189-4364",
    "purpose": "대표",
    "role": "대표 연락처",
    "condition": "",
    "status": "confirmed",
    "verified_date": "2026-08-28",
    "is_primary": true
  },
  "contacts": [
    {
      "phone": "031-5189-4364",
      "display_phone": "031-5189-4364",
      "purpose": "대표",
      "role": "대표 연락처",
      "condition": "",
      "status": "confirmed",
      "verified_date": "2026-08-28",
      "is_primary": true
    }
  ]
}
~~~

보류 업무는 `primary_contact: null`, `contacts: []`를 반환한다. API에는 공개 필드만 포함하고 내부 메모, 로컬 경로, 해시와 관리자 검토내용은 노출하지 않는다. 향후 제3.7절의 공개 안내 필드를 추가하더라도 기존 응답 필드는 제거하거나 이름을 바꾸지 않는다.

현행정보 요청:

~~~http
POST /api/catalog-search
Content-Type: application/json

{"query":"예비신혼부부 건강검진"}
~~~

현행정보 응답 예시:

~~~json
{
  "query": "예비신혼부부 건강검진",
  "total_count": 1,
  "items": [
    {
      "id": "catalog:service:...",
      "item_type": "service",
      "title": "예비신혼부부 무료 건강검진",
      "category": "민원안내 — 검사와 제증명",
      "preview": "대상·시간·준비물의 안전하게 잘린 텍스트",
      "plain_description": "검수된 쉬운 설명",
      "preparation": "검수된 준비물",
      "department": "공식 담당 부서",
      "location_text": "공식 텍스트 위치",
      "phone": "공식 수집본 값",
      "address": "공식 수집본 값",
      "checked_at": "2026-08-26",
      "source_url": "https://www.hscity.go.kr/health/..."
    }
  ]
}
~~~

공식자료 요청:

~~~http
POST /api/content-search
Content-Type: application/json

{"query":"모자보건교육"}
~~~

공식자료 응답 예시:

~~~json
{
  "query": "모자보건교육",
  "total_count": 3,
  "displayed_count": 3,
  "items": [
    {
      "post_id": "20260819172651720",
      "title": "(9월) 동탄구보건소 모자보건교육 안내",
      "board": "보건소식",
      "posted_at": "2026-08-19 17:26:51",
      "source_types": ["post", "inline_image"],
      "is_ocr": true,
      "preview": "검색어 주변의 안전하게 잘린 텍스트",
      "page_url": "https://www.hscity.go.kr/health/..."
    }
  ]
}
~~~

### 9.3 보안 규칙

- SQL에 검색어를 문자열로 합치지 않고 ? 파라미터를 사용한다.
- 미리보기는 HTML이 아닌 일반 텍스트다.
- source_url과 page_url은 `https:`이고 hostname이 정확히 `hscity.go.kr`이거나 `.hscity.go.kr`로 끝나는지 확인한다.
- asset_url은 보조정보로만 취급하고 결과의 기본 이동은 page_url로 한다.
- 검색 원문과 IP를 event_logs에 저장하지 않는다.
- API 응답에는 Cache-Control: no-store를 유지한다.
- `tel:` 전화 링크는 브라우저에서 만들고 클릭 시 서버 API로 이용자 전화번호를 보내지 않는다.
- 실패검색어 분석은 기본 OFF다. 도입하려면 IP·사용자 ID·기기 식별자를 저장하지 않고, 전화번호·이메일처럼 개인정보로 보이는 자유문장은 폐기하며, 보존기간과 접근권한을 먼저 정한다.

### 9.4 후속 공개 데이터 연결 규칙

제3.7절의 공개 필드를 API에 연결할 때 다음을 지킨다.

- 원문 `name`, 위치, 검색점수, 연락처와 기존 필드를 유지한다.
- 공개 필드는 같은 업무 ID의 승인된 데이터만 결합한다.
- 값이 없으면 다른 본문에서 추측하거나 내부 상태 문자열을 대신 보내지 않는다.
- 연락처 조회는 현재 일괄조회 경로를 그대로 사용한다.
- 시험은 임시 DB fixture로 수행하여 운영 `event_logs`를 바꾸지 않는다.
- 공개 URL은 HTTPS와 화성특례시 공식 도메인을 검증한다.
- API 응답의 일반 텍스트를 HTML로 신뢰하지 않는다.

### 9.5 API 계약 회귀 기준

- A011과 F101의 `primary_contact`는 `031-5189-4364`이고 같은 객체가 `contacts`에도 포함된다.
- A012의 `contacts`는 정확히 5개이고 primary는 1개다.
- A011·A012·F101에 `031-5189-4354`가 없다.
- 보류 12개 업무는 `primary_contact: null`, `contacts: []`다.
- 기존 위치·검색 응답 필드는 그대로다.
- 자연키 중복, primary 중복과 고아 `task_id`가 0이다.
- 자동시험은 운영 DB가 아닌 임시 DB를 사용한다.

---

## 10. 기존 상세 안내에 공개문구를 연결하는 기준

### 10.1 구현 경계

공개문구는 현재 검색결과와 상세 안내의 기존 필드에만 바인딩한다. 새 카드·탭·버튼·제목·팝업·화면 구역을 만들지 않는다. `public/index.html`, `public/css/style.css`, 이미지와 글꼴은 변경하지 않는다.

향후 허용되는 프런트 변경은 기존 `public/js/app.js`의 텍스트·데이터 바인딩 최소 수정뿐이다. 기존 DOM ID, CSS class, 이벤트 리스너, 검색·위치·SMS 흐름을 유지한다.

### 10.2 기존 영역별 데이터 규칙

| 기존 영역 | 표시 원칙 |
|---|---|
| 검색결과 제목 | 승인된 `public_title`; 없으면 검증된 기존 업무명 |
| 첫 안내문 | `primary_action`과 `public_summary`를 짧고 쉬운 문장으로 표시 |
| 문의하는 곳 | 검증된 담당 조직 정보만 표시 |
| 전화로 문의하기 | `contacts` 전체를 primary 우선으로 표시 |
| 이용 안내 | 이용대상·준비물·비용·운영시간 중 확인된 값만 표시 |
| 방문 전 확인사항 | `public_caution`; 확인되지 않은 상태값은 공개하지 않음 |
| 최근 확인일 | 승인된 `verified_date` |
| 위치 안내 | 기존 `floor`, `place`, `route`, 좌표와 마커 동작 유지 |

연락처가 여러 개면 각 번호를 용도·조건과 함께 별도 `tel:` 링크로 표시한다. 링크의 `href`에는 숫자만 사용하고, 화면에는 `display_phone`을 우선한다. primary가 없으면 번호를 추측하지 않는다.

### 10.3 안전한 출력

- API 문자열은 기존 이스케이프 또는 안전한 DOM 생성 경로를 사용한다.
- 서버 응답을 검증 없이 HTML로 삽입하지 않는다.
- 공식 링크는 HTTPS와 허용 도메인을 검사한다.
- 새 공개 필드가 없어도 기존 검색·상세·위치·연락처·SMS가 동작한다.
- 공개문구가 길면 제3.3절의 단축·중복제거·핵심행동·보류 순서를 따른다.

### 10.4 회귀 확인

- A011과 F101은 대표번호 1개를 표시한다.
- A012는 대표 포함 용도별 연락처 5개를 모두 표시한다.
- 보류 업무는 임의 번호나 내부 검토 상태를 표시하지 않는다.
- A011·A012·F101에 `031-5189-4354`가 표시되지 않는다.
- 검색, Enter, 추천어, 결과 선택, 상세 dialog, 층 선택, 위치 아이콘, SMS가 유지된다.
- 1440·768·390·360px에서 기존 배치와 줄바꿈이 유지된다.
- 운영 DB 검색 이벤트를 만들지 않는 시험 경로를 사용한다.

---

## 11. 공식 기관정보와 검증 연락처

### 11.0 공식정보 처리 목적

확인된 기관정보는 표시하되, 공식 페이지끼리 충돌하는 값은 확정해서 보여 주지 않는다.

### 11.1 현재 수집본에서 확인된 대표 정보

| 항목 | 값 | 처리 |
|---|---|---|
| 기관명 | 동탄구보건소 | 화면에 사용 |
| 주소 | 화성시 동탄구 노작로 226-9 | 공식출처·확인일과 함께 표시 |
| 일반 운영 | 평일 09:00~18:00, 점심 12:00~13:00 | 업무별 예외가 있으므로 안내 문구 필요 |
| 일반 접수마감 | 11:40 / 17:40 | 업무별 차이 확인 |
| 보건행정과 | 031-5189-4377 | 공식 확인일 표시 |
| 건강증진과 | 031-5189-6918·6920 | 용도 구분 확인 후 표시 |
| 우편번호 | 공식 페이지에 18460과 18640 충돌 | 해결 전 화면 표시 보류 |

전화·운영시간은 바뀔 수 있으므로 화면에 확인일 2026-08-26과 공식사이트 링크를 함께 둔다.

### 11.2 업무별 공식 연락처 반영 기준

최종 확정대조 XLSX의 검증 연락처는 운영 DB에 반영되어 있다.

| 구분 | 현재 수량 |
|---|---:|
| 전체 업무 | 63 |
| 활성 연락처가 연결된 업무 | 51 |
| 활성 연락처 | 93 |
| primary 연락처 | 45 |
| 실제 복수 연락처 업무 | 20 |
| 보류 업무 | 12 |
| 보류 업무의 활성 연락처 | 0 |

활성 연락처의 `match_status`는 `confirmed`, `confirmed_multiple`, `conditional`만 허용한다. 과거 검토상태인 `ambiguous`, `conflict`, `probable_review`, `unmatched`는 근거자료에는 보존하지만 활성 연락처나 공개 상태문구로 사용하지 않는다.

보류 업무는 H004, F105, F109, F111, F202, F203, F205, F206, F301, F302, F303, F304다. 이 12개 업무에는 번호를 임의 생성하거나 대표번호를 대신 넣지 않는다.

### 11.3 핵심 연락처 고정값

| 업무 | 검증 결과 |
|---|---|
| A011 결핵 상담·관리 | `031-5189-4364` primary 1행 |
| F101 결핵실 위치 안내 | `031-5189-4364` primary 1행 |
| A012 결핵 검사 | 5행, primary는 `031-5189-4364` |

A012의 추가 연락처는 다음과 같다.

- `031-5189-4344`: 흉부 X선
- `031-5189-4369`: 검체검사
- `031-5189-4368`: 진단검사실
- `031-5189-4377`: 민원접수

`031-5189-4354`는 서남부권 결핵 담당이므로 A011·A012·F101의 활성 연락처에 포함하지 않는다. 복수·조건부 번호는 번호마다 별도 행과 용도·조건을 유지한다. 공개 화면은 내부 검토 메모를 노출하지 않는다.

### 11.4 향후 공식정보 갱신

연락처나 운영정보를 다시 갱신할 때는 원본 해시 확인, dry-run, 임시 DB, 복구본, 변경예정 보고, 별도 승인, 단일 트랜잭션과 무결성 검사를 반복한다. 현재 93행을 공개문구 작업 때문에 다시 적용하지 않는다.

우편번호처럼 공식 페이지 간 값이 충돌하는 항목은 보류 상태로 남기고 공개 화면에서는 `현재 공식자료를 확인하고 있습니다.`라고 안내한다. 새 정보를 표시할 공간이 없으면 제3.3절 순서로 내용을 정리하며 화면 구역을 추가하지 않는다.

---

## 12. 관리자용 읽기 전용 검수 기준

### 12.0 관리자 검수 목적

관리자가 구조화 정보 1,424건, 기존 위치안내 시범 63건, 공식자료 문서 1,396개·FTS 청크 2,075개의 상태를 확인하게 한다.

### 12.1 관리자 검수 지표

- 활성 민원업무 수: 63
- 별칭 수: 316
- 구조화 catalog_items·FTS: 각각 1,424
- 현행정보 유형 6종 합계: 445
- 게시판 제목 3종 합계: 979
- 공식자료 전체 문서: 1,396
- 검색 가능 문서: 1,360
- 검색 청크·FTS 행: 각각 2,075
- 서로 다른 게시물 수
- 게시판별 게시물 수
- source_type별 청크 수
- OCR 참고자료 수
- 빈 본문·잘못된 URL·중복 key 수
- 가장 오래된 등록일과 최신 등록일
- 업무별 연락처 상태별 수량과 출처·확인일 누락 수

검색 원문, IP, 휴대전화번호를 관리자 통계에 저장하지 않는다.

수정 PRD의 “관리자 웹 편집”은 이 읽기 전용 검수 화면과 다른 기능이다. 로그인·수정·승인·감사기록 설계가 끝나기 전에는 Streamlit 화면에 쓰기 기능을 추가하지 않는다.

### 12.2 현재 일정에서의 처리

관리자 화면의 새 지표·편집·로그인 구현은 남은 일주일 범위가 아니다. 기존 읽기 전용 검수 기능을 유지하고 공개문구 전환에 필요한 수량은 SQL·시험 보고서로 검증한다.

`admin/dashboard.py`, `scripts/init_db.py`와 관리자 화면을 공개문구 작업의 명분으로 변경하지 않는다. 관리자 검수에서도 검색 원문, IP와 휴대전화번호를 저장하거나 표시하지 않는다.

---

## 13. 자동시험과 노년층 사용성 시험

### 13.1 고령층 사용성 시험

자동시험은 코드 오류를 찾지만 65세 이상 민원인이 실제 문구를 이해하는지는 확인하지 못한다. 개발 중에는 노년층 3~5명에게 형성평가를 하고, 최종 인수시험은 최소 5명으로 진행한다.

참가자에게 정답이 되는 검색어를 알려 주지 않고 다음 과업을 제시한다.

1. 평소 말하는 표현으로 원하는 민원을 검색한다.
2. 검색결과의 첫 문장을 읽고 다음 행동을 말한다.
3. 이용대상·준비물·비용·운영시간 중 표시된 내용을 찾는다.
4. 방문 위치와 위치 안내 아이콘을 확인한다.
5. 대표번호와 용도별 추가번호를 구분한다.

각 참가자별로 성공·중단 지점·도움 요청 여부·걸린 시간을 기록하되 이름, 전화번호와 자유문장 개인정보는 저장하지 않는다. 실패하면 먼저 문장을 짧게 하고 동의어를 보완한다. 버튼명·순서·크기·배치 등 디자인은 바꾸지 않는다.

### 13.2 자동시험 실행 명령

~~~powershell
.\.venv\Scripts\python.exe -m compileall app.py db.py search_engine.py scripts admin tests
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe scripts\import_catalog.py --check
.\.venv\Scripts\python.exe scripts\import_second_pass.py --check
~~~

### 13.3 로컬 기술 합격 조건

| 검증항목 | 합격 기준 |
|---|---|
| Python 문법 | compileall 오류 0 |
| 기존 민원업무 | 63건 |
| 기존 별칭 | 316건 |
| 연락처 | 93행·51개 업무·primary 45행 |
| 보류 연락처 | 12개 업무·활성 0행 |
| 구조화 catalog_items·FTS | 각각 1,424건 |
| 현행 서비스·직원업무·시설·기관 조사기록 | 445건 |
| 전체 게시판 제목 | 979건 |
| 공식자료 전체 문서 | 1,396건 |
| 검색 가능 문서 | 1,360건 |
| 검색 청크·FTS | 각각 2,075건 |
| 수집 게시물 | 507건 |
| 공식 첨부파일 | 819개 |
| 추출 레코드 | 889개 |
| 본문 추출 실패 | 0개 |
| 자동시험 | 기준일 64 passed, 이후 전체 시험 실패 0 |
| 외부 URL | `https:` + `hscity.go.kr` 또는 `.hscity.go.kr` 하위도메인만 |
| 비밀정보 | Git 추적 0 |
| 연락처 구조 | primary 포함 배열, 번호별 `tel:` 링크, 문자열 결합 0, 내부 메모 비노출 |
| 디자인 | 제3.2절과 제7절의 현재 화면 완전 유지 |
| 반응형 | 1440·768·390·360px의 기존 배치와 줄바꿈 유지 |
| 무결성 | 중복·primary 중복·고아 FK 0, `foreign_key_check` 0, `integrity_check` ok |

### 13.4 Git 검사

~~~powershell
git status
git check-ignore .env
git check-ignore source_data\attachments_second_pass
git check-ignore source_data\동탄구보건소_공식정보_수집본_2026-08-26.xlsx
~~~

.env와 원본 수집 폴더가 ignored로 확인되어야 한다.

### 13.5 최종 검수 원칙

- API 회귀시험은 임시 DB를 사용한다.
- 운영 DB에서 자동 검색·SMS 호출로 이벤트를 만들지 않는다.
- 공개문구와 공식 근거를 업무 ID별로 대조한다.
- A011·A012·F101과 보류 12개 업무를 별도 검사한다.
- 현재 디자인의 화면 비교는 변경 여부 확인에만 사용한다.
- 문제가 생기면 치명적·중요·경미로 분류하고 데이터·문구의 최소 수정만 수행한다.
- 전체 pytest와 `git diff --check`를 다시 실행한다.

---

## 14. 최종 시연 실행 순서

### 14.1 서버 시작

~~~powershell
Set-Location -LiteralPath 'C:\Users\corle\OneDrive\바탕 화면\보건민원_검색엔진_MVP'
.\.venv\Scripts\python.exe scripts\import_catalog.py --check
.\.venv\Scripts\python.exe scripts\import_second_pass.py --check
.\.venv\Scripts\python.exe app.py
~~~

### 14.2 브라우저 시연

1. http://127.0.0.1:5000을 연다.
2. 화성특례시 로고, 동탄구보건소 표기, 배경과 현재 디자인이 같은지 확인한다.
3. 노년층이 쓰는 일상어로 검색하고 추천어·Enter 입력을 확인한다.
4. 검색결과의 첫 문장에서 다음 행동을 이해할 수 있는지 확인한다.
5. 결과를 선택해 상세 안내와 확정 공개정보를 확인한다.
6. 대표번호와 용도별 추가 연락처 및 각 `tel:` 링크를 확인한다.
7. 층을 바꾸고 위치 아이콘이 기존 방식으로 이동하는지 확인한다.
8. 보류 업무가 미확정 번호나 내부 상태를 공개하지 않는지 확인한다.
9. SMS mock이 primary 연락처만 사용하는지 임시 DB 시험결과로 확인한다.
10. 1440·768·390·360px의 기존 배치와 줄바꿈이 유지되는지 확인한다.

### 14.3 포트 충돌 시

~~~powershell
$env:PORT = '5001'
.\.venv\Scripts\python.exe app.py
~~~

그 후 http://127.0.0.1:5001로 접속한다.

---

## 15. 자주 발생하는 오류

| 증상 | 원인 | 해결 |
|---|---|---|
| 경로가 명령으로 인식됨 | cd 없이 경로만 입력 | Set-Location -LiteralPath '전체 경로' 사용 |
| Activate.ps1 실행 차단 | PowerShell 정책 | 활성화하지 말고 .venv\Scripts\python.exe 직접 실행 |
| No module named flask | 다른 Python 실행 | VS Code 인터프리터를 .venv로 선택 후 requirements-dev 재설치 |
| data/tasks.json 없음 | ZIP의 상위 폴더에서 실행 | app.py가 있는 프로젝트 루트로 이동 |
| DB 없음 | init_db 미실행 | .venv\Scripts\python.exe scripts\init_db.py |
| 현행 서비스·시설 0건 | 엑셀 미복사 또는 catalog import 미실행 | source_data의 XLSX 확인 후 import_catalog.py 실행 |
| 공식자료 0건 | 2차 수집 ZIP 미해제 또는 import 미실행 | source_data 경로 확인 후 importer 실행 |
| 적재 수가 예상과 다름 | partial 매니페스트·오류 HTML·빈값 포함 | 최종 두 매니페스트와 extracted_text만 사용 |
| 긴 게시물ID가 달라짐 | 숫자로 변환 | importer에서 문자열로 강제 |
| 사진이 안 보임 | 파일명·경로 오류 | public\images\hero-dongtan.jpg 확인 |
| CSS만 보이고 검색 안 됨 | index.html을 file://로 열음 | Flask 실행 후 127.0.0.1로 접속 |
| 5000 포트 사용 중 | 다른 서버 실행 중 | Ctrl+C로 종료하거나 PORT=5001 사용 |
| 문자 안내에 번호가 없음 | 해당 업무의 활성 primary가 없음 | 보류 업무인지 확인하고 번호를 임의 입력하지 않음 |
| 전화 링크가 없음 | `primary_contact`와 `contacts`가 비어 있음 | 보류 업무는 쉬운 확인 안내만 사용하고 내부 상태를 공개하지 않음 |
| 전화 링크가 번호 여러 개를 한꺼번에 엶 | 복수번호를 한 문자열에 저장 | task_contacts에서 번호별 링크로 분리 |
| 위치 마커가 엉뚱한 곳에 표시 | 결과 ID와 좌표 매핑 누락 | 해당 결과의 좌표가 없으면 마커를 숨기고 텍스트 위치만 표시 |
| OpenAI 기능이 안 됨 | ENABLE_LLM=false | 정상 상태. 7일차 완료판정에서도 기본검색을 우선하고 LLM은 OFF로 유지 |
| 검색 결과 총수가 100 | 기존 코드의 내부 제한 | 공식자료 API는 전체 개수를 별도 계산 |

OneDrive가 SQLite database is locked 오류를 반복해서 만들면 프로젝트를 C:\Projects\보건민원_검색엔진_MVP로 복사하고 그 위치에서 실행한다.

---

## 16. OpenAI·연락수단·배포·선택기능은 언제 켜는가

### 16.1 LLM 보조검색

기본 검색 결과가 0건인 경우에만 사용한다.

허용:

- 짧은 검색어의 동의어 후보
- 최대 5개의 관련 표현
- 결과가 없으면 기존 검색으로 안전하게 복귀

금지:

- 담당부서·전화번호 생성
- 의료상담 또는 진단
- 공식 자료에 없는 지원대상·금액·기간 생성
- 민원인의 이름·주소·전화번호 전송

API 키는 .env에만 넣고 public/js/app.js에는 넣지 않는다. OPENAI_MODEL은 계정에서 실제 사용할 수 있는 현재 모델 ID를 확인한 뒤 입력한다.

~~~dotenv
ENABLE_LLM=false
OPENAI_API_KEY=YOUR_OPENAI_API_KEY
OPENAI_MODEL=ACCOUNT_SUPPORTED_MODEL_ID
~~~

7일차 로컬 완료본까지 `ENABLE_LLM=false`를 유지한다.

### 16.2 전화와 문자 운영 기준

현재 상세 안내의 검증된 번호별 `tel:` 링크를 기본 연락수단으로 유지한다. QR처럼 새 화면 요소가 필요한 기능은 현재 디자인에 추가하지 않는다.

`SMS_MODE=mock`은 현재 회귀시험용으로 유지한다. SMS 본문은 primary 연락처만 사용하며 여러 번호를 합치지 않는다. 실제 전송은 다음이 모두 끝난 뒤 별도 운영승인을 받는다.

- 공식 업무전화와 최종 확인일 검수
- 발신번호 등록
- 개인정보 이용 고지·동의·파기 절차 승인
- 일·월 발송 한도
- 중복 전송 방지
- 실패·환불·비용 모니터링

### 16.3 Supabase와 공개 배포

현재 SQLite는 로컬 시연에 적합하다. Vercel 같은 서버리스 환경에서 로컬 SQLite와 176MB 원본 ZIP을 운영 데이터로 사용하면 안 된다.

공개 배포 전 필요한 작업:

1. Supabase에 catalog_items, source_documents, document_chunks에 대응하는 운영 스키마 추가
2. 서버 전용 키만 Flask 환경변수에 저장
3. 브라우저의 Supabase 직접 접근 금지
4. 공유 rate limit 저장소 적용
5. 관리자 인증
6. 보안·개인정보 검토
7. 공식자료 갱신 작업과 검수자 지정

Render 무료환경은 시험 배포 후보일 뿐 확정 운영환경이 아니다. 슬립 시간, 임시 파일시스템, 가격, 데이터 유지 조건은 변경될 수 있으므로 배포 직전에 공식 문서를 다시 확인한다. 정식 운영은 영구 DB, 정기 백업, 복원시험, 장애 대응과 기관 승인 서버 구성을 우선한다.

### 16.4 선택기능과 데이터 갱신

음성 입력, QR과 관리자 편집처럼 새 버튼·화면 구역이 필요한 기능은 현재 확정 디자인에 추가하지 않는다. 필요성이 생기면 현 서비스 밖의 별도 운영안으로 검토한다.

**실패검색어 분석**

- 기본 OFF로 둔다.
- 현재 검색 API와 `event_logs`에는 실패한 원문 query를 저장하지 않는다.
- 초기 민원 표현 50개는 자동 로그가 아니라 동의받은 대면 사용성 시험에서 관찰하고, 담당자가 전화번호·이메일·주소·이름 등 개인정보를 제거한 뒤 별도 검수표에 옮긴다.
- 운영 통계가 나중에 승인되면 사전에 승인된 정규화 표현 ID와 합계 횟수만 집계하고 IP·계정·기기 식별자와 연결하지 않는다. 새로운 자유문장 원문을 자동 저장하는 기능은 별도 개인정보 검토·고지·보존기간 승인 전 구현하지 않는다.
- 담당자는 정규화 표현을 동의어로 추가하기 전에 공식 업무와 대조한다.

**Google Sheets 또는 CSV 동기화**

- 공개 가능한 업무정보만 별도 시트에 둔다.
- 공개 CSV에 내부 메모·개인 연락처·검수상태를 넣지 않는다.
- 원격값을 운영 DB에 바로 덮어쓰지 않고 다운로드 → 스키마·수량·URL 검사 → 변경 비교 → 승인 → 백업 → 트랜잭션 반영 순서를 지킨다.
- 10분 자동 갱신은 검증·승인 절차를 우회하므로 정식 운영에서 기본값으로 사용하지 않는다.

선택기능은 이번 남은 일주일 일정에 포함하지 않는다. 승인 없는 운영 DB 변경과 자유문장 원문 저장은 항상 0건이어야 한다.

---

## 17. 기준 코드와 운영 준비에서 반드시 기억할 한계

1. 현재 63개 업무의 내부 원문은 노년층 민원인용 문장으로 전수 전환되지 않았다.
2. 선정이 완료된 A011·A012·R002의 실제 민원인용 공개문구 작성과 선행검토가 남아 있다.
3. 이용대상·준비물·비용·운영시간은 공식근거가 없는 경우 보류해야 한다.
4. 위치자료 중 공식 확정 여부가 불명확한 값은 추측하거나 확정 위치처럼 쓰지 않는다.
5. 과거 게시물과 OCR 본문은 현재 행정정보와 구분하고 공식 원문 확인이 필요하다.
6. 역사적 전화번호를 현재 연락처로 자동 승격하지 않는다.
7. Flask 개발서버와 memory 기반 rate limit은 인터넷 공개 운영용 구성이 아니다.
8. 실제 운영 API 검색은 `event_logs`와 물리 DB 해시를 바꿀 수 있으므로 시험에는 임시 DB를 쓴다.
9. 초기 노년층 파일럿과 KWCAG 검수는 코드 자동시험으로 대체할 수 없다.
10. 이 서비스는 의료진단 도구가 아니다. 응급상황은 119와 의료기관 이용 대상이다.
11. 실패검색어·LLM·실제 문자·외부 동기화는 개인정보와 운영승인 전 기본 OFF다.
12. 현재 디자인은 완성 상태이므로 접근성이나 정보량 문제도 새 화면 요소나 CSS 변경으로 해결하지 않는다.

---

## 18. 남은 일주일 완성 일정

### 18.1 일차별 종료 게이트

| 일차 | 남은 작업 | 당일 종료조건 |
|---|---|---|
| 1일차 | 구현매뉴얼 갱신, 민원인용 공개정보 구조 확정, 대표 업무 3건 선정, 공식 근거자료 연결 | 기준 문서·공개 필드·대표 3건·출처목록 확정 |
| 2일차 | 대표 업무 3건의 민원인용 문구 작성, 현재 디자인 안에서 문구만 교체한 결과 확인, 사용자 문구 승인 | 3건 문구 승인, 디자인 변경 0건 |
| 3일차 | 63개 업무의 민원인용 제목과 핵심 안내문 작성, 이용대상·준비물·비용·운영시간 근거 대조, 미확인 항목 보류목록 작성 | 63개 업무의 승인·보류 상태와 근거 연결 |
| 4일차 | 승인 공개 데이터를 별도 구조로 적재, 업무 ID·출처 연결, API 공개 데이터 연결, 운영 적용 전 임시 DB 검증 | 임시 DB 수량·출처·rollback·재실행 동일성 통과 |
| 5일차 | 기존 상세 안내에 공개문구 연결, 기존 DOM·CSS class 유지, JavaScript 텍스트·데이터 바인딩만 최소 수정 | HTML·CSS·이미지·글꼴 변경 0건, 기존 상세영역에서만 표시 |
| 6일차 | 노년층 관점 문구 검토, 모바일·데스크톱 가독성 확인, 검색·위치·연락처·SMS 회귀시험, 공식자료 대조 | 디자인 변경 없이 치명적·중요 오류 0건 |
| 7일차 | 잘못된 문구·데이터 수정, 보류항목 정리, 전체 자동시험, DB 무결성 검사, 백업, 운영 절차와 매뉴얼 최종 갱신 | 전체 시험·무결성·백업·운영절차 통과 |

연락처 스키마·93행 적재·검색 API 연락처 연결·상세 연락처 표시·SMS primary 사용은 이미 완료됐으므로 이 일정에서 다시 개발하지 않는다.

### 18.2 매일 공통으로 지킬 규칙

- 작업 시작 전 `git status`, 기존 `git diff`, 관련 파일의 현재 내용을 읽고 사용자의 기존 변경을 보존한다.
- 그날의 범위만 진행하고 다음 일차 작업을 미리 시작하지 않는다.
- 운영 DB를 바꾸는 작업 전에는 날짜·시각이 포함된 복구본을 만든다.
- 시험은 임시 DB를 사용하고, 검증 때문에 운영 DB의 검색 이벤트나 연락처를 바꾸지 않는다.
- 한 번에 여러 원인을 고치지 않는다. 실패 원인 하나를 최소 수정한 뒤 관련시험과 전체 회귀시험을 다시 실행한다.
- 완료 보고에는 변경 파일, 실행 명령, 시험결과, 종료 게이트, 남은 차단사항을 반드시 포함한다.
- 모든 일차에 제3.2절의 디자인 완전 고정 원칙을 적용한다.
- 내용이 현재 영역에 맞지 않으면 제3.3절의 문장 단축·중복 삭제·핵심 행동·보류 순서로 해결한다.
- 완료된 연락처·API·위치 기능을 다시 구현하지 않고 회귀시험으로 보호한다.

### 18.3 대표 업무 3건 선행검토

63개 업무를 한꺼번에 바꾸지 않고 다음 3건으로 문장구조를 먼저 검증한다. 이 절은 대표 업무 선정결과와 공식 근거만 확정한다. 실제 민원인용 문구 작성, 코드 구현, DB 반영과 화면 적용은 시작하지 않는다.

1. A011 결핵 상담·관리
2. A012 결핵 검사
3. R002 어르신 오늘 건강(AI·IoT·스마트워치)

#### 18.3.1 R002 선정 이유

- 공식자료에서 서비스 대상이 65세 이상 어르신으로 직접 확인된다.
- 노년층과 직접 관련된 유일한 강한 A등급 후보다.
- A011·A012의 결핵업무와 다른 방문건강·비대면 건강관리 유형이다.
- `어르신`, `스마트워치`, `AI·IoT`, `건강관리` 등 실제 검색 가능성이 높은 별칭을 보유한다.
- 6개월 동안 건강기기·건강미션·비대면 모니터링을 이용하는 서비스다.
- 대표 연락처 `031-5189-5032`가 공식 직원업무 및 최종 연락처 대조자료에서 확인된다.

#### 18.3.2 R002 공식 근거

- 공식 서비스 페이지: [AI·IoT 기반 어르신 건강관리사업](https://www.hscity.go.kr/health/business/region/AIhealthcare.jsp)
- 보관 원문 대상조건: [`reports/contact_matching/20260827_172043/raw/041_health_business_region_AIhealthcare.jsp.html` 37행](reports/contact_matching/20260827_172043/raw/041_health_business_region_AIhealthcare.jsp.html#L37)
- 보관 원문 서비스 및 6개월 과정: [같은 원문 50행부터](reports/contact_matching/20260827_172043/raw/041_health_business_region_AIhealthcare.jsp.html#L50)
- 수집 URL·HTTP 기록: [`reports/contact_matching/20260827_172043/source_manifest.json` 535행](reports/contact_matching/20260827_172043/source_manifest.json#L535)
- 업무 원본: [`data/tasks.json` 689행](data/tasks.json#L689)
- 공식 직원업무 연락처 근거: [`reports/contact_matching/20260827_172043/raw/008_health_organ_BD_selectHealthOrganList.do_q_healthNm_dongtan_q_currPage_6.html` 3099행부터](reports/contact_matching/20260827_172043/raw/008_health_organ_BD_selectHealthOrganList.do_q_healthNm_dongtan_q_currPage_6.html#L3099)
- 최종 연락처 대조: [`data/source/동탄구보건소_검색업무별_공식연락처_확정대조_2026-08-28.xlsx`](data/source/동탄구보건소_검색업무별_공식연락처_확정대조_2026-08-28.xlsx)의 `PDF대조_확정_63` 시트 16행
- 서비스 연락처 대조: 같은 XLSX의 `서비스연락처_96` 시트 46행
- 시설위치 대조: 같은 XLSX의 `시설위치_대조_63` 시트 16행

#### 18.3.3 R002에서 확인된 정보

- 공식 대상: 만성질환 관리 또는 건강행태 개선이 필요한 65세 이상 어르신
- 우선순위: 독거어르신, 기존 방문건강관리 대상자 등
- 서비스: AI·IoT 건강기기, 건강미션, 비대면 모니터링, 6개월 참여
- 담당: 동탄구보건소 건강증진과 지역보건팀
- 대표 연락처: `031-5189-5032`
- 권역별 방문건강 연락처가 별도로 존재함

공식 근거가 추가 확인되기 전에는 “현재 누구나 즉시 신청할 수 있다” 또는 “현재 모집 중이다”라고 기록하거나 공개하지 않는다.

#### 18.3.4 R002 확인 필요와 공개 안전조건

다음 항목은 `[확인 필요]`이며, 확인 전까지 공개용 문구의 확정정보로 사용하지 않는다.

- 이용 비용
- 신청 시 준비물
- 현장 상담·접수시간
- 최초 방문 또는 등록 장소
- 현재 모집 또는 신청 가능 여부
- DB의 `3층 보건행정과` 위치가 현재 조직·서비스 흐름과 일치하는지
- `031-5189-4779` 담당 권역이 `동탄3·6동`인지 `동탄3·5·6동`인지
- XLSX가 참조한 `동탄보건소 건강증진과 현황_260828.pdf` 원문 파일

공개정보를 작성할 때는 다음 안전조건을 적용한다.

- `3층 보건행정과`를 R002의 확정 방문장소로 표시하지 않는다.
- 비용이 무료라고 추측하지 않는다.
- 준비물이 없다고 추측하지 않는다.
- 운영시간을 보건소 일반 운영시간으로 대신하지 않는다.
- 현재 모집 중이라고 추측하지 않는다.
- 권역별 연락처가 충돌하면 대표번호 `031-5189-5032`를 우선 안내한다.
- 미확정 정보는 “방문 전에 전화로 확인해 주세요”로 처리한다.

#### 18.3.5 다른 후보를 선정하지 않은 이유

- M009 예방접종: 65세 이상 조건이 일부 백신에만 적용되어 전체 업무를 노년층 무료사업으로 오인할 위험이 있다.
- A001 진료 접수: 노년층 전용업무가 아니라 일부 65세 이상 이용자의 본인부담 면제조건이다.
- D001: 60세 조건과 여러 치매서비스가 하나의 업무에 혼합되어 있다.
- D002: 공식적인 숫자 연령조건이 없고 연락처 역할이 충돌한다.
- R005: 노년층 관련 가능성은 있으나 대상·비용·준비물·운영시간 근거가 부족하다.

#### 18.3.6 디자인 완전 고정과 이번 승인 범위

R002 선정은 데이터와 문구 설계를 위한 결정일 뿐 화면 변경 승인이 아니다. 이번 반영에서 HTML, CSS, JavaScript, 이미지, 글꼴과 화면 구성은 모두 변경하지 않으며 현재 디자인을 완전히 유지한다. 실제 민원인용 문구 작성과 화면 적용은 별도 승인 전까지 시작하지 않는다.

#### 18.3.7 대표업무 선정 조사시점 상태

| 항목 | 조사시점 값 |
|---|---:|
| `tasks` | 63 |
| `aliases` | 316 |
| `task_contacts` | 93 |
| `event_logs` | 118 |
| 조사시점 DB SHA-256 | `9871a1dcd888f2949a40469a18e9d25955bd6d21dc1cb41cf822fe5f2001b54e` |

`event_logs`는 실제 검색 때마다 증가하므로 전체 DB의 물리 SHA-256도 달라질 수 있다. 위 값은 대표업무 선정 조사시점의 스냅샷이며, 파일 해시만으로 핵심 업무데이터 변경 여부를 판단하지 않는다.

선행검토 절차는 다음과 같다.

1. 기존 내부 안내문을 확인한다.
2. 업무 ID에 연결된 공식자료와 근거를 확인한다.
3. 민원인용 제목·첫 행동·안내문을 작성한다.
4. 현재 디자인을 그대로 둔 상태에서 문구만 바꾼 결과를 확인한다.
5. 사용자에게 문구 승인을 받는다.
6. 승인된 문장구조를 나머지 업무에 적용한다.

F101은 연락처 회귀검증의 핵심 업무이지 세 번째 노년층 지원업무로 자동 선정하지 않는다. 이번 매뉴얼 갱신에서는 세 업무의 실제 공개문구를 작성하거나 화면에 적용하지 않는다.

---

## 19. 최종 완료 판정

### 19.1 서비스 완료조건

- [ ] 노년층 민원인이 담당 조직을 몰라도 검색할 수 있다.
- [ ] 일상적인 표현으로 검색할 수 있다.
- [ ] 검색결과의 첫 문장만 읽어도 다음 행동을 알 수 있다.
- [ ] 대표 연락처와 용도별 연락처를 구분할 수 있다.
- [ ] 위치 안내 아이콘이 기존 방식으로 정상 이동한다.
- [ ] 이용대상·준비물·비용·운영시간을 추측하지 않는다.
- [ ] 내부 직원용 표현이 공개 화면에 직접 노출되지 않는다.
- [ ] 보류 정보가 확정정보처럼 표시되지 않는다.
- [ ] 기존 검색·추천어·상세 안내 기능이 유지된다.
- [ ] 기존 연락처와 SMS 기능이 유지된다.
- [ ] 기존 위치 안내 기능이 유지된다.
- [ ] 현재 디자인이 완전히 유지된다.
- [ ] HTML·CSS·이미지·글꼴 변경이 없다.
- [ ] 모바일과 데스크톱에서 기존 레이아웃이 유지된다.
- [ ] 모든 공개문구를 업무 ID와 공식 근거자료에 연결할 수 있다.
- [ ] 전체 pytest가 통과한다.
- [ ] `git diff --check`가 통과한다.

### 19.2 데이터 완료조건

- [x] `tasks` 63건과 `aliases` 316건 유지
- [x] `task_contacts` 93행, 연결 업무 51개, primary 45행
- [x] 보류 12개 업무의 활성 연락처 0행
- [x] 검색 API의 `primary_contact`와 primary 포함 `contacts`
- [x] A011·A012·F101 핵심 연락처와 `031-5189-4354` 제외
- [ ] 63개 업무의 공개문구와 공식 출처 연결 완료
- [ ] 중복·primary 중복·고아 FK 0건
- [ ] `foreign_key_check` 오류 0건과 `integrity_check` ok
- [ ] 운영 DB 백업·복원 절차 검증

### 19.3 운영 전 필수사항

다음 중 하나라도 미완료이면 정식 대민 운영 완료로 표시하지 않는다.

- [ ] 63개 공개문구의 기관 검수와 승인
- [ ] 공식 페이지 충돌·보류항목의 처리 결정
- [ ] 개인정보 처리와 실제 문자 발송 정책 승인
- [ ] 운영 서버·공유 rate limit·관리자 인증
- [ ] 정기 데이터 갱신 책임자와 주기
- [ ] 모바일·접근성 실기기 시험
- [ ] 노년층 5명 사용성 인수시험
- [ ] KWCAG 최종 점검
- [ ] 장애 대응·정기 백업·복원 시험

---

## 20. 쉬운 용어 설명

| 용어 | 쉬운 설명 |
|---|---|
| 프론트엔드 | 사용자가 브라우저에서 직접 보는 화면 |
| 백엔드 | 화면 뒤에서 검색·데이터 처리를 맡는 서버 부분 |
| Flask | 파이썬으로 웹서버와 API를 만드는 가벼운 웹 프레임워크 |
| API | 검색화면과 서버가 정해진 형식으로 정보를 주고받는 통로 |
| 데이터베이스(DB) | 정보를 일정한 구조로 저장·검색·수정하는 저장소 |
| SQLite | 별도 서버 설치 없이 한 파일로 사용하는 가벼운 데이터베이스 |
| FTS | 긴 글에서 검색어와 관련된 부분을 빠르게 찾는 전문검색 기능 |
| 동의어 사전 | `연명치료`, `사전연명`처럼 같은 업무를 가리키는 여러 표현의 연결표 |
| 저장소(Repository) | Git으로 코드 변경이력을 보관하고 되돌릴 수 있는 공간 |
| 배포 | 내 PC에서 만든 서비스를 다른 사람이 접속할 서버에 올리는 작업 |
| 서버 슬립 | 방문자가 없을 때 서버가 멈췄다가 다음 접속 때 다시 켜지는 절전 동작 |
| QR 코드 | 키오스크의 상세주소를 개인 스마트폰으로 옮겨 여는 그림형 링크 |

---

## 21. 참고 링크

- [화성특례시 보건소 공식 사이트](https://www.hscity.go.kr/health/index.do)
- [OpenAI Codex IDE 확장 공식 문서](https://developers.openai.com/codex/ide)
- [Python 3.12 공식 문서](https://docs.python.org/3.12/)
- [Flask 공식 문서](https://flask.palletsprojects.com/)
- [SQLite 공식 문서](https://www.sqlite.org/docs.html)
- [VS Code Python 공식 문서](https://code.visualstudio.com/docs/python/python-tutorial)

---

## 안전 실행 요약

매 작업은 현재 Git 차이와 관련 파일을 먼저 읽고, 기존 사용자 변경을 보존한다. 자동시험은 임시 DB를 사용하고 운영 API 검색으로 `event_logs`를 만들지 않는다.

~~~powershell
Set-Location -LiteralPath 'C:\Users\corle\OneDrive\바탕 화면\보건민원_검색엔진_MVP'
git status --short
git diff --check
.\.venv\Scripts\python.exe --version
.\.venv\Scripts\python.exe -m pytest -q
~~~

공개문구나 공개 데이터의 운영 DB 적용은 다음 절차를 모두 통과한 뒤에만 수행한다.

1. 원문 업무 ID와 공식 출처를 연결한다.
2. dry-run 보고서를 검토한다.
3. SQLite backup API로 시각이 포함된 복구본을 만든다.
4. 임시 DB에서 수량·재실행 동일성·rollback을 시험한다.
5. 사용자에게 운영 적용 전 변경예정을 다시 보고한다.
6. 별도 최종 승인 후 단일 트랜잭션으로 적용한다.
7. 수량·중복·FK·무결성·핵심 업무를 다시 검사한다.

기준일의 검증 연락처 93행은 이미 적용 완료됐으므로 재적재하지 않는다. 남은 일주일에는 노년층 민원인용 문구와 공개 안내정보만 제18절 일정에 따라 진행한다. 모든 단계에서 현재 디자인은 변경하지 않는다.
