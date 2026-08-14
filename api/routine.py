# -*- coding: utf-8 -*-
"""
api/routine.py
==============
Vercel Serverless Function (Python) — AI 몰입 루틴 설계 엔드포인트.

    POST /api/routine
      요청 : {"tasks": "...", "minutes": 120, "startTime": "14:00",
              "energy": 3, "workType": "글쓰기", "blocker": "알림"}
      성공 : 200 {"ok": true, "data": {...}}
      실패 : 4xx/5xx {"ok": false, "error": {"code": "...", "message": "..."}}

처리 순서
    1) 요청 검증      : 메서드 / 본문 크기 / 필수값 / 범위
    2) 호출 빈도 제한 : 같은 IP 의 과도한 연속 호출 차단 (과금 보호)
    3) LLM 호출       : OpenAI 또는 Gemini (환경 변수에 있는 키로 자동 선택)
    4) 응답 정규화    : JSON 파싱 → 블록 검증 → 실제 시각(HH:MM) 계산
    5) 결과 반환

보안
    API 키는 소스에 두지 않고 os.environ 에서만 읽는다.
    (로컬은 .env, 배포는 Vercel 프로젝트의 Environment Variables)
"""

from http.server import BaseHTTPRequestHandler
from datetime import datetime, timedelta, timezone

import json
import os
import re
import time

import requests


# ---------------------------------------------------------------------------
# 상수
# ---------------------------------------------------------------------------

OPENAI_URL = "https://api.openai.com/v1/chat/completions"
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

DEFAULT_OPENAI_MODEL = "gpt-4o-mini"
DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"

UPSTREAM_TIMEOUT = 20          # LLM 응답 대기 한도(초). 프론트 타임아웃(25초)보다 짧게 둔다.
MAX_BODY_BYTES = 8 * 1024      # 요청 본문 최대 크기 (8KB)
MAX_TASKS_LEN = 300            # 할 일 입력 최대 길이
MIN_TASKS_LEN = 5

ALLOWED_MINUTES = (60, 90, 120, 180, 240, 360)
MAX_BLOCKS = 12

KST = timezone(timedelta(hours=9))  # 시작 시각이 없을 때 사용할 기준 시간대

# 호출 빈도 제한 (같은 IP 기준)
RATE_LIMIT_COUNT = 8
RATE_LIMIT_WINDOW = 60         # 초

# 서버리스 인스턴스가 살아 있는 동안만 유지되는 임시 기록.
# 완벽한 차단이 아니라 "실수로 연타했을 때의 과금 보호" 목적이다.
_RECENT_CALLS = {}


# ---------------------------------------------------------------------------
# 오류 표현
# ---------------------------------------------------------------------------

class ApiError(Exception):
    """HTTP 상태 코드 + 프론트가 해석할 오류 코드를 함께 전달한다."""

    def __init__(self, status, code, message):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


def classify_upstream(status):
    """LLM 제공자가 돌려준 HTTP 상태를 서비스 오류 코드로 변환한다."""
    if status in (401, 403):
        return 502, "UPSTREAM_AUTH", "AI 서비스 인증에 실패했습니다."
    if status == 429:
        return 429, "UPSTREAM_QUOTA", "AI 사용량 한도를 초과했습니다."
    if 400 <= status < 500:
        return 502, "UPSTREAM_ERROR", "AI 요청이 거부되었습니다."
    return 502, "UPSTREAM_ERROR", "AI 서비스에 일시적인 문제가 있습니다."


# ---------------------------------------------------------------------------
# 1) 입력 검증
# ---------------------------------------------------------------------------

def validate(payload):
    """요청 본문을 검사하고 정규화된 딕셔너리를 돌려준다."""
    if not isinstance(payload, dict):
        raise ApiError(400, "INVALID_INPUT", "요청 형식이 올바르지 않습니다.")

    tasks = str(payload.get("tasks") or "").strip()
    if not tasks:
        raise ApiError(400, "EMPTY_INPUT", "오늘 할 일을 입력해 주세요.")
    if len(tasks) < MIN_TASKS_LEN:
        raise ApiError(400, "TOO_SHORT", "할 일을 조금 더 구체적으로 적어 주세요.")
    if len(tasks) > MAX_TASKS_LEN:
        raise ApiError(400, "TOO_LONG", "할 일은 300자 이내로 입력해 주세요.")

    try:
        minutes = int(payload.get("minutes", 120))
    except (TypeError, ValueError):
        raise ApiError(400, "INVALID_INPUT", "사용할 수 있는 시간 값이 올바르지 않습니다.")
    if minutes not in ALLOWED_MINUTES:
        raise ApiError(400, "INVALID_INPUT", "사용할 수 있는 시간 값이 올바르지 않습니다.")

    try:
        energy = int(payload.get("energy", 3))
    except (TypeError, ValueError):
        raise ApiError(400, "INVALID_INPUT", "컨디션 값이 올바르지 않습니다.")
    if not 1 <= energy <= 5:
        raise ApiError(400, "INVALID_INPUT", "컨디션은 1~5 사이여야 합니다.")

    return {
        "tasks": tasks,
        "minutes": minutes,
        "energy": energy,
        "work_type": str(payload.get("workType") or "기타 사무").strip()[:30],
        "blocker": str(payload.get("blocker") or "").strip()[:100],
        "start_at": parse_start_time(payload.get("startTime")),
    }


