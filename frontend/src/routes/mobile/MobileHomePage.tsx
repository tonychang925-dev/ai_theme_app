import './mobile.css';

interface MobileEntryCard {
  title: string;
  description: string;
  href: string;
  eyebrow: string;
  status: string;
  icon: string;
}

const entryCards: MobileEntryCard[] = [
  {
    title: '今日复盘',
    description: '查看最新交易日市场摘要、核心题材、重点股票与风险提示。',
    href: '/mobile/recap',
    eyebrow: 'Recap',
    status: 'Phase 2 接入',
    icon: '📊',
  },
  {
    title: 'AI选股',
    description: '移动端查看电脑端已生成的弱转强与强势股候选结果。',
    href: '/mobile/screener',
    eyebrow: 'Screener',
    status: 'Phase 3 接入',
    icon: '🤖',
  },
  {
    title: '新闻荐股',
    description: '粘贴新闻文本，由电脑端 AI 管线完成题材匹配与股票推荐。',
    href: '/mobile/news-recommend',
    eyebrow: 'News AI',
    status: 'Phase 4 接入',
    icon: '📰',
  },
  {
    title: '实时情报',
    description: '聚合 JYHF-CDP、实时新闻与事件队列的最新情报流。',
    href: '/mobile/intel',
    eyebrow: 'Intel',
    status: 'Phase 2+ 接入',
    icon: '⚡',
  },
];

export function MobileHomePage() {
  return (
    <main className="mobile-shell" aria-labelledby="mobile-page-title">
      <section className="mobile-hero">
        <div className="mobile-hero__badge">iOS HTML5 投资驾驶舱</div>
        <h1 id="mobile-page-title">AI 投资移动入口</h1>
        <p>
          手机端负责展示和轻量触发，电脑端继续承担复盘生成、AI 选股、新闻理解与实时情报采集。
        </p>
      </section>

      <section className="mobile-entry-grid" aria-label="移动端功能入口">
        {entryCards.map((card) => (
          <a className="mobile-entry-card" href={card.href} key={card.href}>
            <span className="mobile-entry-card__glow" aria-hidden="true" />
            <span className="mobile-entry-card__topline">
              <span className="mobile-entry-card__eyebrow">{card.eyebrow}</span>
              <span className="mobile-entry-card__status">{card.status}</span>
            </span>
            <span className="mobile-entry-card__body">
              <span className="mobile-entry-card__icon" aria-hidden="true">
                {card.icon}
              </span>
              <span>
                <strong>{card.title}</strong>
                <small>{card.description}</small>
              </span>
            </span>
            <span className="mobile-entry-card__cta">进入模块</span>
          </a>
        ))}
      </section>

      <section className="mobile-safety-note" aria-label="移动端使用边界">
        <strong>研究用途提示</strong>
        <p>移动端仅展示研究分析结果，不直接访问数据库、Redis、CDP 端口，也不输出买卖指令。</p>
      </section>
    </main>
  );
}
