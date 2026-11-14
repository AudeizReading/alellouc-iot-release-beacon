"""Verify release publication through a mocked HTTP transport, without credentials."""

import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError, URLError
from urllib.response import addinfourl

from github_releases import GitHubReleases, release_response

API = "https://api.github.com"
REPOSITORY = "example/application"
GIT_TAG = "application/v2/build-123-1"
UPLOAD = "https://uploads.github.com/repos/example/application/releases/42/assets"
TOKEN = "fixture-token-not-a-credential"


def release_payload(*, draft: bool = True) -> dict:
    return {
        "id": 42, "tag_name": GIT_TAG, "draft": draft,
        "upload_url": UPLOAD + "{?name,label}",
        "html_url": "https://github.com/example/application/releases/tag/" + GIT_TAG,
    }


def response(payload: object, status: int = 201) -> addinfourl:
    return addinfourl(io.BytesIO(json.dumps(payload).encode()), {}, API, status)


class ReleaseCommandsTests(unittest.TestCase):
    def setUp(self) -> None:
        transport = patch("github_releases.urlopen", autospec=True)
        self.transport = transport.start()
        self.addCleanup(transport.stop)
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.digest = Path(directory.name) / "application-v2.release.yaml"
        self.digest.write_text('docker_image: "example/application:v2@sha256:abc"\n')
        self.client = GitHubReleases(API, REPOSITORY, TOKEN)

    def test_draft_targets_exact_commit_and_preserves_docker_version_as_title(self) -> None:
        reply = response(release_payload())
        self.transport.return_value = reply
        release = self.client.create_draft(GIT_TAG, "v2", "a" * 40)
        request = self.transport.call_args.args[0]
        self.assertEqual(request.full_url, f"{API}/repos/{REPOSITORY}/releases")
        self.assertEqual(request.method, "POST")
        self.assertEqual(json.loads(request.data), {
            "tag_name": GIT_TAG, "target_commitish": "a" * 40,
            "name": "v2", "draft": True, "generate_release_notes": True,
        })
        self.assertEqual(request.get_header("Authorization"), f"Bearer {TOKEN}")
        self.assertEqual(request.get_header("X-github-api-version"), "2022-11-28")
        self.assertEqual(self.transport.call_args.kwargs, {"timeout": 60})
        self.assertEqual(release.id, 42)
        self.assertTrue(release.draft)
        self.assertTrue(reply.closed)

    def test_upload_sends_file_bytes_to_flat_release_asset_name(self) -> None:
        self.transport.return_value = response({
            "name": self.digest.name, "size": self.digest.stat().st_size,
            "state": "uploaded",
        })
        self.client.upload_digest(UPLOAD + "{?name,label}", self.digest)
        request = self.transport.call_args.args[0]
        self.assertEqual(request.full_url, f"{UPLOAD}?name={self.digest.name}")
        self.assertEqual(request.method, "POST")
        self.assertEqual(request.data, self.digest.read_bytes())
        self.assertEqual(request.get_header("Content-type"), "application/octet-stream")

    def test_publish_promotes_exact_release_as_stable_and_latest(self) -> None:
        self.transport.return_value = response(release_payload(draft=False), 200)
        release = self.client.publish(42, GIT_TAG)
        request = self.transport.call_args.args[0]
        self.assertEqual(request.full_url, f"{API}/repos/{REPOSITORY}/releases/42")
        self.assertEqual(request.method, "PATCH")
        self.assertEqual(json.loads(request.data), {
            "draft": False, "prerelease": False, "make_latest": "true",
        })
        self.assertFalse(release.draft)

    def test_lifecycle_uploads_before_publishing(self) -> None:
        self.transport.side_effect = [
            response(release_payload()),
            response({"name": self.digest.name, "size": self.digest.stat().st_size,
                      "state": "uploaded"}),
            response(release_payload(draft=False), 200),
        ]
        draft = self.client.create_draft(GIT_TAG, "v2", "a" * 40)
        self.client.upload_digest(draft.upload_url, self.digest)
        self.client.publish(draft.id, draft.tag)
        methods = [call.args[0].method for call in self.transport.call_args_list]
        self.assertEqual(methods, ["POST", "POST", "PATCH"])

    def test_draft_rejects_published_or_wrong_tag_response(self) -> None:
        for change in ({"draft": False}, {"tag_name": "another-tag"}):
            with self.subTest(change=change):
                self.transport.return_value = response(release_payload() | change)
                with self.assertRaises(ValueError):
                    self.client.create_draft(GIT_TAG, "v2", "a" * 40)

    def test_publish_rejects_wrong_release_or_remaining_draft(self) -> None:
        for change in ({"id": 43}, {"tag_name": "another-tag"}, {"draft": True}):
            with self.subTest(change=change):
                payload = release_payload(draft=False) | change
                self.transport.return_value = response(payload, 200)
                with self.assertRaises(ValueError):
                    self.client.publish(42, GIT_TAG)

    def test_upload_rejects_incomplete_or_unexpected_asset(self) -> None:
        asset = {"name": self.digest.name, "size": self.digest.stat().st_size,
                 "state": "uploaded"}
        for payload in ([], asset | {"name": "other.yaml"},
                        asset | {"size": 0}, asset | {"state": "starter"}):
            with self.subTest(payload=payload):
                self.transport.return_value = response(payload)
                with self.assertRaises(ValueError):
                    self.client.upload_digest(UPLOAD, self.digest)

    def test_http_and_network_failures_propagate_without_retry(self) -> None:
        http_failures = (HTTPError(API, 403, "Forbidden", {}, None),
                         HTTPError(API, 422, "Unprocessable Entity", {}, None))
        for failure in http_failures:
            self.addCleanup(failure.close)
        failures = (*http_failures, URLError("network unavailable"))
        for failure in failures:
            with self.subTest(failure=failure):
                self.transport.reset_mock()
                self.transport.side_effect = failure
                with self.assertRaises(type(failure)) as caught:
                    self.client.create_draft(GIT_TAG, "v2", "a" * 40)
                self.assertIs(caught.exception, failure)
                self.transport.assert_called_once()

    def test_unexpected_success_status_is_not_accepted(self) -> None:
        reply = response(release_payload(), 202)
        self.transport.return_value = reply
        with self.assertRaises(RuntimeError):
            self.client.create_draft(GIT_TAG, "v2", "a" * 40)
        self.assertTrue(reply.closed)

    def test_missing_digest_fails_before_http_request(self) -> None:
        with self.assertRaises(FileNotFoundError):
            self.client.upload_digest(UPLOAD, self.digest.with_name("missing.yaml"))
        self.transport.assert_not_called()


class ReleaseBoundaryTests(unittest.TestCase):
    def test_invalid_release_responses_are_rejected(self) -> None:
        changes = ({"id": True}, {"id": 0}, {"tag_name": ""}, {"draft": "true"},
                   {"upload_url": "http://uploads.github.com/assets"},
                   {"html_url": None})
        for payload in (None, [], *(release_payload() | change for change in changes)):
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                release_response(payload)

    def test_missing_credentials_or_non_https_api_are_rejected(self) -> None:
        for api, repository, token in ((API, "", TOKEN), (API, REPOSITORY, ""),
                                       ("http://api.github.com", REPOSITORY, TOKEN)):
            with self.subTest(api=api, repository=repository, token=bool(token)):
                with self.assertRaises(ValueError):
                    GitHubReleases(api, repository, token)
