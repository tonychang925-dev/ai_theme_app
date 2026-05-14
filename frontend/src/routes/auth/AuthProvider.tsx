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
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string) => Promise<void>;
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
    const resp = await fetch('/api/v2/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password }),
    });
    if (!resp.ok) {
      const err = await resp.json();
      throw new Error(err.detail || '登录失败');
    }
    const data = await resp.json();
    localStorage.setItem('auth_token', data.token);
    setToken(data.token);
    setUser(data.user);
    window.location.replace('/mobile');
  };

  const register = async (email: string, password: string) => {
    const resp = await fetch('/api/v2/auth/register', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password }),
    });
    if (!resp.ok) {
      const err = await resp.json();
      throw new Error(err.detail || '注册失败');
    }
    const data = await resp.json();
    localStorage.setItem('auth_token', data.token);
    setToken(data.token);
    setUser(data.user);
  };

  const logout = () => {
    localStorage.removeItem('auth_token');
    setToken(null);
    setUser(null);
    window.location.href = '/login';
  };

  return (
    <AuthContext.Provider value={{ user, token, loading, login, register, logout }}>
      {children}
    </AuthContext.Provider>
  );
}
