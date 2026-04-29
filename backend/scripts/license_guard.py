"""License verification system with machine fingerprint and expiration.

Generates and validates license files bound to machine hardware ID.
"""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import platform
import struct
import time
import uuid
from pathlib import Path

logger = logging.getLogger(__name__)

_LICENSE_DIR = Path(__file__).resolve().parent.parent / "data"
_LICENSE_FILE = _LICENSE_DIR / "license.key"
_MACHINE_ID_FILE = _LICENSE_DIR / ".machine_id"

_LICENSE_SECRET = os.environ.get(
    "KTP_LICENSE_SECRET",
    "ktp_rs_2026_license_secret_key_do_not_share",
)


def _get_machine_fingerprint() -> str:
    if _MACHINE_ID_FILE.exists():
        return _MACHINE_ID_FILE.read_text().strip()

    components = []
    try:
        components.append(platform.node())
    except Exception:
        pass
    try:
        components.append(platform.machine())
    except Exception:
        pass
    try:
        mac = uuid.getnode()
        components.append(f"{mac:012x}")
    except Exception:
        pass
    try:
        import subprocess
        result = subprocess.run(
            ["cat", "/etc/machine-id"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            components.append(result.stdout.strip()[:64])
    except Exception:
        pass

    raw = "|".join(components) if components else str(uuid.getnode())
    fingerprint = hashlib.sha256(raw.encode()).hexdigest()[:32]

    _LICENSE_DIR.mkdir(parents=True, exist_ok=True)
    _MACHINE_ID_FILE.write_text(fingerprint)

    return fingerprint


def get_machine_id() -> str:
    return _get_machine_fingerprint()


def _sign_payload(payload: dict) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    sig = hashlib.sha256((raw + _LICENSE_SECRET).encode()).hexdigest()
    return base64.urlsafe_b64encode(
        json.dumps({"p": payload, "s": sig}).encode()
    ).decode()


def _verify_token(token: str) -> dict | None:
    try:
        data = json.loads(base64.urlsafe_b64decode(token))
        payload = data["p"]
        sig = data["s"]
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        expected = hashlib.sha256((raw + _LICENSE_SECRET).encode()).hexdigest()
        if sig != expected:
            return None
        return payload
    except Exception:
        return None


def generate_license(
    customer: str,
    expires_days: int = 365,
    machine_id: str | None = None,
    features: list[str] | None = None,
) -> str:
    mid = machine_id or get_machine_id()
    payload = {
        "customer": customer,
        "machine_id": mid,
        "issued_at": int(time.time()),
        "expires_at": int(time.time()) + expires_days * 86400,
        "features": features or ["all"],
    }
    return _sign_payload(payload)


def validate_license() -> tuple[bool, str]:
    if not _LICENSE_FILE.exists():
        return False, "许可证文件不存在，请联系供应商获取授权"

    try:
        token = _LICENSE_FILE.read_text().strip()
    except Exception:
        return False, "许可证文件读取失败"

    payload = _verify_token(token)
    if payload is None:
        return False, "许可证签名无效，文件可能被篡改"

    current_machine = get_machine_id()
    if payload.get("machine_id") != current_machine:
        return False, f"许可证与当前机器不匹配 (license={payload.get('machine_id', '?')[:8]}..., current={current_machine[:8]}...)"

    expires_at = payload.get("expires_at", 0)
    if expires_at > 0 and time.time() > expires_at:
        from datetime import datetime
        exp_date = datetime.fromtimestamp(expires_at).strftime("%Y-%m-%d")
        return False, f"许可证已过期 (到期日: {exp_date})"

    return True, f"授权有效 - 客户: {payload.get('customer', 'N/A')}"


def check_license_on_startup() -> None:
    valid, msg = validate_license()
    if valid:
        logger.info("License check passed: %s", msg)
    else:
        logger.error("License check FAILED: %s", msg)
        if os.environ.get("KTP_LICENSE_SKIP") == "1":
            logger.warning("License check skipped (KTP_LICENSE_SKIP=1)")
            return
        raise SystemExit(f"LICENSE ERROR: {msg}")


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python license_guard.py machine-id       # Show machine ID")
        print("  python license_guard.py generate <customer> [days] [machine_id]")
        print("  python license_guard.py validate          # Validate current license")
        sys.exit(1)

    cmd = sys.argv[1]
    if cmd == "machine-id":
        print(f"Machine ID: {get_machine_id()}")
    elif cmd == "generate":
        customer = sys.argv[2] if len(sys.argv) > 2 else "default"
        days = int(sys.argv[3]) if len(sys.argv) > 3 else 365
        mid = sys.argv[4] if len(sys.argv) > 4 else None
        token = generate_license(customer, days, mid)
        _LICENSE_DIR.mkdir(parents=True, exist_ok=True)
        _LICENSE_FILE.write_text(token)
        print(f"License generated for '{customer}' ({days} days)")
        print(f"Machine ID: {mid or get_machine_id()}")
        print(f"Saved to: {_LICENSE_FILE}")
    elif cmd == "validate":
        valid, msg = validate_license()
        print(f"Valid: {valid}")
        print(f"Message: {msg}")
        sys.exit(0 if valid else 1)
