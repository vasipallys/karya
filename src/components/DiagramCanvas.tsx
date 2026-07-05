import { useMemo, useRef, useState } from "react";
import {
  Box, Check, ChevronDown, Database, Focus, Layers3, Maximize2,
  Link2, Minus, MousePointer2, Plus, Sparkles, SquarePlus, X,
} from "lucide-react";
import type { DiagramEdge, DiagramNode } from "../types";

interface Props {
  nodes: DiagramNode[];
  edges: DiagramEdge[];
  selectedId: string | null;
  onSelect: (node: DiagramNode | null) => void;
  onMoveNode: (id: string, dx: number, dy: number) => void;
  onRequestAdd: () => void;
  connectMode: boolean;
  connectFrom: string | null;
  onToggleConnect: () => void;
  onNodeActivate: (node: DiagramNode) => void;
}

const center = (node: DiagramNode) => ({
  x: node.x + node.width / 2,
  y: node.y + node.height / 2,
});

function edgePath(from: DiagramNode, to: DiagramNode) {
  const a = center(from);
  const b = center(to);
  const startX = a.x < b.x ? from.x + from.width : a.x > b.x ? from.x : a.x;
  const endX = a.x < b.x ? to.x : a.x > b.x ? to.x + to.width : b.x;
  const startY = a.x === b.x ? (a.y < b.y ? from.y + from.height : from.y) : a.y;
  const endY = a.x === b.x ? (a.y < b.y ? to.y : to.y + to.height) : b.y;
  const curve = Math.max(45, Math.abs(endX - startX) * 0.42);
  if (Math.abs(endX - startX) < 30) {
    const mid = (startY + endY) / 2;
    return `M ${startX} ${startY} C ${startX} ${mid}, ${endX} ${mid}, ${endX} ${endY}`;
  }
  return `M ${startX} ${startY} C ${startX + (endX > startX ? curve : -curve)} ${startY}, ${endX - (endX > startX ? curve : -curve)} ${endY}, ${endX} ${endY}`;
}

function ProgressBadge({ status, x, y }: { status: DiagramNode["status"]; x: number; y: number }) {
  const colors = { synced: "#52c995", modified: "#f0b45c", stale: "#ee7684" };
  return (
    <g transform={`translate(${x},${y})`}>
      <circle r="9" fill="#e9eff5" filter="url(#softSmall)" />
      <circle r="4" fill={colors[status]} />
    </g>
  );
}

function PersonNode({ node, active, onClick }: { node: DiagramNode; active: boolean; onClick: () => void }) {
  const cx = node.x + node.width / 2;
  return (
    <g data-node-id={node.id} className={`diagram-node person-node ${active ? "is-selected" : ""}`} onClick={onClick} tabIndex={0}>
      <title>{`${node.title}\n${node.description}\n${node.source.path}:${node.source.line}`}</title>
      <circle className="node-hit" cx={cx} cy={node.y + 50} r="48" />
      <circle className="actor-disc" cx={cx} cy={node.y + 50} r="41" filter="url(#softNode)" />
      <circle className="actor-head" cx={cx} cy={node.y + 36} r="11" />
      <path className="actor-body" d={`M ${cx - 22} ${node.y + 73} C ${cx - 20} ${node.y + 50}, ${cx + 20} ${node.y + 50}, ${cx + 22} ${node.y + 73}`} />
      <text className="node-title centered" x={cx} y={node.y + 116}>{node.title}</text>
      <text className="node-subtitle centered" x={cx} y={node.y + 135}>{node.subtitle}</text>
      <ProgressBadge status={node.status} x={cx + 39} y={node.y + 17} />
    </g>
  );
}

