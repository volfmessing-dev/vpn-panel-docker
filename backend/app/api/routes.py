from datetime import datetime, timezone
import re
from fastapi import APIRouter, Depends, HTTPException, Response, status
import qrcode
import qrcode.image.svg
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.node import Node
from app.models.routing_policy import RoutingPolicy, RoutingPolicySource, RoutingPolicyTarget
from app.models.tunnel import Tunnel, TunnelType
from app.models.vpn_user import VpnUser
from app.schemas.node import NodeCreate, NodeCreateResult, NodeRead, NodeUpdate
from app.schemas.routing_policy import RoutingPolicyApplyResult, RoutingPolicyPreview, RoutingPolicyRead, RoutingPolicySnapshot, RoutingPolicyUpdate
from app.schemas.health import NodeHealth
from app.schemas.facts import NodeFacts
from app.schemas.topology import Topology
from app.schemas.tunnel import AmneziaWGApplyResult, TunnelApplyResult, TunnelCreate, TunnelPreview, TunnelRead, TunnelUpdate
from app.schemas.cloud_tunnel import CloudTunnelSnapshot
from app.schemas.vpn_user import VpnBypassDomainsUpdate, VpnUserApplyResult, VpnUserConfig, VpnUserCreate, VpnUserRead, VpnUserUpdate
from app.services.deployment.topology import build_topology
from app.services.deployment.tunnel_allocator import create_ru_cloud_uplink
from app.services.deployment.facts import collect_node_facts
from app.services.deployment.health import check_node
from app.services.wireguard.tunnel_preview import build_amneziawg_preview, build_wireguard_preview
from app.services.wireguard.apply import apply_ru_cloud_tunnel, ensure_tunnel_keys
from app.services.wireguard.amnezia_apply import apply_amneziawg_tunnel, ensure_exit_forwarding
from app.services.wireguard.active import collect_active_cloud_tunnels
from app.services.wireguard.generator import build_config_preview
from app.services.wireguard.remove import stop_removed_tunnel_on_ru_cloud
from app.services.wireguard.routing_policy import routing_policy_previews, routing_policy_snapshot, update_routing_policy
from app.services.wireguard.users import (
    apply_vpn_users,
    build_user_config,
    collect_bypass_status,
    create_vpn_user,
    list_vpn_users_with_handshakes,
    update_bypass_domains,
)

router = APIRouter()


@router.get("/nodes", response_model=list[NodeRead])
def list_nodes(db: Session = Depends(get_db)) -> list[Node]:
    return list(db.scalars(select(Node).order_by(Node.id)).all())


@router.post("/nodes", response_model=NodeCreateResult, status_code=status.HTTP_201_CREATED)
def create_node(payload: NodeCreate, db: Session = Depends(get_db)) -> NodeCreateResult:
    data = payload.model_dump()
    uplink_type = data.pop("uplink_type")
    node = Node(**data)
    db.add(node)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Node name already exists") from exc
    db.refresh(node)
    created_tunnel = None
    apply_result = None
    apply_error = None
    if uplink_type != "none":
        try:
            created_tunnel = create_ru_cloud_uplink(node, TunnelType(uplink_type), db)
        except (IntegrityError, ValueError) as exc:
            db.rollback()
            db.delete(node)
            db.commit()
            status_code = 409 if isinstance(exc, IntegrityError) else 400
            raise HTTPException(status_code=status_code, detail=str(exc)) from exc
        if created_tunnel.type == TunnelType.amneziawg:
            source = db.get(Node, created_tunnel.source_node_id)
            target = db.get(Node, created_tunnel.target_node_id)
            if source and target:
                try:
                    apply_result = apply_amneziawg_tunnel(created_tunnel, source, target, db)
                    if apply_result.status == "failed":
                        apply_error = apply_result.message
                except (FileNotFoundError, ValueError) as exc:
                    apply_error = str(exc)
    return NodeCreateResult(node=NodeRead.model_validate(node), created_tunnel=created_tunnel, apply_result=apply_result, apply_error=apply_error)


