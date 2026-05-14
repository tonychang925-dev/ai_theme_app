import { useState, FormEvent, useEffect } from 'react';
import { useAuth } from './AuthProvider';
import './auth.css';

export function LoginPage() {
  const { user, login, logout } = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [remember, setRemember] = useState(true);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [showForm, setShowForm] = useState(false);

  useEffect(() => {
    const saved = localStorage.getItem('login_creds');
    if (saved) {
      try {
        const creds = JSON.parse(saved);
        setEmail(creds.email || '');
        setPassword(creds.password || '');
        setRemember(true);
      } catch {}
    }
  }, []);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      if (remember) {
        localStorage.setItem('login_creds', JSON.stringify({ email, password }));
      } else {
        localStorage.removeItem('login_creds');
      }
      await login(email, password);
    } catch (err) {
      setError(err instanceof Error ? err.message : '登录失败');
    } finally {
      setLoading(false);
    }
  };

  const handleSwitchAccount = () => {
    logout();
    setShowForm(true);
  };

  return (
    <main className="auth-shell">
      {/* ── Right 1/3 overlay: logo + title + form ── */}
      <section className="auth-form-panel">
        {/* Logo */}
        <img
          className="auth-logo-img"
          src="/logo-brand.png"
          alt="AI 投资助理"
        />

        {/* Title below logo */}
        <h1 className="auth-sidebar-title"><span>AI</span> 投资助理</h1>
        <p className="auth-sidebar-sub">Investment Intelligence</p>

        <div className="auth-form-card">
          {user && !showForm ? (
            /* ── Already logged in ── */
            <>
              <h2 className="auth-form-title">已登录</h2>
              <p className="auth-form-subtitle">选择操作以继续</p>

              <div className="auth-logged-in-user">
                <div className="auth-user-email">{user.email}</div>
                <div className="auth-user-role">
                  角色: {user.role === 'admin' ? '管理员' : '普通用户'}
                </div>
              </div>
              <button
                className="auth-btn"
                style={{ marginBottom: 12 }}
                onClick={() => { window.location.href = '/'; }}
              >
                进入系统
              </button>
              <button
                className="auth-btn auth-btn-secondary"
                onClick={handleSwitchAccount}
              >
                切换账号
              </button>
            </>
          ) : (
            /* ── Login form ── */
            <>
              <h2 className="auth-form-title">欢迎回来</h2>
              <p className="auth-form-subtitle">请使用邮箱和密码登录您的账户</p>

              <form onSubmit={handleSubmit}>
                <input
                  className="auth-input"
                  type="email"
                  placeholder="邮箱地址"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                  autoFocus
                />
                <input
                  className="auth-input"
                  type="password"
                  placeholder="密码"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                  minLength={6}
                />
                <label className="auth-remember">
                  <input type="checkbox" checked={remember} onChange={(e) => setRemember(e.target.checked)} />
                  记住密码
                </label>
                {error && <p className="auth-error">{error}</p>}
                <button className="auth-btn" type="submit" disabled={loading}>
                  {loading ? '登录中...' : '登 录'}
                </button>
              </form>
            </>
          )}
        </div>

        <p className="auth-copyright">© 2026 AI Investment Assistant</p>
      </section>
    </main>
  );
}