function CardNode({ node, active, onClick }: { node: DiagramNode; active: boolean; onClick: () => void }) {
  const isPrimary = node.kind === "system";
  const isDatabase = node.kind === "database";
  return (
    <g data-node-id={node.id} className={`diagram-node card-node ${active ? "is-selected" : ""}`} onClick={onClick} tabIndex={0}>
      <title>{`${node.title}\n${node.description}\n${node.source.path}:${node.source.line}`}</title>
      <rect className="node-hit" x={node.x - 8} y={node.y - 8} width={node.width + 16} height={node.height + 16} rx="25" />
      <rect className={`node-card ${isPrimary ? "primary" : ""}`} x={node.x} y={node.y} width={node.width} height={node.height} rx="22" filter="url(#softNode)" />
      {isPrimary && <path className="node-header" d={`M ${node.x + 22} ${node.y} H ${node.x + node.width - 22} Q ${node.x + node.width} ${node.y} ${node.x + node.width} ${node.y + 22} V ${node.y + 55} H ${node.x} V ${node.y + 22} Q ${node.x} ${node.y} ${node.x + 22} ${node.y}`} />}
      <g transform={`translate(${node.x + 22}, ${node.y + (isPrimary ? 81 : 27)})`}>
        <circle className={`node-icon-wrap ${isPrimary ? "primary" : ""}`} cx="15" cy="15" r="15" />
        {isDatabase ? (
          <Database className="svg-icon" x="7" y="7" width="16" height="16" />
        ) : isPrimary ? (
          <Sparkles className="svg-icon light" x="7" y="7" width="16" height="16" />
        ) : (
          <Box className="svg-icon" x="7" y="7" width="16" height="16" />
        )}
      </g>
      <text className={`node-title ${isPrimary ? "light" : ""}`} x={node.x + (isPrimary ? 20 : 62)} y={node.y + (isPrimary ? 35 : 34)}>{node.title}</text>
      <text className="node-subtitle" x={node.x + 22} y={node.y + (isPrimary ? 111 : 68)}>{node.subtitle}</text>
      <text className="node-description" x={node.x + 22} y={node.y + (isPrimary ? 134 : 90)}>
        {node.description.length > 37 ? `${node.description.slice(0, 37)}…` : node.description}
      </text>
      {node.technology && (
        <g transform={`translate(${node.x + 20},${node.y + node.height - 31})`}>
          <rect className="tech-pill" width={Math.min(node.technology.length * 6.2 + 24, node.width - 40)} height="19" rx="9.5" />
          <text className="tech-text" x="11" y="13">{node.technology}</text>
        </g>
      )}
      <ProgressBadge status={node.status} x={node.x + node.width - 20} y={node.y + 20} />
    </g>
  );
}

