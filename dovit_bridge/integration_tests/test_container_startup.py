"""Offline verification of the built image; run only with fresh tmpfs mounts.

The caller supplies --network none, fresh tmpfs /data and /share, and the
read-only production inventory at /inventory.csv. No Docker calls occur here.
Every startup case executes the untouched production module entry point.
"""
from __future__ import annotations

import csv
import hashlib
import http.client
import importlib
import importlib.metadata
import json
import os
from pathlib import Path, PurePosixPath
import pkgutil
import socket
import subprocess
import sys
import tempfile
import time

sys.dont_write_bytecode = True

APP = Path("/app")
DATA = Path("/data")
SHARE = Path("/share")
INVENTORY = Path("/inventory.csv")
START_TIMEOUT = 60.0
BUILD_ONLY = {"Dockerfile", "config.yaml", "build.yaml", ".dockerignore"}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_isolation() -> dict:
    require(sys.platform == "linux", "This smoke test must run inside its Linux container")
    require(APP.is_dir(), "Expected /app image directory is absent")
    interfaces = {name for _, name in socket.if_nameindex()}
    require("lo" in interfaces and interfaces <= {"lo", "tunl0", "sit0"},
            "Container has an unexpected network interface")
    for name in interfaces - {"lo"}:
        flags = int((Path("/sys/class/net") / name / "flags").read_text().strip(), 16)
        require(not flags & 1, "A non-loopback interface is administratively up")
    require(not Path("/proc/self/net/route").read_text().splitlines()[1:],
            "Container must have no IPv4 routes (--network none)")
    mount_types = {}
    for line in Path("/proc/self/mountinfo").read_text().splitlines():
        before, after = line.split(" - ", 1)
        mount_types[before.split()[4]] = after.split()[0]
    for directory in (DATA, SHARE):
        require(mount_types.get(str(directory)) == "tmpfs", "Fixture mounts must be tmpfs")
        require(not any(directory.iterdir()), "Fixture mounts must initially be empty")
    return {"network": "no_external_interface_or_ipv4_route", "interfaces": sorted(interfaces),
            "data_and_share": "fresh_tmpfs"}


