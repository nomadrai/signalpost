#!/usr/bin/env python3
"""Serve a generated Signalpost viewer with a bounded profile research endpoint."""

from __future__ import annotations

import argparse
import json
import sys
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from norway_company_agent.research import answer_profile  # noqa: E402
from norway_company_agent.viewer import build_viewer, read_envelopes  # noqa: E402


def _plain(value):
    if isinstance(value, dict):
        return {key: _plain(child) for key, child in value.items()}
    if isinstance(value, list):
        return [_plain(child) for child in value]
    return value.replace("\u2014", " - ") if isinstance(value, str) else value


class ViewerHandler(SimpleHTTPRequestHandler):
    profiles: dict[str, dict] = {}

    def _send_json(self, status: int, value: dict) -> None:
        payload = json.dumps(value, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/api/research":
            self._send_json(404, {"error": "Unknown API route"})
            return
        try:
            length = int(self.headers.get("Content-Length") or "0")
            if length <= 0 or length > 100_000:
                raise ValueError("Request body must be between 1 byte and 100 KB")
            payload = json.loads(self.rfile.read(length))
            org = "".join(character for character in str(payload.get("organisation_number") or "") if character.isdigit())
            question = " ".join(str(payload.get("question") or "").split())
            if len(org) != 9 or not question or len(question) > 500:
                raise ValueError("A valid organisation number and a question up to 500 characters are required")
            profile = self.profiles.get(org)
            if profile is None:
                self._send_json(404, {"error": "Organisation number is not in this viewer snapshot"})
                return
            self._send_json(200, _plain(answer_profile(profile, question)))
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            self._send_json(400, {"error": str(exc)})
        except Exception:
            self._send_json(500, {"error": "Research request failed safely"})

    def log_message(self, format: str, *args) -> None:
        print(f"[viewer] {format % args}", file=sys.stderr)


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve the Signalpost static viewer with bounded profile research")
    parser.add_argument("--source", required=True, help="Envelope JSONL, JSON, or run directory")
    parser.add_argument("--output", required=True, help="Generated viewer directory")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    rows = read_envelopes(args.source)
    build_viewer(args.source, args.output)
    ViewerHandler.profiles = {
        str(row.get("organisation_number")): (row.get("profile") or row)
        for row in rows
    }
    handler = partial(ViewerHandler, directory=str(Path(args.output).resolve()))
    server = ThreadingHTTPServer((args.host, args.port), handler)
    print(f"Signalpost viewer: http://{args.host}:{args.port}/")
    print("Bounded research API: POST /api/research")
    print("Research routing: local deterministic natural-language topics; no model, paid API, or live crawl")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
