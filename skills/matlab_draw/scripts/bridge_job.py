#!/usr/bin/env python3
"""Inspect, submit and wait for jobs on the configured MATLAB file bridge."""

import argparse
import datetime
import json
import re
import shutil
import sys
import time
import uuid
from pathlib import Path

DEFAULT_ROOT = "Z:/workspace/matlab-chatgpt-bridge"
TASK_ID = re.compile(r"^[A-Za-z][A-Za-z0-9_-]*$")


def emit(value):
    print(json.dumps(value, ensure_ascii=True))


def read_json(path):
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object: {path}")
    return value


def resolve_root(value):
    root = Path(value).expanduser().absolute()
    if not root.is_dir() or not (root / "chatgpt_matlab_bridge.m").is_file():
        raise ValueError(f"Not an installed MATLAB bridge directory: {root}")
    return root


def inspect_status(root):
    path = root / "status.json"
    value = read_json(path)
    age = max(0.0, time.time() - path.stat().st_mtime)
    return {"root": str(root), "status": value, "age_seconds": round(age, 2)}


def submit(root, script, inputs):
    status = inspect_status(root)
    state = status["status"].get("state")
    if state not in {"ready", "busy"}:
        raise ValueError(f"Bridge state is {state!r}; open MATLAB or restore the bridge first")
    if state == "ready" and status["age_seconds"] > 15:
        raise ValueError("Bridge ready status is stale; check MATLAB before submitting")
    source_script = Path(script).expanduser().absolute()
    if not source_script.is_file() or source_script.suffix.lower() != ".m":
        raise ValueError("--script must be an existing MATLAB .m file")
    selected_inputs = [Path(p).expanduser().absolute() for p in inputs]
    reserved = {"task.m", "request.json", "request.json.tmp", "result.json", "result.json.tmp"}
    seen = set(reserved)
    for path in selected_inputs:
        if not path.is_file():
            raise ValueError(f"Input is not a regular file: {path}")
        name = path.name.casefold()
        if name in seen:
            raise ValueError(f"Input filename collides with another staged file: {path.name}")
        seen.add(name)
    task_id = "matlab_draw_" + datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%S")
    task_id += "_" + uuid.uuid4().hex[:12]
    job_dir = root / "jobs" / task_id
    job_dir.mkdir(parents=True, exist_ok=False)
    # A request is published only after every selected file has been copied.
    shutil.copyfile(source_script, job_dir / "task.m")
    for path in selected_inputs:
        shutil.copyfile(path, job_dir / path.name)
    request = {"task_id": task_id, "script": "task.m"}
    tmp = job_dir / "request.json.tmp"
    tmp.write_text(json.dumps(request), encoding="utf-8")
    tmp.replace(job_dir / "request.json")
    return {"task_id": task_id, "job_dir": str(job_dir), "status": "submitted"}


def wait_for_result(root, task_id, timeout):
    if not TASK_ID.fullmatch(task_id):
        raise ValueError("Invalid task ID")
    if not 0 < timeout <= 60:
        raise ValueError("--timeout must be greater than zero and at most 60 seconds")
    job_dir = root / "jobs" / task_id
    if not (job_dir / "request.json").is_file():
        raise ValueError(f"No published request for this task: {task_id}")
    result_path = job_dir / "result.json"
    deadline = time.monotonic() + timeout
    last = None
    while True:
        if result_path.is_file():
            last = read_json(result_path)
            if last.get("task_id") != task_id:
                raise ValueError("Result task ID does not match the requested task")
            state = last.get("status")
            if state in {"completed", "failed"}:
                return {"task_id": task_id, "job_dir": str(job_dir), "result": last}, (0 if state == "completed" else 1)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return {"task_id": task_id, "job_dir": str(job_dir), "status": "timeout", "last_result": last}, 3
        time.sleep(min(0.5, remaining))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=DEFAULT_ROOT)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("status")
    submit_parser = commands.add_parser("submit")
    submit_parser.add_argument("--script", required=True)
    submit_parser.add_argument("--input", action="append", default=[])
    wait_parser = commands.add_parser("wait")
    wait_parser.add_argument("--task-id", required=True)
    wait_parser.add_argument("--timeout", type=float, default=30)
    args = parser.parse_args()
    try:
        root = resolve_root(args.root)
        if args.command == "status":
            emit(inspect_status(root))
            return 0
        if args.command == "submit":
            emit(submit(root, args.script, args.input))
            return 0
        value, code = wait_for_result(root, args.task_id, args.timeout)
        emit(value)
        return code
    except (OSError, ValueError, json.JSONDecodeError) as error:
        emit({"status": "error", "message": str(error)})
        return 2


if __name__ == "__main__":
    sys.exit(main())
