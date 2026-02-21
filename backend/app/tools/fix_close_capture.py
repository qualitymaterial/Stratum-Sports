from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path


PROBE_CODE = (
    "import app.tasks.poller as p; "
    "print(p.__file__); "
    "print('CloseCaptureState', hasattr(p,'CloseCaptureState'))"
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _run_stream(cmd: list[str], *, cwd: Path, extra_env: dict[str, str] | None = None) -> int:
    print(f"$ {' '.join(cmd)}", flush=True)
    env = os.environ.copy()
    if extra_env:
        env.update(extra_env)
    completed = subprocess.run(
        cmd,
        cwd=str(cwd),
        env=env,
        check=False,
    )
    return int(completed.returncode)


def _run_capture(cmd: list[str], *, cwd: Path, extra_env: dict[str, str] | None = None) -> tuple[int, str]:
    print(f"$ {' '.join(cmd)}", flush=True)
    env = os.environ.copy()
    if extra_env:
        env.update(extra_env)
    completed = subprocess.run(
        cmd,
        cwd=str(cwd),
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    output = (completed.stdout or "") + (completed.stderr or "")
    if output:
        print(output, end="", flush=True)
    return int(completed.returncode), output


def _close_capture_present(output: str) -> bool:
    for line in output.splitlines():
        stripped = line.strip()
        if stripped.startswith("CloseCaptureState"):
            return stripped.endswith("True")
    return False


def _warn_missing_envs(env_output: str) -> None:
    enabled_ok = False
    max_events_ok = False
    for line in env_output.splitlines():
        stripped = line.strip()
        if stripped.startswith("STRATUM_CLOSE_CAPTURE_ENABLED="):
            enabled_ok = stripped.split("=", 1)[1].strip() != ""
        if stripped.startswith("STRATUM_CLOSE_CAPTURE_MAX_EVENTS_PER_CYCLE="):
            max_events_ok = stripped.split("=", 1)[1].strip() != ""

    if not enabled_ok:
        print("[WARN] STRATUM_CLOSE_CAPTURE_ENABLED missing; recommended value: true", flush=True)
    if not max_events_ok:
        print("[WARN] STRATUM_CLOSE_CAPTURE_MAX_EVENTS_PER_CYCLE missing; recommended value: 10", flush=True)


def main() -> int:
    root = _repo_root()

    if shutil.which("docker") is None:
        print("docker CLI is required for this tool.", flush=True)
        return 127

    compose_version_cmd = ["docker", "compose", "version"]
    compose_rc, _compose_out = _run_capture(compose_version_cmd, cwd=root)
    if compose_rc != 0:
        print("docker compose plugin is required for this tool.", flush=True)
        return compose_rc

    print("=== FIX CLOSE CAPTURE (OPS) ===", flush=True)
    print("=== REBUILD + RECREATE WORKER ===", flush=True)

    build_cmd = ["docker", "build", "-t", "stratumsports-worker", "-f", "backend/Dockerfile", "backend"]
    build_rc = _run_stream(build_cmd, cwd=root)
    if build_rc != 0:
        return build_rc

    image_probe_cmd = [
        "docker",
        "run",
        "--rm",
        "stratumsports-worker",
        "python",
        "-c",
        PROBE_CODE,
    ]
    image_probe_rc, image_probe_out = _run_capture(image_probe_cmd, cwd=root)
    if image_probe_rc != 0:
        return image_probe_rc
    if not _close_capture_present(image_probe_out):
        print("CloseCaptureState not present in rebuilt worker image.", flush=True)
        return 1

    print("[VERIFY MODE] Setting ODDS_API_KEY empty during recreate to avoid Odds API calls.", flush=True)
    rebuild_cmd = ["docker", "compose", "up", "-d", "--build", "--force-recreate", "worker"]
    rebuild_rc = _run_stream(
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
    verify_rc, verify_out = _run_capture(verify_cmd, cwd=root)
    if verify_rc != 0:
        return verify_rc

    has_close_capture = _close_capture_present(verify_out)
    if not has_close_capture:
        print("CloseCaptureState verification failed after rebuild.", flush=True)
        return 1

    env_verify_cmd = [
        "docker",
        "compose",
        "exec",
        "-T",
        "worker",
        "sh",
        "-lc",
        (
            "echo STRATUM_CLOSE_CAPTURE_ENABLED=$STRATUM_CLOSE_CAPTURE_ENABLED; "
            "echo STRATUM_CLOSE_CAPTURE_MAX_EVENTS_PER_CYCLE=$STRATUM_CLOSE_CAPTURE_MAX_EVENTS_PER_CYCLE"
        ),
    ]
    env_rc, env_out = _run_capture(env_verify_cmd, cwd=root)
    if env_rc != 0:
        return env_rc
    _warn_missing_envs(env_out)

    logs_cmd = ["docker", "compose", "logs", "--tail=200", "worker"]
    logs_rc, logs_out = _run_capture(logs_cmd, cwd=root)
    if logs_rc != 0:
        return logs_rc

    if "CLOSE-CAPTURE" not in logs_out:
        print(
            'If no "CLOSE-CAPTURE" appears, the worker is still running an old codepath OR '
            "close-capture planning logs aren’t executing.",
            flush=True,
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
