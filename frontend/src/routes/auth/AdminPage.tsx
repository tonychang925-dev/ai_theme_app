import { useState, useEffect } from 'react';
import { useAuth } from './AuthProvider';
import './auth.css';

interface UserItem {
  id: number;
  email: string;
  role: string;
  is_active: boolean;
  created_at: string;
  last_login: string | null;
}

export function AdminPage() {
  const { user, token, logout } = useAuth();
  const [users, setUsers] = useState<UserItem[]>([]);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [role, setRole] = useState('user');
  const [msg, setMsg] = useState('');
  const [err, setErr] = useState('');

  const fetchUsers = async () => {
    if (!token) return;
    const resp = await fetch('/api/v2/admin/users', { headers: { Authorization: `Bearer ${token}` } });
    if (resp.ok) setUsers((await resp.json()).users);
  };

  useEffect(() => { fetchUsers(); }, [token]);

  const addUser = async (e: React.FormEvent) => {
    e.preventDefault();
    setErr(''); setMsg('');
    const resp = await fetch('/api/v2/admin/users', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
      body: JSON.stringify({ email, password, role }),
    });
    if (!resp.ok) { setErr((await resp.json()).detail || '添加失败'); return; }
    setMsg(`已添加 ${email}`);
    setEmail(''); setPassword('');
    fetchUsers();
  };

  const formatTime = (s: string | null) => s ? new Date(s).toLocaleString() : '--';

  return (
    <main className="auth-shell">
      {/* ── Left sidebar ── */}
      <aside className="auth-sidebar">
        <div className="auth-brand">
          <div className="auth-logo">AI</div>
          <h1 className="auth-sidebar-title"><span>AI</span> 投资助理</h1>
          <p className="auth-sidebar-sub">Admin Panel</p>
        </div>
        <div style={{ position: 'relative', zIndex: 2, textAlign: 'center', marginTop: 32 }}>
          <p style={{ fontSize: 14, color: 'rgba(255,255,255,0.7)' }}>
            当前: <strong style={{ color: '#00ddfe' }}>{user?.email}</strong>
          </p>
          <p style={{ fontSize: 12, color: 'rgba(255,255,255,0.4)' }}>角色: {user?.role}</p>
        </div>
        <p className="auth-sidebar-footer">
          <a href="/" style={{ color: '#00ddfe', textDecoration: 'none', fontWeight: 600 }}>返回桌面</a>
        </p>
      </aside>

      {/* ── Right panel ── */}
      <section className="auth-form-panel">
        <div className="auth-form-card" style={{ maxWidth: 480 }}>
          <h2 className="auth-form-title">用户管理</h2>
          <p className="auth-form-subtitle">创建新用户或查看现有账户</p>

          <form onSubmit={addUser}>
            <input className="auth-input" type="email" placeholder="新用户邮箱" value={email} onChange={e => setEmail(e.target.value)} required />
            <input className="auth-input" type="password" placeholder="初始密码（至少6位）" value={password} onChange={e => setPassword(e.target.value)} required minLength={6} />
            <select className="auth-select" value={role} onChange={e => setRole(e.target.value)}>
              <option value="user">普通用户</option>
              <option value="admin">管理员</option>
            </select>
            {err && <p className="auth-error">{err}</p>}
            {msg && <p style={{ color: '#00c48c', fontSize: 13, marginBottom: 12, textAlign: 'center' }}>{msg}</p>}
            <button className="auth-btn" type="submit">添加用户</button>
          </form>

          <h3 style={{ color: '#e2e8f0', fontSize: 16, marginTop: 28, marginBottom: 12 }}>
            用户列表 ({users.length})
          </h3>
          <div style={{ maxHeight: 260, overflowY: 'auto' }}>
            {users.map(u => (
              <div key={u.id} style={{
                display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                padding: '10px 0', borderBottom: '1px solid rgba(255,255,255,0.04)',
                fontSize: 13, color: '#7a8498'
              }}>
                <span>
                  {u.email}
                  <span style={{
                    color: u.role === 'admin' ? '#ffd26c' : '#00ddfe',
                    fontSize: 10,
                    marginLeft: 8,
                    fontWeight: 600
                  }}>[{u.role}]</span>
                </span>
                <span style={{ fontSize: 11 }}>{formatTime(u.last_login)}</span>
              </div>
            ))}
          </div>

          <div style={{ marginTop: 20, display: 'flex', gap: 12, justifyContent: 'center' }}>
            <a href="/" style={{ color: '#7a8498', fontSize: 13, textDecoration: 'none' }}>桌面端</a>
            <a href="/mobile" style={{ color: '#7a8498', fontSize: 13, textDecoration: 'none' }}>移动端</a>
            <a href="#" onClick={(e) => { e.preventDefault(); logout(); }} style={{ color: '#ef6a61', fontSize: 13, textDecoration: 'none', fontWeight: 600, marginLeft: 16 }}>退出登录</a>
          </div>
        </div>
      </section>
    </main>
  );
}
