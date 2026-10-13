import subprocess
from pathlib import Path

from app.core.config import get_settings
from app.models.node import Node


def ssh_command(node: Node, remote_command: str, timeout: int = 8) -> subprocess.CompletedProcess[str]:
    key_path = Path(get_settings().ssh_key_path)
    if not key_path.exists():
        raise FileNotFoundError(f"SSH key not mounted at {key_path}")
    if not node.ssh_user:
        raise ValueError("Node has no SSH user configured")

    command = [
        "ssh",
        "-i",
        str(key_path),
        "-o",
        "BatchMode=yes",
        "-o",
        "IdentitiesOnly=yes",
        "-o",
        "StrictHostKeyChecking=yes",
        "-o",
        "UserKnownHostsFile=/run/secrets/ssh/known_hosts",
        "-o",
        "ConnectTimeout=4",
        "-p",
        str(node.ssh_port),
        f"{node.ssh_user}@{node.host}",
        remote_command,
    ]
    return subprocess.run(command, capture_output=True, check=False, text=True, timeout=timeout)
