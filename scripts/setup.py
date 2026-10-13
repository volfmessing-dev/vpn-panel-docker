#!/usr/bin/env python3
"""Generate local credentials. No personal data is shipped with this project."""
import getpass
import os
from pathlib import Path
import secrets
import subprocess

root = Path(__file__).resolve().parents[1]
if (root / ".env").exists() or (root / "traefik/users.htpasswd").exists():
    raise SystemExit("Existing .env or authentication file found; refusing to overwrite. Edit manually.")
subprocess.run(["docker", "info"], check=True, stdout=subprocess.DEVNULL)
password = getpass.getpass("New panel password for admin (12+ characters): ")
if len(password) < 12 or password != getpass.getpass("Repeat password: "):
    raise SystemExit("Passwords must match and contain at least 12 characters.")
result = subprocess.run(
    ["docker", "run", "--rm", "-i", "httpd:2.4-alpine", "htpasswd", "-niB", "admin"],
    input=password + "\n", text=True, capture_output=True, check=True,
)
os.umask(0o077)
(root / "secrets/ssh").mkdir(parents=True, exist_ok=True)
(root / "secrets/ssh/known_hosts").touch(exist_ok=True)
(root / "traefik/users.htpasswd").write_text(result.stdout)
env = (root / ".env.example").read_text().replace("POSTGRES_PASSWORD=\n", "POSTGRES_PASSWORD=" + secrets.token_hex(32) + "\n")
(root / ".env").write_text(env)
print("Created .env, authentication and SSH directory. Login: admin")
print("Start: docker compose up -d --build")