@router.put("/nodes/{node_id}", response_model=NodeRead)
def update_node(node_id: int, payload: NodeUpdate, db: Session = Depends(get_db)) -> Node:
    node = db.get(Node, node_id)
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")

    for key, value in payload.model_dump().items():
        setattr(node, key, value)

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Node name already exists") from exc
    db.refresh(node)
    return node


@router.delete("/nodes/{node_id}")
def delete_node(node_id: int, db: Session = Depends(get_db)) -> dict[str, object]:
    node = db.get(Node, node_id)
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")
    if node.role == "ru_cloud":
        raise HTTPException(status_code=400, detail="RU_Cloud node cannot be deleted")

    ru_cloud = _ru_cloud_node(db)
    related_tunnels = list(
        db.scalars(
            select(Tunnel)
            .where(or_(Tunnel.source_node_id == node_id, Tunnel.target_node_id == node_id))
            .order_by(Tunnel.id)
        ).all()
    )

    cleanup_errors = [
        error
        for tunnel in related_tunnels
        if (error := stop_removed_tunnel_on_ru_cloud(ru_cloud, tunnel, node))
    ]
    if cleanup_errors:
        raise HTTPException(status_code=502, detail="; ".join(cleanup_errors))

    deleted_tunnel_ids = [tunnel.id for tunnel in related_tunnels]
    for tunnel in related_tunnels:
        db.delete(tunnel)
    db.delete(node)
    db.commit()

    reapplied_tunnels = []
    for tunnel in db.scalars(select(Tunnel).where(Tunnel.type == TunnelType.wireguard, Tunnel.enabled.is_(True)).order_by(Tunnel.id)):
        source = db.get(Node, tunnel.source_node_id)
        target = db.get(Node, tunnel.target_node_id)
        if source and target and target.role == "ru_cloud":
            result = apply_ru_cloud_tunnel(tunnel, source, target, db)
            if result.status == "failed":
                raise HTTPException(status_code=502, detail=result.message)
            reapplied_tunnels.append(tunnel.id)

    users_result = apply_vpn_users(ru_cloud, db)
    if users_result.status == "failed":
        raise HTTPException(status_code=502, detail=users_result.message)

    return {
        "deleted_node_id": node_id,
        "deleted_tunnel_ids": deleted_tunnel_ids,
        "reapplied_tunnel_ids": reapplied_tunnels,
        "applied_users": users_result.applied_users,
    }


def _archived_node(node: Node) -> bool:
    return bool(re.match(r"^Archived(_|$)", node.name, re.IGNORECASE))


def _checkable_node(node_id: int, db: Session) -> Node:
    node = db.get(Node, node_id)
    if node is None:
        raise HTTPException(status_code=404, detail="Node not found")
    if _archived_node(node):
        raise HTTPException(status_code=409, detail="Archived node checks are disabled")
    return node


@router.get("/nodes/health", response_model=list[NodeHealth])
def nodes_health(db: Session = Depends(get_db)):
    nodes = list(db.scalars(select(Node).order_by(Node.id)).all())
    return [_health_result(node) for node in nodes if not _archived_node(node)]


@router.get("/nodes/facts", response_model=list[NodeFacts])
def nodes_facts(db: Session = Depends(get_db)):
    nodes = list(db.scalars(select(Node).order_by(Node.id)).all())
    return [_facts_result(node) for node in nodes if not _archived_node(node)]


def _health_result(node: Node) -> NodeHealth:
    result = check_node(node)
    result.checked_at = datetime.now(timezone.utc)
    return result


def _facts_result(node: Node) -> NodeFacts:
    result = collect_node_facts(node)
    result.checked_at = datetime.now(timezone.utc)
    return result


@router.get("/nodes/{node_id}/health", response_model=NodeHealth)
def node_health(node_id: int, db: Session = Depends(get_db)) -> NodeHealth:
    return _health_result(_checkable_node(node_id, db))


@router.get("/nodes/{node_id}/facts", response_model=NodeFacts)
def node_facts(node_id: int, db: Session = Depends(get_db)) -> NodeFacts:
    return _facts_result(_checkable_node(node_id, db))


