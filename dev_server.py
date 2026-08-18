#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
dev_server.py
=============
로컬 개발용 서버. `vercel dev` 없이도 프론트 + api/ 함수를 함께 실행해 볼 수 있다.

    python dev_server.py            → http://localhost:3000
    python dev_server.py --port 8080

동작 방식
    · /api/routine, /api/contact, /api/health  →  api/ 폴더의 파이썬 함수로 넘긴다.
    · 그 외 경로                                →  프로젝트 폴더의 정적 파일(html/css/js)을 서빙한다.

    Vercel 은 api/<이름>.py 파일을 자동으로 /api/<이름> 주소에 연결해 준다.
    이 스크립트는 그 규칙을 로컬에서 흉내 낸 것이고, 배포에는 사용되지 않는다.

주의
    이 파일은 학습/개발 편의를 위한 것이며 운영 서버가 아니다.
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import sys
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
API_DIR = BASE_DIR / "api"


# ---------------------------------------------------------------------------
# .env 로딩 — 배포 환경의 "Environment Variables" 를 로컬에서 대신하는 파일
# ---------------------------------------------------------------------------

def load_env() -> None:
    env_path = BASE_DIR / ".env"
    if not env_path.exists():
        print("[안내] .env 파일이 없습니다. AI 기능은 NO_API_KEY 오류를 반환합니다.")
        print("       copy .env.example .env  후 키를 채워 주세요. (Windows)")
        return

    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip().strip("'\"")
        if value:
            os.environ.setdefault(key.strip(), value)


# ---------------------------------------------------------------------------
# api/*.py 를 모듈로 읽어 들인다.
# ---------------------------------------------------------------------------

def load_api_modules() -> dict:
    modules = {}
    for path in sorted(API_DIR.glob("*.py")):
        if path.name.startswith("_"):
            continue
        spec = importlib.util.spec_from_file_location("api_" + path.stem, path)
        module = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(module)
        except Exception as error:  # 의존 패키지 누락 등
            print(f"[오류] api/{path.name} 을 불러오지 못했습니다: {error}")
            print("       pip install -r api/requirements.txt 를 실행했는지 확인하세요.")
            continue
        modules["/api/" + path.stem] = module
        print(f"  · /api/{path.stem}  ←  api/{path.name}")
    return modules


_COMBINED_CACHE: dict = {}


def combined_class(api_handler_cls, dev_cls):
    """
    api/ 의 handler 클래스와 개발 서버 핸들러를 합친 임시 클래스를 만든다.

    api/ 의 handler 는 do_POST 뿐 아니라 _send / _client_ip 같은 보조 메서드도 쓰기 때문에,
    메서드 하나만 떼어 호출하면 나머지를 찾지 못한다. 그래서 요청 처리 순간에만
    인스턴스의 클래스를 통째로 바꿔 끼운다. (상태는 모두 인스턴스에 있어 안전하다.)
    """
    key = (api_handler_cls, dev_cls)
    if key not in _COMBINED_CACHE:
        _COMBINED_CACHE[key] = type(
            "Dev_" + api_handler_cls.__module__, (api_handler_cls, dev_cls), {}
        )
    return _COMBINED_CACHE[key]


class DevHandler(SimpleHTTPRequestHandler):
    """정적 파일 서빙 + /api/* 를 서버리스 함수 클래스로 위임하는 핸들러."""

    api_modules: dict = {}
    in_api = False

    # --- 라우팅 ----------------------------------------------------------
    def _api_module(self):
        path = self.path.split("?", 1)[0].rstrip("/")
        return self.api_modules.get(path)

    def _dispatch(self, method_name: str) -> bool:
        """경로가 /api/* 면 해당 함수로 처리하고 True 를 반환한다."""
        module = self._api_module()
        if module is None:
            return False

        api_cls = getattr(module, "handler", None)
        if api_cls is None or method_name not in vars(api_cls):
            # 그 함수가 지원하지 않는 메서드 (예: /api/health 의 POST)
            self.send_error(405, "Method Not Allowed")
            return True

        original = self.__class__
        self.__class__ = combined_class(api_cls, original)
        self.in_api = True
        try:
            getattr(self, method_name)()
        finally:
            self.__class__ = original
            self.in_api = False
        return True

    def do_POST(self):
        if not self._dispatch("do_POST"):
            self.send_error(404, "Not Found")

    def do_OPTIONS(self):
        if not self._dispatch("do_OPTIONS"):
            self.send_error(404, "Not Found")

    def do_GET(self):
        if not self._dispatch("do_GET"):
            super().do_GET()

    # --- 정적 파일 --------------------------------------------------------
    def guess_type(self, path):
        """한글이 깨지지 않도록 텍스트 파일에 charset 을 붙인다."""
        mime = super().guess_type(path)
        if mime.startswith(("text/", "application/javascript")) and "charset" not in mime:
            return mime + "; charset=utf-8"
        return mime

    def end_headers(self):
        # 개발 중에는 캐시 때문에 수정이 반영되지 않는 일을 막는다.
        # (api 응답은 자기 헤더를 직접 설정하므로 건드리지 않는다.)
        if not self.in_api:
            self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, fmt, *args):
        sys.stderr.write("  %s %s\n" % (self.command, self.path))


def main() -> int:
    parser = argparse.ArgumentParser(description="몰입 설계소 로컬 개발 서버")
    parser.add_argument("--port", type=int, default=3000, help="포트 번호 (기본 3000)")
    args = parser.parse_args()

    load_env()

    print("\n[API 라우트]")
    DevHandler.api_modules = load_api_modules()
    if not DevHandler.api_modules:
        print("  (없음) — api/ 폴더를 확인하세요.")

    handler_factory = partial(DevHandler, directory=str(BASE_DIR))
    server = ThreadingHTTPServer(("127.0.0.1", args.port), handler_factory)

    print(f"\n서버 실행 중 →  http://localhost:{args.port}")
    print("종료하려면 Ctrl+C\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n서버를 종료합니다.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
