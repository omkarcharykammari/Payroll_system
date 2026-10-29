'use client';

import React, { useState } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { Mail, Lock, ArrowRight, Loader2, AlertCircle } from 'lucide-react';
import { api, getErrorMessage } from '@/lib/api';
import { useAuth } from '@/lib/auth-context';

export default function LoginPage() {
  const router = useRouter();
  const { login, refreshUser } = useAuth();

  const [loading, setLoading] = useState(false);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError('');

    try {
      const response = await api.post('/auth/login', { email, password });
      if (response.data?.access_token) {
        // Store token first so refreshUser's interceptor can use it
        login(response.data.access_token, response.data.user);
        // Fetch full /auth/me to normalize company_name and employee data
        await refreshUser();
        router.push('/dashboard');
      } else {
        setError('Login failed: Token missing from response.');
      }
    } catch (err: any) {
      setError(getErrorMessage(err));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex bg-white font-sans selection:bg-blue-600 selection:text-white">
      {/* Left Form */}
      <div className="w-full lg:w-1/2 flex flex-col justify-center px-8 sm:px-16 lg:px-24 relative z-10">
        <div className="max-w-md w-full mx-auto">
          {/* Logo */}
          <div className="flex items-center gap-3 mb-12">
            <div className="w-10 h-10 bg-blue-600 rounded-xl flex items-center justify-center shadow-lg shadow-blue-600/20">
              <svg className="w-6 h-6 text-white" width="24" height="24" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M13 10V3L4 14h7v7l9-11h-7z" />
              </svg>
            </div>
            <span className="text-2xl font-black tracking-tight text-slate-900">Vertex</span>
          </div>

          <div>
            <h1 className="text-3xl font-extrabold text-slate-900 tracking-tight">Welcome back</h1>
            <p className="text-slate-500 mt-2 font-medium">Please enter your credentials to sign in.</p>
          </div>

          <form onSubmit={handleLogin} className="mt-8 space-y-5">
            {error && (
              <div className="p-3.5 bg-rose-50 border border-rose-200 rounded-xl text-xs font-bold text-rose-700 flex items-center gap-2">
                <AlertCircle className="w-4 h-4 flex-shrink-0" />
                <span>{error}</span>
              </div>
            )}

            <div>
              <label className="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-2">
                Email Address
              </label>
              <div className="relative">
                <Mail className="w-5 h-5 absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400" />
                <input
                  type="email"
                  required
                  placeholder="name@company.com"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="w-full pl-11 pr-4 py-3 bg-slate-50 border border-slate-200 rounded-xl text-sm font-medium focus:bg-white focus:outline-none focus:ring-2 focus:ring-blue-600/20 focus:border-blue-600 transition-all"
                />
              </div>
            </div>

            <div>
              <div className="flex items-center justify-between mb-2">
                <label className="block text-xs font-bold text-slate-700 uppercase tracking-wider">
                  Password
                </label>
                <Link
                  href="/forgot-password"
                  className="text-xs font-bold text-blue-600 hover:text-blue-700 transition-colors"
                >
                  Forgot password?
                </Link>
              </div>
              <div className="relative">
                <Lock className="w-5 h-5 absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400" />
                <input
                  type="password"
                  required
                  placeholder="••••••••"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="w-full pl-11 pr-4 py-3 bg-slate-50 border border-slate-200 rounded-xl text-sm font-medium focus:bg-white focus:outline-none focus:ring-2 focus:ring-blue-600/20 focus:border-blue-600 transition-all"
                />
              </div>
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full py-3.5 px-4 bg-slate-900 hover:bg-slate-800 text-white font-bold rounded-xl shadow-lg shadow-slate-900/10 hover:shadow-slate-900/20 transition-all flex items-center justify-center gap-2 group disabled:opacity-50"
            >
              {loading ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin text-white" />
                  <span>Signing in...</span>
                </>
              ) : (
                <>
                  <span>Sign In</span>
                  <ArrowRight className="w-4 h-4 group-hover:translate-x-0.5 transition-transform" />
                </>
              )}
            </button>
          </form>

          <div className="mt-8 text-center text-xs text-slate-500 font-medium">
            Don't have a company account yet?{' '}
            <Link href="/signup" className="font-bold text-blue-600 hover:text-blue-700">
              Register company
            </Link>
          </div>
        </div>
      </div>

      {/* Right Graphic Banner */}
      <div className="hidden lg:flex w-1/2 bg-slate-900 p-12 flex-col justify-between relative overflow-hidden">
        <div className="absolute inset-0 bg-gradient-to-br from-blue-900/40 via-transparent to-transparent pointer-events-none" />
        <div className="relative z-10 flex items-center gap-2 text-white/80">
          <span className="font-mono text-xs uppercase tracking-widest font-semibold">Vertex Enterprise</span>
        </div>
        <div className="relative z-10 max-w-md">
          <h2 className="text-4xl font-extrabold text-white tracking-tight leading-tight">
            High-precision payroll & workforce operations.
          </h2>
          <p className="mt-4 text-slate-400 font-medium text-sm leading-relaxed">
            Multi-tenant compliance engine with automated EPF, ESIC, Professional Tax, and Income Tax TDS calculations.
          </p>
        </div>
        <div className="relative z-10 text-xs text-slate-500">
          © {new Date().getFullYear()} Vertex HR & Payroll Platform. All rights reserved.
        </div>
      </div>
    </div>
  );
}