"""Rung 2 without Docker: serve function/handler.py on a local URL.

    uv run function/local_server.py            # http://127.0.0.1:9000, real model (needs the key)
    PROVIDER=fake uv run function/local_server.py

Then, in another terminal:  uv run record.py --provider http --url http://127.0.0.1:9000 --runs 1

It is the same handler the deploy script ships, called with the same event shape a
function URL delivers. What it does not reproduce: the cold start, the time limit, and
the network. Those are what the deployed function is for.
"""
from __future__ import annotations

import json
import os
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from function.handler import handler  # noqa: E402


class _Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        n = int(self.headers.get("content-length", 0))
        body = self.rfile.read(n).decode()
        event = {"requestContext": {"http": {"method": "POST"}}, "headers": dict(self.headers), "body": body, "isBase64Encoded": False}
        out = handler(event, None)
        payload = out["body"].encode()
        self.send_response(out["statusCode"])
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, fmt, *args):  # one line per request, like CloudWatch
        print(f"  {self.address_string()} {fmt % args}")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "9000"))
    print(f"serving function/handler.py at http://127.0.0.1:{port}  (provider: {os.environ.get('PROVIDER', 'gemini')})")
    HTTPServer(("127.0.0.1", port), _Handler).serve_forever()
