from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path


PROBE_CODE = (
    "import app.tasks.poller as p; "
    "print(p.__file__); "
    "print('CloseCaptureState', hasattr(p,'CloseCaptureState'))"
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _run_stream(
    cmd: list[str],
    *,
    cwd: Path | None = None,
    extra_env: dict[str, str] | None = None,
) -> tuple[int, str]:
    print(f"$ {' '.join(cmd)}", flush=True)
    env = os.environ.copy()
    if extra_env:
        env.update(extra_env)
    process = subprocess.Popen(
        cmd,
        cwd=str(cwd) if cwd else None,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    captured: list[str] = []
    assert process.stdout is not None
    for line in process.stdout:
        print(line, end="")
        captured.append(line)
    return process.wait(), "".join(captured)


def _close_capture_present(output: str) -> bool:
    for line in output.splitlines():
        stripped = line.strip()
        if stripped.startswith("CloseCaptureState"):
            return stripped.endswith("True")
    return False


def _print_env_check() -> None:
    print("=== ENV CHECK ===", flush=True)
    enabled = os.getenv("STRATUM_CLOSE_CAPTURE_ENABLED")
    max_events = os.getenv("STRATUM_CLOSE_CAPTURE_MAX_EVENTS_PER_CYCLE")

    if enabled:
        print(f"STRATUM_CLOSE_CAPTURE_ENABLED={enabled}", flush=True)
    else:
        print(
            "[WARN] STRATUM_CLOSE_CAPTURE_ENABLED missing; recommended value: true",
            flush=True,
        )

    if max_events:
        print(f"STRATUM_CLOSE_CAPTURE_MAX_EVENTS_PER_CYCLE={max_events}", flush=True)
    else:
        print(
            "[WARN] STRATUM_CLOSE_CAPTURE_MAX_EVENTS_PER_CYCLE missing; recommended value: 10",
            flush=True,
        )


def main() -> int:
    root = _repo_root()

    if shutil.which("docker") is None:
        print("docker CLI is required for this tool.", flush=True)
        return 127

    print("=== FIX CLOSE CAPTURE ===", flush=True)
    pre_verify_cmd = [
        "docker",
        "compose",
        "run",
        "--rm",
        "--no-deps",
        "backend",
        "python",
        "-c",
        PROBE_CODE,
    ]
    pre_rc, pre_out = _run_stream(pre_verify_cmd, cwd=root)
    if pre_rc != 0:
        print("Pre-fix backend probe failed.", flush=True)
        return pre_rc

    _print_env_check()

    print("=== REBUILD + RECREATE WORKER ===", flush=True)
    print("[VERIFY MODE] Setting ODDS_API_KEY to empty for worker recreate to avoid external API calls.", flush=True)
    rebuild_cmd = ["docker", "compose", "up", "-d", "--build", "--force-recreate", "worker"]
    rebuild_rc, _rebuild_out = _run_stream(
        rebuild_cmd,
        cwd=root,
        extra_env={"ODDS_API_KEY": ""},
    )
    if rebuild_rc != 0:
        return rebuild_rc

    print("=== VERIFY (NO API CALLS) ===", flush=True)
    verify_cmd = [
        "docker",
        "compose",
        "exec",
        "-T",
        "worker",
        "python",
        "-c",
        PROBE_CODE,
    ]
    verify_rc, verify_out = _run_stream(verify_cmd, cwd=root)
    if verify_rc != 0:
        return verify_rc

    has_close_capture = _close_capture_present(verify_out)
    if not has_close_capture:
        print("CloseCaptureState verification failed after rebuild.", flush=True)
        return 1

    logs_cmd = ["docker", "compose", "logs", "--tail=200", "worker"]
    logs_rc, logs_out = _run_stream(logs_cmd, cwd=root)
    if logs_rc != 0:
        return logs_rc

    close_capture_lines = [line for line in logs_out.splitlines() if "CLOSE-CAPTURE" in line]
    if close_capture_lines:
        print("=== CLOSE-CAPTURE LOG MATCHES ===", flush=True)
        for line in close_capture_lines:
            print(line, flush=True)
    else:
        print(
            "Close-capture code is present but not emitting logs; worker may not be running the poller loop.",
            flush=True,
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
