'use client';

import React, { createContext, useContext, useEffect, useState } from 'react';
import { api, CurrentUser } from './api';

interface AuthContextType {
  user: CurrentUser | null;
  loading: boolean;
  login: (token: string, user: CurrentUser) => void;
  logout: () => Promise<void>;
  refreshUser: () => Promise<void>;
  isStaff: boolean;
  isAdmin: boolean;
}

const AuthContext = createContext<AuthContextType>({
  user: null,
  loading: true,
  login: () => {},
  logout: async () => {},
  refreshUser: async () => {},
  isStaff: false,
  isAdmin: false,
});

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [loading, setLoading] = useState(true);

  const refreshUser = async () => {
    try {
      const res = await api.get('/auth/me');
      if (res.data) {
        // Normalize: add flat company_name from nested company object
        const meData = res.data;
        const normalized: CurrentUser = {
          ...meData,
          company_name: meData.company?.name ?? meData.company_name ?? null,
        };
        setUser(normalized);
        localStorage.setItem('vertex_user', JSON.stringify(normalized));
      }
    } catch (err) {
      setUser(null);
      localStorage.removeItem('vertex_token');
      localStorage.removeItem('vertex_user');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    const token = typeof window !== 'undefined' ? localStorage.getItem('vertex_token') : null;
    if (token) {
      refreshUser();
    } else {
      setLoading(false);
    }
  }, []);

  const login = (token: string, userData: CurrentUser) => {
    localStorage.setItem('vertex_token', token);
    localStorage.setItem('vertex_user', JSON.stringify(userData));
    setUser(userData);
  };

  const logout = async () => {
    try {
      await api.post('/auth/logout');
    } catch (e) {
      // ignore network errors on logout
    } finally {
      localStorage.removeItem('vertex_token');
      localStorage.removeItem('vertex_user');
      setUser(null);
      window.location.href = '/login';
    }
  };

  const isStaff = user?.role === 'owner' || user?.role === 'admin' || user?.role === 'hr';
  const isAdmin = user?.role === 'owner' || user?.role === 'admin';

  return (
    <AuthContext.Provider
      value={{
        user,
        loading,
        login,
        logout,
        refreshUser,
        isStaff,
        isAdmin,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}
