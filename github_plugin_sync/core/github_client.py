# -*- coding: utf-8 -*-
"""Minimal GitHub API client used by the plugin.

The implementation intentionally relies only on Python's standard library so
that the plugin can run in a stock QGIS installation without requiring users
to install extra dependencies. It supports public access and token-based
authentication (Personal Access Tokens – classic or fine-grained).
"""

from __future__ import annotations

import json
import re
import ssl
import tarfile
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Iterable, List, Optional


GITHUB_API = "https://api.github.com"
USER_AGENT = "QGIS-GitHubPluginSync/1.0.0"


class GitHubError(Exception):
    """Raised for any unsuccessful GitHub interaction."""


@dataclass
class RepoRef:
    """Reference to a GitHub repository in ``owner/name`` form."""

    owner: str
    name: str

    @property
    def full_name(self) -> str:
        return f"{self.owner}/{self.name}"

    @classmethod
    def parse(cls, value: str) -> "RepoRef":
        """Accepts ``owner/name`` or any GitHub URL."""
        value = (value or "").strip()
        if not value:
            raise GitHubError("Repository must not be empty")
        # Normalise URLs
        url_match = re.match(
            r"^(?:https?://)?(?:www\.)?github\.com/([^/]+)/([^/#?]+?)(?:\.git)?/?$",
            value,
        )
        if url_match:
            return cls(owner=url_match.group(1), name=url_match.group(2))
        slash_match = re.match(r"^([^/\s]+)/([^/\s]+?)(?:\.git)?$", value)
        if slash_match:
            return cls(owner=slash_match.group(1), name=slash_match.group(2))
        raise GitHubError(
            f"Invalid repository reference: {value!r}. "
            "Expected 'owner/name' or a GitHub URL."
        )


