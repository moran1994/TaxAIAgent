#!/usr/bin/env python3
"""S0 fake-door server: static landing + lead capture to leads.jsonl"""
from __future__ import annotations

import json
import argparse
from datetime import datetime, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
LEADS = ROOT.parent / "leads.jsonl"
FUNNEL = ROOT.parent / "funnel.jsonl"


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def _json(self, code: int, payload: dict):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_POST(self):
        path = urlparse(self.path).path
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            data = json.loads(raw.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            return self._json(400, {"ok": False, "error": "invalid_json"})

        data["_received_at"] = datetime.now(timezone.utc).isoformat()
        data["_path"] = path

        if path in ("/api/lead", "/api/event"):
            out = LEADS if path == "/api/lead" else FUNNEL
            out.parent.mkdir(parents=True, exist_ok=True)
            with out.open("a", encoding="utf-8") as f:
                f.write(json.dumps(data, ensure_ascii=False) + "\n")
            return self._json(200, {"ok": True})

        return self._json(404, {"ok": False, "error": "not_found"})

    def log_message(self, fmt: str, *args):
        print("[%s] %s" % (self.log_date_time_string(), fmt % args))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5174)
    args = parser.parse_args()
    httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"S0 landing on http://{args.host}:{args.port}/  leads -> {LEADS}")
    httpd.serve_forever()


if __name__ == "__main__":
    main()
