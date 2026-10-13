#!/usr/bin/env python3
"""Render Traefik file-provider configuration; Compose does not interpolate bind mounts."""
from pathlib import Path
import re
root = Path(__file__).resolve().parents[1]
env = dict(line.split("=", 1) for line in (root / ".env").read_text().splitlines() if line and not line.startswith("#") and "=" in line)
domain = env.get("PANEL_DOMAIN", "")
if not re.fullmatch(r"[a-zA-Z0-9](?:[a-zA-Z0-9.-]*[a-zA-Z0-9])?", domain) or "." not in domain:
    raise SystemExit("Set a valid PANEL_DOMAIN in .env first.")
s = (root / "traefik/dynamic.yml").read_text()
s = s.replace("        - web\n", "        - websecure\n")
s = s.replace("rule: PathPrefix(`/api`) || Path(`/health`)", f"rule: Host(`{domain}`) && (PathPrefix(`/api`) || Path(`/health`))")
s = s.replace("rule: PathPrefix(`/`)", f"rule: Host(`{domain}`)")
s = s.replace("      priority: 100", "      tls:\n        certResolver: letsencrypt\n      priority: 100").replace("      priority: 1\n", "      tls:\n        certResolver: letsencrypt\n      priority: 1\n")
s = s.replace("  middlewares:\n", "  middlewares:\n    redirect-to-https:\n      redirectScheme:\n        scheme: https\n")
s = s.replace("  routers:\n", f"  routers:\n    redirect:\n      entryPoints: [web]\n      rule: Host(`{domain}`)\n      middlewares: [redirect-to-https]\n      service: vpn-panel\n")
(root / "traefik/dynamic-tls.yml").write_text(s)
print("Rendered TLS configuration. Restart using both Compose files.")
