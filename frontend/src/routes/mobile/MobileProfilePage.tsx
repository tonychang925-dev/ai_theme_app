import { useState } from 'react';
import { useAuth } from '../auth/AuthProvider';
import './mobile.css';

export function MobileProfilePage() {
  const { user, token, logout } = useAuth();
  const [oldPwd, setOldPwd] = useState('');
  const [newPwd, setNewPwd] = useState('');
  const [msg, setMsg] = useState('');
  const [err, setErr] = useState('');

  const changePassword = async (e: React.FormEvent) => {
    e.preventDefault();
    setErr(''); setMsg('');
    if (newPwd.length < 6) { setErr('新密码至少 6 位'); return; }
    const resp = await fetch('/api/v2/auth/password', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
      body: JSON.stringify({ old_password: oldPwd, new_password: newPwd }),
    });
    if (!resp.ok) { setErr((await resp.json()).detail || '修改失败'); return; }
    setMsg('密码修改成功');
    setOldPwd(''); setNewPwd('');
  };

  return (
    <main className="mobile-shell">
      <header className="mobile-page-header">
        <button type="button" className="mobile-back-btn" onClick={() => { window.location.href = '/mobile'; }}>← 首页</button>
        <h1 className="mobile-page-title">账户</h1>
      </header>

      <section className="mobile-card" style={{ margin: '12px 16px' }}>
        <h2 className="mobile-card-title">账户信息</h2>
        <p className="mobile-card-text">{user?.email}</p>
        <p className="mobile-card-text" style={{ color: '#5dade2', fontSize: 13 }}>角色: {user?.role}</p>
      </section>

      <section className="mobile-card" style={{ margin: '12px 16px' }}>
        <h2 className="mobile-card-title">修改密码</h2>
        <form onSubmit={changePassword}>
          <input className="auth-input" type="password" placeholder="原密码" value={oldPwd} onChange={e => setOldPwd(e.target.value)} required />
          <input className="auth-input" type="password" placeholder="新密码（至少6位）" value={newPwd} onChange={e => setNewPwd(e.target.value)} required minLength={6} />
          {err && <p className="auth-error">{err}</p>}
          {msg && <p style={{ color: '#5dade2', textAlign: 'center', fontSize: 14 }}>{msg}</p>}
          <button className="auth-btn" type="submit">修改密码</button>
        </form>
      </section>

      <section style={{ margin: '12px 16px' }}>
        <button onClick={logout} style={{
          width: '100%', padding: 12, background: 'rgba(255,100,100,0.12)',
          border: '1px solid rgba(255,100,100,0.25)', borderRadius: 12,
          color: '#e08080', fontSize: 16, cursor: 'pointer'
        }}>退出登录</button>
      </section>
    </main>
  );
}
