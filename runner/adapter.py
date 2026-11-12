"""Adapter process transport for the conformance runner."""

from __future__ import annotations

import json
import pathlib
import queue
import subprocess
import threading


class AdapterTimeout(Exception):
    """No response line arrived within the request timeout."""


class AdapterBroken(Exception):
    """The adapter exited, closed stdout, or answered with a non-object line."""


_EOF = object()


class Adapter:
    def __init__(
        self, argv: list[str], cwd: pathlib.Path, stderr_path: pathlib.Path
    ):
        self._argv = list(argv)
        self._cwd = pathlib.Path(cwd)
        self._stderr_path = pathlib.Path(stderr_path)
        self._process: subprocess.Popen | None = None
        self._stderr = None
        self._lines: queue.Queue | None = None
        self._reader: threading.Thread | None = None

    def start(self) -> dict:
        stderr = self._stderr_path.open("ab")
        try:
            process = subprocess.Popen(
                self._argv,
                cwd=self._cwd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=stderr,
                text=True,
                encoding="utf-8",
                bufsize=1,
            )
        except OSError:
            stderr.close()
            raise
        self._stderr = stderr
        self._process = process
        lines: queue.Queue = queue.Queue()
        self._lines = lines
        self._reader = threading.Thread(
            target=self._read_lines, args=(process.stdout, lines), daemon=True
        )
        self._reader.start()
        return self.request({"type": "hello", "protocol": 1}, timeout=30.0)

    def _read_lines(self, stream, lines: queue.Queue) -> None:
        try:
            for line in stream:
                lines.put(line)
        finally:
            lines.put(_EOF)

    def request(self, obj: dict, timeout: float) -> dict:
        process = self._process
        lines = self._lines
        if process is None or process.stdin is None or lines is None:
            raise AdapterBroken()
        try:
            process.stdin.write(json.dumps(obj, ensure_ascii=False) + "\n")
            process.stdin.flush()
        except (OSError, ValueError):
            raise AdapterBroken() from None
        try:
            item = lines.get(timeout=timeout)
        except queue.Empty:
            raise AdapterTimeout() from None
        if item is _EOF:
            raise AdapterBroken()
        try:
            answer = json.loads(item)
        except json.JSONDecodeError:
            raise AdapterBroken() from None
        if not isinstance(answer, dict):
            raise AdapterBroken()
        return answer

    def close(self) -> int:
        process = self._process
        if process is None:
            return 0
        if process.stdin is not None:
            try:
                process.stdin.close()
            except OSError:
                pass
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        status = process.returncode
        self._cleanup()
        return 0 if status is None else status

    def kill(self) -> None:
        process = self._process
        if process is None:
            return
        try:
            process.kill()
        except OSError:
            pass
        try:
            process.wait()
        except OSError:
            pass
        self._cleanup()

    def _cleanup(self) -> None:
        if self._stderr is not None:
            self._stderr.close()
            self._stderr = None
        self._process = None
        self._lines = None
        self._reader = None
