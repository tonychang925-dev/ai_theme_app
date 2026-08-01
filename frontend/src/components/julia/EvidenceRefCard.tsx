import React, { useState } from "react";

interface EvidenceRefCardProps {
  label: string;
  description?: string;
  source?: string;
}

export const EvidenceRefCard: React.FC<EvidenceRefCardProps> = ({
  label,
  description,
  source,
}) => {
  const [expanded, setExpanded] = useState(false);

  return (
    <div
      onClick={() => setExpanded(!expanded)}
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 4,
        padding: "2px 8px",
        background: expanded ? "#1a3a2c" : "#162230",
        border: `1px solid ${expanded ? "#39ff14" : "#243040"}`,
        borderRadius: 4,
        cursor: "pointer",
        fontSize: 11,
        color: expanded ? "#39ff14" : "#66d9ef",
        transition: "all 0.15s ease",
        userSelect: "none",
      }}
      title={source || label}
    >
      <span style={{ fontSize: 10 }}>{expanded ? "▾" : "▸"}</span>
      <span>{label}</span>
      {expanded && description && (
        <span
          style={{
            display: "block",
            marginTop: 4,
            fontSize: 10,
            color: "#8da6b8",
            lineHeight: 1.4,
          }}
        >
          {description}
        </span>
      )}
      {expanded && source && (
        <span
          style={{
            display: "block",
            marginTop: 2,
            fontSize: 9,
            color: "#5a7a8a",
          }}
        >
          来源: {source}
        </span>
      )}
    </div>
  );
};

export default EvidenceRefCard;
