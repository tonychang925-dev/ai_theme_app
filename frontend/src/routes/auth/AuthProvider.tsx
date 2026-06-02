import { createContext, useContext, useState, useEffect, type ReactNode } from 'react';

interface User {
  id: number;
  email: string;
  role: string;
}

interface AuthContextType {
  user: User | null;
  token: string | null;
  loading: boolean;
  isAdmin: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextType | null>(null);

export function useAuth(): AuthContextType {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}

export function AuthProvider({ children }: { children: ReactNode }) {
  // URL hash fallback: Safari 可能清除 localStorage
  const hashToken = window.location.hash.startsWith('#token=') ? decodeURIComponent(window.location.hash.slice(7)) : null;
  if (hashToken) {
    localStorage.setItem('auth_token', hashToken);
    window.location.hash = '';
  }
  const storedToken = localStorage.getItem('auth_token');
  const [user, setUser] = useState<User | null>(null);
  const [token, setToken] = useState<string | null>(storedToken);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (token) {
      const ctrl = new AbortController();
      const timer = setTimeout(() => ctrl.abort(), 8000);
      fetch('/api/v2/auth/me', { headers: { Authorization: `Bearer ${token}` }, signal: ctrl.signal })
        .then(r => r.ok ? r.json() : Promise.reject(r.status))
        .then(d => setUser(d.user))
        .catch(() => { /* 超时或无网：保留 token，跳过校验 */ })
        .finally(() => { clearTimeout(timer); setLoading(false); });
    } else {
      setLoading(false);
    }
  }, [token]);

  const login = async (email: string, password: string) => {
    const ctrl = new AbortController();
    const timer = window.setTimeout(() => ctrl.abort(), 10000);
    let resp: Response;
    try {
      resp = await fetch('/api/v2/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password }),
        signal: ctrl.signal,
      });
    } catch (err) {
      if (err instanceof Error && err.name === 'AbortError') {
        throw new Error('登录请求超时，请检查 web_app_service 与数据库状态');
      }
      throw new Error('登录请求失败，请检查 web_app_service 是否可用');
    } finally {
      window.clearTimeout(timer);
    }
    if (!resp.ok) {
      let detail = '登录失败';
      try {
        const err = await resp.json();
        detail = err.detail || detail;
      } catch {}
      throw new Error(detail);
    }
    const data = await resp.json();
    localStorage.setItem('auth_token', data.token);
    setToken(data.token);
    setUser(data.user);
    // 支持 returnUrl 跳转回原页面
    const params = new URLSearchParams(window.location.search);
    const returnUrl = params.get('returnUrl');
    window.location.replace(returnUrl || '/');
  };

  const isAdmin = user?.role === 'admin';

  const logout = () => {
    localStorage.removeItem('auth_token');
    setToken(null);
    setUser(null);
    window.location.href = '/login';
  };

  return (
    <AuthContext.Provider value={{ user, token, loading, isAdmin, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}