@router.get("/cloud/tunnels/active", response_model=CloudTunnelSnapshot)
def active_cloud_tunnels(db: Session = Depends(get_db)) -> CloudTunnelSnapshot:
    node = db.scalar(select(Node).where(Node.role == "ru_cloud").order_by(Node.id))
    if not node:
        raise HTTPException(status_code=404, detail="RU_Cloud node not found")
    return collect_active_cloud_tunnels(node)


@router.get("/routing-policies", response_model=RoutingPolicySnapshot)
def list_routing_policies(db: Session = Depends(get_db)) -> RoutingPolicySnapshot:
    return routing_policy_snapshot(db)


@router.get("/routing-policies/preview", response_model=list[RoutingPolicyPreview])
def preview_routing_policies(db: Session = Depends(get_db)) -> list[RoutingPolicyPreview]:
    return routing_policy_previews(db)


@router.post("/routing-policies/apply", response_model=RoutingPolicyApplyResult)
def apply_routing_policies(db: Session = Depends(get_db)) -> RoutingPolicyApplyResult:
    ru_cloud = _ru_cloud_node(db)
    warnings = [warning for preview in routing_policy_previews(db) for warning in preview.warnings]
    if warnings:
        raise HTTPException(status_code=400, detail="; ".join(warnings))

    reapplied_tunnels: list[int] = []
    selected_exit_tunnel_ids = {
        policy.target_tunnel_id
        for policy in db.scalars(select(RoutingPolicy).where(RoutingPolicy.target == RoutingPolicyTarget.tunnel, RoutingPolicy.enabled.is_(True))).all()
        if policy.target_tunnel_id is not None
    }
    for tunnel_id in sorted(selected_exit_tunnel_ids):
        tunnel = db.get(Tunnel, tunnel_id)
        if not tunnel or tunnel.type != TunnelType.amneziawg:
            continue
        exit_node = db.get(Node, tunnel.target_node_id)
        if not exit_node:
            raise HTTPException(status_code=400, detail=f"Exit node for tunnel {tunnel.id} not found")
        try:
            ensure_exit_forwarding(tunnel, exit_node)
        except ValueError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    for tunnel in db.scalars(select(Tunnel).where(Tunnel.type == TunnelType.wireguard, Tunnel.enabled.is_(True)).order_by(Tunnel.id)):
        source = db.get(Node, tunnel.source_node_id)
        target = db.get(Node, tunnel.target_node_id)
        if source and target and target.id == ru_cloud.id:
            result = apply_ru_cloud_tunnel(tunnel, source, target, db)
            if result.status == "failed":
                raise HTTPException(status_code=502, detail=result.message)
            reapplied_tunnels.append(tunnel.id)

    users_result = apply_vpn_users(ru_cloud, db)
    if users_result.status == "failed":
        raise HTTPException(status_code=502, detail=users_result.message)

    return RoutingPolicyApplyResult(
        status="applied",
        message="Routing policies applied to RU_Cloud",
        applied_users=users_result.applied_users,
        reapplied_tunnel_ids=reapplied_tunnels,
        warnings=[],
    )


@router.put("/routing-policies/{source}", response_model=RoutingPolicyRead)
def update_policy(source: RoutingPolicySource, payload: RoutingPolicyUpdate, db: Session = Depends(get_db)) -> RoutingPolicyRead:
    try:
        policy = update_routing_policy(
            source=source,
            target=payload.target,
            target_tunnel_id=payload.target_tunnel_id,
            direct_interface=payload.direct_interface,
            enabled=payload.enabled,
            db=db,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return next(item for item in routing_policy_snapshot(db).policies if item.id == policy.id)


@router.get("/users", response_model=list[VpnUserRead])
def list_users(db: Session = Depends(get_db)) -> list[VpnUserRead]:
    return list_vpn_users_with_handshakes(_ru_cloud_node(db), db)


@router.post("/users", response_model=VpnUserRead, status_code=status.HTTP_201_CREATED)
def create_user(payload: VpnUserCreate, db: Session = Depends(get_db)) -> VpnUser:
    try:
        user = create_vpn_user(payload.name, payload.enabled, db)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="User name or IP already exists") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return user


