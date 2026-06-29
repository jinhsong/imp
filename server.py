#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
수입 모델 인증 확인 - 로컬 프록시 서버 (의존성 없음, Python 3 표준 라이브러리만 사용)

역할
  1) index.html 등 정적 파일을 제공한다.
  2) /fetch?url=<대상URL> 로 들어오면 서버가 대신 대상 URL을 받아와(=CORS 우회) 본문을 그대로 돌려준다.
     - 보안을 위해 허용된 호스트(rra.go.kr, data.go.kr)로만 중계한다.
     - 안전인증 serviceKey 등 민감 정보가 외부 제3자 프록시를 거치지 않고 내 PC에서만 처리된다.

사용법
  python3 server.py            # http://localhost:8000 에서 실행
  python3 server.py 9000       # 포트 지정
  그 후 브라우저에서 http://localhost:8000 접속 → 설정에서 '연결 방식'을 "로컬 프록시"로 둔다.
"""
import sys
import os
import ssl
import urllib.request
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

# 중계를 허용할 호스트 (오·남용 방지). 필요 시 추가하세요.
ALLOWED_HOSTS = (
    "rra.go.kr", "www.rra.go.kr", "ccac.rra.go.kr",
    "data.go.kr", "www.data.go.kr",
    "apis.data.go.kr", "api.data.go.kr", "apis.data.or.kr",
)

ROOT = os.path.dirname(os.path.abspath(__file__))

# 일부 환경의 인증서 검증 이슈를 피하기 위한 컨텍스트 (정부 사이트는 보통 유효).
_SSL_CTX = ssl.create_default_context()


def host_allowed(netloc: str) -> bool:
    host = netloc.split(":")[0].lower()
    return any(host == h or host.endswith("." + h) for h in ALLOWED_HOSTS)


class Handler(BaseHTTPRequestHandler):
    server_version = "CertCheckerProxy/1.0"

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "*")

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/fetch":
            return self.handle_fetch(parsed)
        return self.handle_static(parsed)

    # ---- /fetch 중계 ----
    def handle_fetch(self, parsed):
        qs = parse_qs(parsed.query)
        target = (qs.get("url") or [""])[0]
        if not target:
            return self.send_json(400, b'{"error":"missing url param"}')

        tp = urlparse(target)
        if tp.scheme not in ("http", "https") or not host_allowed(tp.netloc):
            return self.send_json(403, b'{"error":"host not allowed"}')

        req = urllib.request.Request(target, headers={
            # 정부 사이트는 기본 파이썬 UA를 막는 경우가 있어 브라우저 UA로 위장.
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/124.0 Safari/537.36",
            "Accept": "application/json, text/html, application/xml, */*",
            "Accept-Language": "ko-KR,ko;q=0.9",
        })
        try:
            with urllib.request.urlopen(req, timeout=30, context=_SSL_CTX) as resp:
                body = resp.read()
                ctype = resp.headers.get("Content-Type", "text/html; charset=utf-8")
                self.send_response(200)
                self.send_header("Content-Type", ctype)
                self._cors()
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
        except urllib.error.HTTPError as e:
            body = e.read()
            self.send_response(e.code)
            self.send_header("Content-Type", e.headers.get("Content-Type", "text/plain"))
            self._cors()
            self.end_headers()
            self.wfile.write(body)
        except Exception as e:  # noqa
            msg = ('{"error":"upstream fetch failed","detail":%r}' % str(e)).encode("utf-8")
            self.send_json(502, msg)

    # ---- 정적 파일 ----
    def handle_static(self, parsed):
        path = parsed.path
        if path in ("/", ""):
            path = "/index.html"
        # 경로 탈출 방지
        safe = os.path.normpath(os.path.join(ROOT, path.lstrip("/")))
        if not safe.startswith(ROOT) or not os.path.isfile(safe):
            return self.send_json(404, b'{"error":"not found"}')
        ctype = {
            ".html": "text/html; charset=utf-8",
            ".js": "application/javascript; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".json": "application/json; charset=utf-8",
        }.get(os.path.splitext(safe)[1], "application/octet-stream")
        with open(safe, "rb") as f:
            body = f.read()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self._cors()
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_json(self, code, body: bytes):
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self._cors()
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        sys.stderr.write("[proxy] " + (fmt % args) + "\n")


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = "http://localhost:%d" % port
    print("=" * 56)
    print(" 수입 모델 인증 확인 - 로컬 프록시 실행 중")
    print("  브라우저에서 열기 :  %s" % url)
    print("  중지            :  Ctrl + C")
    print("=" * 56)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n종료합니다.")
        httpd.shutdown()


if __name__ == "__main__":
    main()
