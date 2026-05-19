import React from 'react';
import type { IntelSession, IntelItemType } from '../../lib/api';
import { navigateTo } from '../../lib/navigation';

interface IntelFiltersProps {
  date: string;
  setDate: (date: string) => void;
  session: IntelSession;
  setSession: (session: IntelSession) => void;
  type: IntelItemType;
  setType: (type: IntelItemType) => void;
  recapDates: {
    postMarket: string;
    preMarket: string;
  };
}

export function IntelFilters({
  date,
  setDate,
  session,
  setSession,
  type,
  setType,
  recapDates,
}: IntelFiltersProps) {
  return (
    <section className="intel-filters">
      <label>
        <span>日期</span>
        <input type="date" value={date} onChange={(e) => setDate(e.target.value)} />
      </label>
      <label>
        <span>时段</span>
        <select value={session} onChange={(e) => setSession(e.target.value as IntelSession)}>
          <option value="all">全部</option>
          <option value="pre">盘前</option>
          <option value="intra">盘中</option>
          <option value="post">盘后</option>
        </select>
      </label>
      <label>
        <span>类型</span>
        <select value={type} onChange={(e) => setType(e.target.value as IntelItemType)}>
          <option value="all">情报</option>
          <option value="recap">复盘</option>
          <option value="weak_to_strong">弱转强</option>
          <option value="theme_cycle">题材周期</option>
          <option value="theme_identity">主线身份</option>
          <option value="stock_signal">强势股</option>
          <option value="event_review">待复核事件</option>
          <option value="event">新事件</option>
          <option value="new_theme">新题材</option>
          <option value="stock_move">异动</option>
        </select>
      </label>
      <button
        type="button"
        className="recap-filter-button"
        onClick={() => navigateTo("/realtime-collector")}
      >
        启动实时采集
      </button>
      <button
        type="button"
        className="recap-filter-button"
        onClick={() => navigateTo("/collection")}
      >
        日采集控制台
      </button>
      <button
        type="button"
        className="recap-filter-button"
        onClick={() => navigateTo(`/recap?date=${recapDates.postMarket}&report_type=post_market`)}
      >
        当日复盘
      </button>
      <button
        type="button"
        className="recap-filter-button"
        onClick={() => navigateTo(`/pre-market-brief?trade_date=${recapDates.preMarket}`)}
      >
        盘前必读
      </button>
      <button
        type="button"
        className="recap-filter-button"
        onClick={() => navigateTo('/screener')}
      >
        AI选股
      </button>
      <button
        type="button"
        className="recap-filter-button"
        onClick={() => navigateTo(`/intel/strong-stocks/watch?date=${date}&window_days=7`)}
      >
        强势股跟踪
      </button>
    </section>
  );
}
