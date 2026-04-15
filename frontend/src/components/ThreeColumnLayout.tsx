import { ReactNode } from 'react';
import './ThreeColumnLayout.css';

interface ThreeColumnLayoutProps {
  /** 左栏内容（主题雷达） */
  leftPanel?: ReactNode;
  /** 中栏内容（AI事件流） */
  centerPanel?: ReactNode;
  /** 右栏内容（市场验证） */
  rightPanel?: ReactNode;
  /** 左栏宽度（默认280px） */
  leftWidth?: string;
  /** 右栏宽度（默认320px） */
  rightWidth?: string;
  /** 最小高度（默认100vh） */
  minHeight?: string;
  /** 是否显示面板边框 */
  showBorders?: boolean;
  /** 自定义CSS类名 */
  className?: string;
}

/**
 * 三栏"投研作战台"布局组件
 *
 * 提供响应式设计：桌面端三栏，平板端两栏，移动端单栏堆叠。
 * 遵循前端架构优化方案中的布局规范。
 */
export function ThreeColumnLayout({
  leftPanel,
  centerPanel,
  rightPanel,
  leftWidth = '280px',
  rightWidth = '320px',
  minHeight = '100vh',
  showBorders = false,
  className = '',
}: ThreeColumnLayoutProps) {
  const hasLeftPanel = !!leftPanel;
  const hasRightPanel = !!rightPanel;
  const hasCenterPanel = !!centerPanel;

  // 确定布局类型
  const layoutType = hasLeftPanel && hasCenterPanel && hasRightPanel
    ? 'three-column'
    : hasLeftPanel && hasCenterPanel
    ? 'two-column-left'
    : hasCenterPanel && hasRightPanel
    ? 'two-column-right'
    : 'single-column';

  return (
    <div
      className={`three-column-layout ${layoutType} ${showBorders ? 'with-borders' : ''} ${className}`}
      style={{ minHeight }}
      data-testid="three-column-layout"
    >
      {hasLeftPanel && (
        <aside
          className="three-column-layout-left"
          style={{ width: leftWidth, minWidth: leftWidth }}
          data-testid="left-panel"
        >
          <div className="panel-content">
            {leftPanel}
          </div>
        </aside>
      )}

      <main
        className="three-column-layout-center"
        data-testid="center-panel"
      >
        <div className="panel-content">
          {centerPanel || <div className="panel-placeholder">中央面板内容</div>}
        </div>
      </main>

      {hasRightPanel && (
        <aside
          className="three-column-layout-right"
          style={{ width: rightWidth, minWidth: rightWidth }}
          data-testid="right-panel"
        >
          <div className="panel-content">
            {rightPanel}
          </div>
        </aside>
      )}
    </div>
  );
}