def parse_start_time(value):
    """'HH:MM' 문자열을 datetime 으로 바꾼다. 값이 없거나 형식이 틀리면 현재(KST) 시각."""
    now = datetime.now(KST)
    if isinstance(value, str) and re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", value.strip()):
        hour, minute = (int(part) for part in value.strip().split(":"))
        return now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    # 값이 없으면 5분 단위로 올림한 현재 시각을 쓴다.
    return (now + timedelta(minutes=(5 - now.minute % 5) % 5)).replace(second=0, microsecond=0)


# ---------------------------------------------------------------------------
# 2) 호출 빈도 제한
# ---------------------------------------------------------------------------

def check_rate_limit(client_ip):
    now = time.time()
    history = [t for t in _RECENT_CALLS.get(client_ip, []) if now - t < RATE_LIMIT_WINDOW]
    if len(history) >= RATE_LIMIT_COUNT:
        raise ApiError(429, "RATE_LIMITED", "요청이 너무 잦습니다. 잠시 후 다시 시도해 주세요.")
    history.append(now)
    _RECENT_CALLS[client_ip] = history

    # 메모리가 무한정 늘지 않도록 오래된 항목을 정리한다.
    if len(_RECENT_CALLS) > 500:
        for ip in [k for k, v in _RECENT_CALLS.items() if not v or now - v[-1] > RATE_LIMIT_WINDOW]:
            _RECENT_CALLS.pop(ip, None)


# ---------------------------------------------------------------------------
# 3) LLM 호출
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = (
    "당신은 대학원생과 지식노동자의 '집중 시간 설계'를 돕는 코치입니다. "
    "사용자의 남은 시간과 컨디션에 맞춰 현실적인 시간 블록 계획을 만듭니다. "
    "항상 설명 없이 JSON 객체 하나만 출력합니다."
)

USER_PROMPT = """아래 조건으로 오늘의 집중 시간표를 설계하세요.

[조건]
- 오늘 해야 할 일: {tasks}
- 사용할 수 있는 총 시간: {minutes}분
- 시작 시각: {start_hhmm}
- 현재 컨디션: {energy}/5 (1=매우 낮음, 5=매우 좋음)
- 작업 유형: {work_type}
- 방해 요소: {blocker}

[설계 규칙]
1. 블록의 duration_min 합계는 {minutes}분을 넘지 않아야 합니다. (±5분 이내로 맞추세요)
2. type 은 "focus"(집중) 또는 "break"(회복) 둘 중 하나입니다.
3. 집중 블록은 컨디션이 높으면 45~50분, 보통이면 35~40분, 낮으면 20~25분으로 잡습니다.
4. 집중 블록 사이에는 5~15분짜리 break 블록을 넣습니다. 마지막 블록은 focus 로 끝냅니다.
5. 머리를 많이 쓰는 작업을 앞쪽(컨디션이 남아 있을 때)에 배치하고, 뒤쪽에는 정리·검토형 작업을 둡니다.
6. 마지막 집중 블록에는 '다음 작업 예약'처럼 내일로 이어지는 마무리 작업을 포함하세요.
7. goal 은 "이만큼 하면 성공"이라고 판단할 수 있는 측정 가능한 완료 기준으로 씁니다.
8. 사용자가 적지 않은 할 일을 새로 만들어 내지 마세요.

[출력 형식] — 아래 JSON 객체 하나만 출력 (코드블록·주석·설명 금지)
{{
  "headline": "오늘 설계의 한 줄 요약 (25자 이내)",
  "strategy": "왜 이 순서로 배치했는지 2문장 설명",
  "blocks": [
    {{
      "type": "focus",
      "title": "블록 이름 (20자 이내)",
      "goal": "완료 기준 한 문장",
      "tip": "이 블록에서 지킬 요령 한 문장",
      "duration_min": 45
    }}
  ],
  "checklist": ["마무리 시 확인할 항목 3개"],
  "caution": "오늘 특히 주의할 점 한 문장"
}}

모든 문장은 한국어 존댓말로 씁니다."""


