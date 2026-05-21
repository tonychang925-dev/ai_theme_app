import React from 'react';
import type { IntelSession, IntelItemType } from '../../lib/api';

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
    </section>
  );
}
