import React, { useState } from "react";
import EvidenceRefCard from "./EvidenceRefCard";

interface JuliaMessageProps {
  role: "julia" | "tony";
  text: string;
  evidenceRefs?: string[];
  renderedEvidenceLinks?: string[];
  confidence?: number;
  limitations?: string[];
  status?: string;
}

export const JuliaMessage: React.FC<JuliaMessageProps> = ({
  role,
  text,
  evidenceRefs = [],
  renderedEvidenceLinks = [],
  confidence,
  limitations = [],
  status,
}) => {
  const [showDetails, setShowDetails] = useState(false);
  const isJulia = role === "julia";
  const isShadow = status === "shadow";

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: isJulia ? "flex-start" : "flex-end",
        marginBottom: 10,
      }}
    >
      {/* Label */}
      <div
        style={{
          fontSize: 10,
          color: isJulia ? "#5a7a8a" : "#dd6b20",
          marginBottom: 2,
          paddingLeft: isJulia ? 4 : 0,
          paddingRight: isJulia ? 0 : 4,
        }}
      >
        {isJulia ? (
          <>
            Julia {isShadow && "(Shadow分析)"}
          </>
        ) : (
          "Tony"
        )}
      </div>

      {/* Bubble */}
      <div
        style={{
          maxWidth: "85%",
          padding: "8px 12px",
          borderRadius: isJulia ? "4px 12px 12px 12px" : "12px 4px 12px 12px",
          background: isJulia ? "#162230" : "#1a2a1a",
          border: `1px solid ${isJulia ? "#243040" : "#2a4a2a"}`,
          color: "#c8d6e5",
          fontSize: 13,
          lineHeight: 1.6,
          wordBreak: "break-word",
        }}
      >
        <div>{text}</div>

        {/* Evidence Refs */}
        {evidenceRefs.length > 0 && (
          <div style={{ marginTop: 8, display: "flex", flexWrap: "wrap", gap: 4 }}>
            {renderedEvidenceLinks.map((link, i) => (
              <EvidenceRefCard
                key={i}
                label={link.replace("EvidenceRef: ", "")}
                source={evidenceRefs[i] || undefined}
              />
            ))}
          </div>
        )}

        {/* Details toggle */}
        {(confidence !== undefined || limitations.length > 0) && (
          <div style={{ marginTop: 6 }}>
            <button
              onClick={() => setShowDetails(!showDetails)}
              style={{
                fontSize: 10,
                padding: "1px 6px",
                background: "transparent",
                border: "1px solid #3a5060",
                borderRadius: 3,
                color: "#5a7a8a",
                cursor: "pointer",
              }}
            >
              {showDetails ? "收起详情" : "详情"}
            </button>
            {showDetails && (
              <div
                style={{
                  marginTop: 4,
                  fontSize: 10,
                  color: "#5a7a8a",
                  lineHeight: 1.5,
                }}
              >
                {confidence !== undefined && (
                  <div>
                    置信度: {(confidence * 100).toFixed(0)}%
                  </div>
                )}
                {limitations.length > 0 && (
                  <div style={{ marginTop: 2 }}>
                    限制:
                    {limitations.map((lim, i) => (
                      <div key={i} style={{ paddingLeft: 8 }}>
                        · {lim}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
};

export default JuliaMessage;
