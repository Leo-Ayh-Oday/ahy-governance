#!/usr/bin/env python3
"""One-click deploy to ahyops server.

Usage:
  py deploy.py           # Full deploy: upload, rebuild, restart, verify
  py deploy.py --quick   # Quick deploy: upload HTML/static only, no restart
  py deploy.py --check   # Just verify routes are working

Requires: pip install paramiko
"""

import argparse
import os
import sys
import time
import urllib.request
from pathlib import Path

import paramiko

# ── Config ──────────────────────────────────────────────────────
HOST = os.environ.get("AHYOPS_HOST", "39.105.175.218")
USER = os.environ.get("AHYOPS_USER", "root")
PASS = os.environ.get("AHYOPS_PASS", "")  # Set AHYOPS_PASS env var before deploying
KEY_PATH = os.environ.get("AHYOPS_KEY", "")  # Or use SSH key
REMOTE_DIR = "/root/ahy-governance"
LOCAL_DIR = Path(__file__).parent
CONTAINER = "ahyops"

# Files to deploy by category
PYTHON_FILES = [
    "ahy_governance/__init__.py",
    "ahy_governance/interfaces.py",
    "ahy_governance/storage.py",
    "ahy_governance/migration.py",
    "ahy_governance/middleware.py",
    "ahy_governance/scaffold.py",
    "ahy_governance/__main__.py",
    "ahy_governance/health_monitor.py",
    "ahy_governance/cost_tracker.py",
    "ahy_governance/audit_logger.py",
    "ahy_governance/rbac.py",
    "ahy_governance/memory_sharing.py",
    "ahy_governance/webhook_alerts.py",
    "ahy_governance/prompt_guard.py",
    "ahy_governance/conflict_detector.py",
    "ahy_governance/auth.py",
    "ahy_governance/compliance_reporter.py",
    "web/server.py",
]

STATIC_FILES = [
    "web/static/index.html",
    "web/static/assets",
]

CONFIG_FILES = [
    "pyproject.toml",
    "docker-compose.yml",
    "Dockerfile",
    "LICENSE",
    "README.md",
    "README_CN.md",
    "scripts/entrypoint.sh",
    "web/compliance.html",
    "web/landing.html",
    "nginx/nginx.conf",
    "nginx/conf.d/ahyops.conf",
]


def connect():
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    if KEY_PATH and Path(KEY_PATH).exists():
        ssh.connect(HOST, username=USER, key_filename=KEY_PATH, timeout=15)
    elif PASS:
        ssh.connect(HOST, username=USER, password=PASS, timeout=15)
    else:
        print("ERROR: Set $env:AHYOPS_PASS or $env:AHYOPS_KEY before deploying.")
        sys.exit(1)
    return ssh


def _ensure_remote_dir(sftp, remote_dir: str):
    """Ensure remote directory exists, creating parents as needed."""
    try:
        sftp.stat(remote_dir)
    except FileNotFoundError:
        parts = remote_dir.strip("/").split("/")
        for i in range(1, len(parts) + 1):
            partial = "/" + "/".join(parts[:i])
            try:
                sftp.stat(partial)
            except FileNotFoundError:
                sftp.mkdir(partial)


def upload_files(ssh, paths: list[str]) -> int:
    """Upload files or directories via SFTP. Returns count of uploaded files."""
    sftp = ssh.open_sftp()
    uploaded = 0

    def _upload_path(relative_path: str):
        nonlocal uploaded
        local_path = LOCAL_DIR / relative_path
        if not local_path.exists():
            print(f"  SKIP {relative_path} (not found)")
            return

        if local_path.is_dir():
            for child in sorted(local_path.rglob("*")):
                if not child.is_file():
                    continue
                child_rel = str(child.relative_to(LOCAL_DIR)).replace("\\", "/")
                remote_path = f"{REMOTE_DIR}/{child_rel}"
                _ensure_remote_dir(sftp, os.path.dirname(remote_path))
                sftp.put(str(child), remote_path)
                print(f"  OK  {child_rel} ({child.stat().st_size:,} bytes)")
                uploaded += 1
        else:
            remote_path = f"{REMOTE_DIR}/{relative_path}"
            _ensure_remote_dir(sftp, os.path.dirname(remote_path))
            sftp.put(str(local_path), remote_path)
            print(f"  OK  {relative_path} ({local_path.stat().st_size:,} bytes)")
            uploaded += 1

    for p in paths:
        _upload_path(p)

    sftp.close()
    return uploaded


