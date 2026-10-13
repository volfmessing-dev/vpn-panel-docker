from datetime import datetime
import subprocess

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api import routes
from app.db.session import Base, get_db
from app.models.node import Node, NodeRole
from app.schemas.facts import NodeFacts
from app.schemas.health import NodeHealth
from app.services.deployment import health


@pytest.fixture
def node_api(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add_all([Node(name=name, role=NodeRole.amnezia_exit, host=f"192.0.2.{index}", ssh_user="test", ssh_port=22)
                    for index, name in enumerate(["Exit_A", "Archived_B", "archived_c", "Other"], 1)])
        db.commit()
        calls = []
        def check(node):
            calls.append(("health", node.id))
            return NodeHealth(node_id=node.id, name=node.name, status="up", check="ssh", message="SSH login succeeded")
        def facts(node):
            calls.append(("facts", node.id))
            return NodeFacts(node_id=node.id, name=node.name, status="up", hostname="fixture")
        monkeypatch.setattr(routes, "check_node", check)
        monkeypatch.setattr(routes, "collect_node_facts", facts)
        app = FastAPI()
        app.include_router(routes.router, prefix="/api")
        app.dependency_overrides[get_db] = lambda: db
        with TestClient(app) as client:
            yield client, calls
    engine.dispose()


@pytest.mark.parametrize("kind", ["health", "facts"])
def test_single_check_only_targets_requested_node(node_api, kind):
    client, calls = node_api
    response = client.get(f"/api/nodes/1/{kind}")
    assert response.status_code == 200
    assert calls == [(kind, 1)]
    assert response.json()["node_id"] == 1
    assert datetime.fromisoformat(response.json()["checked_at"].replace("Z", "+00:00")).utcoffset().total_seconds() == 0


@pytest.mark.parametrize("kind", ["health", "facts"])
@pytest.mark.parametrize("node_id,expected", [(2, 409), (3, 409), (999, 404)])
def test_missing_and_retired_nodes_are_never_probed(node_api, kind, node_id, expected):
    client, calls = node_api
    assert client.get(f"/api/nodes/{node_id}/{kind}").status_code == expected
    assert calls == []


@pytest.mark.parametrize("kind", ["health", "facts"])
def test_bulk_checks_skip_retired_nodes(node_api, kind):
    client, calls = node_api
    response = client.get(f"/api/nodes/{kind}")
    assert response.status_code == 200
    assert [row["node_id"] for row in response.json()] == [1, 4]
    assert calls == [(kind, 1), (kind, 4)]


def test_mikrotik_check_uses_tcp_and_never_logs_in(monkeypatch):
    node = Node(id=5, name="MikroTik", role=NodeRole.mikrotik, host="192.0.2.5", ssh_user="test", ssh_port=22)
    calls = []
    def tcp(host, port):
        calls.append((host, port))
        return NodeHealth(node_id=0, name="", status="up", check="tcp", message="Port reachable")
    monkeypatch.setattr(health, "_tcp_check", tcp)
    monkeypatch.setattr(health, "ssh_command", lambda *args, **kw: pytest.fail("MikroTik must not execute SSH commands"))
    result = health.check_node(node)
    assert calls == [(node.host, 22)]
    assert (result.node_id, result.check, result.status) == (5, "tcp", "up")


def test_ssh_timeout_returns_failure_without_mutation(monkeypatch):
    node = Node(id=1, name="NL", role=NodeRole.amnezia_exit, host="192.0.2.1", ssh_user="test", ssh_port=22)
    def timeout(node, command, timeout):
        assert command == "printf ok"
        raise subprocess.TimeoutExpired("ssh", timeout)
    monkeypatch.setattr(health, "ssh_command", timeout)
    result = health.check_node(node)
    assert result.status == "down"
    assert result.check == "ssh"
