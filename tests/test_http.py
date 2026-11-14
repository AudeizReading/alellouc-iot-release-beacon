"""Verify the live application started with python -m server.app."""

import json
import os
import socket
import time
import tomllib
import unittest
from contextlib import closing
from http.client import HTTPConnection
from pathlib import Path


def wait_for_server(port: int) -> None:
    """Allow up to ten seconds for the application to start listening."""
    deadline = time.monotonic() + 10
    while True:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                return
        except ConnectionRefusedError:
            if time.monotonic() >= deadline:
                raise
            time.sleep(0.1)


class RunningServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.port = int(os.environ["PORT"])
        wait_for_server(cls.port)

    def request(
        self, method: str, path: str, headers: dict[str, str] | None = None,
    ) -> tuple[int, dict[str, str], bytes]:
        with closing(HTTPConnection("127.0.0.1", self.port, timeout=3)) as client:
            client.request(method, path, headers=headers or {})
            response = client.getresponse()
            return response.status, dict(response.getheaders()), response.read()

    def test_runtime_uses_a_nonroot_user(self) -> None:
        self.assertNotEqual(os.geteuid(), 0)

    def test_html_page_and_security_headers(self) -> None:
        status, headers, body = self.request("GET", "/", {"Accept": "text/html"})
        self.assertEqual(status, 200)
        self.assertEqual(headers["Content-Type"], "text/html; charset=utf-8")
        self.assertIn(os.environ["APP_NAME"].encode(), body)
        self.assertIn(b'<!doctype html>', body.lower())
        self.assertEqual(headers["X-Content-Type-Options"], "nosniff")
        self.assertIn("default-src 'none'", headers["Content-Security-Policy"])
        self.assertEqual(int(headers["Content-Length"]), len(body))

    def test_json_reports_the_running_application(self) -> None:
        status, headers, body = self.request("GET", "/", {"Accept": "application/json"})
        project = tomllib.loads(Path("pyproject.toml").read_text())["project"]
        self.assertEqual(status, 200)
        self.assertEqual(headers["Content-Type"], "application/json; charset=utf-8")
        self.assertEqual(json.loads(body), {
            "app": os.environ["APP_NAME"],
            "version": project["version"],
            "pod": socket.gethostname(),
        })

    def test_stylesheet_is_served_from_the_application(self) -> None:
        status, headers, body = self.request("GET", "/css/stylesheet.css")
        self.assertEqual(status, 200)
        self.assertEqual(headers["Content-Type"], "text/css; charset=utf-8")
        self.assertTrue(body)
        self.assertEqual(body, Path("appli/css/stylesheet.css").read_bytes())

    def test_head_returns_headers_without_a_body(self) -> None:
        status, headers, body = self.request("HEAD", "/", {"Accept": "text/html"})
        self.assertEqual(status, 200)
        self.assertEqual(headers["Content-Type"], "text/html; charset=utf-8")
        self.assertGreater(int(headers["Content-Length"]), 0)
        self.assertEqual(body, b"")

    def test_rejections_preserve_http_statuses(self) -> None:
        cases = (
            ("GET", "/missing", {}, 404),
            ("GET", "/?query=1", {}, 400),
            ("POST", "/", {}, 405),
            ("GET", "/", {"Accept": "image/png"}, 406),
            ("GET", "/", {"Content-Length": "1"}, 400),
            ("GET", "/", {"Accept": "text/html;q=2"}, 400),
        )
        for method, path, request_headers, expected_status in cases:
            with self.subTest(method=method, path=path, headers=request_headers):
                status, headers, body = self.request(method, path, request_headers)
                self.assertEqual(status, expected_status)
                self.assertEqual(headers["Content-Type"], "text/html; charset=utf-8")
                self.assertTrue(body)