class GitHubClient:
    """Thin wrapper around GitHub's REST v3 endpoints."""

    def __init__(self, token: Optional[str] = None, timeout: float = 30.0):
        self.token = token or None
        self.timeout = timeout
        # Default SSL context so certificate validation is enforced.
        self._ssl_ctx = ssl.create_default_context()

    # ------------------------------------------------------------------
    # Core request helper
    # ------------------------------------------------------------------
    def _request(self, url: str, accept: str = "application/vnd.github+json"):
        headers = {
            "Accept": accept,
            "User-Agent": USER_AGENT,
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        req = urllib.request.Request(url, headers=headers)
        try:
            return urllib.request.urlopen(
                req, timeout=self.timeout, context=self._ssl_ctx
            )
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
            message = _extract_error_message(body) or exc.reason
            raise GitHubError(
                f"GitHub request failed ({exc.code}): {message}"
            ) from exc
        except urllib.error.URLError as exc:
            raise GitHubError(f"Network error: {exc.reason}") from exc

    def _get_json(self, url: str):
        with self._request(url) as resp:
            raw = resp.read().decode("utf-8")
        try:
            return json.loads(raw)
        except ValueError as exc:
            raise GitHubError("Invalid JSON returned by GitHub") from exc

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def check_auth(self):
        """Return the authenticated user payload, or ``None`` if anonymous."""
        if not self.token:
            return None
        return self._get_json(f"{GITHUB_API}/user")

    def get_repo(self, repo: RepoRef):
        return self._get_json(f"{GITHUB_API}/repos/{repo.owner}/{repo.name}")

    def list_branches(self, repo: RepoRef) -> List[str]:
        branches: List[str] = []
        url: Optional[str] = (
            f"{GITHUB_API}/repos/{repo.owner}/{repo.name}/branches?per_page=100"
        )
        while url:
            with self._request(url) as resp:
                page = json.loads(resp.read().decode("utf-8"))
                link = resp.headers.get("Link", "")
            branches.extend(item["name"] for item in page if "name" in item)
            url = _next_link(link)
        return branches

    def get_file(self, repo: RepoRef, branch: str, path: str) -> Optional[bytes]:
        """Download a single file. Returns ``None`` when not present."""
        url = (
            f"{GITHUB_API}/repos/{repo.owner}/{repo.name}/contents/"
            f"{urllib.parse.quote(path)}?ref={urllib.parse.quote(branch)}"
        )
        try:
            with self._request(url, accept="application/vnd.github.raw") as resp:
                return resp.read()
        except GitHubError as exc:
            if "404" in str(exc):
                return None
            raise

    def list_directory(self, repo: RepoRef, branch: str,
                       path: str = "") -> List[dict]:
        """Return the contents listing of ``path`` for ``branch``.

        Each entry is a dict with at least ``name``, ``path`` and ``type``
        ("file" / "dir"). Returns an empty list if the path does not exist.
        """
        quoted_path = urllib.parse.quote(path.strip("/"))
        url = (
            f"{GITHUB_API}/repos/{repo.owner}/{repo.name}/contents/"
            f"{quoted_path}?ref={urllib.parse.quote(branch)}"
        )
        try:
            data = self._get_json(url)
        except GitHubError as exc:
            if "404" in str(exc):
                return []
            raise
        if isinstance(data, dict):  # single file
            return [data]
        return list(data) if isinstance(data, list) else []

    def find_plugin_folders(self, repo: RepoRef, branch: str,
                            max_depth: int = 2) -> List[str]:
        """Return folder paths (relative to repo root) that contain a
        ``metadata.txt`` file. The repo root itself is represented as an
        empty string.

        The search is breadth-first up to ``max_depth`` levels to keep
        the number of API calls bounded on large repositories.
        """
        candidates: List[str] = []
        visited = set()
        queue: List[tuple] = [("", 0)]
        while queue:
            path, depth = queue.pop(0)
            if path in visited:
                continue
            visited.add(path)
            entries = self.list_directory(repo, branch, path)
            has_metadata = any(
                e.get("type") == "file" and e.get("name") == "metadata.txt"
                for e in entries
            )
            if has_metadata:
                candidates.append(path)
            if depth < max_depth:
                for entry in entries:
                    if entry.get("type") != "dir":
                        continue
                    name = entry.get("name", "")
                    if not name or name.startswith("."):
                        continue
                    child = f"{path}/{name}".strip("/")
                    queue.append((child, depth + 1))
        return candidates

    def download_tarball(self, repo: RepoRef, branch: str, destination: str) -> str:
        """Fetch the ``tarball`` archive for ``branch`` into ``destination``.

        Returns the path to the root directory extracted from the archive.
        """
        url = (
            f"{GITHUB_API}/repos/{repo.owner}/{repo.name}/"
            f"tarball/{urllib.parse.quote(branch)}"
        )
        with self._request(url, accept="application/vnd.github+json") as resp:
            data = resp.read()
        with tempfile.NamedTemporaryFile(delete=False, suffix=".tar.gz") as tmp:
            tmp.write(data)
            tar_path = tmp.name
        try:
            with tarfile.open(tar_path, "r:gz") as tar:
                members = list(_safe_tar_members(tar, destination))
                top_levels = {
                    m.name.strip("/").split("/", 1)[0]
                    for m in members
                    if m.name.strip("/")
                }
                if len(top_levels) != 1:
                    raise GitHubError(
                        "Unexpected tarball layout – expected one root folder"
                    )
                root = next(iter(top_levels))
                tar.extractall(destination, members=members)
        finally:
            try:
                import os
                os.unlink(tar_path)
            except OSError:
                pass
        import os
        return os.path.join(destination, root)


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------
def _next_link(link_header: str) -> Optional[str]:
    if not link_header:
        return None
    for part in link_header.split(","):
        segments = [s.strip() for s in part.split(";")]
        if len(segments) < 2:
            continue
        url = segments[0].strip("<>")
        if any(s == 'rel="next"' for s in segments[1:]):
            return url
    return None


def _extract_error_message(body: str) -> str:
    try:
        data = json.loads(body)
        if isinstance(data, dict) and "message" in data:
            return str(data["message"])
    except ValueError:
        pass
    return body.strip()


def _safe_tar_members(tar: tarfile.TarFile, destination: str) -> Iterable[tarfile.TarInfo]:
    """Yield members, raising on path traversal attempts."""
    import os
    dest = os.path.realpath(destination)
    for member in tar.getmembers():
        member_path = os.path.realpath(os.path.join(destination, member.name))
        if not member_path.startswith(dest + os.sep) and member_path != dest:
            raise GitHubError(f"Unsafe path in archive: {member.name!r}")
        yield member
