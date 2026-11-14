"""Run the CI suite against a temporary native Python application process."""

import os
import socket
import subprocess
import sys
import tempfile
import unittest
from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from pathlib import Path
from typing import TextIO
from unittest.mock import patch


def available_port() -> int:
    """Ask the OS for an unused loopback port for this test invocation."""
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


def application_environment() -> dict[str, str]:
    """Supply explicit test-only settings to the server and its HTTP tests."""
    return {
        "APP_NAME": "ci-app",
        "PART": "ci",
        "PORT": str(available_port()),
        "IOT_LEADER_LOGIN": "ci",
        "MAINTENER_MAIL": "ci@example.invalid",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONUNBUFFERED": "1",
    }


@contextmanager
def running_server(log: TextIO) -> Iterator[subprocess.Popen[bytes]]:
    """Own the test server and stop it even when discovery or assertions fail."""
    process = subprocess.Popen(
        [sys.executable, "-B", "-m", "server.app"],
        stdout=log, stderr=subprocess.STDOUT,
    )
    try:
        yield process
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


def run_tests() -> bool:
    """Run every test module and fail explicitly if none were discovered."""
    suite = unittest.defaultTestLoader.discover(str(Path(__file__).parent))
    if suite.countTestCases() == 0:
        raise RuntimeError("No tests discovered")
    return unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful()


def print_server_log(log: TextIO) -> None:
    """Display the owned server's captured output before its log is closed."""
    log.seek(0)
    sys.stderr.write(log.read())


def main() -> int:
    application = Path(__file__).resolve().parents[1] / "app"
    os.chdir(application)
    sys.path.insert(0, str(application))
    with ExitStack() as cleanup:
        cleanup.enter_context(patch.dict(os.environ, application_environment()))
        log = cleanup.enter_context(tempfile.TemporaryFile(mode="w+", encoding="utf-8"))
        cleanup.callback(print_server_log, log)
        server = cleanup.enter_context(running_server(log))
        successful = run_tests()
        if server.poll() is not None:
            raise RuntimeError("The application process exited unexpectedly")
        return 0 if successful else 1


if __name__ == "__main__":
    raise SystemExit(main())
