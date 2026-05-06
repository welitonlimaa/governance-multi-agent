"""
Servidor local do dashboard de governança.

Serve o dashboard.html com o último relatório JSON disponível via HTTP.
O endpoint /api/report retorna o JSON do relatório mais recente.

Uso:
    python dashboard.py            # abre em http://localhost:8080
    python dashboard.py --port 9090
"""

from __future__ import annotations

import argparse
import json
import os
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from config import STORAGE_PATH

DASHBOARD_HTML = Path(__file__).parent / "dashboard.html"
REPORTS_DIR = STORAGE_PATH / "governance-reports"


def get_latest_report() -> dict | None:
    if not REPORTS_DIR.exists():
        return None
    files = sorted(REPORTS_DIR.glob("*.json"), key=os.path.getmtime, reverse=True)
    if not files:
        return None
    try:
        return json.loads(files[0].read_text(encoding="utf-8"))
    except Exception:
        return None


class DashboardHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def do_GET(self):
        if self.path == "/api/report":
            self._serve_report()
        elif self.path in ("/", "/dashboard", "/index.html"):
            self._serve_html()
        else:
            self.send_error(404)

    def _serve_report(self):
        report = get_latest_report()
        if report is None:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b'{"error": "No report found"}')
            return
        body = json.dumps(report, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _serve_html(self):
        html = DASHBOARD_HTML.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(html)))
        self.end_headers()
        self.wfile.write(html)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()

    url = f"http://localhost:{args.port}"
    print(f"\n🌐  Dashboard disponível em: {url}")
    print(f"📊  Relatório via API:        {url}/api/report")
    print("     Ctrl+C para encerrar\n")

    server = HTTPServer(("localhost", args.port), DashboardHandler)
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n👋  Dashboard encerrado.")


if __name__ == "__main__":
    main()
