"""프론트엔드 정적 서버. `python -m http.server`는 Windows 레지스트리 설정에 따라 .js를 text/plain으로 보내
ES 모듈(Vue 화면)이 막히므로, 파일 형식을 직접 지정해 서빙한다.

사용: python scripts/serve_frontend.py [포트=5500]
"""
import functools
import http.server
import sys
from pathlib import Path

FRONTEND = Path(__file__).resolve().parents[1] / "frontend"


class Handler(http.server.SimpleHTTPRequestHandler):
    extensions_map = {**http.server.SimpleHTTPRequestHandler.extensions_map,
                      ".js": "text/javascript", ".mjs": "text/javascript", ".css": "text/css",
                      ".html": "text/html", ".json": "application/json", ".svg": "image/svg+xml"}

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")  # 수정한 화면이 바로 보이게(개발용)
        super().end_headers()


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 5500
    handler = functools.partial(Handler, directory=str(FRONTEND))
    with http.server.ThreadingHTTPServer(("127.0.0.1", port), handler) as httpd:
        print(f"프론트엔드: http://127.0.0.1:{port}  (폴더 {FRONTEND})")
        httpd.serve_forever()
