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
import re
import ssl
import http.cookiejar
import urllib.request
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

# 중계를 허용할 호스트 (오·남용 방지). 필요 시 추가하세요.
ALLOWED_HOSTS = (
    "rra.go.kr", "www.rra.go.kr", "ccac.rra.go.kr",
    "emsit.go.kr", "www.emsit.go.kr",   # 전파인증(적합성평가) 무료 Open API
    "safetykorea.kr", "www.safetykorea.kr", "office.safetykorea.kr",  # 안전인증(KC)
    "data.go.kr", "www.data.go.kr",
    "apis.data.go.kr", "api.data.go.kr", "apis.data.or.kr",
)

ROOT = os.path.dirname(os.path.abspath(__file__))

# 세션 쿠키 유지(JSESSIONID 등) + 리다이렉트 처리를 위한 공용 opener.
# RRA 검색은 먼저 검색페이지를 받아 세션 쿠키를 받아야 결과 POST 가 동작한다.
_COOKIES = http.cookiejar.CookieJar()
_CTX_VERIFY = ssl.create_default_context()
_CTX_NOVERIFY = ssl.create_default_context()
_CTX_NOVERIFY.check_hostname = False
_CTX_NOVERIFY.verify_mode = ssl.CERT_NONE
_OPENER_V = urllib.request.build_opener(
    urllib.request.HTTPSHandler(context=_CTX_VERIFY),
    urllib.request.HTTPCookieProcessor(_COOKIES))
_OPENER_N = urllib.request.build_opener(
    urllib.request.HTTPSHandler(context=_CTX_NOVERIFY),
    urllib.request.HTTPCookieProcessor(_COOKIES))


def _open(req, timeout=30):
    """검증 SSL 우선, 인증서 검증 실패 시에만 비검증으로 재시도(공공 사이트 인증서 이슈 대비)."""
    try:
        return _OPENER_V.open(req, timeout=timeout)
    except (ssl.SSLError, urllib.error.URLError) as e:
        reason = getattr(e, "reason", None)
        if isinstance(e, ssl.SSLError) or isinstance(reason, ssl.SSLError):
            sys.stderr.write("[proxy] SSL 검증 실패 → 비검증으로 재시도\n")
            return _OPENER_N.open(req, timeout=timeout)
        raise


def _to_utf8(body: bytes, ctype: str):
    """euc-kr/cp949 응답을 UTF-8 로 변환해 브라우저 한글 깨짐을 막는다.
    (RRA 결과 페이지가 euc-kr 이라 fetch().text() 가 깨지는 문제 대응)
    텍스트/HTML 류에만 적용하고, 변환 실패 시 원본을 그대로 둔다."""
    low = ctype.lower()
    if not any(t in low for t in ("text", "html", "xml", "json")):
        return body, ctype
    enc = None
    m = re.search(r"charset=([\w\-]+)", low)
    if m:
        enc = m.group(1).lower()
    if enc is None:
        # 헤더에 charset 없으면 문서 앞부분의 meta charset 확인
        head = body[:2048].decode("ascii", "ignore").lower()
        mm = re.search(r'charset=["\']?([\w\-]+)', head)
        if mm:
            enc = mm.group(1).lower()
    if enc in ("euc-kr", "euckr", "ks_c_5601-1987", "ksc5601", "cp949", "ms949"):
        try:
            body = body.decode("cp949").encode("utf-8")  # cp949 ⊃ euc-kr
            ctype = re.sub(r"charset=[\w\-]+", "charset=utf-8", low) \
                if "charset=" in low else (ctype + "; charset=utf-8")
        except Exception:  # noqa
            pass
    return body, ctype


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
        if parsed.path == "/favicon.ico":
            self.send_response(204)
            self._cors()
            self.end_headers()
            return
        return self.handle_static(parsed)

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == "/fetch":
            length = int(self.headers.get("Content-Length", 0) or 0)
            body = self.rfile.read(length) if length else b""
            return self.handle_fetch(parsed, post_body=body)
        return self.send_json(404, b'{"error":"not found"}')

    # ---- /fetch 중계 (GET 또는 POST) ----
    def handle_fetch(self, parsed, post_body=None):
        qs = parse_qs(parsed.query)
        target = (qs.get("url") or [""])[0]
        if not target:
            return self.send_json(400, b'{"error":"missing url param"}')

        tp = urlparse(target)
        if tp.scheme not in ("http", "https") or not host_allowed(tp.netloc):
            return self.send_json(403, b'{"error":"host not allowed"}')

        fwd = {
            # 정부 사이트는 기본 파이썬 UA를 막는 경우가 있어 브라우저 UA로 위장.
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/124.0 Safari/537.36",
            "Accept": "application/json, text/html, application/xml, */*",
            "Accept-Language": "ko-KR,ko;q=0.9",
        }
        # 안전인증(SafetyKorea)은 AuthKey 헤더 인증 → 클라이언트가 보낸 값을 그대로 중계.
        auth = self.headers.get("AuthKey")
        if auth:
            fwd["AuthKey"] = auth

        host = tp.netloc.split(":")[0].lower()
        is_rra = host.endswith("rra.go.kr")

        # 전파인증 실시간조회 등 POST 요청: 본문/Content-Type/Referer/Origin 설정.
        if post_body is not None:
            fwd["Content-Type"] = self.headers.get(
                "Content-Type", "application/x-www-form-urlencoded; charset=UTF-8")
            origin = tp.scheme + "://" + tp.netloc
            fwd["Origin"] = origin
            # RRA 결과 POST 는 검색페이지를 Referer 로 요구.
            fwd["Referer"] = ("https://www.rra.go.kr/ko/license/A_c_search.do"
                              if is_rra else origin + "/")
            # RRA: 먼저 검색페이지를 GET 해 세션 쿠키(JSESSIONID)를 받아둔다.
            if is_rra:
                try:
                    _open(urllib.request.Request(fwd["Referer"], headers={
                        "User-Agent": fwd["User-Agent"], "Accept": fwd["Accept"],
                        "Accept-Language": fwd["Accept-Language"]}), timeout=20).read()
                except Exception as e:  # noqa  (쿠키 시드는 실패해도 본 요청 시도)
                    sys.stderr.write("[proxy] RRA 세션 시드 실패: %r\n" % e)

        req = urllib.request.Request(target, data=post_body, headers=fwd)
        try:
            with _open(req, timeout=30) as resp:
                body = resp.read()
                ctype = resp.headers.get("Content-Type", "text/html; charset=utf-8")
                body, ctype = _to_utf8(body, ctype)
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
            import json as _json
            detail = "%s: %s" % (type(e).__name__, e)
            reason = getattr(e, "reason", None)
            if reason is not None:
                detail += " (reason: %r)" % (reason,)
            sys.stderr.write("[proxy] upstream 실패 [%s] %s\n" % (target, detail))
            msg = _json.dumps({"error": "upstream fetch failed", "detail": detail},
                              ensure_ascii=False).encode("utf-8")
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
