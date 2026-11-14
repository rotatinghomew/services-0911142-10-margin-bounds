from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse
import argparse
import json
import mimetypes
import os

from .service import Workbench


class Handler(BaseHTTPRequestHandler):
    def __init__(self, *args, workbench, **kwargs):
        self.workbench = workbench
        super().__init__(*args, **kwargs)

    def log_message(self, message, *args):
        return

    def send(self, status, payload, content_type="application/json; charset=utf-8"):
        body = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode() if not isinstance(payload, bytes) else payload
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        try:
            if parsed.path == "/health":
                return self.send(200, {"status": "ok"})
            if parsed.path == "/api/context":
                return self.send(200, self.workbench.context())
            if parsed.path == "/api/data":
                revision = parse_qs(parsed.query).get("revision", [self.workbench.default_revision])[0]
                return self.send(200, self.workbench.store.dataset(revision))
            if parsed.path == "/api/notebooks":
                return self.send(200, self.workbench.store.notebooks())
            if parsed.path.startswith("/api/notebooks/"):
                identifier = parsed.path.rsplit("/", 1)[-1]
                return self.send(200, self.workbench.store.notebook(identifier))
            static = {"/": "index.html", "/app.js": "app.js", "/style.css": "style.css"}
            if parsed.path not in static:
                return self.send(404, {"error": "路径不存在"})
            path = self.workbench.root / "web" / static[parsed.path]
            return self.send(200, path.read_bytes(), (mimetypes.guess_type(path)[0] or "application/octet-stream") + "; charset=utf-8")
        except LookupError as error:
            self.send(404, {"error": str(error)})

    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > 8000000:
                return self.send(413, {"error": "请求正文应为1字节至8MB"})
            body = json.loads(self.rfile.read(length), parse_constant=lambda value: (_ for _ in ()).throw(ValueError("非有限JSON数值")))
            if not isinstance(body, dict):
                raise ValueError("请求正文应为对象")
            if self.path == "/api/explore":
                return self.send(200, self.workbench.inspect(body))
            if self.path == "/api/datasets":
                return self.send(201, self.workbench.upload(body))
            if self.path == "/api/notebooks":
                return self.send(201, self.workbench.save(body))
            self.send(404, {"error": "路径不存在"})
        except LookupError as error:
            self.send(404, {"error": str(error)})
        except (ValueError, TypeError, KeyError, UnicodeError) as error:
            self.send(400, {"error": str(error)})


def make_server(root, state, host="127.0.0.1", port=8080):
    workbench = Workbench(root, state)
    return ThreadingHTTPServer((host, port), partial(Handler, workbench=workbench))


def main():
    parser = argparse.ArgumentParser(description="本地分析工作台")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--state", default=os.environ.get("ANALYSIS_STATE", ".state"))
    args = parser.parse_args()
    root = Path(__file__).resolve().parent.parent
    server = make_server(root, args.state, args.host, args.port)
    print(f"分析工作台已启动：http://{args.host}:{server.server_port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
