"""Scripted adapter used by the runner's tests."""

import json
import pathlib
import sys
import time


def _send(obj):
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _send_raw(line):
    sys.stdout.write(line if line.endswith("\n") else line + "\n")
    sys.stdout.flush()


def _user_dict_text(request):
    data = pathlib.Path(request["user_dict"]["path"]).read_bytes()
    return data.decode("utf-8")


def _answer_case(behavior, request):
    case_id = request["id"]
    if "exit" in behavior:
        sys.exit(behavior["exit"])
    if "sleep" in behavior:
        time.sleep(behavior["sleep"])
        _send({"type": "result", "id": case_id, "steps": []})
        return
    if "raw" in behavior:
        _send_raw(behavior["raw"])
        return
    if "steps" in behavior:
        _send({"type": "result", "id": case_id, "steps": behavior["steps"]})
        return
    if "error" in behavior:
        _send({"type": "result", "id": case_id, "error": behavior["error"]})
        return
    if "append_user_dict" in behavior:
        path = pathlib.Path(request["user_dict"]["path"])
        with path.open("a", encoding="utf-8") as stream:
            stream.write(behavior["append_user_dict"] + "\n")
    if "user_dict_text" in behavior or "append_user_dict" in behavior:
        _send(
            {
                "type": "result",
                "id": case_id,
                "steps": [
                    {
                        "text": _user_dict_text(request),
                        "preedit": "",
                        "mode": "hiragana",
                    }
                ],
            }
        )
        return
    _send(
        {
            "type": "result",
            "id": case_id,
            "error": {"code": "engine-error"},
        }
    )


def main() -> int:
    sys.stdin.reconfigure(encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    script = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
    record_path = script.get("record")
    record = (
        pathlib.Path(record_path).open("a", encoding="utf-8")
        if record_path is not None
        else None
    )
    try:
        hello_behavior = script.get("hello_behavior")
        hello = {
            "type": "hello",
            "protocol": script.get("protocol", 1),
            "engine": script["engine"],
            "version": script["version"],
        }
        for line in sys.stdin:
            if record is not None:
                record.write(line)
                record.flush()
            request = json.loads(line)
            if request.get("type") == "hello":
                if hello_behavior is not None and "sleep" in hello_behavior:
                    time.sleep(hello_behavior["sleep"])
                elif hello_behavior is not None and "exit" in hello_behavior:
                    sys.exit(hello_behavior["exit"])
                elif hello_behavior is not None and "raw" in hello_behavior:
                    _send_raw(hello_behavior["raw"])
                    continue
                _send(hello)
            elif request.get("type") == "case":
                behavior = script.get("cases", {}).get(request["id"])
                if behavior is None:
                    _send(
                        {
                            "type": "result",
                            "id": request["id"],
                            "error": {"code": "engine-error"},
                        }
                    )
                else:
                    _answer_case(behavior, request)
    finally:
        if record is not None:
            record.close()

    exit_record = script.get("exit_record")
    if exit_record is not None:
        with pathlib.Path(exit_record).open("a", encoding="utf-8") as stream:
            stream.write("closed\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
