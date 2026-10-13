import json
import os
import subprocess
from pathlib import Path

import pytest

from app.services.wireguard import users


@pytest.mark.parametrize("failure", ["", "dns", "servfail", "restore"])
def test_refresh_preserves_live_set_until_successful_swap(tmp_path: Path, monkeypatch, failure: str) -> None:
    monkeypatch.setattr(users, "bypass_domains", lambda: ["example.com"])
    monkeypatch.setattr(users, "BYPASS_CIDRS", ["192.0.2.0/30"])
    state = tmp_path / "state.json"
    state.write_text(json.dumps({"vpn_panel_bypass_v4": ["203.0.113.7"]}))
    trace = tmp_path / "trace.jsonl"
    fake = tmp_path / "bin"
    fake.mkdir()
    ipset = fake / "ipset"
    ipset.write_text("""#!/usr/bin/env python3
import json, os, sys
from pathlib import Path
path = Path(os.environ['SET_STATE'])
s = json.loads(path.read_text())
a = sys.argv[1:]
with open(os.environ['SET_TRACE'], 'a') as f:
    f.write(json.dumps({'action': a[0], 'live': s.get('vpn_panel_bypass_v4')}) + '\\n')
if a[0] == 'destroy':
    s.pop(a[1], None)
elif a[0] == 'create':
    s.setdefault(a[1], [])
elif a[0] == 'restore':
    for line in sys.stdin:
        fields = line.split()
        s[fields[1]].append(fields[2])
    path.write_text(json.dumps(s))
    if os.environ['FAILURE'] == 'restore': sys.exit(1)
elif a[0] == 'swap':
    s[a[1]], s[a[2]] = s[a[2]], s[a[1]]
elif a[0] == 'save':
    for ip in s[a[1]]: print('add', a[1], ip)
path.write_text(json.dumps(s))
""")
    ipset.chmod(0o755)
    dig = fake / "dig"
    dig.write_text("""#!/usr/bin/env python3
import os, sys
if os.environ['FAILURE'] == 'dns': sys.exit(9)
status = 'SERVFAIL' if os.environ['FAILURE'] == 'servfail' else 'NOERROR'
print(';; ->>HEADER<<- opcode: QUERY, status: ' + status + ', id: 1')
print('example.com. 60 IN A 198.51.100.9')
""")
    dig.chmod(0o755)
    # Lock implementation is exercised separately on the Linux production host.
    flock = fake / "flock"
    flock.write_text("#!/bin/sh\nexit 0\n")
    flock.chmod(0o755)
    script = users._policy_script([], "awg1", "enp3s0")
    script = script.replace("/run/lock/vpn-panel-bypass.lock", str(tmp_path / "lock"))
    script = script.replace("/run/vpn-panel-bypass.", str(tmp_path / "work."))
    script = script.replace("/var/lib/vpn-panel-bypass.ipset", str(tmp_path / "saved.ipset"))
    result = subprocess.run(
        ["bash", "-c", script, "refresh", "--refresh-only"],
        env={**os.environ, "PATH": f"{fake}:{os.environ['PATH']}", "SET_STATE": str(state),
             "SET_TRACE": str(trace), "FAILURE": failure},
        capture_output=True, text=True, timeout=10,
    )
    final = json.loads(state.read_text())
    events = [json.loads(line) for line in trace.read_text().splitlines()]
    swap_index = next((i for i, event in enumerate(events) if event["action"] == "swap"), len(events))
    assert all(event["live"] == ["203.0.113.7"] for event in events[:swap_index + 1])
    assert "vpn_panel_bypass_v4_next" not in final
    if failure:
        assert result.returncode != 0
        assert final["vpn_panel_bypass_v4"] == ["203.0.113.7"]
        assert not (tmp_path / "saved.ipset").exists()
    else:
        assert result.returncode == 0, result.stderr
        assert set(final["vpn_panel_bypass_v4"]) == {"192.0.2.0", "192.0.2.1", "192.0.2.2", "192.0.2.3", "198.51.100.9"}
        assert "198.51.100.9" in (tmp_path / "saved.ipset").read_text()
        assert "5 entries" in result.stdout
