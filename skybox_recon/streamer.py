"""Local-network audio/video streaming of a transport stream.

Serves http://<this-computer>:<port>/stream.ts to any player on the same
network (VLC, Kodi, mpv, smart TVs, phones). Works over Wi-Fi 6 or any other
LAN; no internet connection is used. The source is a recorded .ts file
(looped) or a file another tool is still writing (followed live, like tail -f),
such as dvbv5-zap -o capture.ts.
"""
from __future__ import annotations

import os
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

CHUNK = 188 * 348   # ~64 KiB, whole TS packets


def lan_addresses() -> list[str]:
    addrs = set()
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("192.0.2.1", 9))   # TEST-NET address: no packet is sent
        addrs.add(s.getsockname()[0])
        s.close()
    except OSError:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            addrs.add(info[4][0])
    except OSError:
        pass
    return sorted(a for a in addrs if not a.startswith("127.")) or ["127.0.0.1"]


class TSStreamServer:
    def __init__(self, source: str, port: int = 8090, follow: bool = False, loop: bool = True,
                 bind: str = "0.0.0.0", pace_mbps: float | None = None) -> None:
        self.source, self.port, self.follow, self.loop = source, port, follow, loop
        self.bind, self.pace_mbps = bind, pace_mbps
        self.clients = 0
        self.bytes_sent = 0
        self._stop = threading.Event()
        self._httpd: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    def urls(self) -> list[str]:
        return [f"http://{a}:{self.port}/stream.ts" for a in lan_addresses()]

    def start(self) -> None:
        if not os.path.isfile(self.source):
            raise FileNotFoundError(self.source)
        server = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):  # keep the GUI log clean
                pass

            def do_GET(self):  # noqa: N802
                if self.path.split("?")[0] not in ("/", "/stream.ts"):
                    self.send_error(404)
                    return
                if self.path.startswith("/stream.ts") is False:
                    body = ("<html><body><h1>Skybox Recon stream</h1>"
                            "<p>Open <a href='/stream.ts'>/stream.ts</a> in VLC, Kodi or mpv.</p></body></html>").encode()
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return
                self.send_response(200)
                self.send_header("Content-Type", "video/mp2t")
                self.send_header("Cache-Control", "no-cache")
                self.end_headers()
                server.clients += 1
                try:
                    server._pump(self.wfile)
                except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                    pass
                finally:
                    server.clients -= 1

        self._httpd = ThreadingHTTPServer((self.bind, self.port), Handler)
        self._httpd.daemon_threads = True
        self.port = self._httpd.server_address[1]
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()

    def _pump(self, out) -> None:
        with open(self.source, "rb") as f:
            started = time.monotonic()
            sent = 0
            while not self._stop.is_set():
                block = f.read(CHUNK)
                if not block:
                    if self.follow:
                        time.sleep(0.05)
                        continue
                    if self.loop:
                        f.seek(0)
                        continue
                    return
                out.write(block)
                sent += len(block)
                self.bytes_sent += len(block)
                if self.pace_mbps:
                    ahead = sent * 8 / (self.pace_mbps * 1e6) - (time.monotonic() - started)
                    if ahead > 0:
                        time.sleep(ahead)

    def stop(self) -> None:
        self._stop.set()
        if self._httpd:
            self._httpd.shutdown()
            self._httpd.server_close()
