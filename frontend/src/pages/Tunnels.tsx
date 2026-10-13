import { useEffect, useMemo, useState } from "react";
import { applyAmneziaWGTunnel, applyRuCloudTunnel, createTunnel, deleteTunnel, generateTunnelKeys, getTunnelPreview, getTunnels, updateTunnel } from "../api/client";
import type { AmneziaWGApplyResult, NodeRecord, TunnelApplyResult, TunnelPreview, TunnelRecord } from "../types/api";

interface Props {
  nodes: NodeRecord[];
}

export function Tunnels({ nodes }: Props) {
  const [tunnels, setTunnels] = useState<TunnelRecord[]>([]);
  const [preview, setPreview] = useState<TunnelPreview | null>(null);
  const [applyResult, setApplyResult] = useState<TunnelApplyResult | null>(null);
  const [awgApplyResult, setAwgApplyResult] = useState<AmneziaWGApplyResult | null>(null);
  const [name, setName] = useState("mikrotik-ru-cloud");
  const [sourceNodeId, setSourceNodeId] = useState<number>(0);
  const [targetNodeId, setTargetNodeId] = useState<number>(0);
  const [tunnelType, setTunnelType] = useState<"wireguard" | "amneziawg">("wireguard");
  const [tunnelCidr, setTunnelCidr] = useState("10.200.0.0/30");
  const [listenPort, setListenPort] = useState(51840);
  const [lanCidr, setLanCidr] = useState("192.168.50.0/24");
  const [enabled, setEnabled] = useState(true);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const sourceOptions = useMemo(() => nodes.filter((node) => node.role === "mikrotik"), [nodes]);
  const targetOptions = useMemo(() => nodes.filter((node) => node.role === "ru_cloud"), [nodes]);

  useEffect(() => {
    if (!sourceNodeId && sourceOptions[0]) setSourceNodeId(sourceOptions[0].id);
    if (!targetNodeId && targetOptions[0]) setTargetNodeId(targetOptions[0].id);
  }, [sourceNodeId, sourceOptions, targetNodeId, targetOptions]);

  async function refreshTunnels() {
    try {
      setTunnels(await getTunnels());
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load tunnels");
    }
  }

  useEffect(() => {
    refreshTunnels();
  }, []);

  async function addTunnel() {
    setBusy(true);
    try {
      const tunnel = await createTunnel({
        name,
        type: tunnelType,
        source_node_id: sourceNodeId,
        target_node_id: targetNodeId,
        tunnel_cidr: tunnelCidr,
        listen_port: listenPort,
        lan_cidr: lanCidr,
        enabled,
        source_public_key: null,
        target_public_key: null,
        applied_at: null
      });
      await refreshTunnels();
      setPreview(await getTunnelPreview(tunnel.id));
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create tunnel");
    } finally {
      setBusy(false);
    }
  }

  function startEdit(tunnel: TunnelRecord) {
    setEditingId(tunnel.id);
    setName(tunnel.name);
    setTunnelType(tunnel.type);
    setSourceNodeId(tunnel.source_node_id);
    setTargetNodeId(tunnel.target_node_id);
    setTunnelCidr(tunnel.tunnel_cidr);
    setListenPort(tunnel.listen_port);
    setLanCidr(tunnel.lan_cidr);
    setEnabled(tunnel.enabled);
    setApplyResult(null);
    setError(null);
  }

  function resetForm() {
    setEditingId(null);
    setName("mikrotik-ru-cloud");
    setTunnelType("wireguard");
    setTunnelCidr("10.200.0.0/30");
    setListenPort(51840);
    setLanCidr("192.168.50.0/24");
    setEnabled(true);
    if (sourceOptions[0]) setSourceNodeId(sourceOptions[0].id);
    if (targetOptions[0]) setTargetNodeId(targetOptions[0].id);
  }

  async function saveTunnel() {
    if (!editingId) return;
    setBusy(true);
    try {
      const tunnel = await updateTunnel(editingId, {
        name,
        type: tunnelType,
        source_node_id: sourceNodeId,
        target_node_id: targetNodeId,
        tunnel_cidr: tunnelCidr,
        listen_port: listenPort,
        lan_cidr: lanCidr,
        enabled,
        source_public_key: null,
        target_public_key: null,
        applied_at: null
      });
      setEditingId(null);
      await refreshTunnels();
      setPreview(await getTunnelPreview(tunnel.id));
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update tunnel");
    } finally {
      setBusy(false);
    }
  }

  async function removeTunnel(tunnel: TunnelRecord) {
    if (!window.confirm(`Delete tunnel ${tunnel.name}?`)) return;
    setBusy(true);
    try {
      await deleteTunnel(tunnel.id);
      if (preview?.tunnel_id === tunnel.id) setPreview(null);
      if (editingId === tunnel.id) setEditingId(null);
      await refreshTunnels();
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete tunnel");
    } finally {
      setBusy(false);
    }
  }

  async function createKeys(id: number) {
    setBusy(true);
    try {
      await generateTunnelKeys(id);
      await refreshTunnels();
      setPreview(await getTunnelPreview(id));
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to generate keys");
    } finally {
      setBusy(false);
    }
  }

  async function applyRuCloud(id: number) {
    setBusy(true);
    try {
      const result = await applyRuCloudTunnel(id);
      setApplyResult(result);
      setAwgApplyResult(null);
      await refreshTunnels();
      setPreview(await getTunnelPreview(id));
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to apply RU_Cloud");
    } finally {
      setBusy(false);
    }
  }

  async function applyAwg(id: number) {
    if (!window.confirm("Apply this AmneziaWG tunnel on RU_Cloud and exit host?")) return;
    setBusy(true);
    try {
      const result = await applyAmneziaWGTunnel(id);
      setAwgApplyResult(result);
      setApplyResult(null);
      await refreshTunnels();
      setPreview(await getTunnelPreview(id));
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to apply AmneziaWG");
    } finally {
      setBusy(false);
    }
  }

  async function showPreview(id: number) {
    setBusy(true);
    try {
      setPreview(await getTunnelPreview(id));
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to build preview");
    } finally {
      setBusy(false);
    }
  }

  function nodeName(id: number) {
    return nodes.find((node) => node.id === id)?.name ?? `node-${id}`;
  }

  return (
    <section className="split-layout">
      <div className="panel">
        <h3>{editingId ? `Edit tunnel #${editingId}` : "Create tunnel"}</h3>
        <div className="form-grid">
          <label>
            Name
            <input value={name} onChange={(event) => setName(event.target.value)} />
          </label>
          <label>
            Type
            <select value={tunnelType} onChange={(event) => setTunnelType(event.target.value as "wireguard" | "amneziawg")}>
              <option value="wireguard">WireGuard</option>
              <option value="amneziawg">AmneziaWG</option>
            </select>
          </label>
          <label>
            Source
            <select value={sourceNodeId} onChange={(event) => setSourceNodeId(Number(event.target.value))}>
              <option value={0}>Select MikroTik</option>
              {sourceOptions.map((node) => <option key={node.id} value={node.id}>{node.name}</option>)}
            </select>
          </label>
          <label>
            Target
            <select value={targetNodeId} onChange={(event) => setTargetNodeId(Number(event.target.value))}>
              <option value={0}>Select RU Cloud</option>
              {targetOptions.map((node) => <option key={node.id} value={node.id}>{node.name}</option>)}
            </select>
          </label>
          <label>
            Tunnel CIDR
            <input value={tunnelCidr} onChange={(event) => setTunnelCidr(event.target.value)} />
          </label>
          <label>
            Listen port
            <input type="number" value={listenPort} onChange={(event) => setListenPort(Number(event.target.value))} />
          </label>
          <label>
            MikroTik LAN CIDR
            <input value={lanCidr} onChange={(event) => setLanCidr(event.target.value)} />
          </label>
          <label className="checkbox-label">
            <input type="checkbox" checked={enabled} onChange={(event) => setEnabled(event.target.checked)} />
            Enabled
          </label>
          {editingId ? (
            <div className="button-row">
              <button className="primary-button" onClick={saveTunnel} disabled={busy || !sourceNodeId || !targetNodeId}>
                Save
              </button>
              <button className="secondary-button" onClick={resetForm} disabled={busy}>Cancel</button>
            </div>
          ) : (
            <button className="primary-button" onClick={addTunnel} disabled={busy || !sourceNodeId || !targetNodeId}>
              Create preview
            </button>
          )}
        </div>
      </div>

      <div className="panel">
        <h3>Tunnels</h3>
        {error ? <div className="alert">{error}</div> : null}
        <div className="node-list">
          {tunnels.map((tunnel) => (
            <article key={tunnel.id} className="node-row">
              <div className="node-row-main">
                <div>
                  <strong>{tunnel.name}</strong>
                  <span>{nodeName(tunnel.source_node_id)} {"->"} {nodeName(tunnel.target_node_id)}</span>
                  <small>
                    {tunnel.type} {tunnel.tunnel_cidr} UDP/{tunnel.listen_port} LAN {tunnel.lan_cidr}
                    {tunnel.enabled ? " enabled" : " disabled"}
                    {tunnel.applied_at ? ` applied ${tunnel.applied_at}` : ""}
                  </small>
                </div>
                <div className="button-row">
                  {editingId === tunnel.id ? <span className="status-pill">editing</span> : null}
                  <button className="text-button" onClick={() => showPreview(tunnel.id)} disabled={busy}>Preview</button>
                  <button className="text-button" onClick={() => startEdit(tunnel)} disabled={busy}>Edit</button>
                  <button className="text-button" onClick={() => createKeys(tunnel.id)} disabled={busy}>Keys</button>
                  {tunnel.type === "wireguard" ? (
                    <button className="text-button" onClick={() => applyRuCloud(tunnel.id)} disabled={busy}>Apply RU</button>
                  ) : (
                    <button className="text-button" onClick={() => applyAwg(tunnel.id)} disabled={busy}>Apply AWG</button>
                  )}
                  <button className="text-button danger" onClick={() => removeTunnel(tunnel)} disabled={busy}>Delete</button>
                </div>
              </div>
            </article>
          ))}
        </div>

        {preview ? (
          <div className="preview-stack">
            <h3>{preview.name}</h3>
            <div className="notes">
              {preview.notes.map((note) => <span key={note}>{note}</span>)}
            </div>
            {applyResult ? (
              <div className={`facts-error ${applyResult.status === "applied" ? "success" : ""}`}>
                {applyResult.status}: {applyResult.message} ({applyResult.ru_cloud_config_path})
              </div>
            ) : null}
            {awgApplyResult ? (
              <div className={`facts-error ${awgApplyResult.status === "applied" ? "success" : ""}`}>
                {awgApplyResult.status}: {awgApplyResult.message} ({awgApplyResult.interface_name}, exit {awgApplyResult.exit_egress_interface})
              </div>
            ) : null}
            <div className="gateway-grid">
              <div className="fact">
                <span>Tunnel network</span>
                <code>{preview.tunnel_network}</code>
              </div>
              <div className="fact">
                <span>{preview.type === "amneziawg" ? "AWG peer" : "MikroTik gateway"}</span>
                <code>{preview.gateway}</code>
              </div>
              <div className="fact">
                <span>{preview.type === "amneziawg" ? "Exit AWG IP" : "RU_Cloud WG IP"}</span>
                <code>{preview.target_tunnel_ip}</code>
              </div>
              <div className="fact">
                <span>{preview.type === "amneziawg" ? "RU_Cloud AWG IP" : "MikroTik WG IP"}</span>
                <code>{preview.source_tunnel_ip}</code>
              </div>
              <div className="fact">
                <span>{preview.type === "amneziawg" ? "Exit endpoint" : "RU endpoint"}</span>
                <code>{preview.endpoint}</code>
              </div>
              <div className="fact">
                <span>{preview.type === "amneziawg" ? "Interface" : "MikroTik allowed"}</span>
                <code>{preview.type === "amneziawg" ? preview.interface_name ?? "-" : preview.mikrotik_allowed_ips}</code>
              </div>
            </div>
            {preview.type === "wireguard" ? (
              <>
                <h4>MikroTik wg config</h4>
                <pre className="code-preview">{preview.mikrotik_config}</pre>
              </>
            ) : null}
            <h4>{preview.type === "amneziawg" ? `RU_Cloud AWG config ${preview.ru_cloud_config_path ?? ""}` : "RU_Cloud wg config"}</h4>
            <pre className="code-preview">{preview.ru_cloud_config}</pre>
            {preview.exit_config ? (
              <>
                <h4>Exit AWG config {preview.exit_config_path ?? ""}</h4>
                <pre className="code-preview">{preview.exit_config}</pre>
              </>
            ) : null}
            <h4>{preview.type === "amneziawg" ? "RU_Cloud commands" : "MikroTik commands"}</h4>
            <pre className="code-preview">{preview.type === "amneziawg" ? preview.ru_cloud_commands : preview.mikrotik_commands}</pre>
            {preview.exit_commands ? (
              <>
                <h4>Exit commands</h4>
                <pre className="code-preview">{preview.exit_commands}</pre>
              </>
            ) : null}
          </div>
        ) : null}
      </div>
    </section>
  );
}
