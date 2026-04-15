interface Strategy {
  strategy_id: string;
  strategy_name: string;
  description?: string;
  is_active?: boolean;
}

interface StrategySelectorProps {
  strategies: Strategy[];
  selectedStrategyId: string | null;
  onStrategySelect: (strategyId: string) => void;
}

export function StrategySelector({
  strategies,
  selectedStrategyId,
  onStrategySelect,
}: StrategySelectorProps) {
  const selected = strategies.find((s) => s.strategy_id === selectedStrategyId);

  return (
    <div className="screener-form-stack">
      <select
        value={selectedStrategyId ?? ''}
        onChange={(e) => onStrategySelect(e.target.value)}
        className="screener-input"
      >
        <option value="" disabled>
          请选择选股策略
        </option>
        {strategies.map((s) => (
          <option key={s.strategy_id} value={s.strategy_id}>
            {s.strategy_name}
          </option>
        ))}
      </select>

      {selectedStrategyId && (
        <div className="workspace-card screener-inline-note-card">
          <p className="workspace-note">{selected?.description || '暂无描述'}</p>
        </div>
      )}
    </div>
  );
}
