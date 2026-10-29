'use client';

import React from 'react';
import { useQuery } from '@tanstack/react-query';
import { useRouter } from 'next/navigation';
import { 
  TrendingUp, Download, ArrowUpRight, Plus, 
  Calendar, CheckCircle, Clock, Users, ArrowRight 
} from 'lucide-react';
import { api, DashboardReport } from '@/lib/api';
import { useAuth } from '@/lib/auth-context';
import { LoadingSpinner, ErrorState } from '@/components/FeedbackStates';
import { PayrollCostChart, DepartmentDonutChart } from '@/components/Charts';


export default function DashboardPage() {
  const router = useRouter();
  const { user, isStaff } = useAuth();

  const { data, isLoading, error, refetch } = useQuery<DashboardReport>({
    queryKey: ['dashboard'],
    queryFn: async () => {
      const res = await api.get('/dashboard');
      return res.data;
    },
  });

  if (isLoading) {
    return <LoadingSpinner text="Loading payroll dashboard..." />;
  }

  if (error || !data) {
    return (
      <ErrorState
        title="Failed to load dashboard"
        message="Could not retrieve the payroll overview. Please make sure the backend is reachable."
        onRetry={() => refetch()}
      />
    );
  }

  const { next_payroll_run, banner, stats, payroll_status, employees } = data;

  const payrollCards = [
    {
      label: 'Next Payroll Payday',
      value: next_payroll_run?.date ? new Date(next_payroll_run.date).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }) : '—',
      sub: `${next_payroll_run?.days_remaining ?? 0} days remaining`,
      highlight: true,
    },
    {
      label: 'Total Gross Pay',
      value: `₹${Number(stats?.total_gross_pay || 0).toLocaleString('en-IN')}`,
      sub: stats?.gross_change_percent ? `${stats.gross_change_percent > 0 ? '+' : ''}${stats.gross_change_percent}% vs last month` : 'Current cycle',
      trend: stats?.gross_change_percent,
    },
    {
      label: 'Taxes & Deductions',
      value: `₹${Number(stats?.taxes_and_deductions || 0).toLocaleString('en-IN')}`,
      sub: 'PF, ESI, TDS & PT',
    },
    {
      label: 'Net Pay Disbursement',
      value: `₹${Number(stats?.net_pay || 0).toLocaleString('en-IN')}`,
      sub: `${payroll_status?.label || 'In progress'}`,
    },
  ];

  return (
    <div className="space-y-8">
      {/* Page Header */}
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
        <div>
          <h1 className="text-3xl font-black text-slate-900 tracking-tight">Payroll Overview</h1>
          <p className="text-sm font-medium text-slate-500 mt-1">
            Real-time status for {user?.company_name || 'your company'}.
          </p>
        </div>
        {isStaff && (
          <button 
            onClick={() => router.push('/payroll')}
            className="bg-slate-900 hover:bg-slate-800 text-white px-5 py-2.5 rounded-xl text-sm font-bold transition-all shadow-lg shadow-slate-900/20 flex items-center gap-2"
          >
            <Plus className="w-5 h-5" /> Manage Payroll
          </button>
        )}
      </div>

      {/* Action Banner */}
      <div className="bg-gradient-to-r from-blue-600 to-indigo-700 rounded-2xl p-6 md:p-8 text-white flex flex-col md:flex-row items-center justify-between gap-6 shadow-xl shadow-blue-600/10">
        <div>
          <div className="inline-flex items-center gap-2 px-2.5 py-1 rounded-md bg-white/20 text-white text-xs font-bold uppercase tracking-wider mb-3">
            {payroll_status?.status || 'Active Cycle'}
          </div>
          <h2 className="text-2xl font-bold mb-1">{banner?.title || 'Monthly Payroll Cycle'}</h2>
          <p className="text-blue-100 font-medium">{banner?.message || 'Ready for processing'}</p>
        </div>
        {isStaff && (
          <button 
            onClick={() => router.push('/payroll')}
            className="bg-white text-blue-700 hover:bg-blue-50 px-6 py-3 rounded-xl font-bold transition-colors shadow-sm flex items-center gap-2 whitespace-nowrap"
          >
            {banner?.action_label || 'Go to Payroll'} <ArrowUpRight className="w-4 h-4" />
          </button>
        )}
      </div>

      {/* Stats Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        {payrollCards.map((stat, i) => (
          <div key={i} className="bg-white p-6 rounded-2xl border border-slate-200 shadow-sm hover:shadow-md transition-shadow">
            <p className="text-sm font-semibold text-slate-500 mb-2">{stat.label}</p>
            <h3 className="text-2xl lg:text-3xl font-black text-slate-900 mb-2 tabular-nums">{stat.value}</h3>
            <p className={`text-sm font-medium flex items-center gap-1 ${
              stat.trend && stat.trend > 0 ? 'text-emerald-600' : 'text-slate-500'
            }`}>
              {stat.trend && <TrendingUp className="w-4 h-4" />}
              {stat.sub}
            </p>
          </div>
        ))}
      </div>

      {/* Visual Analytics Charts (Fintech Standard) */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2">
          <PayrollCostChart currentGross={Number(stats?.total_gross_pay || 0)} />
        </div>
        <div>
          <DepartmentDonutChart departments={employees?.by_department || {}} />
        </div>
      </div>

      {/* Workforce & Lifecycle Summary */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Active Workforce */}
        <div className="bg-white border border-slate-200 rounded-2xl p-6 shadow-sm">
          <div className="flex items-center justify-between mb-4">
            <h3 className="font-bold text-slate-900 text-lg">Active Employees</h3>
            <span className="px-2.5 py-1 bg-emerald-100 text-emerald-700 text-xs font-bold rounded-full">
              {employees?.total_active ?? 0} Enrolled
            </span>
          </div>
          <div className="space-y-3">
            {Object.entries(employees?.by_department || {}).map(([dept, count]) => (
              <div key={dept} className="flex justify-between items-center text-sm">
                <span className="text-slate-600 font-medium">{dept}</span>
                <span className="font-bold text-slate-900">{count}</span>
              </div>
            ))}
          </div>
          {isStaff && (
            <button
              onClick={() => router.push('/employees')}
              className="mt-6 w-full py-2.5 text-center text-sm font-bold text-blue-600 hover:text-blue-700 border border-blue-200 hover:bg-blue-50/50 rounded-xl transition-colors flex items-center justify-center gap-2"
            >
              View Directory <ArrowRight className="w-4 h-4" />
            </button>
          )}
        </div>


        {/* Payroll Lifecycle Steps */}
        <div className="bg-white border border-slate-200 rounded-2xl p-6 shadow-sm lg:col-span-2">
          <div className="flex items-center justify-between mb-4">
            <h3 className="font-bold text-slate-900 text-lg">Payroll Cycle Pipeline</h3>
            <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
              Stage: {payroll_status?.label}
            </span>
          </div>
          <div className="space-y-4">
            {(payroll_status?.steps || []).map((st, idx) => (
              <div 
                key={st.name} 
                className={`p-3.5 rounded-xl border flex items-center justify-between ${
                  st.status === 'DONE' 
                    ? 'bg-emerald-50/50 border-emerald-200 text-emerald-900' 
                    : st.status === 'IN_PROGRESS'
                    ? 'bg-blue-50/50 border-blue-200 text-blue-900'
                    : 'bg-slate-50/50 border-slate-200 text-slate-400'
                }`}
              >
                <div className="flex items-center gap-3">
                  <div className={`w-7 h-7 rounded-full flex items-center justify-center font-bold text-xs ${
                    st.status === 'DONE' ? 'bg-emerald-600 text-white' : 
                    st.status === 'IN_PROGRESS' ? 'bg-blue-600 text-white' : 'bg-slate-200 text-slate-600'
                  }`}>
                    {st.status === 'DONE' ? <CheckCircle className="w-4 h-4" /> : idx + 1}
                  </div>
                  <div>
                    <h4 className="font-bold text-sm text-slate-900">{st.name}</h4>
                    <p className="text-xs text-slate-500">{st.description}</p>
                  </div>
                </div>
                <span className={`text-xs font-bold uppercase tracking-wider ${
                  st.status === 'DONE' ? 'text-emerald-700' :
                  st.status === 'IN_PROGRESS' ? 'text-blue-700' : 'text-slate-400'
                }`}>
                  {st.status}
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}