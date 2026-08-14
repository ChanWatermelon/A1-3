# -*- coding: utf-8 -*-
"""
api/contact.py
==============
Vercel Serverless Function (Python) — 문의 접수 엔드포인트.

    POST /api/contact
      요청 : {"name": "...", "email": "...", "topic": "...", "message": "..."}
      성공 : 200 {"ok": true, "message": "..."}
      실패 : 4xx/5xx {"ok": false, "error": {"code": "...", "message": "..."}}

동작
    · 필수값/길이/이메일 형식을 서버에서 한 번 더 검증한다.
      (프론트 검증은 사용자 편의용이고, 실제 신뢰 경계는 서버다.)
    · 환경 변수 CONTACT_WEBHOOK_URL 이 설정되어 있으면 그 주소로 내용을 전달한다.
      (보너스 과제: Slack / Make / Zapier 같은 외부 자동화 도구 연동)
    · 웹훅이 없거나 전달에 실패해도 사용자에게는 접수 완료로 응답하고,
      서버 로그에 남겨 운영자가 확인할 수 있게 한다.
"""

from http.server import BaseHTTPRequestHandler
from datetime import datetime, timedelta, timezone

import json
import os
import re
import time

import requests


MAX_BODY_BYTES = 8 * 1024
MAX_MESSAGE_LEN = 500
MIN_MESSAGE_LEN = 10
WEBHOOK_TIMEOUT = 8
KST = timezone(timedelta(hours=9))

EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]{2,}$")

RATE_LIMIT_COUNT = 5
RATE_LIMIT_WINDOW = 300  # 5분
_RECENT_CALLS = {}


class ApiError(Exception):
    def __init__(self, status, code, message):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


def validate(payload):
    if not isinstance(payload, dict):
        raise ApiError(400, "INVALID_INPUT", "요청 형식이 올바르지 않습니다.")

    name = str(payload.get("name") or "").strip()
    message = str(payload.get("message") or "").strip()
    email = str(payload.get("email") or "").strip()
    topic = str(payload.get("topic") or "기타").strip()[:20]

    if not name or not message:
        raise ApiError(400, "EMPTY_INPUT", "이름과 문의 내용을 입력해 주세요.")
    if len(message) < MIN_MESSAGE_LEN:
        raise ApiError(400, "TOO_SHORT", "문의 내용을 10자 이상 입력해 주세요.")
    if len(message) > MAX_MESSAGE_LEN:
        raise ApiError(400, "TOO_LONG", "문의 내용은 500자 이내로 입력해 주세요.")
    if email and not EMAIL_PATTERN.match(email):
        raise ApiError(400, "INVALID_EMAIL", "이메일 형식이 올바르지 않습니다.")

    return {"name": name[:40], "email": email[:80], "topic": topic, "message": message}


def check_rate_limit(client_ip):
    now = time.time()
    history = [t for t in _RECENT_CALLS.get(client_ip, []) if now - t < RATE_LIMIT_WINDOW]
    if len(history) >= RATE_LIMIT_COUNT:
        raise ApiError(429, "RATE_LIMITED", "문의가 너무 잦습니다. 잠시 후 다시 시도해 주세요.")
    history.append(now)
    _RECENT_CALLS[client_ip] = history


def forward_to_webhook(entry):
    """
    외부 자동화 도구로 문의 내용을 전달한다.
    실패해도 예외를 밖으로 던지지 않는다. (사용자 경험 > 알림 전달)
    """
    url = (os.environ.get("CONTACT_WEBHOOK_URL") or "").strip()
    if not url:
        return False

    summary = (
        "[몰입 설계소 문의]\n"
        "· 유형: {topic}\n"
        "· 이름: {name}\n"
        "· 이메일: {email}\n"
        "· 접수: {at}\n"
        "-----\n{message}"
    ).format(at=entry["received_at"], email=entry["email"] or "(미입력)", **entry)

    try:
        response = requests.post(
            url,
            json={"text": summary, "data": entry},  # Slack 은 text, 그 외 도구는 data 를 사용
            timeout=WEBHOOK_TIMEOUT,
        )
        if response.status_code >= 400:
            print("[contact] webhook failed: HTTP %s" % response.status_code)
            return False
        return True
    except requests.exceptions.RequestException as error:
        print("[contact] webhook error: %s" % type(error).__name__)
        return False


class handler(BaseHTTPRequestHandler):

    def _send(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _client_ip(self):
        forwarded = self.headers.get("x-forwarded-for", "")
        return forwarded.split(",")[0].strip() or self.client_address[0]

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
            try:
                length = int(self.headers.get("content-length") or 0)
            except ValueError:
                raise ApiError(400, "INVALID_INPUT", "요청 형식이 올바르지 않습니다.")
            if length <= 0:
                raise ApiError(400, "EMPTY_INPUT", "요청 내용이 비어 있습니다.")
            if length > MAX_BODY_BYTES:
                raise ApiError(413, "TOO_LONG", "요청 내용이 너무 깁니다.")

            try:
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                raise ApiError(400, "INVALID_INPUT", "요청 본문이 올바른 JSON 이 아닙니다.")

            entry = validate(payload)
            check_rate_limit(self._client_ip())
            entry["received_at"] = datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S KST")

            delivered = forward_to_webhook(entry)
            if not delivered:
                # 웹훅이 없어도 최소한 로그에는 남긴다. (개인정보는 이름/유형까지만)
                print("[contact] received: topic=%s name=%s len=%d"
                      % (entry["topic"], entry["name"], len(entry["message"])))

            self._send(200, {
                "ok": True,
                "delivered": delivered,
                "message": "문의가 접수되었습니다. 소중한 의견 감사합니다!",
            })

        except ApiError as error:
            self._send(error.status, {
                "ok": False,
                "error": {"code": error.code, "message": error.message},
            })
        except Exception as error:
            print("[contact] unexpected error: %s: %s" % (type(error).__name__, error))
            self._send(500, {
                "ok": False,
                "error": {"code": "UPSTREAM_ERROR", "message": "접수 처리 중 오류가 발생했습니다."},
            })

    def log_message(self, fmt, *args):
        return