def verify_routes():
    """Check all routes are healthy."""
    routes = [
        ("/", "Landing"),
        ("/app/", "Dashboard"),
        ("/compliance", "Compliance"),
        ("/docs", "API Docs"),
        ("/api/proxy/health", "API Health"),
    ]
    ok = 0
    fail = 0
    for path, name in routes:
        try:
            req = urllib.request.Request(f"http://{HOST}{path}")
            req.add_header("Accept", "text/html,application/json")
            resp = urllib.request.urlopen(req, timeout=10)
            print(f"  [{resp.status}] {name}  {path}")
            ok += 1
        except Exception as e:
            print(f"  [FAIL] {name}  {path}  — {e}")
            fail += 1
    return fail == 0


def main():
    parser = argparse.ArgumentParser(description="Deploy to ahyops server")
    parser.add_argument("--quick", action="store_true", help="HTML/static only, no restart")
    parser.add_argument("--check", action="store_true", help="Only verify routes")
    parser.add_argument("--restart", action="store_true", help="Only restart container")
    args = parser.parse_args()

    print("=" * 55)
    print("  ahyops deploy")
    print("=" * 55)

    # ── Check-only mode ────────────────────────────────────────
    if args.check:
        print("\nVerifying routes...")
        verify_routes()
        return

    ssh = connect()
    print(f"Connected: {HOST}")

    # ── Restart-only mode ──────────────────────────────────────
    if args.restart:
        print("\nRestarting containers...")
        _, out, _ = ssh.exec_command(f"cd {REMOTE_DIR} && docker compose up -d --force-recreate 2>&1")
        time.sleep(3)
        print("Verifying...")
        verify_routes()
        ssh.close()
        return

    # ── Quick mode: static only ────────────────────────────────
    if args.quick:
        print("\n[Quick] Uploading static files...")
        upload_files(ssh, STATIC_FILES)
        # Copy entire static dir into container
        ssh.exec_command(f"docker cp {REMOTE_DIR}/web/static/. {CONTAINER}:/app/web/static/")
        print("  cp web/static/ → container")
        print("\nQuick deploy done (no restart)")
        print("Verifying...")
        verify_routes()
        ssh.close()
        return

    # ── Full deploy ────────────────────────────────────────────
    print("\n[1/3] Uploading all files...")
    all_files = STATIC_FILES + PYTHON_FILES + CONFIG_FILES
    uploaded = upload_files(ssh, all_files)
    print(f"  Uploaded: {uploaded}/{len(all_files)} files")

    print("\n[2/3] Rebuilding & restarting...")
    cmds = [
        f"cd {REMOTE_DIR} && docker compose down 2>&1",
        f"cd {REMOTE_DIR} && docker compose up -d --build 2>&1",
    ]
    for cmd in cmds:
        _, out, stderr = ssh.exec_command(cmd)
        out_str = out.read().decode()
        err_str = stderr.read().decode()
        lines = out_str.strip().split("\n")
        for line in lines[-8:]:
            if line.strip():
                print(f"  {line.strip()[:150]}")
        if err_str.strip():
            print(f"  ERR: {err_str.strip()[:200]}")

    time.sleep(3)

    print("\n[3/3] Verifying...")
    if verify_routes():
        print("\nDeploy complete!")
    else:
        print("\nDeploy done with some route issues — check above.")
        sys.exit(1)

    # Setup host cron backup as safety net (every 10 min)
    print("\n[+] Setting up host backup cron...")
    cron_line = (
        f"*/10 * * * * docker cp {CONTAINER}:/app/data/ahy_governance.db "
        f"/root/ahy-backup/ahy_governance.db 2>/dev/null; "
        f"docker cp {CONTAINER}:/app/data/auth.db /root/ahy-backup/auth.db 2>/dev/null"
    )
    check_cmd = f"crontab -l 2>/dev/null | grep -F '{cron_line}' || (crontab -l 2>/dev/null; echo '{cron_line}') | crontab -"
    ssh.exec_command(check_cmd)
    print("  Host cron: every 10 min docker cp → /root/ahy-backup/")

    ssh.close()


if __name__ == "__main__":
    main()
