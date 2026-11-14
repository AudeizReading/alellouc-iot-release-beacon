"""GitHub release commands used by the standalone publication workflow."""

import json
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen

API_VERSION = "2022-11-28"


def https_url(value: object) -> str:
    """Validate URLs received from the GitHub context or API."""
    if not isinstance(value, str):
        raise ValueError("Expected a GitHub HTTPS URL")
    parsed = urlsplit(value)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError("Expected a GitHub HTTPS URL")
    return value


@dataclass(frozen=True)
class Release:
    id: int
    tag: str
    draft: bool
    upload_url: str
    html_url: str


def release_response(value: object) -> Release:
    """Normalize a release API response into its resource identity and state."""
    if not isinstance(value, dict):
        raise ValueError("Expected a GitHub release object")
    identity = value.get("id")
    tag = value.get("tag_name")
    draft = value.get("draft")
    if type(identity) is not int or identity < 1:
        raise ValueError("Invalid GitHub release ID")
    if not isinstance(tag, str) or not tag:
        raise ValueError("Invalid GitHub release tag")
    if type(draft) is not bool:
        raise ValueError("Invalid GitHub release state")
    return Release(
        identity, tag, draft,
        https_url(value.get("upload_url")), https_url(value.get("html_url")),
    )


class GitHubReleases:
    """Bind release commands to one repository and its job-scoped token.

    Creation returns GitHub's resource handle so subsequent writes target
    that exact draft instead of looking up an editable release title.
    """

    def __init__(self, api_url: str, repository: str, token: str) -> None:
        if not repository or not token:
            raise ValueError("GitHub repository and token are required")
        self._releases_url = f"{https_url(api_url).rstrip('/')}/repos/{repository}/releases"
        self._token = token

    def _request(
        self, method: str, url: str, body: bytes,
        content_type: str, expected_status: int,
    ) -> object:
        request = Request(
            https_url(url), data=body, method=method,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {self._token}",
                "Content-Type": content_type,
                "X-GitHub-Api-Version": API_VERSION,
            },
        )
        with urlopen(request, timeout=60) as response:
            if response.status != expected_status:
                raise RuntimeError(f"Unexpected GitHub HTTP status: {response.status}")
            return json.load(response)

    def create_draft(self, git_tag: str, title: str, commit: str) -> Release:
        payload = {
            "tag_name": git_tag, "target_commitish": commit,
            "name": title, "draft": True, "generate_release_notes": True,
        }
        result = self._request(
            "POST", self._releases_url, json.dumps(payload).encode(),
            "application/json", 201,
        )
        release = release_response(result)
        if release.tag != git_tag or not release.draft:
            raise ValueError("GitHub did not return the requested draft release")
        return release

    def upload_digest(self, upload_url: str, path: Path) -> None:
        body = path.read_bytes()
        endpoint = upload_url.partition("{")[0]
        query = urlencode({"name": path.name})
        asset = self._request(
            "POST", f"{endpoint}?{query}", body, "application/octet-stream", 201,
        )
        if not isinstance(asset, dict):
            raise ValueError("Expected a GitHub release asset object")
        if asset.get("name") != path.name or asset.get("size") != len(body):
            raise ValueError("GitHub returned an unexpected digest asset")
        if asset.get("state") != "uploaded":
            raise ValueError("GitHub digest asset upload is incomplete")

    def publish(self, identity: int, git_tag: str) -> Release:
        payload = {"draft": False, "prerelease": False, "make_latest": "true"}
        result = self._request(
            "PATCH", f"{self._releases_url}/{identity}",
            json.dumps(payload).encode(), "application/json", 200,
        )
        release = release_response(result)
        if release.id != identity or release.tag != git_tag or release.draft:
            raise ValueError("GitHub did not publish the requested release")
        return release