@router.put("/users/{user_id}", response_model=VpnUserRead)
def update_user(user_id: int, payload: VpnUserUpdate, db: Session = Depends(get_db)) -> VpnUser:
    user = db.get(VpnUser, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.name = payload.name
    user.enabled = payload.enabled
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="User name already exists") from exc
    db.refresh(user)
    return user


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(user_id: int, db: Session = Depends(get_db)) -> None:
    user = db.get(VpnUser, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    db.delete(user)
    db.commit()
    ru_cloud = _ru_cloud_node(db)
    apply_vpn_users(ru_cloud, db)


@router.post("/users/apply", response_model=VpnUserApplyResult)
def apply_users(db: Session = Depends(get_db)) -> VpnUserApplyResult:
    return apply_vpn_users(_ru_cloud_node(db), db)


@router.get("/users/bypass")
def users_bypass(db: Session = Depends(get_db)) -> dict[str, object]:
    return collect_bypass_status(_ru_cloud_node(db))


@router.post("/users/bypass/refresh", response_model=VpnUserApplyResult)
def refresh_users_bypass(db: Session = Depends(get_db)) -> VpnUserApplyResult:
    return apply_vpn_users(_ru_cloud_node(db), db)


@router.put("/users/bypass/domains")
def update_users_bypass_domains(payload: VpnBypassDomainsUpdate, db: Session = Depends(get_db)) -> dict[str, list[str]]:
    try:
        domains = update_bypass_domains(payload.domains)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    result = apply_vpn_users(_ru_cloud_node(db), db)
    if result.status == "failed":
        raise HTTPException(status_code=502, detail=result.message)
    return {"domains": domains}


@router.get("/users/{user_id}/config", response_model=VpnUserConfig)
def user_config(user_id: int, db: Session = Depends(get_db)) -> VpnUserConfig:
    user = db.get(VpnUser, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    try:
        return build_user_config(user, _ru_cloud_node(db))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/users/{user_id}/download")
def user_config_download(user_id: int, db: Session = Depends(get_db)) -> Response:
    payload = user_config(user_id, db)
    return Response(
        content=payload.config,
        media_type="application/x-wireguard-profile",
        headers={"Content-Disposition": f'attachment; filename="{payload.filename}"'},
    )


@router.get("/users/{user_id}/qr")
def user_config_qr(user_id: int, db: Session = Depends(get_db)) -> Response:
    payload = user_config(user_id, db)
    factory = qrcode.image.svg.SvgPathImage
    image = qrcode.make(payload.config, image_factory=factory)
    return Response(content=image.to_string().decode(), media_type="image/svg+xml")


@router.get("/tunnels", response_model=list[TunnelRead])
def list_tunnels(db: Session = Depends(get_db)) -> list[Tunnel]:
    return list(db.scalars(select(Tunnel).order_by(Tunnel.id)).all())


@router.post("/tunnels", response_model=TunnelRead, status_code=status.HTTP_201_CREATED)
def create_tunnel(payload: TunnelCreate, db: Session = Depends(get_db)) -> Tunnel:
    source = db.get(Node, payload.source_node_id)
    target = db.get(Node, payload.target_node_id)
    if not source or not target:
        raise HTTPException(status_code=404, detail="Source or target node not found")

    tunnel = Tunnel(**payload.model_dump())
    db.add(tunnel)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Tunnel name already exists") from exc
    db.refresh(tunnel)
    return tunnel


@router.put("/tunnels/{tunnel_id}", response_model=TunnelRead)
def update_tunnel(tunnel_id: int, payload: TunnelUpdate, db: Session = Depends(get_db)) -> Tunnel:
    tunnel = db.get(Tunnel, tunnel_id)
    if not tunnel:
        raise HTTPException(status_code=404, detail="Tunnel not found")

    source = db.get(Node, payload.source_node_id)
    target = db.get(Node, payload.target_node_id)
    if not source or not target:
        raise HTTPException(status_code=404, detail="Source or target node not found")

    for key, value in payload.model_dump().items():
        setattr(tunnel, key, value)

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Tunnel name already exists") from exc
    db.refresh(tunnel)
    return tunnel


@router.delete("/tunnels/{tunnel_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_tunnel(tunnel_id: int, db: Session = Depends(get_db)) -> None:
    tunnel = db.get(Tunnel, tunnel_id)
    if not tunnel:
        raise HTTPException(status_code=404, detail="Tunnel not found")
    db.delete(tunnel)
    db.commit()


@router.get("/tunnels/{tunnel_id}/preview", response_model=TunnelPreview)
def tunnel_preview(tunnel_id: int, db: Session = Depends(get_db)) -> TunnelPreview:
    tunnel = db.get(Tunnel, tunnel_id)
    if not tunnel:
        raise HTTPException(status_code=404, detail="Tunnel not found")
    source = db.get(Node, tunnel.source_node_id)
    target = db.get(Node, tunnel.target_node_id)
    if not source or not target:
        raise HTTPException(status_code=404, detail="Source or target node not found")
    try:
        if tunnel.type == TunnelType.wireguard:
            return build_wireguard_preview(tunnel, source, target)
        if tunnel.type == TunnelType.amneziawg:
            return build_amneziawg_preview(tunnel, source, target)
        raise HTTPException(status_code=400, detail="Unsupported tunnel type")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/tunnels/{tunnel_id}/keys", response_model=TunnelRead)
def tunnel_keys(tunnel_id: int, db: Session = Depends(get_db)) -> Tunnel:
    tunnel = db.get(Tunnel, tunnel_id)
    if not tunnel:
        raise HTTPException(status_code=404, detail="Tunnel not found")
    return ensure_tunnel_keys(tunnel, db)


@router.post("/tunnels/{tunnel_id}/apply/ru-cloud", response_model=TunnelApplyResult)
def apply_tunnel_ru_cloud(tunnel_id: int, db: Session = Depends(get_db)) -> TunnelApplyResult:
    tunnel = db.get(Tunnel, tunnel_id)
    if not tunnel:
        raise HTTPException(status_code=404, detail="Tunnel not found")
    source = db.get(Node, tunnel.source_node_id)
    target = db.get(Node, tunnel.target_node_id)
    if not source or not target:
        raise HTTPException(status_code=404, detail="Source or target node not found")
    if tunnel.type != TunnelType.wireguard:
        raise HTTPException(status_code=400, detail="Only WireGuard apply is implemented")
    try:
        return apply_ru_cloud_tunnel(tunnel, source, target, db)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/tunnels/{tunnel_id}/apply/awg", response_model=AmneziaWGApplyResult)
def apply_tunnel_awg(tunnel_id: int, db: Session = Depends(get_db)) -> AmneziaWGApplyResult:
    tunnel = db.get(Tunnel, tunnel_id)
    if not tunnel:
        raise HTTPException(status_code=404, detail="Tunnel not found")
    source = db.get(Node, tunnel.source_node_id)
    target = db.get(Node, tunnel.target_node_id)
    if not source or not target:
        raise HTTPException(status_code=404, detail="Source or target node not found")
    if tunnel.type != TunnelType.amneziawg:
        raise HTTPException(status_code=400, detail="Only AmneziaWG apply is implemented")
    if source.role != "ru_cloud" or target.role != "amnezia_exit":
        raise HTTPException(status_code=400, detail="AmneziaWG tunnel must be RU_Cloud -> Amnezia exit")
    try:
        result = apply_amneziawg_tunnel(tunnel, source, target, db)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if result.status == "failed":
        raise HTTPException(status_code=502, detail=result.message)
    return result


@router.get("/topology", response_model=Topology)
def topology(db: Session = Depends(get_db)) -> Topology:
    nodes = [NodeRead.model_validate(node) for node in db.scalars(select(Node).order_by(Node.id)).all()]
    return build_topology(nodes)


@router.get("/config/preview")
def config_preview(db: Session = Depends(get_db)) -> dict[str, str]:
    nodes = [NodeRead.model_validate(node) for node in db.scalars(select(Node).order_by(Node.id)).all()]
    return {"config": build_config_preview(nodes)}


def _ru_cloud_node(db: Session) -> Node:
    node = db.scalar(select(Node).where(Node.role == "ru_cloud").order_by(Node.id))
    if not node:
        raise HTTPException(status_code=404, detail="RU_Cloud node not found")
    return node
