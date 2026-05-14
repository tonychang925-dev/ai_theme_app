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
      <div className="auth-card" style={{ maxWidth: 520 }}>
        <h1 className="auth-title">用户管理</h1>
        <p style={{ textAlign: 'center', color: '#6a7088', fontSize: 13, marginBottom: 20 }}>
          当前: <strong style={{ color: '#ffd700' }}>{user?.email}</strong> ({user?.role})
        </p>

        <form onSubmit={addUser}>
          <input className="auth-input" type="email" placeholder="新用户邮箱" value={email} onChange={e => setEmail(e.target.value)} required />
          <input className="auth-input" type="password" placeholder="初始密码（至少6位）" value={password} onChange={e => setPassword(e.target.value)} required minLength={6} />
          <select className="auth-input" value={role} onChange={e => setRole(e.target.value)}>
            <option value="user">普通用户</option>
            <option value="admin">管理员</option>
          </select>
          {err && <p className="auth-error">{err}</p>}
          {msg && <p style={{ color: '#5dade2', textAlign: 'center', fontSize: 13 }}>{msg}</p>}
          <button className="auth-btn" type="submit">添加用户</button>
        </form>

        <h2 style={{ color: '#ffd700', fontSize: 16, marginTop: 24 }}>用户列表 ({users.length})</h2>
        <div style={{ maxHeight: 300, overflowY: 'auto', marginTop: 8 }}>
          {users.map(u => (
            <div key={u.id} style={{
              display: 'flex', justifyContent: 'space-between', alignItems: 'center',
              padding: '8px 0', borderBottom: '1px solid rgba(255,255,255,0.06)',
              fontSize: 13, color: '#8a90a8'
            }}>
              <span>{u.email} <span style={{ color: u.role === 'admin' ? '#ffd700' : '#5dade2', fontSize: 11 }}>[{u.role}]</span></span>
              <span style={{ fontSize: 11 }}>{formatTime(u.last_login)}</span>
            </div>
          ))}
        </div>

        <p className="auth-link" style={{ display: 'flex', gap: 16, justifyContent: 'center', marginTop: 20 }}>
          <a href="/">桌面端</a>
          <a href="/mobile">移动端</a>
          <a href="#" onClick={(e) => { e.preventDefault(); logout(); }} style={{ color: '#e08080' }}>退出登录</a>
        </p>
      </div>
    </main>
  );
}