export default function DiagramCanvas({
  nodes, edges, selectedId, onSelect, onMoveNode, onRequestAdd,
  connectMode, connectFrom, onToggleConnect, onNodeActivate,
}: Props) {
  const [zoom, setZoom] = useState(0.92);
  const [pan, setPan] = useState({ x: 18, y: 9 });
  const [isPanning, setIsPanning] = useState(false);
  const pointer = useRef({ x: 0, y: 0 });
  const draggedNode = useRef<{ id: string; x: number; y: number } | null>(null);
  const nodeMap = useMemo(() => new Map(nodes.map((node) => [node.id, node])), [nodes]);

  const zoomBy = (delta: number) => setZoom((value) => Math.min(1.4, Math.max(0.58, value + delta)));
  const resetView = () => { setZoom(0.92); setPan({ x: 18, y: 9 }); };

  return (
    <section className="canvas-shell">
      <div className="canvas-head">
        <div className="breadcrumbs">
          <span>Karya platform</span><i>/</i><strong>System context</strong>
          <button className="crumb-menu" aria-label="Diagram menu"><ChevronDown size={14} /></button>
        </div>
        <div className="sync-indicator"><span><Check size={12} /></span> Synced with <code>main@8c41e2a</code></div>
      </div>

      <div className="canvas-stage">
        <div className="canvas-tools">
          <button className="tool-button active" title="Select"><MousePointer2 size={17} /></button>
          <button className="tool-button" title="Add node" onClick={onRequestAdd}><SquarePlus size={17} /></button>
          <button className={`tool-button ${connectMode ? "active" : ""}`} title="Connect nodes" onClick={onToggleConnect}><Link2 size={17} /></button>
          <button className="tool-button" title="Layers"><Layers3 size={17} /></button>
          <span />
          <button className="tool-button" title="Fit view" onClick={resetView}><Focus size={17} /></button>
        </div>
        {connectMode && (
          <div className="connect-banner">
            <Link2 size={14} />
            <span>{connectFrom ? "Now select the target node" : "Select the first node to connect"}</span>
            <button onClick={onToggleConnect} aria-label="Cancel connection"><X size={13} /></button>
          </div>
        )}
        <div className="zoom-tools">
          <button onClick={() => zoomBy(0.1)} aria-label="Zoom in"><Plus size={16} /></button>
          <strong>{Math.round(zoom * 100)}%</strong>
          <button onClick={() => zoomBy(-0.1)} aria-label="Zoom out"><Minus size={16} /></button>
          <button onClick={resetView} aria-label="Fit canvas"><Maximize2 size={15} /></button>
        </div>
        <svg
          id="architecture-canvas"
          className={`architecture-canvas ${isPanning ? "is-panning" : ""}`}
          viewBox="0 0 1040 650"
          role="img"
          aria-label="Karya system context architecture diagram"
          onWheel={(event) => {
            event.preventDefault();
            zoomBy(event.deltaY > 0 ? -0.05 : 0.05);
          }}
          onPointerDown={(event) => {
            const nodeElement = (event.target as SVGElement).closest<SVGGElement>(".diagram-node");
            if (nodeElement) {
              if (connectMode) return;
              const id = nodeElement.dataset.nodeId;
              const node = nodes.find((item) => item.id === id);
              if (id && node) {
                draggedNode.current = { id, x: event.clientX, y: event.clientY };
                onSelect(node);
                (event.currentTarget as SVGSVGElement).setPointerCapture(event.pointerId);
              }
              return;
            }
            pointer.current = { x: event.clientX - pan.x, y: event.clientY - pan.y };
            setIsPanning(true);
            (event.currentTarget as SVGSVGElement).setPointerCapture(event.pointerId);
            onSelect(null);
          }}
          onPointerMove={(event) => {
            if (draggedNode.current) {
              const bounds = event.currentTarget.getBoundingClientRect();
              const dx = (event.clientX - draggedNode.current.x) * (1040 / bounds.width) / zoom;
              const dy = (event.clientY - draggedNode.current.y) * (650 / bounds.height) / zoom;
              draggedNode.current.x = event.clientX;
              draggedNode.current.y = event.clientY;
              onMoveNode(draggedNode.current.id, dx, dy);
            } else if (isPanning) {
              setPan({ x: event.clientX - pointer.current.x, y: event.clientY - pointer.current.y });
            }
          }}
          onPointerUp={() => { setIsPanning(false); draggedNode.current = null; }}
        >
          <defs>
            <pattern id="dotGrid" width="28" height="28" patternUnits="userSpaceOnUse">
              <circle cx="2" cy="2" r="1.2" fill="#b6c5d4" opacity=".35" />
            </pattern>
            <filter id="softNode" x="-25%" y="-25%" width="150%" height="160%">
              <feDropShadow dx="7" dy="8" stdDeviation="7" floodColor="#a3b1c6" floodOpacity=".48" />
              <feDropShadow dx="-6" dy="-6" stdDeviation="6" floodColor="#ffffff" floodOpacity=".94" />
            </filter>
            <filter id="softSmall" x="-80%" y="-80%" width="260%" height="260%">
              <feDropShadow dx="2" dy="2" stdDeviation="2" floodColor="#a3b1c6" floodOpacity=".55" />
              <feDropShadow dx="-2" dy="-2" stdDeviation="2" floodColor="#fff" />
            </filter>
            <filter id="edgeShadow" x="-10%" y="-20%" width="120%" height="140%">
              <feDropShadow dx="1" dy="3" stdDeviation="2" floodColor="#8aa0b2" floodOpacity=".35" />
            </filter>
            <linearGradient id="primaryGradient" x1="0" x2="1">
              <stop stopColor="#4fc3f7" /><stop offset="1" stopColor="#29b6f6" />
            </linearGradient>
            <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
              <path d="M 0 0 L 10 5 L 0 10 z" fill="#7d96a4" />
            </marker>
          </defs>
          <rect width="1040" height="650" fill="url(#dotGrid)" />
          <g transform={`translate(${pan.x} ${pan.y}) scale(${zoom})`}>
            {edges.map((edge) => {
              const from = nodeMap.get(edge.from);
              const to = nodeMap.get(edge.to);
              if (!from || !to) return null;
              const a = center(from);
              const b = center(to);
              const midX = (a.x + b.x) / 2;
              const midY = (a.y + b.y) / 2 - 12;
              return (
                <g className="diagram-edge" key={edge.id}>
                  <path d={edgePath(from, to)} markerEnd="url(#arrow)" filter="url(#edgeShadow)" />
                  <g transform={`translate(${midX - 48},${midY - 10})`}>
                    <rect width="112" height="29" x="-8" y="-4" rx="12" filter="url(#softSmall)" />
                    <text className="edge-label" x="48" y="8">{edge.label.length > 22 ? `${edge.label.slice(0, 22)}…` : edge.label}</text>
                    <text x="48" y="19">{edge.protocol}</text>
                  </g>
                </g>
              );
            })}
            {nodes.map((node) => node.kind === "person"
              ? <PersonNode key={node.id} node={node} active={selectedId === node.id || connectFrom === node.id} onClick={() => onNodeActivate(node)} />
              : <CardNode key={node.id} node={node} active={selectedId === node.id || connectFrom === node.id} onClick={() => onNodeActivate(node)} />
            )}
          </g>
        </svg>
        <div className="canvas-legend">
          <span><i className="dot synced" /> In sync</span>
          <span><i className="dot modified" /> Modified</span>
          <span><i className="dot stale" /> Stale</span>
        </div>
      </div>
    </section>
  );
}
