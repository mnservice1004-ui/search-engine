# 동탄구보건소 보건민원 검색엔진

## VS Code·Codex 단계별 구현 매뉴얼

> 작성·검증 기준일: 2026-08-26  
> 대상 환경: Windows 10/11, VS Code, Python 3.12  
> 사용자 확인 환경: Python 3.12.10 설치, 프로젝트 폴더와 .venv 생성 완료  
> 공식 출처: [화성특례시 보건소](https://www.hscity.go.kr/health/index.do)  
> Codex 사용 기준: [OpenAI 공식 Codex IDE 확장 문서](https://developers.openai.com/codex/ide)

---

## 1. 먼저 알아야 할 현재 상태

현재 가지고 있는 보건민원_검색엔진_MVP는 실행 가능한 좋은 출발점이지만, 아직 “2차 수집 자료 전체를 검색하는 사이트”는 아니다.

현재 구현된 범위:

- index(1).html에서 가져온 민원업무 63건과 별칭 316건 검색
- 관련도 점수 계산, 추천 검색어, 상위 10건 표시
- 1~3층 배치도, 위치 마커, 상세 안내
- Flask API와 SQLite
- 문자 모의전송, 선택적 LLM 보조검색
- Streamlit 관리자 확인 화면
- 기본 자동시험 12개

아직 구현되지 않은 범위:

- 통합 엑셀의 현행 서비스·직원업무·시설 및 기관 조사기록 445건 검색
- 전체 보건소식·고시공고·입찰공고 제목 979건 검색
- 공식 게시물 507건 검색
- 공식 첨부파일 819개의 추출 본문 검색
- OCR·HWP·HWPX·PDF에서 추출한 본문 검색
- 수집 게시물·첨부·OCR 추출문서 1,396개를 SQLite 검색 DB에 적재하는 기능
- 사용자가 제공한 하늘 사진을 이용한 화면 디자인
- 화면과 문자에 표시되는 기관명을 “동탄구보건소”로 통일하는 작업

따라서 최종 목표는 통합 엑셀의 구조화 정보 1,424건과 2차 수집 문서 1,396건을 검색하게 만들고, 기존 63개 “민원·위치 검색”은 검수 중인 위치안내 시범기능으로 보존하는 것이다.

### 1.1 내일까지 완성할 현실적인 범위

| 우선순위 | 기능 | 내일까지 포함 여부 |
|---|---|---|
| P0 | 현행 서비스·직원업무·시설 및 기관 조사기록 445건 검색 | 필수 |
| P0 | 전체 게시판 제목 979건 검색 | 필수 |
| P0 | 공식자료 1,396개 문서·2,075개 FTS 청크 적재 | 필수 |
| P0 | 게시물·첨부본문 검색 API와 결과 화면 | 필수 |
| P0 | 공식 원문 링크, 등록일, 자료유형 표시 | 필수 |
| P1 | 기존 63개 민원업무 검색·지도·상세 | 유지 |
| P1 | 하늘 사진 기반 반응형 화면 | 필수 |
| P1 | 자동시험과 수동시험 | 필수 |
| P2 | OpenAI API를 이용한 검색어 확장 | 시연에서는 OFF 권장 |
| P2 | 실제 문자 발송 | 시연에서는 mock 유지 |
| P3 | Supabase·Vercel 공개 배포 | 로컬 시연 후 진행 |

내일까지의 합격선은 “내 PC에서 현행 구조화 정보와 공식 게시물·첨부본문을 검색하고 공식 원문으로 이동할 수 있으며, 기존 위치안내도 유지되는 상태”이다. 실제 문자 발송과 공개 배포를 서두르면 개인정보·비용·보안 문제가 커지므로 뒤로 미룬다.

### 1.2 예상 소요시간

| 단계 | 초보자 예상시간 |
|---|---:|
| 기존 실행 확인 | 30~60분 |
| 기관명·사진 화면 | 45~90분 |
| 엑셀·JSON·TXT 적재 | 2~3시간 |
| 검색 API | 1.5~2.5시간 |
| 세 탭 프런트엔드 | 1.5~2.5시간 |
| 기관정보·관리자 화면 | 1~1.5시간 |
| 전체 시험·오류수정 | 1~2시간 |
| 합계 | 약 8~13시간 |

직접 코드를 한 줄씩 타이핑하면 내일까지 초보자가 감당하기 어렵다. 이 매뉴얼의 Codex 프롬프트를 한 단계씩 실행하고, 매 단계의 완료 기준을 사용자가 확인하는 방식이면 로컬 시연본은 현실적인 범위다. 테스트가 실패한 상태에서 다음 단계로 넘어가지 않는다.

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
| 01-1000026005.jpg 등 4개 사진 | 하늘·공원 분위기의 프런트엔드 배경 후보 |
| 프로젝트기획서_보건민원 정보 검색 사이트.pdf | 최초 요구사항 기준 |
| index(1).html | 63개 업무·별칭·층별 지도 원본 |

현재 첨부목록에는 index(2).html이 없고 index(1).html만 있다. 따라서 이 매뉴얼은 실제로 확인 가능한 index(1).html과 현재 MVP ZIP을 기준으로 한다. 나중에 index(2).html을 받으면 기능 차이를 비교한 뒤 별도 반영한다.

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

## 3. 최종 구조

~~~mermaid
flowchart LR
    U[민원인 브라우저] --> F[HTML CSS JavaScript]
    F --> A[Flask API]
    A --> C[구조화 공식정보 1424건]
    A --> T[기존 위치안내 시범 63건]
    A --> D[공식자료 문서 1396건]
    C --> S[(SQLite FTS5)]
    T --> S
    D --> S
    A -. 결과 0건일 때만 .-> L[선택적 LLM 검색어 확장]
    A -. mock 또는 승인 후 .-> M[문자 서비스]
    Q[Streamlit 관리자 화면] --> S
~~~

### 3.1 사용기술별 역할

| 기술 | 이 프로젝트에서 하는 일 | 이번 로컬 시연 |
|---|---|---|
| VS Code | 폴더·터미널·Git diff·디버깅을 한곳에서 관리 | 사용 |
| Codex IDE 확장 | 단계별 파일 수정, 테스트 실행, 오류 분석 | 사용 |
| Python 3.12 | 데이터 적재·검색·API·시험 실행 | 사용 |
| openpyxl | 통합 XLSX를 한 번 읽어 SQLite로 적재 | 사용 |
| Flask | 브라우저와 검색 DB 사이의 REST API | 사용 |
| SQLite FTS5 | 구조화 정보·게시물·첨부본문의 로컬 전문검색 | 사용 |
| HTML·CSS·JavaScript | 세 탭, 하늘 사진 hero, 결과 카드, 지도·상세 | 사용 |
| Streamlit | 내부 관리자용 수량·오류 검수 화면 | 사용 |
| pytest | 기존 기능과 새 적재·검색 API 회귀시험 | 사용 |
| Git·GitHub | 단계별 체크포인트·변경이력; 원본·DB·키는 제외 | Git 사용, 원격 업로드는 선택 |
| OpenAI API | 기본검색 0건일 때만 검색어 확장 | 기본 OFF |
| SOLAPI | 승인 후 실제 문자 발송 | mock 유지 |
| Supabase | 공개 운영 시 중앙 DB | 후속 |
| Vercel 등 배포환경 | 공개 웹 배포 | 현재 ZIP에 설정이 없어 후속 검증 |
| PyInstaller | 내부 데이터 점검도구를 EXE로 배포할 때만 사용 | 후속 |

내일까지는 앞의 9개 기술로 로컬 시연본을 완성한다. 뒤의 OpenAI API·SOLAPI·Supabase·배포·PyInstaller는 핵심검색이 통과한 뒤 켠다.

### 3.2 세 검색영역을 분리하는 이유

현행 서비스, 민원·위치 결과, 공지·첨부자료는 의미가 다르다. 기존 63건은 index(1).html의 시범 위치자료이며, 공식 사이트의 현행 서비스 전체를 대표하지 않는다. 공식자료와 자동으로 대조되기 전까지는 “위치안내 검수 중” 상태로 취급한다.

- 현행 서비스·시설 검색은 “지금 누가, 무엇을 준비해, 언제·어디서 이용하는가”를 답한다.
- 민원·위치 검색은 “어느 부서·몇 층·어디로 가야 하는가”를 답한다.
- 공식자료 검색은 “어떤 게시물·첨부문서에 해당 내용이 있는가”를 답한다.

세 결과를 한 목록에 섞으면 오래된 채용공고와 현재 서비스가 같은 등급으로 보이는 문제가 생긴다. 화면에 다음 세 탭을 둔다.

1. 현행 서비스·시설
2. 민원·위치 안내 시범
3. 공식 게시물·첨부자료

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
5. 사용할 사진 한 장을 public\images\hero-dongtan.jpg라는 이름으로 복사한다.

PowerShell 예시:

~~~powershell
Set-Location -LiteralPath 'C:\Users\corle\OneDrive\바탕 화면\보건민원_검색엔진_MVP'
New-Item -ItemType Directory -Force source_data
New-Item -ItemType Directory -Force public\images

Copy-Item -LiteralPath 'C:\Users\corle\Downloads\동탄구보건소_공식정보_수집본_2026-08-26.xlsx' -Destination '.\source_data\'
Copy-Item -LiteralPath 'C:\Users\corle\Downloads\01-1000026005.jpg' -Destination '.\public\images\hero-dongtan.jpg'
~~~

다운로드 위치가 다르면 경로만 바꾼다. 압축을 풀기 전에는 ZIP이 전송 중 손상되지 않았는지 다음 명령으로 확인한다.

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
Expand-Archive -LiteralPath 'C:\Users\corle\Downloads\동탄구보건소_첨부파일_2차수집_2026-08-26.zip' -DestinationPath '.\source_data\' -Force

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
│  ├─ map_points.json
│  └─ tasks.json
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
source_data/
data/*.db
data/backups/
__pycache__/
.pytest_cache/
~~~

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

## 6. 1단계 — 현재 MVP 실행 확인

### 목표

코드를 고치기 전에 현재 상태가 실행되는지 확인한다.

### 6.1 PowerShell 실행

VS Code 메뉴에서 터미널 → 새 터미널을 연다.

~~~powershell
Set-Location -LiteralPath 'C:\Users\corle\OneDrive\바탕 화면\보건민원_검색엔진_MVP'
py -3.12 --version
Test-Path '.\.venv\Scripts\python.exe'
~~~

예상 결과:

~~~text
Python 3.12.10
True
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

### 6.3 환경파일과 DB 준비

~~~powershell
if (-not (Test-Path '.env')) { Copy-Item '.env.example' '.env' }
.\.venv\Scripts\python.exe scripts\init_db.py
~~~

예상 핵심 출력:

~~~text
업무 건수: 63
공식 업무전화 미등록: 63건
~~~

공식 전화가 63건 모두 비어 있는 것은 현재 데이터의 정상 상태다. 번호를 추측하여 입력하지 않는다.

### 6.4 자동시험

~~~powershell
.\.venv\Scripts\python.exe -m pytest -q
~~~

현재 제공 코드의 목표는 12 passed이다. 실패가 있으면 전체 오류 문장을 Codex에 붙여 넣고 다음 단계로 넘어가지 않는다.

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
3. scripts/init_db.py를 실행하여 업무 63건과 별칭 316건을 확인하라.
4. pytest 전체를 실행하라.
5. app.py를 실행하기 전 발생 가능한 오류를 보고하라.

검사 결과와 정확한 다음 명령만 보고하고 멈춰라.
~~~

### 완료 기준

- Python 3.12.10이 확인된다.
- 가상환경 python.exe를 직접 실행할 수 있다.
- SQLite 업무 63건이 생성된다.
- 자동시험이 모두 통과한다.
- http://127.0.0.1:5000이 열린다.

---

## 7. 2단계 — 기관명과 사진형 화면 수정

### 목표

현재 화면의 “동탄보건소”를 현행 기관명 “동탄구보건소”로 바꾸고, 첨부한 하늘 사진 분위기를 적용한다.

### 7.1 변경할 파일

| 파일 | 변경 |
|---|---|
| public/index.html | 제목·헤더·설명·공식출처 링크 |
| public/css/style.css | hero 사진·어두운 오버레이·반응형 간격 |
| sms_service.py | 문자 머리말의 기관명 |
| tests | 새 기관명과 기존 기능 회귀시험 |

역사적 게시물 제목에 있는 “동탄보건지소”나 “동탄보건소”까지 일괄 치환하면 안 된다. 현재 서비스 브랜드 문구만 바꾼다.

### 7.2 권장 화면 문구

~~~text
동탄구보건소
보건민원 정보 검색
민원업무·위치와 공식 게시물·첨부자료를 한곳에서 찾아보세요.
~~~

### 7.3 권장 CSS 핵심

Codex가 기존 .site-header 스타일을 다음 원칙으로 바꾸게 한다.

~~~css
.site-header {
  position: relative;
  min-height: 300px;
  display: flex;
  align-items: center;
  color: #fff;
  background:
    linear-gradient(120deg, rgba(10, 35, 56, .84), rgba(18, 81, 92, .48)),
    url("/images/hero-dongtan.jpg") center 42% / cover no-repeat;
}
~~~

텍스트 명암비를 위해 오버레이를 제거하지 않는다. 모바일에서는 min-height를 약 230px로 줄인다.

### 7.4 이 단계의 Codex 프롬프트

~~~text
보건민원_검색엔진_MVP의 현재 기능을 유지하면서 화면 브랜드와 hero 영역만 수정해라.

요구사항:
1. 현행 기관명은 정확히 “동탄구보건소”다.
2. public/images/hero-dongtan.jpg를 헤더 배경으로 사용한다.
3. 하늘과 나무가 보이되 흰 글자가 읽히도록 네이비·청록 반투명 오버레이를 사용한다.
4. 제목은 “동탄구보건소 보건민원 정보 검색”으로 한다.
5. PC·태블릿·모바일에서 깨지지 않게 한다.
6. 키보드 포커스와 prefers-reduced-motion 접근성을 유지한다.
7. sms_service.py의 현재 서비스 머리말만 동탄구보건소로 바꾼다.
8. 수집된 역사적 게시물 제목은 바꾸지 않는다.
9. 관련 테스트를 추가하고 전체 pytest를 실행한다.

이 단계 밖의 기능은 변경하지 마라.
완료 후 변경 파일, 테스트 결과, 화면 확인 항목을 보고하고 멈춰라.
~~~

### 완료 기준

- 화면 상단에 동탄구보건소가 표시된다.
- 하늘 사진이 찌그러지지 않는다.
- 흰 글자가 밝은 구름 위에서도 읽힌다.
- 모바일 폭 360px에서 가로 스크롤이 생기지 않는다.
- 기존 민원검색·지도 기능이 그대로 작동한다.

---

## 8. 3단계 — 수집자료 전체를 SQLite FTS에 적재

### 목표

먼저 통합 엑셀의 구조화 정보 1,424건을 색인한다. 이어서 최종 ZIP의 게시글 507건과 추출 레코드 889건을 출처별 문서로 보존하고, 검색 가능한 1,360개 문서를 3,000자 단위 2,075개 청크로 나누어 SQLite FTS5에 넣는다.

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
- 모든 외부 URL은 HTTPS와 hscity.go.kr 도메인을 검사한다.
- 행별 URL이 비어 있으면 요약 시트에 기록된 해당 시트의 대표 공식 원문만 대체 출처로 사용하고, 대표 원문도 없으면 실패한다.
- 빈 셀은 빈 문자열로 다루고 문자열 None이나 nan을 본문에 넣지 않는다.
- 수집본 원본 셀을 수정하지 않는다.
- 데이터오류_검증의 충돌 항목은 별도 관리자 경고로 보존하고, 안전한 적용 기준이 정해지기 전에는 확정 표시하지 않는다.

#### 8.A.5 이 단계의 Codex 프롬프트

~~~text
통합 엑셀의 구조화 공식정보를 SQLite FTS5에 적재하는 기능만 구현해라.

입력:
source_data/동탄구보건소_공식정보_수집본_2026-08-26.xlsx

구현:
1. requirements-dev.txt에 openpyxl>=3.1,<4를 추가한다.
2. sql/sqlite_schema.sql에 catalog_items와 catalog_items_fts를 추가한다.
3. scripts/import_catalog.py와 테스트를 만든다.
4. load_workbook(data_only=True, read_only=True)로 읽는다.
5. 직접 색인할 시트와 행 수는 service 96, institution 147, staff 82, news 920, notice 46, bid 13, medical_pharmacy 108, postpartum 4, other 8이다.
6. 합계 catalog_items와 FTS는 각각 정확히 1,424행이어야 한다.
7. 헤더 이름과 행 수가 다르면 DB를 변경하기 전에 실패하라.
8. --check 옵션은 헤더·수량·URL·필수값만 검사하고 DB를 변경하지 않는다.
9. 실제 import는 한 transaction에서 catalog_items와 FTS만 비운 뒤 다시 넣는다.
10. 기존 tasks, aliases, event_logs, 연락처와 source_documents는 변경하지 않는다.
11. 서비스_원문기록, 현행검색_24, 데이터오류_검증, HTML·첨부 검수시트는 민원인 검색 FTS에 넣지 않는다.
12. 직원 성명은 추측하지 않는다.
13. source_url은 HTTPS hscity.go.kr만 허용한다.
14. 빈 셀은 빈 문자열로 다루고 None 또는 nan이라는 글자를 저장하지 않는다.
15. institution에는 항상 원문확인 warning을 넣고 서술형 본문의 전화번호를 phone으로 승격하지 않는다.
16. 전화번호는 전용 열만 사용하며 --는 빈값으로 바꾼다.
17. 테스트는 작은 임시 XLSX와 임시 DB를 사용한다.

전체 테스트를 실행하라.

이 단계 밖의 기능은 변경하지 마라.
완료 후 변경 파일, 실행 명령, 9개 유형별 적재 수량, 테스트 결과를 보고하고 멈춰라.
~~~

#### 8.A.6 실행과 확인

~~~powershell
Copy-Item -LiteralPath '.\data\health_search.db' -Destination '.\data\health_search.before_collected_import.db' -Force
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe scripts\init_db.py
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

#### 8.B.7 이 단계의 Codex 프롬프트

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

#### 8.B.8 실행

먼저 DB를 정확한 파일명으로 백업한다.

~~~powershell
Copy-Item -LiteralPath '.\data\health_search.db' -Destination '.\data\health_search.before_second_pass.db' -Force
.\.venv\Scripts\python.exe scripts\init_db.py
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

### 완료 기준

- catalog_items와 catalog_items_fts가 각각 1,424행이다.
- 현행 서비스·직원업무·시설·기관 조사기록 445건과 게시판 제목 979건이 유형별로 분리된다.
- 게시글·첨부·OCR 자료가 source_type별로 분리된다.
- 두 번 실행해도 1,396 / 1,360 / 2,075 / 2,075가 유지된다.
- 기존 위치안내 시범 63건과 별칭 316건이 그대로다.
- 빈값·undefined·오류 HTML이 검색되지 않는다.
- 수집 당시 절대경로가 DB에 들어가지 않는다.
- tasks와 공식 연락처가 변경되지 않는다.

---

## 9. 4단계 — 현행정보와 공식자료 검색 API 구현

### 목표

현행 서비스·기관·직원업무·시설을 검색하는 API와, 전체 게시물 제목·상세본문·첨부본문을 검색하는 API를 추가한다.

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
- source_url과 page_url은 HTTPS hscity.go.kr 주소인지 다시 확인한다.
- asset_url은 보조정보로만 취급하고 결과의 기본 이동은 page_url로 한다.
- 검색 원문과 IP를 event_logs에 저장하지 않는다.
- API 응답에는 Cache-Control: no-store를 유지한다.

### 9.4 이 단계의 Codex 프롬프트

~~~text
SQLite catalog_items_fts, source_documents, document_chunks_fts를 검색하는 두 API만 구현해라.

변경 대상:
- db.py
- app.py
- 필요하면 별도 document_search.py
- tests

요구사항:
1. POST /api/catalog-search와 POST /api/content-search를 추가한다.
2. 검색어는 2~80자다.
3. 정규식 [0-9A-Za-z가-힣]{2,}로 안전한 토큰만 추출한다.
4. 원문 query를 FTS MATCH 문법에 직접 넣지 않는다.
5. 3자 이상은 trigram FTS, 2자 토큰은 파라미터화된 LIKE로 찾는다.
6. bm25 가중치는 title 8.0, category 또는 source_name 3.0, body 1.0으로 시작한다.
7. catalog-search는 현행 서비스·직원업무·시설·기관 조사기록 445건만 검색하고 item_type, 전화, 주소, 확인일, warning, source_url을 반환한다.
8. content-search는 news·notice·bid 제목 979건과 상세 문서 1,396건·FTS 2,075행을 함께 검색한다.
9. 같은 게시물의 catalog 제목행과 board/post_sn의 여러 문서·청크는 page_url 기준으로 한 게시물로 묶는다.
10. 게시물별 최고 청크를 240자 안팎 미리보기로 반환한다.
11. 각 API는 최대 20개를 반환하되 total_count는 100으로 잘리지 않게 한다.
12. 게시물 동점은 최신 posted_at 순이다.
13. source_url과 page_url은 HTTPS hscity.go.kr 주소만 반환한다.
14. source_type, extraction_method, is_ocr를 반환한다.
15. 과거 게시물과 OCR 결과에는 원문 확인 경고를 반환한다.
16. 검색어·IP·휴대전화번호를 로그에 저장하지 않는다.
17. tests는 실제 data/health_search.db를 쓰지 말고 임시 DB fixture를 사용한다.
18. 기존 /api/search와 63개 위치안내 시범검색 동작을 유지한다.
19. institution의 warning은 절대 숨기지 말고, 서술형 본문 속 전화번호를 현재 phone으로 승격하지 않는다.

테스트에 다음 사례를 포함한다:
- 예비신혼부부 건강검진 현행 서비스 검색
- 직원 업무와 의료기관·약국 유형 검색
- 첨부 없는 게시물 제목 검색
- 모자보건교육 검색 성공
- 완전히없는검색어 0건
- 한 글자 검색 400
- FTS 연산자·따옴표·SQL 특수문자 입력 안전
- 2자 검색어 금연과 난임 검색
- 여러 청크가 한 게시물로 합쳐짐
- 공식 도메인이 아닌 URL 제외

전체 테스트를 실행하라.

이 단계 밖의 기능은 변경하지 마라.
완료 후 변경 파일, API 예시, 테스트 결과, 남은 위험을 보고하고 멈춰라.
~~~

### 9.5 API 시험

서버를 다시 실행한 뒤 새 PowerShell에서 실행한다.

~~~powershell
$catalogBody = @{ query = '예비신혼부부 건강검진' } | ConvertTo-Json
Invoke-RestMethod -Uri 'http://127.0.0.1:5000/api/catalog-search' -Method Post -ContentType 'application/json' -Body $catalogBody

$body = @{ query = '모자보건교육' } | ConvertTo-Json
Invoke-RestMethod -Uri 'http://127.0.0.1:5000/api/content-search' -Method Post -ContentType 'application/json' -Body $body
~~~

### 완료 기준

- 예비신혼부부 건강검진이 현행 서비스에서 검색된다.
- 첨부가 없는 게시물도 제목으로 검색된다.
- 모자보건교육이 공식자료에서 검색된다.
- 같은 게시물이 중복 카드로 나오지 않는다.
- 공식 게시물 page_url이 포함된다.
- 기존 연명치료 민원업무 검색은 R003을 유지한다.
- 테스트 DB가 운영용 event_logs를 오염시키지 않는다.

---

## 10. 5단계 — 세 탭 검색 화면 구현

### 목표

현행 서비스·시설, 민원·위치 안내 시범, 공식자료의 세 탭을 한 화면에서 제공한다.

### 10.1 화면 구성

~~~text
[하늘 사진 Hero]
동탄구보건소
보건민원 정보 검색

[ 현행 서비스·시설 ] [ 민원·위치 안내 시범 ] [ 공식 게시물·첨부자료 ]

[ 검색창                                      ][검색]

현행정보 결과 카드:
자료유형 / 확인일
서비스·시설·업무명
대상·기간·비용·준비물·주소·전화 요약
[공식 원문 열기]

공식자료 결과 카드:
게시판 / 등록일 / 자료유형
게시물 제목
검색어 주변 본문 미리보기
[공식 원문 열기]
~~~

### 10.2 결과 카드 필수 정보

현행정보 카드:

- 자료유형
- 서비스·기관·업무·시설명
- 대상·기간·비용·준비물·주소·공식 업무전화 중 존재하는 값
- 확인일
- 공식 원문 링크
- 자료에 warning이 있으면 숨기지 않고 눈에 띄게 표시
- 업무별 예외와 변동 가능성 안내

공식자료 카드:

- 게시판
- 등록일
- 게시물 제목
- 게시글 본문인지 첨부본문인지
- OCR 추출자료 여부
- 검색어 주변 미리보기
- 공식 원문 링크
- “일정·지원대상·전화번호는 원문에서 최종 확인” 문구

### 10.3 프런트엔드 보안

- 서버 응답을 innerHTML로 넣지 않는다.
- createElement와 textContent를 사용한다.
- 공식 링크는 새 창으로 열 때 rel="noopener noreferrer"를 지정한다.
- URL의 protocol과 hostname을 JavaScript에서 확인한다.
- 게시글HTML_청크를 그대로 렌더링하지 않는다.

### 10.4 이 단계의 Codex 프롬프트

~~~text
기존 민원·위치 화면을 유지하고 “현행 서비스·시설”과 “공식 게시물·첨부자료” 탭을 추가해라.

변경 대상:
- public/index.html
- public/css/style.css
- public/js/app.js
- tests 또는 프런트 검증 코드

요구사항:
1. 세 탭은 현행 서비스·시설 / 민원·위치 안내 시범 / 공식 게시물·첨부자료다.
2. 첫 탭은 /api/catalog-search를 사용하고 서비스·기관·직원업무·시설 정보를 표시한다.
3. 민원 탭은 기존 /api/search와 지도·상세 기능을 그대로 사용하며 “위치안내 검수 중”을 표시한다.
4. 공식자료 탭은 /api/content-search를 사용한다.
5. 현행정보 카드에는 유형, 제목, 요약, 전화·주소·확인일, warning, 공식 원문 링크를 표시한다.
6. 공식자료 카드에는 게시판, 등록일, 자료유형, 제목, 미리보기, 공식 원문 링크를 표시한다.
7. 같은 창에 원문을 덮어쓰지 말고 새 탭으로 연다.
8. href는 HTTPS이며 hostname이 hscity.go.kr과 정확히 같거나 .hscity.go.kr로 끝나는 공식 하위도메인인 경우만 허용한다. 단순 endsWith('hscity.go.kr')만 쓰지 마라.
9. 서버 텍스트는 innerHTML 없이 textContent로만 표시한다.
10. 검색 중, 결과 없음, 오류, 재시도 상태를 각각 표시한다.
11. 키보드 Tab·Enter, aria-selected, aria-live를 지원한다.
12. 모바일 360px, 태블릿 768px, PC 1440px에서 가로 스크롤이 없어야 한다.
13. OCR 자료에는 “OCR 추출 참고” 배지를 표시한다.
14. “최신 일정·대상·비용·연락처는 공식 원문 확인” 문구를 표시한다.
15. 기존 검색·지도·문자 mock 회귀시험을 통과시킨다.

이 단계 밖의 기능은 변경하지 마라.
완료 후 변경 파일, 테스트 결과, 수동 화면 점검표를 보고하고 멈춰라.
~~~

### 10.5 수동 화면시험

| 시험 | 기대 결과 |
|---|---|
| 현행정보 탭에서 예비신혼부부 건강검진 | 대상·준비물·공식 원문 표시 |
| 현행정보 탭에서 기관·직원업무·시설명 | 각 자료유형이 구분되어 표시 |
| 민원 탭에서 연명치료 | R003이 첫 결과 |
| 민원 결과 선택 | 해당 층 배치도와 상세 표시 |
| 공식자료 탭에서 모자보건교육 | 2026-08-19 게시물 포함 |
| 공식자료 탭에서 금연 | 제목·본문 관련 결과 표시 |
| 공식 원문 열기 | hscity.go.kr 새 탭 |
| 한 글자 입력 | 입력 안내, 서버 400 처리 |
| 존재하지 않는 검색어 | 빈 결과 안내 |
| Tab 키 이동 | 탭·입력·버튼·카드·링크 순서 정상 |
| 모바일 폭 360px | 잘림·겹침 없음 |

---

## 11. 6단계 — 공식 기관정보와 데이터 오류 표시

### 목표

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

### 11.2 이 단계의 Codex 프롬프트

~~~text
공식 수집본의 기관정보를 프런트 하단 안내영역에 추가해라.

표시:
- 동탄구보건소
- 화성시 동탄구 노작로 226-9
- 평일 09:00~18:00
- 점심 12:00~13:00
- 일반 접수마감 11:40 / 17:40
- 확인 기준일 2026-08-26
- 공식사이트 링크 https://www.hscity.go.kr/health/index.do

주의:
1. 업무별 운영시간 예외가 있을 수 있다는 문구를 넣어라.
2. 우편번호는 공식 페이지 충돌이 있으므로 표시하지 마라.
3. 전화번호는 용도가 구분된 곳에만 표시하고 대표번호처럼 합치지 마라.
4. 외부 링크 보안과 접근성을 유지하라.
5. 역사적 게시물의 오래된 전화번호를 현재 번호처럼 재사용하지 마라.

이 단계 밖의 기능은 변경하지 마라.
완료 후 변경 파일과 화면 확인 항목을 보고하고 멈춰라.
~~~

---

## 12. 7단계 — 관리자 화면과 데이터 검증 보완

### 목표

관리자가 구조화 정보 1,424건, 기존 위치안내 시범 63건, 공식자료 문서 1,396개·FTS 청크 2,075개의 상태를 확인하게 한다.

### 12.1 관리자 화면에 추가할 지표

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

검색 원문, IP, 휴대전화번호를 관리자 통계에 저장하지 않는다.

### 12.2 현재 코드의 보완점

admin/dashboard.py는 현재 .env를 직접 읽지 않는다. Supabase 전환까지 고려한다면 프로젝트 루트의 .env를 load_dotenv로 읽도록 고친다.

scripts/init_db.py는 현재 SQLITE_PATH 환경값이 아니라 data/health_search.db만 사용한다. 내일까지는 .env의 SQLITE_PATH를 기본값 data/health_search.db로 유지한다. 사용자 지정 경로 지원은 별도 테스트 후 추가한다.

### 12.3 이 단계의 Codex 프롬프트

~~~text
Streamlit 관리자 화면에 공식자료 적재 검증 지표를 추가해라.

요구사항:
1. 프로젝트 루트 .env를 명시적으로 load_dotenv한다.
2. 기존 업무·연락처·비식별 이벤트 지표를 유지한다.
3. catalog_items·FTS 전체와 item_type별 수, source_documents 전체·검색가능 문서, document_chunks·FTS 수, 고유 게시물, 게시판별, source_type별, OCR 상태를 표시한다.
4. 빈 본문, 허용되지 않은 URL, 중복 key가 있으면 빨간 경고를 표시한다.
5. 검색어 원문, IP, 휴대전화번호는 조회·표시·저장하지 않는다.
6. 관리화면은 데이터를 수정하지 않는 읽기 전용으로 유지한다.
7. 임시 DB를 사용하는 테스트를 추가한다.

이 단계 밖의 기능은 변경하지 마라.
완료 후 변경 파일, 실행 명령, 테스트 결과를 보고하고 멈춰라.
~~~

실행:

~~~powershell
.\.venv\Scripts\python.exe -m streamlit run admin\dashboard.py
~~~

기본 접속 주소:

~~~text
http://localhost:8501
~~~

---

## 13. 8단계 — 최종 자동시험

### 13.1 실행 명령

~~~powershell
.\.venv\Scripts\python.exe -m compileall app.py db.py search_engine.py scripts admin tests
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe scripts\import_catalog.py --check
.\.venv\Scripts\python.exe scripts\import_second_pass.py --check
~~~

### 13.2 필수 합격 조건

| 검증항목 | 합격 기준 |
|---|---|
| Python 문법 | compileall 오류 0 |
| 기존 민원업무 | 63건 |
| 기존 별칭 | 316건 |
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
| 자동시험 | 실패 0 |
| 외부 URL | hscity.go.kr HTTPS만 |
| 비밀정보 | Git 추적 0 |

### 13.3 Git 검사

~~~powershell
git status
git check-ignore .env
git check-ignore source_data\attachments_second_pass
git check-ignore source_data\동탄구보건소_공식정보_수집본_2026-08-26.xlsx
~~~

.env와 원본 수집 폴더가 ignored로 확인되어야 한다.

### 13.4 최종 Codex 검수 프롬프트

~~~text
이 프로젝트의 최종 로컬 시연 전 검수를 수행해라.

검사만 먼저 하고 임의 수정하지 마라.

검사 범위:
1. Python compileall
2. pytest 전체
3. 민원업무 63건, 별칭 316건
4. catalog_items와 catalog_items_fts 각각 1,424행, 유형별 합계 445와 979
5. source_documents 1,396행, searchable 1,360행
6. document_chunks와 FTS 각각 2,075행
7. /api/health, /api/search, /api/catalog-search, /api/content-search
8. FTS 쿼리 토큰 정제, SQL 파라미터 바인딩과 공식 URL allowlist
9. 프런트 innerHTML 사용 여부
10. .env, DB, source_data 원본의 Git 제외
11. 동탄구보건소 명칭
12. 모바일·키보드 접근성
13. LLM OFF, SMS mock
14. Flask 개발서버가 외부에 공개되지 않았는지

문제를 치명적/중요/경미로 분류하라.
치명적 문제가 없으면 수동 인수시험 순서를 제시하고 멈춰라.
~~~

---

## 14. 시연 당일 실행 순서

### 14.1 서버 시작

~~~powershell
Set-Location -LiteralPath 'C:\Users\corle\OneDrive\바탕 화면\보건민원_검색엔진_MVP'
.\.venv\Scripts\python.exe scripts\import_catalog.py --check
.\.venv\Scripts\python.exe scripts\import_second_pass.py --check
.\.venv\Scripts\python.exe app.py
~~~

### 14.2 브라우저 시연

1. http://127.0.0.1:5000을 연다.
2. 하늘 사진과 동탄구보건소 이름을 확인한다.
3. 현행 서비스·시설 탭에서 예비신혼부부 건강검진을 검색한다.
4. 대상·준비물·확인일·공식 원문을 확인한다.
5. 민원·위치 안내 시범 탭에서 연명치료를 검색하고 층별 위치를 확인한다.
6. 공식자료 탭에서 모자보건교육을 검색한다.
7. 게시물 제목·등록일·미리보기를 확인한다.
8. 공식 원문 열기를 눌러 hscity.go.kr로 이동한다.
9. 존재하지 않는 검색어의 빈 상태를 보여 준다.
10. 문자 버튼은 mock 또는 공식 연락처 미등록 상태임을 설명한다.

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
| 문자 버튼 비활성 | 공식 연락처 미등록 | 정상 상태, 번호를 임의 입력하지 않음 |
| OpenAI 기능이 안 됨 | ENABLE_LLM=false | 내일까지는 정상, 기본검색부터 완성 |
| 관리자에 Supabase가 안 보임 | .env 미로딩 | dashboard.py에서 load_dotenv 보완 |
| 검색 결과 총수가 100 | 기존 코드의 내부 제한 | 공식자료 API는 전체 개수를 별도 계산 |

OneDrive가 SQLite database is locked 오류를 반복해서 만들면 프로젝트를 C:\Projects\보건민원_검색엔진_MVP로 복사하고 그 위치에서 실행한다.

---

## 16. OpenAI API·문자·Supabase는 언제 켜는가

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

내일까지는 ENABLE_LLM=false를 권장한다.

### 16.2 실제 문자

SMS_MODE=mock을 유지한다. 실제 전송은 다음이 모두 끝난 뒤 켠다.

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

---

## 17. 현재 코드에서 반드시 기억할 한계

1. 현재 MVP ZIP 자체는 통합 엑셀과 2차 수집 자료를 검색하지 않는다.
2. 현재 63개 업무의 출처는 index(1).html이며 공식 2차 수집 데이터와 자동 연결되지 않았다.
3. 63개 위치자료 중 일부는 위치확인 또는 사용자지정 상태이므로 공식 확정 배치도처럼 표시하면 안 된다.
4. 공식 연락처는 현재 tasks DB에 0건이므로 실제 문자 운영이 불가능하다.
5. 기존 Flask app.run은 개발서버이므로 인터넷 공개 운영용이 아니다.
6. 기존 Limiter의 memory 저장소는 여러 서버가 공유하는 운영 제한이 아니다.
7. 기존 test_api.py는 운영 DB를 직접 사용해 이벤트 로그를 남길 수 있으므로 임시 DB fixture로 바꿔야 한다.
8. 기존 /api/search의 total_count는 내부 100건 제한 때문에 대규모 자료의 총수 계산에 사용할 수 없다.
9. 현재 public 화면은 사용자의 하늘 사진을 포함하지 않으므로 2단계 수정이 필요하다.
10. 원본의 역사적 전화번호를 현재 연락처로 자동 승격하면 안 된다.
11. OCR 텍스트에는 오인식이 있을 수 있으므로 결과 카드에 공식 원문 확인을 요구한다.
12. 이 사이트는 의료진단 도구가 아니다. 응급상황은 검색 결과가 아니라 119와 의료기관 이용을 안내해야 한다.

---

## 18. 단계별 진행 체크표

| 단계 | 사용자 확인 문장 | 통과 후 다음 단계 |
|---|---|---|
| 1 | “기존 화면이 열리고 테스트가 통과했다” | 기관명·사진 |
| 2 | “동탄구보건소와 사진 화면이 정상이다” | 자료 적재 |
| 3 | “catalog 1,424·문서 1,396·검색가능 1,360·청크 2,075 적재 완료다” | 검색 API |
| 4 | “API에서 건강검진과 모자보건교육이 검색된다” | 프런트 검색 |
| 5 | “세 탭의 카드와 원문 링크가 정상이다” | 기관정보 |
| 6 | “기관정보와 주의문구가 정상이다” | 관리자 검증 |
| 7 | “관리자 지표가 맞다” | 최종시험 |
| 8 | “전체 테스트 실패 0이다” | 시연 |

실제 작업에서는 한 단계가 끝날 때마다 화면 또는 터미널 결과를 확인한 뒤 다음 프롬프트를 입력한다.

---

## 19. 최종 완료 판정

### 로컬 시연 가능

- [ ] Python 3.12 가상환경으로 실행
- [ ] 기존 민원업무 63건 검색
- [ ] 별칭 316건 유지
- [ ] 구조화 catalog_items·FTS 각각 1,424건
- [ ] 현행정보 445건·게시판 제목 979건 검색
- [ ] 공식자료 문서 1,396건·검색 가능 1,360건 적재
- [ ] 검색 청크·FTS 각각 2,075건
- [ ] 공식자료 검색·게시물 중복제거
- [ ] 공식 원문 링크
- [ ] 동탄구보건소 명칭
- [ ] 하늘 사진 반응형 화면
- [ ] 자동시험 실패 0
- [ ] LLM OFF
- [ ] SMS mock
- [ ] .env·원본·DB Git 제외

### 아직 운영 공개 부적합

다음 중 하나라도 미완료이면 외부 대민 운영본으로 표시하지 않는다.

- [ ] 공식 연락처와 담당업무 전수검증
- [ ] 우편번호 등 공식 페이지 충돌 해결
- [ ] 개인정보 처리와 문자 발송 승인
- [ ] 운영 서버·공유 rate limit
- [ ] 관리자 인증
- [ ] 정기 데이터 갱신 책임자
- [ ] 모바일·접근성 실기기 시험
- [ ] 장애 대응·백업·복원 시험

---

## 20. 참고 링크

- [화성특례시 보건소 공식 사이트](https://www.hscity.go.kr/health/index.do)
- [OpenAI Codex IDE 확장 공식 문서](https://developers.openai.com/codex/ide)
- [Python 3.12 공식 문서](https://docs.python.org/3.12/)
- [Flask 공식 문서](https://flask.palletsprojects.com/)
- [SQLite 공식 문서](https://www.sqlite.org/docs.html)
- [VS Code Python 공식 문서](https://code.visualstudio.com/docs/python/python-tutorial)

---

## 한 줄 실행 요약

~~~powershell
Set-Location -LiteralPath 'C:\Users\corle\OneDrive\바탕 화면\보건민원_검색엔진_MVP'
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe scripts\init_db.py
.\.venv\Scripts\python.exe scripts\import_catalog.py --check
.\.venv\Scripts\python.exe scripts\import_catalog.py
.\.venv\Scripts\python.exe scripts\import_second_pass.py --check
.\.venv\Scripts\python.exe scripts\import_second_pass.py
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe app.py
~~~

브라우저:

~~~text
http://127.0.0.1:5000
~~~

이 요약 명령은 3단계에서 scripts/import_catalog.py와 scripts/import_second_pass.py를 Codex가 구현한 뒤 사용할 수 있다.
