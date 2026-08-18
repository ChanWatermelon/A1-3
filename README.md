# 몰입 설계소 (Molip Design Lab)

> 오늘 남은 시간과 지금의 컨디션을 입력하면, AI가 **집중 블록 타임테이블**을 설계해 주는 웹 서비스입니다.

할 일 목록은 있는데 "뭐부터 하지"로 시간을 흘려보내는 대학원생·연구원·지식노동자를 위해 만들었습니다.
몰입 설계소는 **무엇부터 할지 / 어디까지 하면 끝인지 / 언제 쉴지**를 대신 정해 시간표로 그려 줍니다.

**배포 URL:** <https://a1-3-gamma.vercel.app>
**GitHub:** <https://github.com/ChanWatermelon/A1-3>

---

## 1. 목차

1. [서비스 소개](#2-서비스-소개)
2. [기술 스택](#3-기술-스택)
3. [화면 구성](#4-화면-구성)
4. [프로젝트 구조](#5-프로젝트-구조)
5. [로컬 실행 방법](#6-로컬-실행-방법)
6. [환경 변수 설정](#7-환경-변수-설정-중요)
7. [Vercel 배포 방법](#8-vercel-배포-방법)
8. [AI 기능 설계](#9-ai-기능-설계)
9. [오류 처리 정책](#10-오류-처리-정책)
10. [동작 원리](#11-동작-원리-과제-학습-목표-정리)
11. [문제 해결(FAQ)](#12-문제-해결-트러블슈팅)

---

## 2. 서비스 소개

| 항목 | 내용 |
| --- | --- |
| 서비스명 | 몰입 설계소 |
| 한 줄 소개 | 남은 시간을 집중 블록으로 바꿔 주는 AI 몰입 설계 도구 |
| 타겟 사용자 | 마감이 있는 대학원생·연구원, 자기 시간을 스스로 배분해야 하는 지식노동자 |
| 해결하는 문제 | 할 일 목록만으로는 착수가 안 되고, 순서를 고르는 데 에너지를 다 쓴다 |
| 제공 가치 | 시각이 찍힌 시간표 + 블록별 완료 기준 + 회복(휴식) 배치 |

자세한 기획 내용은 [`docs/서비스기획서.md`](docs/서비스기획서.md) 를 참고하세요.

---

## 3. 기술 스택

| 구분 | 사용 기술 | 비고 |
| --- | --- | --- |
| 프론트엔드 | HTML5, CSS3, Vanilla JavaScript (ES6+) | 프레임워크·빌드 도구 없음 |
| 백엔드 | Vercel Serverless Functions (**Python 3.12**) | `api/` 폴더의 파일이 곧 엔드포인트 |
| HTTP 클라이언트 | `requests` | `requirements.txt` 에 정의 |
| AI API | OpenAI Chat Completions **또는** Google Gemini | 설정된 키를 자동 감지 |
| 배포 | Vercel (GitHub 연동 자동 배포) | `vercel.json` 으로 함수 옵션 지정 |
| 그 외 | localStorage(다크 모드·최근 기록), IntersectionObserver(스크롤 효과) | 외부 라이브러리 0개 |

> **CDN·외부 라이브러리를 전혀 쓰지 않습니다.** 폰트·아이콘·애니메이션 모두 순수 CSS로 구현했습니다.

---

## 4. 화면 구성

한 페이지 안에서 상단 메뉴로 이동하는 **5개 섹션** 구조입니다. (모바일에서는 햄버거 메뉴)

| # | 섹션 | 앵커 | 내용 |
| --- | --- | --- | --- |
| 1 | 홈 | `#home` | 서비스 한 줄 가치 제안, CTA 버튼, 결과 미리보기 카드 |
| 2 | 서비스 소개 | `#about` | 해결하는 문제 3가지 + 동작 방식 4단계(입력→요청→AI→표시) |
| 3 | **AI 몰입 설계** | `#design` | **핵심 기능.** 입력 폼 + 결과 타임라인 + 최근 기록 |
| 4 | 집중 가이드 | `#tips` | FAQ 아코디언 5개 + 집중 팁 3개 |
| 5 | 문의하기 | `#contact` | 문의 폼 (이름/이메일/유형/내용) |

**반응형 기준점**

| 화면 | 폭 | 레이아웃 |
| --- | --- | --- |
| 데스크톱 | 1025px 이상 | 히어로 2단, 카드 3열, 설계 화면 좌우 2단 |
| 태블릿 | 761 ~ 1024px | 히어로 1단, 카드 2열, 설계 화면 상하 배치 |
| 모바일 | 760px 이하 | 전체 1열, 상단 메뉴 → 햄버거 메뉴로 전환 |

---

## 5. 프로젝트 구조

```
a1-3/
├── index.html              # 전체 화면(5개 섹션)
├── css/
│   └── style.css           # 디자인 토큰 · 다크 모드 · 반응형
├── js/
│   ├── main.js             # 공통 UI (다크 모드/메뉴/스크롤/토스트)
│   ├── routine.js          # AI 기능 (입력 검증 → fetch → 결과 렌더링)
│   └── contact.js          # 문의 폼
├── api/                    # ← Vercel Serverless Functions (Python)
│   ├── routine.py          #   POST /api/routine  : AI 루틴 설계
│   ├── contact.py          #   POST /api/contact  : 문의 접수 (+웹훅 연동)
│   └── health.py           #   GET  /api/health   : 배포/환경 변수 점검
├── images/
│   ├── favicon.svg
│   └── og-image.svg
├── docs/
│   ├── 서비스기획서.md
│   ├── 테스트-시나리오.md
│   ├── AI-코딩도구-사용기록.md
│   └── 증빙자료-가이드.md
├── dev_server.py           # 로컬 개발 서버 (배포에는 사용되지 않음)
├── requirements.txt        # requests
├── vercel.json             # 보안 헤더 설정 (함수는 Vercel이 자동 인식)
├── .vercelignore           # 배포본에서 제외할 파일 (dev_server.py, docs/ 등)
├── .env.example            # 환경 변수 이름 템플릿 (값 없음)
├── .gitignore              # .env 등 민감 파일 제외
└── README.md
```

**프론트와 백엔드의 경계**

- 프론트(`index.html`, `css/`, `js/`)는 **API 키를 전혀 알지 못합니다.** `/api/...` 주소만 압니다.
- 백엔드(`api/`)만 환경 변수에서 키를 읽어 외부 AI API를 호출합니다.

---

## 6. 로컬 실행 방법

Python 3.10 이상이 필요합니다.

```bash
# 1) 저장소 받기
git clone https://github.com/ChanWatermelon/A1-3.git
cd A1-3

# 2) (권장) 가상환경
python -m venv .venv
.venv\Scripts\activate          # Windows
source .venv/bin/activate       # macOS / Linux

# 3) 패키지 설치
pip install -r requirements.txt

# 4) 환경 변수 파일 만들기 (아래 7번 참고)
copy .env.example .env          # Windows
cp   .env.example .env          # macOS / Linux

# 5) 실행
python dev_server.py            # → http://localhost:3000
```

실행하면 다음이 표시됩니다.

```
[API 라우트]
  · /api/contact  ←  api/contact.py
  · /api/health   ←  api/health.py
  · /api/routine  ←  api/routine.py

서버 실행 중 →  http://localhost:3000
```

포트를 바꾸려면 `python dev_server.py --port 8080`.

> **`dev_server.py` 는 무엇인가요?**
> Vercel은 `api/routine.py` 파일을 자동으로 `/api/routine` 주소에 연결해 줍니다.
> 로컬에는 그 기능이 없으므로, 같은 규칙을 흉내 내어 정적 파일과 `api/` 함수를 함께 띄우는
> 개발 전용 서버를 만들었습니다. **배포에는 전혀 사용되지 않습니다.**
> (Vercel CLI가 있다면 `vercel dev` 로 실제 배포 환경과 동일하게 실행할 수도 있습니다.)

### 환경 변수가 잘 들어갔는지 확인

브라우저에서 <http://localhost:3000/api/health> 를 열면 다음과 같이 표시됩니다.

```json
{
  "ok": true,
  "ai_configured": true,
  "provider": "openai",
  "webhook_configured": false
}
```

`ai_configured` 가 `false` 면 키가 읽히지 않은 것입니다. **키 값 자체는 절대 출력되지 않습니다.**

---

## 7. 환경 변수 설정 (중요)

> **이 저장소의 어떤 파일에도 실제 API 키 값은 들어 있지 않습니다.**
> 키는 코드가 아니라 환경 변수로만 전달합니다.

### 필요한 키

| 이름 | 필수 여부 | 설명 | 발급처 |
| --- | --- | --- | --- |
| `OPENAI_API_KEY` | 둘 중 **1개 필수** | OpenAI API 키 | <https://platform.openai.com/api-keys> |
| `GEMINI_API_KEY` | 둘 중 **1개 필수** | Google Gemini API 키 | <https://aistudio.google.com/apikey> |

### 방법 A. 로컬 — `.env` 파일

```bash
copy .env.example .env      # Windows
cp   .env.example .env      # macOS / Linux
```

`.env` 를 열어 값을 채웁니다.

```dotenv
OPENAI_API_KEY=여기에_본인_키
```

`.env` 는 `.gitignore` 에 등록되어 있어 **커밋되지 않습니다.**

### 방법 B. 배포 — Vercel 환경 변수

1. Vercel 프로젝트 → **Settings → Environment Variables**
2. `Key` 에 `OPENAI_API_KEY`, `Value` 에 키 값을 입력
3. 적용 환경으로 **Production / Preview / Development** 를 모두 체크
4. **Save** 후 **Deployments → 최신 배포 → Redeploy**
   (환경 변수는 빌드 시점에 주입되므로 저장만으로는 반영되지 않습니다.)

### 왜 환경 변수로 관리하나요?

1. **유출 방지** — 코드에 적으면 GitHub 공개 순간 키가 노출되고, 봇이 수 분 내에 긁어 갑니다.
2. **교체 용이** — 키를 바꿔도 코드를 수정할 필요가 없습니다.
3. **환경 분리** — 개발용/운영용 키를 다르게 쓸 수 있습니다.
4. **과금 보호** — 유출된 키는 그대로 요금 청구로 이어집니다.

### 키가 유출된 것 같다면

1. 해당 콘솔(OpenAI/Google)에서 즉시 **키 폐기(revoke) 후 재발급**
2. Vercel 환경 변수를 새 키로 교체하고 재배포
3. 커밋 이력에 남았다면 히스토리 정리
   ```bash
   # 파일을 추적에서 제외
   git rm --cached .env
   git commit -m "chore: .env 추적 제외"
   # 이미 푸시된 이력에서 지워야 한다면 (주의: 히스토리가 바뀝니다)
   git filter-branch --index-filter "git rm --cached --ignore-unmatch .env" HEAD
   ```
   **단, 이미 공개된 키는 삭제해도 안전하지 않습니다. 반드시 재발급하세요.**

---

## 8. Vercel 배포 방법

```bash
# 1) GitHub 저장소에 올리기
git init
git add .
git commit -m "feat: 몰입 설계소 초기 구현"
git branch -M main
git remote add origin https://github.com/ChanWatermelon/A1-3.git
git push -u origin main
```

2. <https://vercel.com> 로그인 → **Add New → Project** → GitHub 저장소 선택
3. 설정은 **그대로 두고** (Framework Preset: `Other`, Build Command 비움, Output Directory 비움)
4. **Environment Variables** 에 `OPENAI_API_KEY` 추가 → **Deploy**
5. 배포가 끝나면 `https://<프로젝트명>.vercel.app` 접속
---

## 9. AI 기능 설계

### 입력 (사용자 → 브라우저)

| 항목 | 형식 | 필수 | 제약 |
| --- | --- | --- | --- |
| 오늘 할 일 | 텍스트 | **필수** | 5 ~ 300자 |
| 사용할 수 있는 시간 | 선택 | 필수 | 60 / 90 / 120 / 180 / 240 / 360분 |
| 시작 시각 | 시각 | 선택 | 비우면 현재 시각 |
| 컨디션 | 1 ~ 5 | 필수 | 슬라이더 |
| 작업 유형 | 선택 | 필수 | 글쓰기 / 코딩 / 논문 읽기 / 실험·분석 / 발표 준비 / 기타 |
| 방해 요소 | 텍스트 | 선택 | 100자 이내 |

### 출력 (AI → 화면)

| 항목 | 내용 |
| --- | --- |
| `headline` | 오늘 설계의 한 줄 요약 |
| `strategy` | 왜 이 순서로 배치했는지 |
| `blocks[]` | 시작·종료 시각, 집중/회복 구분, 제목, **완료 기준**, 요령, 소요 시간 |
| `checklist[]` | 마무리 시 확인할 항목 3개 |
| `caution` | 오늘 특히 주의할 점 |

### 요청/응답 예시

```http
POST /api/routine
Content-Type: application/json

{ "tasks": "학회 발표 슬라이드 초안 만들기", "minutes": 120,
  "startTime": "14:00", "energy": 3, "workType": "발표 준비", "blocker": "알림" }
```

```json
{
  "ok": true,
  "data": {
    "headline": "오후 2시간, 초안부터 끝냅니다",
    "strategy": "컨디션이 보통이라 40분 집중을 기본으로 잡았습니다. ...",
    "blocks": [
      { "type": "focus", "title": "발표 슬라이드 뼈대", "goal": "목차 5장 확정",
        "tip": "디자인은 건드리지 않습니다.", "duration_min": 40,
        "start": "14:00", "end": "14:40" }
    ],
    "checklist": ["슬라이드 파일 저장하기", "..."],
    "caution": "새 자료를 찾기보다 있는 내용을 정리하세요.",
    "provider": "openai",
    "model": "gpt-4o-mini"
  }
}
```

### 설계상 중요한 점: **시각은 AI가 아니라 서버가 계산합니다**

모델에게는 각 블록의 `duration_min`(소요 분)만 요구하고,
실제 `start`/`end` 시각은 서버가 `시작 시각 + 누적 소요 시간`으로 직접 계산합니다.
LLM이 시각 덧셈을 틀리는 문제를 원천적으로 없애고, **총 시간이 입력값을 절대 넘지 않도록** 보장합니다.

---

## 10. 오류 처리 정책

사용자에게는 **원인 + 다음에 할 행동**을 함께 안내합니다.

| 상황 | HTTP | 코드 | 사용자에게 보이는 안내 |
| --- | --- | --- | --- |
| 빈 입력 | 400 | `EMPTY_INPUT` | "할 일을 입력해 주세요" (서버 요청 없이 즉시 차단) |
| 5자 미만 | 400 | `TOO_SHORT` | "조금만 더 적어 주세요" |
| 300자 초과 | 400 | `TOO_LONG` | "입력이 너무 깁니다" |
| 잘못된 시간/컨디션 값 | 400 | `INVALID_INPUT` | "입력값을 확인해 주세요" |
| 연속 호출(1분 8회 초과) | 429 | `RATE_LIMITED` | "잠시 후 다시 시도해 주세요" |
| 서버에 키 미설정 | 500 | `NO_API_KEY` | "AI 기능이 아직 설정되지 않았습니다" |
| AI 인증 실패(401/403) | 502 | `UPSTREAM_AUTH` | "AI 서비스 인증에 실패했습니다" |
| AI 한도 초과(429) | 429 | `UPSTREAM_QUOTA` | "AI 사용량 한도를 초과했습니다" |
| AI 서버 오류(5xx) | 502 | `UPSTREAM_ERROR` | "AI 서비스가 불안정합니다" |
| 응답이 JSON이 아님 | 502 | `PARSE_ERROR` | "결과를 이해하지 못했습니다" |
| **AI 응답 20초 초과** | 504 | `TIMEOUT` | "응답이 너무 늦습니다" |
| **브라우저 25초 초과** | — | `TIMEOUT` | 요청을 중단하고 안내 (AbortController) |
| 네트워크 끊김 | — | `NETWORK` | "네트워크에 연결할 수 없습니다" |

**지연 처리 UX**: 8초가 지나면 "조금 더 걸리고 있습니다"로 문구를 바꿔 멈춘 것처럼 보이지 않게 하고,
25초에 도달하면 요청을 끊습니다. (서버 타임아웃 20초 < 브라우저 25초 순서로 맞춰 두었습니다.)

**입력 오류와 시스템 오류의 버튼이 다릅니다** — 사용자가 고칠 수 있는 오류는 `입력 수정하기`(입력칸으로 이동),
시스템 오류는 `다시 시도`(같은 값으로 재요청) 버튼이 나옵니다.

---

## 11. 동작 원리 (과제 학습 목표 정리)

### HTML / CSS / JavaScript의 역할

| 언어 | 역할 | 이 프로젝트에서의 예 |
| --- | --- | --- |
| **HTML** | 구조와 의미 | `<form>`, `<section>`, `<label>` — 화면에 무엇이 있는지 |
| **CSS** | 표현 | 색 토큰, 반응형 배치, 다크 모드 — 어떻게 보이는지 |
| **JavaScript** | 동작 | 입력 검증, `fetch` 요청, 결과 DOM 생성 — 무엇이 일어나는지 |

### 입력 → 요청 → 응답 → 화면의 흐름

```
[사용자] 폼에 입력하고 버튼 클릭
   ↓  submit 이벤트
[JS]  event.preventDefault() 로 새로고침 막기
   ↓  빈 입력이면 여기서 중단 (네트워크 낭비 없음)
[JS]  fetch('/api/routine', { method:'POST', body: JSON.stringify(...) })
   ↓  같은 도메인의 서버로 HTTP 요청
[Python]  api/routine.py 의 handler.do_POST() 실행
   ↓  환경 변수에서 키를 읽어 AI API 호출 (requests.post)
[AI API]  JSON 문자열 응답
   ↓
[Python]  JSON 파싱 → 블록 검증 → 시각 계산 → {"ok": true, "data": ...} 반환
   ↓  HTTP 응답
[JS]  await response.json() → createElement 로 타임라인 DOM 생성
   ↓
[화면]  결과 표시
```

### Vercel Serverless Functions란?

항상 켜져 있는 서버를 두는 대신, **요청이 올 때만 함수가 실행되고 끝나면 사라지는** 구조입니다.

- `api/routine.py` 파일을 두면 Vercel이 자동으로 `/api/routine` 주소를 만들어 줍니다.
- 파일 안의 `class handler(BaseHTTPRequestHandler)` 가 진입점입니다. (이름이 `handler` 여야 합니다)
- `requirements.txt` 의 패키지는 배포 시 자동 설치됩니다.
- **함수는 요청마다 초기화될 수 있습니다.** 그래서 이 프로젝트의 호출 빈도 제한은
  "완벽한 차단"이 아니라 "연타 방지" 수준으로만 동작합니다. (코드 주석에도 명시)

**왜 프론트에서 AI API를 직접 부르지 않나요?**
브라우저 JS에 키를 넣으면 개발자 도구에서 누구나 볼 수 있습니다. 서버가 키를 대신 들고 있는 이 구조를
**프록시 패턴**이라고 하며, 서버리스 함수의 가장 흔한 용도입니다.

### 로컬 환경과 배포 환경의 차이

| | 로컬 | 배포(Vercel) |
| --- | --- | --- |
| 실행 주체 | `dev_server.py` (내가 띄운 프로세스) | Vercel이 요청마다 함수 실행 |
| 주소 | `http://localhost:3000` | `https://<프로젝트>.vercel.app` |
| 환경 변수 | `.env` 파일 | 프로젝트 Settings의 Environment Variables |
| 반영 시점 | 저장 후 재실행 | `git push` → 자동 빌드/배포 |
| 시간대 | 내 PC 시간 | UTC (그래서 코드에서 KST로 명시 변환) |

**로컬에서 되는데 배포에서 안 될 때** 확인 순서:
`/api/health` 로 환경 변수 확인 → Vercel의 **Deployments → Functions 로그** 확인 → 브라우저 콘솔/네트워크 탭 확인.

---

## 12. 문제 해결 (트러블슈팅)

| 증상 | 원인 | 해결 |
| --- | --- | --- |
| 배포 후 AI 기능만 실패 | 환경 변수 미설정 또는 재배포 안 함 | Vercel에 변수 추가 후 **Redeploy** |
| `/api/health` 가 404 | `api/` 폴더 위치가 루트가 아님 | 저장소 최상위에 `api/` 가 있어야 함 |
| `ModuleNotFoundError: requests` | `requirements.txt` 누락 | 루트에 `requirements.txt` 가 있는지 확인 |
| 빌드 실패 — `No python entrypoint found in default locations` | **Framework Preset이 파이썬 프레임워크로 잡힘** | 파이썬 프레임워크 프리셋은 `api/` 파일별 함수보다 **우선**한다. 프리셋이 잡히면 `api/*.py` 가 개별 함수가 되지 않고 대표 진입점(`app.py` 등)을 찾다가 실패한다. → **Vercel → Settings → Build and Deployment → Framework Preset 을 `Other` 로 변경 후 Redeploy** ([문서](https://vercel.com/docs/functions/runtimes/python/api-directory)) |
| 빌드 실패 — `maxDuration` / `memory` 관련 | 요금제가 허용하지 않는 값 지정 | `vercel.json` 의 `functions` 블록은 필수가 아니므로 삭제 (Vercel이 `api/*.py` 를 자동 인식) |
| 로컬에서 `python` 이 실행 안 됨 (Windows) | Microsoft Store 스텁 | `py dev_server.py` 로 실행 |
| 응답이 계속 25초 후 끊김 | 모델 응답 지연 | 더 빠른 모델(`gpt-4o-mini`)로 `OPENAI_MODEL` 지정 |
| 결과 시간이 이상함 | — | 시각은 서버가 계산하므로, `시작 시각` 입력값을 확인 |
| 다크 모드가 안 바뀜 | localStorage 차단(시크릿 모드 등) | 현재 세션에는 적용되며 새로고침 시 초기화됨 |

---
