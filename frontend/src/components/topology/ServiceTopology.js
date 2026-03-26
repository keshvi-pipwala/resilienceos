import React, { useEffect, useRef, useState } from "react";
import * as d3 from "d3";

const NODES = [
  { id: "api-gateway", label: "API Gateway", x: 400, y: 80 },
  { id: "user-service", label: "User Service", x: 150, y: 260 },
  { id: "product-service", label: "Product Service", x: 400, y: 260 },
  { id: "order-service", label: "Order Service", x: 650, y: 260 },
  { id: "notification-service", label: "Notification", x: 275, y: 430 },
];

const LINKS = [
  { source: "api-gateway", target: "user-service" },
  { source: "api-gateway", target: "product-service" },
  { source: "api-gateway", target: "order-service" },
  { source: "order-service", target: "user-service" },
  { source: "order-service", target: "product-service" },
  { source: "product-service", target: "notification-service" },
  { source: "order-service", target: "notification-service" },
];

function statusColor(status, errorRate) {
  if (!status || status === "unknown" || status === "unreachable") return "#4a5568";
  if (status === "unhealthy" || errorRate > 0.5) return "#ef4444";
  if (status === "degraded" || errorRate > 0.1) return "#f59e0b";
  return "#22c55e";
}

export default function ServiceTopology({ health, chaosActive, onNodeClick }) {
  const svgRef = useRef(null);
  const [tooltip, setTooltip] = useState(null);

  useEffect(() => {
    const svg = d3.select(svgRef.current);
    svg.selectAll("*").remove();

    const width = 800;
    const height = 520;

    svg
      .attr("viewBox", `0 0 ${width} ${height}`)
      .attr("preserveAspectRatio", "xMidYMid meet");

    // Defs: arrowhead marker
    const defs = svg.append("defs");
    const marker = defs
      .append("marker")
      .attr("id", "arrow")
      .attr("viewBox", "0 -5 10 10")
      .attr("refX", 28)
      .attr("refY", 0)
      .attr("markerWidth", 6)
      .attr("markerHeight", 6)
      .attr("orient", "auto");
    marker.append("path").attr("d", "M0,-5L10,0L0,5").attr("fill", "#2a4a7a");

    // Build node position map
    const nodeMap = Object.fromEntries(NODES.map((n) => [n.id, n]));

    // Draw links
    LINKS.forEach((link) => {
      const src = nodeMap[link.source];
      const tgt = nodeMap[link.target];
      if (!src || !tgt) return;

      const srcHealth = health[link.source] || {};
      const tgtHealth = health[link.target] || {};
      const linkStress = Math.max(
        srcHealth.error_rate || 0,
        tgtHealth.error_rate || 0
      );
      const strokeColor =
        linkStress > 0.5 ? "#ef444460" :
        linkStress > 0.1 ? "#f59e0b50" :
        "#3b9eff25";
      const strokeWidth = linkStress > 0.1 ? 2.5 : 1.5;

      const g = svg.append("g");

      g.append("line")
        .attr("x1", src.x)
        .attr("y1", src.y)
        .attr("x2", tgt.x)
        .attr("y2", tgt.y)
        .attr("stroke", strokeColor)
        .attr("stroke-width", strokeWidth)
        .attr("marker-end", "url(#arrow)");

      // Animated flow dot when traffic is active
      const totalRequests =
        (srcHealth.request_count || 0) + (tgtHealth.request_count || 0);
      if (totalRequests > 0) {
        const dot = g.append("circle")
          .attr("r", 3)
          .attr("fill", linkStress > 0.1 ? "#f59e0b" : "#3b9eff")
          .attr("opacity", 0.8);

        function animateDot() {
          dot
            .attr("cx", src.x)
            .attr("cy", src.y)
            .transition()
            .duration(1500 + Math.random() * 1000)
            .ease(d3.easeLinear)
            .attr("cx", tgt.x)
            .attr("cy", tgt.y)
            .on("end", animateDot);
        }
        setTimeout(animateDot, Math.random() * 1500);
      }
    });

    // Draw nodes
    NODES.forEach((node) => {
      const nodeHealth = health[node.id] || {};
      const color = statusColor(nodeHealth.status, nodeHealth.error_rate || 0);
      const isChaos = chaosActive && chaosActive[node.id];

      const g = svg
        .append("g")
        .attr("transform", `translate(${node.x},${node.y})`)
        .attr("cursor", "pointer")
        .on("click", () => onNodeClick && onNodeClick(node.id))
        .on("mouseenter", (event) => {
          setTooltip({
            x: node.x,
            y: node.y,
            service: node.id,
            health: nodeHealth,
          });
        })
        .on("mouseleave", () => setTooltip(null));

      // Chaos pulse ring
      if (isChaos) {
        g.append("circle")
          .attr("r", 32)
          .attr("fill", "none")
          .attr("stroke", "#ef4444")
          .attr("stroke-width", 1.5)
          .attr("opacity", 0.6)
          .style("animation", "ping-slow 1.5s ease-out infinite");
      }

      // Outer glow ring
      g.append("circle")
        .attr("r", 28)
        .attr("fill", color + "15")
        .attr("stroke", color + "50")
        .attr("stroke-width", 1);

      // Main node circle
      g.append("circle")
        .attr("r", 22)
        .attr("fill", "#0a1628")
        .attr("stroke", color)
        .attr("stroke-width", 2.5);

      // Status indicator dot
      g.append("circle")
        .attr("r", 5)
        .attr("cx", 15)
        .attr("cy", -15)
        .attr("fill", color)
        .attr("stroke", "#020408")
        .attr("stroke-width", 1.5);

      // Service icon text
      const icon = {
        "api-gateway": "GW",
        "user-service": "USR",
        "product-service": "PRD",
        "order-service": "ORD",
        "notification-service": "NTF",
      }[node.id] || "SVC";

      g.append("text")
        .attr("text-anchor", "middle")
        .attr("dy", "0.35em")
        .attr("fill", color)
        .attr("font-size", "10px")
        .attr("font-family", "'JetBrains Mono', monospace")
        .attr("font-weight", "600")
        .text(icon);

      // Label below node
      g.append("text")
        .attr("text-anchor", "middle")
        .attr("dy", "42px")
        .attr("fill", "#94a3b8")
        .attr("font-size", "11px")
        .attr("font-family", "Inter, sans-serif")
        .text(node.label);

      // Error rate badge if degraded
      if ((nodeHealth.error_rate || 0) > 0.05) {
        g.append("rect")
          .attr("x", -22)
          .attr("y", -42)
          .attr("width", 44)
          .attr("height", 16)
          .attr("rx", 4)
          .attr("fill", "#7f1d1d90");
        g.append("text")
          .attr("text-anchor", "middle")
          .attr("dy", "-30px")
          .attr("fill", "#ef4444")
          .attr("font-size", "9px")
          .attr("font-family", "'JetBrains Mono', monospace")
          .text(`${((nodeHealth.error_rate || 0) * 100).toFixed(0)}% err`);
      }
    });

  }, [health, chaosActive, onNodeClick]);

  return (
    <div className="relative w-full">
      <svg
        ref={svgRef}
        className="w-full"
        style={{ height: 520, maxHeight: 520 }}
      />
      {tooltip && (
        <div
          className="absolute z-10 pointer-events-none bg-navy-800 border border-navy-600 rounded-lg p-3 text-xs font-mono shadow-xl"
          style={{
            left: `${(tooltip.x / 800) * 100}%`,
            top: tooltip.y - 80,
            transform: "translateX(-50%)",
            minWidth: 180,
          }}
        >
          <div className="text-electric-400 font-semibold mb-1">{tooltip.service}</div>
          <div className="text-slate-400">
            Status: <span className={
              tooltip.health.status === "healthy" ? "text-success" :
              tooltip.health.status === "degraded" ? "text-warning" :
              "text-danger"
            }>{tooltip.health.status || "unknown"}</span>
          </div>
          <div className="text-slate-400">
            Error rate: <span className="text-white">{((tooltip.health.error_rate || 0) * 100).toFixed(1)}%</span>
          </div>
          <div className="text-slate-400">
            Avg latency: <span className="text-white">{(tooltip.health.avg_latency_ms || 0).toFixed(0)}ms</span>
          </div>
          <div className="text-slate-400">
            Requests: <span className="text-white">{tooltip.health.request_count || 0}</span>
          </div>
        </div>
      )}
    </div>
  );
}