def verify_image_files() -> dict:
    with INVENTORY.open("r", encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        require(set(reader.fieldnames or ()) >= {"RelativePath", "Length", "SHA256"},
                "Production inventory has unexpected columns")
        records = list(reader)
    expected = {}
    seen = set()
    build_count = 0
    for record in records:
        name = record["RelativePath"].replace("\\", "/")
        relative = PurePosixPath(name)
        require(not relative.is_absolute() and ".." not in relative.parts,
                "Production inventory contains an unsafe path")
        require(name not in seen, "Production inventory contains duplicate paths")
        seen.add(name)
        if name in BUILD_ONLY:
            build_count += 1
            continue
        require(name in {"requirements.txt", "dovit_devices.json"} or name.startswith("dovit_bridge/"),
                "Production inventory contains an unexpected image input")
        path = APP.joinpath(*relative.parts)
        require(path.is_file() and not path.is_symlink(), "An inventoried image file is absent")
        require(path.stat().st_size == int(record["Length"]), "Image file length differs from inventory")
        require(sha256(path).upper() == record["SHA256"].upper(), "Image file checksum differs from inventory")
        expected[name] = path
    require(seen >= BUILD_ONLY and build_count == len(BUILD_ONLY), "Inventory misses a build-only input")
    actual = set()
    for path in APP.rglob("*"):
        require(not path.is_symlink(), "Unexpected symlink in /app")
        if path.is_file():
            actual.add(path.relative_to(APP).as_posix())
    require(actual == set(expected), "Image file set mismatch: " + json.dumps({
        "missing": sorted(set(expected) - actual), "extra": sorted(actual - set(expected))}))
    runtime_count = sum(name.startswith("dovit_bridge/") for name in expected)
    require(len(expected) == len(records) - build_count, "Inventory-derived image count is inconsistent")
    return {"inventory_entries": len(records), "build_only_entries": build_count,
            "image_files": len(expected), "runtime_files": runtime_count,
            "length_and_sha256": "all_match", "extra_files": 0}


def verify_python() -> dict:
    require(sys.version_info[:2] == (3, 11), "Image must use Python 3.11")
    require(importlib.metadata.version("paho-mqtt") == "2.1.0", "Image must use Paho 2.1.0")
    pip = subprocess.run([sys.executable, "-m", "pip", "check"], cwd=APP,
                         stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT, text=True, timeout=120)
    require(pip.returncode == 0, "pip check failed")
    package = importlib.import_module("dovit_bridge")
    names = ["dovit_bridge"] + sorted("dovit_bridge." + module.name
                                    for module in pkgutil.iter_modules(package.__path__))
    for name in names:
        importlib.import_module(name)
    return {"version": sys.version.split()[0], "paho_mqtt": "2.1.0",
            "pip_check": "passed", "imported_modules": len(names)}


def fixture_options() -> dict:
    return {"dovit_host": "127.0.0.1", "dovit_port": 9,
            "mqtt_mode": "supervisor", "mqtt_host": "127.0.0.1", "mqtt_port": 9,
            "mqtt_user": "synthetic-smoke-user", "mqtt_pass": "synthetic-smoke-password",
            "mqtt_tls": False, "mqtt_protocol": "3.1.1",
            "web_light_control": False, "web_device_control": False,
            "devices_file": "/share/dovit_devices.json",
            "cover_position_file": "/share/dovit_cover_positions.json",
            "cover_position_mode": "legacy", "enable_discovery": False,
            "publish_discovery": False, "alarm_code": ""}


def prepare_case(name: str) -> dict[Path, str]:
    # Only these known fixture files belong to this harness; never clear a tree.
    for path in (DATA / "options.json", DATA / "dovit_setup.json",
                 SHARE / "dovit_devices.json", SHARE / "dovit_cover_positions.json"):
        path.unlink(missing_ok=True)
    options = DATA / "options.json"
    options.write_text(json.dumps(fixture_options()), encoding="utf-8")
    expected = {options: sha256(options)}
    if name != "missing_device_recovery":
        devices = SHARE / "dovit_devices.json"
        devices.write_text('{"lights":{},"shutters":{},"thermostats":{}}', encoding="utf-8")
        expected[devices] = sha256(devices)
    if name == "oversized_setup_repair":
        private = DATA / "dovit_setup.json"
        private.write_bytes(b"x" * (1024 * 1024 + 1))
        expected[private] = sha256(private)
    return expected


def read_log(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def loopback_status() -> int:
    connection = http.client.HTTPConnection("127.0.0.1", 8099, timeout=0.5)
    try:
        connection.request("GET", "/")
        response = connection.getresponse()
        response.read()
        return response.status
    finally:
        connection.close()


def stop_owned(process: subprocess.Popen | None) -> None:
    if process is None:
        return
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
    else:
        process.wait(timeout=5)
    require(process.poll() is not None, "Owned startup process was not reaped")


def run_case(name: str, expected_log: str) -> dict:
    expected_files = prepare_case(name)
    environment = dict(os.environ, SUPERVISOR_TOKEN="", PYTHONUNBUFFERED="1",
                       PYTHONDONTWRITEBYTECODE="1")
    descriptor, log_name = tempfile.mkstemp(prefix="dovit_image_smoke_", suffix=".log")
    os.close(descriptor)
    log_path = Path(log_name)
    process = None
    result = None
    try:
        with log_path.open("wb") as log_stream:
            process = subprocess.Popen([sys.executable, "-m", "dovit_bridge.main"], cwd=APP,
                                       stdin=subprocess.DEVNULL, stdout=log_stream,
                                       stderr=subprocess.STDOUT, env=environment,
                                       start_new_session=True)
            deadline = time.monotonic() + START_TIMEOUT
            ready = False
            while time.monotonic() < deadline:
                require(process.poll() is None, "Production startup exited before readiness")
                logs = read_log(log_path)
                if expected_log in logs and "Web monitor started port=8099 ingress-only" in logs:
                    try:
                        status = loopback_status()
                    except (OSError, http.client.HTTPException):
                        status = None
                    if status is not None:
                        require(status == 403, "Production ingress peer guard did not reject loopback")
                        ready = True
                        break
                time.sleep(0.1)
            require(ready, "Production startup did not become ready within the bounded wait")
            time.sleep(0.2)
            require(process.poll() is None, "Production startup did not remain running")
            logs = read_log(log_path)
            forbidden = ("Connecting MQTT", "Dovit connection attempt=", "MQTT connection established",
                         "Bridge terminated unexpectedly", "Traceback (most recent call last)")
            require(not any(marker in logs for marker in forbidden), "Restricted startup logged a transport or failure")
            require("synthetic-smoke-password" not in logs, "Synthetic private password entered startup logs")
            require(expected_log in logs, "Expected restricted-mode log is absent")
            for path, expected_hash in expected_files.items():
                require(path.is_file() and sha256(path) == expected_hash, "A fixture changed during restricted startup")
            permitted_data = {"options.json"} | ({"dovit_setup.json"} if name == "oversized_setup_repair" else set())
            permitted_share = set() if name == "missing_device_recovery" else {"dovit_devices.json", "dovit_cover_positions.json"}
            require({path.name for path in DATA.iterdir()} == permitted_data, "Restricted startup created unexpected private files")
            require({path.name for path in SHARE.iterdir()} <= permitted_share, "Restricted startup created unexpected share files")
            result = {"case": name, "production_entrypoint": "passed", "remained_running": True,
                      "loopback_http_status": 403, "transport_logs": False,
                      "fixtures_unchanged": True}
    finally:
        try:
            stop_owned(process)
        finally:
            log_path.unlink(missing_ok=True)
    result["owned_process_reaped"] = True
    return result


def main() -> int:
    report = {"status": "running", "cases": []}
    try:
        report["isolation"] = verify_isolation()
        report["image_inventory"] = verify_image_files()
        report["python"] = verify_python()
        for name, marker in (
                ("missing_device_recovery", "restricted web recovery only. Dovit/MQTT disabled"),
                ("missing_supervisor_token_setup", "MQTT configuration unavailable key=mqtt_supervisor_token_missing"),
                ("oversized_setup_repair", "Setup overrides invalid; original preserved; no transports started")):
            report["cases"].append(run_case(name, marker))
        report["status"] = "passed"
        report["ui_policy"] = "untouched_production_peer_guard; successful_UI_not_asserted"
    except Exception as error:
        report["status"] = "failed"
        report["error"] = {"type": type(error).__name__, "message": str(error)[:1200]}
    print(json.dumps(report, sort_keys=True))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
