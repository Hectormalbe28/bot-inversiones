"""Exercise a real HTTP process with disposable storage; no provider connections."""

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen


def main() -> None:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    with tempfile.TemporaryDirectory(prefix="bot-smoke-") as directory:
        env = os.environ | {
            "APP_HOST": "127.0.0.1",
            "APP_PORT": str(port),
            "APP_ENV": "test",
            "DATA_DIR": str(Path(directory) / "data"),
            "ARTIFACT_DIR": str(Path(directory) / "artifacts"),
            "LOG_DIR": str(Path(directory) / "logs"),
            "AI_ENABLED": "false",
            "LIVE_TRADING_ENABLED": "false",
            "LIVE_APPROVED_DEFAULT": "false",
            "PAPER_BROKER_ENABLED": "false",
        }
        with tempfile.TemporaryFile(mode="w+b") as output:
            process = subprocess.Popen(
                [sys.executable, "-m", "app"],
                env=env,
                stdout=output,
                stderr=output,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            try:
                deadline = time.monotonic() + 20
                while True:
                    if process.poll() is not None:
                        raise RuntimeError(f"API exited during startup: {process.returncode}")
                    try:
                        with urlopen(f"http://127.0.0.1:{port}/readyz", timeout=2) as response:
                            health = json.load(response)
                        break
                    except URLError:
                        if time.monotonic() > deadline:
                            raise RuntimeError("HTTP startup timed out") from None
                        time.sleep(0.1)
                assert health["status"] == "AVAILABLE", health
                assert health["live_trading_enabled"] is False
                for path in ("/healthz", "/docs", "/openapi.json", "/v1/system/providers"):
                    with urlopen(f"http://127.0.0.1:{port}{path}", timeout=2) as response:
                        assert response.status == 200
                print("PASS: real HTTP startup, readiness, health, docs, OpenAPI and providers")
            finally:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)


if __name__ == "__main__":
    main()