def build_prompt(data):
    return USER_PROMPT.format(
        tasks=data["tasks"],
        minutes=data["minutes"],
        start_hhmm=data["start_at"].strftime("%H:%M"),
        energy=data["energy"],
        work_type=data["work_type"],
        blocker=data["blocker"] or "특별히 없음",
    )


def call_llm(prompt):
    """설정된 키에 따라 OpenAI 또는 Gemini 를 호출하고 (본문텍스트, 제공자, 모델)을 반환한다."""
    openai_key = (os.environ.get("OPENAI_API_KEY") or "").strip()
    gemini_key = (os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY") or "").strip()

    if openai_key:
        model = (os.environ.get("OPENAI_MODEL") or "").strip() or DEFAULT_OPENAI_MODEL
        return _call_openai(openai_key, model, prompt), "openai", model
    if gemini_key:
        model = (os.environ.get("GEMINI_MODEL") or "").strip() or DEFAULT_GEMINI_MODEL
        return _call_gemini(gemini_key, model, prompt), "gemini", model

    # 키가 없으면 외부 호출을 시도하지 않고 바로 안내한다.
    raise ApiError(500, "NO_API_KEY", "서버에 AI API 키가 설정되어 있지 않습니다.")


def _post(url, headers, body):
    """공통 POST 래퍼 — 타임아웃/네트워크/상태코드 오류를 ApiError 로 바꾼다."""
    try:
        response = requests.post(url, headers=headers, json=body, timeout=UPSTREAM_TIMEOUT)
    except requests.exceptions.Timeout:
        raise ApiError(504, "TIMEOUT", "AI 서비스 응답이 지연되고 있습니다.")
    except requests.exceptions.RequestException:
        raise ApiError(502, "UPSTREAM_ERROR", "AI 서비스에 연결하지 못했습니다.")

    if response.status_code >= 400:
        status, code, message = classify_upstream(response.status_code)
        # 응답 본문에는 키가 섞일 수 있으므로 클라이언트로 그대로 내보내지 않는다.
        print("[routine] upstream error %s: %s" % (response.status_code, response.text[:300]))
        raise ApiError(status, code, message)

    try:
        return response.json()
    except ValueError:
        raise ApiError(502, "PARSE_ERROR", "AI 응답을 해석하지 못했습니다.")


def _call_openai(api_key, model, prompt):
    data = _post(
        OPENAI_URL,
        {"Authorization": "Bearer %s" % api_key, "Content-Type": "application/json"},
        {
            "model": model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.7,
            "response_format": {"type": "json_object"},  # JSON 만 나오도록 강제
        },
    )
    try:
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        raise ApiError(502, "PARSE_ERROR", "AI 응답 구조가 예상과 다릅니다.")


def _call_gemini(api_key, model, prompt):
    data = _post(
        GEMINI_URL.format(model=model),
        {"x-goog-api-key": api_key, "Content-Type": "application/json"},
        {
            "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.7, "responseMimeType": "application/json"},
        },
    )
    try:
        parts = data["candidates"][0]["content"]["parts"]
        return "".join(part.get("text", "") for part in parts)
    except (KeyError, IndexError, TypeError):
        raise ApiError(502, "PARSE_ERROR", "AI 응답 구조가 예상과 다릅니다.")


# ---------------------------------------------------------------------------
# 4) 응답 정규화
# ---------------------------------------------------------------------------

def extract_json(text):
    """모델이 코드블록이나 설명을 섞어 보내도 JSON 객체 부분만 뽑아 파싱한다."""
    if not text or not text.strip():
        raise ApiError(502, "PARSE_ERROR", "AI 응답이 비어 있습니다.")

    cleaned = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start == -1 or end <= start:
        raise ApiError(502, "PARSE_ERROR", "AI 응답에서 JSON 을 찾지 못했습니다.")
    try:
        return json.loads(cleaned[start:end + 1])
    except json.JSONDecodeError:
        raise ApiError(502, "PARSE_ERROR", "AI 응답을 JSON 으로 해석하지 못했습니다.")


def clip(value, limit, fallback=""):
    text = str(value or "").strip()
    return (text[:limit] if text else fallback)


def normalize(raw, data):
    """
    모델 출력에서 필요한 값만 뽑아 검증하고, 총 시간 안에 들어오도록 정리한다.
    시작/종료 시각은 모델의 말이 아니라 서버가 직접 계산한다. (표시 오류 방지)
    """
    if not isinstance(raw, dict):
        raise ApiError(502, "PARSE_ERROR", "AI 응답 형식이 올바르지 않습니다.")

    raw_blocks = raw.get("blocks")
    if not isinstance(raw_blocks, list) or not raw_blocks:
        raise ApiError(502, "PARSE_ERROR", "AI 가 시간 블록을 만들지 못했습니다.")

    cursor = data["start_at"]
    remaining = data["minutes"]
    blocks = []

    for item in raw_blocks[:MAX_BLOCKS]:
        if not isinstance(item, dict) or remaining <= 0:
            continue

        title = clip(item.get("title"), 40)
        if not title:
            continue

        try:
            duration = int(float(item.get("duration_min", 30)))
        except (TypeError, ValueError):
            duration = 30
        duration = max(5, min(duration, 120))
        # 남은 시간을 넘기면 잘라 붙이고, 5분 미만만 남으면 블록을 만들지 않는다.
        if duration > remaining:
            duration = remaining
        if duration < 5:
            break

        block_type = "break" if str(item.get("type", "")).lower().startswith("b") else "focus"
        end = cursor + timedelta(minutes=duration)

        blocks.append({
            "type": block_type,
            "title": title,
            "goal": clip(item.get("goal"), 120),
            "tip": clip(item.get("tip"), 120),
            "duration_min": duration,
            "start": cursor.strftime("%H:%M"),
            "end": end.strftime("%H:%M"),
        })

        cursor = end
        remaining -= duration

    if not blocks:
        raise ApiError(502, "PARSE_ERROR", "AI 가 유효한 시간 블록을 만들지 못했습니다.")

    # 마지막이 휴식으로 끝나면 어색하므로 제거한다. (단, 블록이 하나뿐이면 유지)
    while len(blocks) > 1 and blocks[-1]["type"] == "break":
        blocks.pop()

    checklist = raw.get("checklist")
    if isinstance(checklist, str):
        checklist = [checklist]
    if not isinstance(checklist, list):
        checklist = []
    checklist = [clip(item, 60) for item in checklist if clip(item, 60)][:5]
    if not checklist:
        checklist = ["오늘 끝낸 분량 기록하기", "내일 첫 작업 한 줄로 적어 두기", "책상 정리하고 마치기"]

    return {
        "headline": clip(raw.get("headline"), 40, "오늘의 몰입 설계"),
        "strategy": clip(raw.get("strategy"), 240),
        "blocks": blocks,
        "checklist": checklist,
        "caution": clip(raw.get("caution"), 160, "무리하지 말고 컨디션에 맞춰 조정하세요."),
    }


# ---------------------------------------------------------------------------
# 5) HTTP 핸들러
# ---------------------------------------------------------------------------

class handler(BaseHTTPRequestHandler):
    """Vercel 이 요청마다 호출하는 진입점. 클래스 이름은 반드시 handler 여야 한다."""

    # --- 공통 응답 -------------------------------------------------------
    def _send(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_error(self, error):
        self._send(error.status, {"ok": False, "error": {"code": error.code, "message": error.message}})

    def _client_ip(self):
        forwarded = self.headers.get("x-forwarded-for", "")
        return forwarded.split(",")[0].strip() or self.client_address[0]

    # --- 라우팅 ----------------------------------------------------------
    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Allow", "POST, OPTIONS")
        self.end_headers()

    def do_GET(self):
        self._send(405, {
            "ok": False,
            "error": {"code": "METHOD_NOT_ALLOWED", "message": "이 주소는 POST 요청만 받습니다."},
        })

    def do_POST(self):
        try:
            payload = self._read_json_body()
            data = validate(payload)
            check_rate_limit(self._client_ip())

            text, provider, model = call_llm(build_prompt(data))
            result = normalize(extract_json(text), data)
            result["provider"] = provider
            result["model"] = model

            self._send(200, {"ok": True, "data": result})

        except ApiError as error:
            self._send_error(error)
        except Exception as error:  # 예상하지 못한 오류도 JSON 형식으로 돌려준다.
            print("[routine] unexpected error: %s: %s" % (type(error).__name__, error))
            self._send(500, {
                "ok": False,
                "error": {"code": "UNKNOWN", "message": "서버에서 알 수 없는 오류가 발생했습니다."},
            })

    # --- 본문 읽기 -------------------------------------------------------
    def _read_json_body(self):
        try:
            length = int(self.headers.get("content-length") or 0)
        except ValueError:
            raise ApiError(400, "INVALID_INPUT", "요청 형식이 올바르지 않습니다.")

        if length <= 0:
            raise ApiError(400, "EMPTY_INPUT", "요청 내용이 비어 있습니다.")
        if length > MAX_BODY_BYTES:
            raise ApiError(413, "TOO_LONG", "요청 내용이 너무 깁니다.")

        try:
            return json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise ApiError(400, "INVALID_INPUT", "요청 본문이 올바른 JSON 이 아닙니다.")

    # 기본 로그 형식을 줄여 Vercel 로그를 읽기 쉽게 만든다.
    def log_message(self, fmt, *args):
        return
