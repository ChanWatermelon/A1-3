# -*- coding: utf-8 -*-
"""
api/health.py
=============
Vercel Serverless Function (Python) — 배포 상태 점검용 엔드포인트.

    GET /api/health
      → {"ok": true, "python": "3.12.x", "ai_configured": true, "provider": "openai", ...}

용도
    배포 직후 "환경 변수가 제대로 등록됐는지"를 브라우저에서 바로 확인하기 위한 것이다.
    로컬과 배포 환경의 차이(로컬 .env vs Vercel Environment Variables)를 디버깅할 때 쓴다.

주의
    키의 "설정 여부(True/False)"만 노출하고 값은 절대 반환하지 않는다.
"""

from http.server import BaseHTTPRequestHandler
from datetime import datetime, timedelta, timezone

import json
import os
import platform

KST = timezone(timedelta(hours=9))


def has_env(*names):
    return any((os.environ.get(name) or "").strip() for name in names)


class handler(BaseHTTPRequestHandler):

    def do_GET(self):
        openai_ready = has_env("OPENAI_API_KEY")
        gemini_ready = has_env("GEMINI_API_KEY", "GOOGLE_API_KEY")

        payload = {
            "ok": True,
            "service": "몰입 설계소",
            "python": platform.python_version(),
            "server_time_kst": datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S"),
            # 키 값이 아니라 "설정되어 있는지"만 알려 준다.
            "ai_configured": openai_ready or gemini_ready,
            "provider": "openai" if openai_ready else ("gemini" if gemini_ready else None),
            "webhook_configured": has_env("CONTACT_WEBHOOK_URL"),
            "endpoints": ["/api/routine (POST)", "/api/contact (POST)", "/api/health (GET)"],
        }

        body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        return
