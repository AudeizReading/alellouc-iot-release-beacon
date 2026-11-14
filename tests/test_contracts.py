"""Exercise application contracts without additional test dependencies."""

import os
import tomllib
import unittest
from email.message import Message
from http import HTTPStatus
from pathlib import Path
from unittest.mock import patch

from server.config.settings import Settings, load_settings
from server.request.header.validate import negotiate_content_type
from server.request.rejected import RequestRejected
from server.request.validate import validate_headers, validate_no_body, validate_target
from server.response.page import render_html


class SettingsTests(unittest.TestCase):
    def setUp(self) -> None:
        environment = patch.dict(os.environ, {
            "APP_NAME": "ci-app",
            "PART": "ci",
            "PORT": "8080",
            "IOT_LEADER_LOGIN": "ci",
            "MAINTENER_MAIL": "ci@example.invalid",
        }, clear=True)
        environment.start()
        self.addCleanup(environment.stop)

    def test_settings_read_the_application_version(self) -> None:
        project = tomllib.loads(Path("pyproject.toml").read_text())["project"]
        settings = load_settings()
        self.assertEqual(settings.app_name, "ci-app")
        self.assertEqual(settings.app_version, project["version"])
        self.assertEqual(settings.port, 8080)
        self.assertEqual(settings.team_mail, "ci@example.invalid")

    def test_required_identifiers_reject_empty_values(self) -> None:
        for name in ("APP_NAME", "PART", "IOT_LEADER_LOGIN", "MAINTENER_MAIL"):
            with self.subTest(variable=name), patch.dict(os.environ, {name: ""}):
                with self.assertRaises(ValueError):
                    load_settings()

    def test_invalid_ports_are_rejected(self) -> None:
        for value in ("0", "65536", "not-a-number"):
            with self.subTest(port=value), patch.dict(os.environ, {"PORT": value}):
                with self.assertRaises(ValueError):
                    load_settings()


class ContentNegotiationTests(unittest.TestCase):
    def test_supported_representations_and_preferences(self) -> None:
        cases = (
            (None, "text/html"),
            ("*/*", "text/html"),
            ("text/html", "text/html"),
            ("application/json", "application/json"),
            ("text/html;q=0.5, application/json;q=0.9", "application/json"),
            ("text/html;q=0, */*;q=1", "application/json"),
        )
        for accept, expected in cases:
            with self.subTest(accept=accept):
                self.assertEqual(negotiate_content_type(accept), expected)

    def test_invalid_or_unacceptable_preferences(self) -> None:
        cases = (
            ("image/png", HTTPStatus.NOT_ACCEPTABLE),
            ("text/html;q=2", HTTPStatus.BAD_REQUEST),
            ("text/html;q=0.5, text/html;q=1", HTTPStatus.BAD_REQUEST),
        )
        for accept, status in cases:
            with self.subTest(accept=accept):
                with self.assertRaises(RequestRejected) as caught:
                    negotiate_content_type(accept)
                self.assertEqual(caught.exception.status, status)


class RequestValidationTests(unittest.TestCase):
    def test_only_declared_targets_are_accepted(self) -> None:
        for target in ("/", "/css/stylesheet.css"):
            with self.subTest(target=target):
                validate_target(f"GET {target} HTTP/1.1")

    def test_invalid_targets_preserve_error_categories(self) -> None:
        cases = (
            ("/missing", HTTPStatus.NOT_FOUND),
            ("//", HTTPStatus.NOT_FOUND),
            ("/?query=1", HTTPStatus.BAD_REQUEST),
        )
        for target, status in cases:
            with self.subTest(target=target):
                with self.assertRaises(RequestRejected) as caught:
                    validate_target(f"GET {target} HTTP/1.1")
                self.assertEqual(caught.exception.status, status)

    def test_http11_requires_one_nonempty_host(self) -> None:
        for hosts in ((), ("",), ("localhost", "duplicate")):
            with self.subTest(hosts=hosts):
                headers = Message()
                for host in hosts:
                    headers["Host"] = host
                with self.assertRaises(RequestRejected) as caught:
                    validate_headers(headers, "HTTP/1.1")
                self.assertEqual(caught.exception.status, HTTPStatus.BAD_REQUEST)

    def test_request_bodies_are_rejected(self) -> None:
        cases = (("Content-Length", "1"), ("Transfer-Encoding", "chunked"))
        for name, value in cases:
            with self.subTest(header=name):
                headers = Message()
                headers[name] = value
                with self.assertRaises(RequestRejected) as caught:
                    validate_no_body(headers)
                self.assertEqual(caught.exception.status, HTTPStatus.BAD_REQUEST)


class RenderingTests(unittest.TestCase):
    def test_frontend_assets_render_and_escape_request_data(self) -> None:
        settings = Settings(
            app_name="ci-app", app_version="test-version", part="ci", port=8080,
            team="ci", team_mail="ci@example.invalid", podname="test-pod",
        )
        html = render_html(
            settings, method="GET", path="/<unsafe>", status=HTTPStatus.OK,
        ).decode("utf-8")
        self.assertIn("test-version", html)
        self.assertIn("/&lt;unsafe&gt;", html)
        self.assertNotIn("/<unsafe>", html)
        self.assertIn('href="/css/stylesheet.css"', html)
