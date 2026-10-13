"""Install KTP as isolated systemd user services using an existing private .env."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sqlite3
import sys


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--app', type=Path, required=True)
    parser.add_argument('--data-dir', type=Path, required=True)
    parser.add_argument('--admin-user', required=True)
    parser.add_argument('--backend-port', type=int, default=8005)
    parser.add_argument('--frontend-port', type=int, default=3002)
    args = parser.parse_args()
    app, data = args.app.resolve(), args.data_dir.resolve()
    os.umask(0o077)
    from dotenv import load_dotenv, set_key
    env = app / 'backend/.env'
    assert env.is_file(), 'Create the private backend/.env first'
    load_dotenv(env, override=True)
    assert os.environ.get('APP_AUTH_ENABLED', '').lower() == 'true', 'Enable application authentication first'
    assert os.environ.get('KTP_LICENSE_SECRET') not in (None, '', 'ktp_rs_2026_license_secret_key_do_not_share'), 'Configure a private license signing secret first'
    user_db = data / 'var/data/users.sqlite3'
    user_db.parent.mkdir(parents=True, exist_ok=True)
    temporary_dir = data / 'tmp'
    temporary_dir.mkdir(parents=True, exist_ok=True)
    temporary_dir.chmod(0o700)
    legacy_users = app / 'backend/data/users.sqlite3'
    if not user_db.exists() and legacy_users.is_file():
        with sqlite3.connect(legacy_users) as source, sqlite3.connect(user_db) as target:
            source.backup(target)
    # Keep report tools and persistent authentication under this deployment's data directory.
    for key, value in {
        'APSIM_REPORT_OUTPUT_DIR': str(data / 'reports'),
        'APSIM_DEMO_DB': str(data / 'models/GxExM.db'),
        'KTP_USER_DB_PATH': str(user_db),
        'TMPDIR': str(temporary_dir),
    }.items():
        set_key(env, key, value)
        os.environ[key] = value
    env.chmod(0o600)
    sys.path.insert(0, str(app / 'backend'))
    from scripts import license_guard
    if not license_guard.validate_license()[0]:
        token = license_guard.generate_license(customer=args.admin_user, expires_days=365)
        license_guard._LICENSE_DIR.mkdir(parents=True, exist_ok=True)
        license_guard._LICENSE_FILE.write_text(token)
        license_guard._LICENSE_FILE.chmod(0o600)
    assert license_guard.validate_license()[0]
    from ktp_backend.auth import get_user_store
    store = get_user_store()
    password_file = data / 'credentials/admin-password'
    password = password_file.read_text().strip()
    if store.get_user(args.admin_user) is None:
        store.create_user(args.admin_user, password, role='admin')
    assert store.verify_password(args.admin_user, password)
    from infra.imagery.crop_spatial import verify_crop_model
    verify_crop_model()
    assert Path(os.environ['LAI_LUT_PATH']).is_file()
    assert (data / 'models/GxExM.db').is_file()
    unit_dir = Path.home() / '.config/systemd/user'
    unit_dir.mkdir(parents=True, exist_ok=True)
    executable = Path(sys.executable).resolve()
    quote = lambda value: json.dumps(str(value))
    backend = f'''[Unit]
Description=KTP backend

[Service]
Type=simple
WorkingDirectory={app / 'backend'}
EnvironmentFile={env}
Environment={quote('PATH=' + str(executable.parent) + ':/usr/local/bin:/usr/bin:/bin')}
ExecStart={quote(executable)} -m uvicorn apps.api_gateway.main:app --host 127.0.0.1 --port {args.backend_port} --timeout-keep-alive 30
Restart=on-failure
RestartSec=3
TimeoutStopSec=45
UMask=0077

[Install]
WantedBy=default.target
'''
    frontend = f'''[Unit]
Description=KTP frontend and streaming API proxy
Requires=ktp-backend.service
After=ktp-backend.service

[Service]
Type=simple
WorkingDirectory={app}
Environment=BACKEND_URL=http://127.0.0.1:{args.backend_port}
Environment=FRONTEND_PORT={args.frontend_port}
Environment={quote('TMPDIR=' + str(temporary_dir))}
Environment={quote('PATH=' + str(executable.parent) + ':/usr/local/bin:/usr/bin:/bin')}
ExecStart={quote(executable)} {quote(app / 'deploy/serve_frontend.py')}
Restart=on-failure
RestartSec=3
UMask=0077

[Install]
WantedBy=default.target
'''
    for name, body in [('ktp-backend.service', backend), ('ktp-frontend.service', frontend)]:
        path = unit_dir / name
        if path.exists() and path.read_text() != body:
            backup = data / 'backups' / (name + '.previous')
            backup.parent.mkdir(parents=True, exist_ok=True)
            if not backup.exists(): backup.write_text(path.read_text())
        path.write_text(body)
    subprocess.run(['systemctl', '--user', 'daemon-reload'], check=True)
    subprocess.run(['systemctl', '--user', 'enable', '--now', 'ktp-backend.service', 'ktp-frontend.service'], check=True)
    print(json.dumps({'installed': True, 'services': ['ktp-backend', 'ktp-frontend'],
                      'admin_user': args.admin_user, 'password_file': str(password_file),
                      'license_valid': True, 'model_checksum_verified': True,
                      'frontend_port': args.frontend_port, 'backend_bind': f'127.0.0.1:{args.backend_port}'}))


if __name__ == '__main__':
    main()
