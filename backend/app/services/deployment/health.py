import socket
import time

from app.models.node import Node, NodeRole
from app.schemas.health import NodeHealth
from app.services.deployment.ssh import ssh_command


def check_node(node: Node) -> NodeHealth:
    started_at = time.monotonic()

    if node.role == NodeRole.mikrotik:
        result = _tcp_check(node.host, node.ssh_port)
        result.check = "tcp"
    elif node.ssh_user:
        result = _ssh_check(node)
    else:
        result = _tcp_check(node.host, node.ssh_port)

    result.node_id = node.id
    result.name = node.name
    result.latency_ms = round((time.monotonic() - started_at) * 1000)
    return result


def _tcp_check(host: str, port: int) -> NodeHealth:
    try:
        with socket.create_connection((host, port), timeout=4):
            return NodeHealth(node_id=0, name="", status="up", check="tcp", message=f"{host}:{port} is reachable")
    except OSError as exc:
        return NodeHealth(node_id=0, name="", status="down", check="tcp", message=str(exc))


def _ssh_check(node: Node) -> NodeHealth:
    try:
        completed = ssh_command(node, "printf ok", timeout=8)
    except FileNotFoundError as exc:
        return NodeHealth(
            node_id=0,
            name="",
            status="unknown",
            check="ssh",
            message=str(exc),
        )
    except TimeoutError:
        return NodeHealth(node_id=0, name="", status="down", check="ssh", message="SSH check timed out")
    except Exception as exc:
        return NodeHealth(node_id=0, name="", status="down", check="ssh", message=str(exc))

    if completed.returncode == 0 and completed.stdout.strip() == "ok":
        return NodeHealth(node_id=0, name="", status="up", check="ssh", message="SSH login succeeded")

    message = completed.stderr.strip() or completed.stdout.strip() or f"ssh exited with {completed.returncode}"
    return NodeHealth(node_id=0, name="", status="down", check="ssh", message=message)
