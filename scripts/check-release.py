#!/usr/bin/env python3
"""Check tracked release files for accidentally included operational data."""
import ipaddress
from pathlib import Path
import re
import subprocess
root = Path(__file__).resolve().parents[1]
files = subprocess.check_output(['git', 'ls-files'], cwd=root, text=True).splitlines()
allowed = [ipaddress.ip_network(n) for n in ['0.0.0.0/32','1.1.1.1/32','10.0.0.0/8','127.0.0.0/8','192.168.0.0/16','192.0.2.0/24','198.51.100.0/24','203.0.113.0/24']]
errors = []
for name in files:
    p = Path(name)
    if any(part in {'secrets','diagnostics','backups','data','.idea'} for part in p.parts) or p.suffix in {'.sql','.dump','.backup','.rsc'} or (p.name.startswith('.env') and p.name != '.env.example') or p.name == 'users.htpasswd':
        errors.append(f'Forbidden release file: {name}')
    text = (root/p).read_text()
    if re.search(r'-----BEGIN (?:OPENSSH |RSA |EC )?PRIVATE KEY-----', text):
        errors.append(f'Private key material: {name}')
    if name.startswith(('backend/app/', 'frontend/src/', 'frontend/tests/')):
        for match in re.findall(r'(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?![\d.])', text):
            try:
                address = ipaddress.ip_address(match)
            except ValueError:
                continue
            if not any(address in network for network in allowed):
                errors.append(f'Non-example public address in {name}')
if errors:
    raise SystemExit('\n'.join(errors))
print(f'Release file checks passed ({len(files)} tracked files). Manual review of identifiers is also required.')
