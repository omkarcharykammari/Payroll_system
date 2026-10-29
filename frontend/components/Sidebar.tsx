'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { 
  LayoutDashboard, Users, Clock, CalendarDays, 
  Wallet, FileBarChart, Settings, LogOut, FileText, CheckSquare
} from 'lucide-react';
import { useAuth } from '@/lib/auth-context';

export default function Sidebar() {
  const pathname = usePathname();
  const { user, isStaff, logout } = useAuth();

  // Employer / Staff menu
  const staffNavItems = [
    { name: 'Dashboard', href: '/dashboard', icon: LayoutDashboard },
    { name: 'Directory', href: '/employees', icon: Users },
    { name: 'Attendance', href: '/attendance', icon: Clock },
    { name: 'Leave', href: '/leave', icon: CalendarDays },
    { name: 'Payroll', href: '/payroll', icon: Wallet },
    { name: 'Payslips', href: '/payslips', icon: FileText },
    { name: 'Reports', href: '/reports', icon: FileBarChart },
    { name: 'Settings', href: '/settings', icon: Settings },
  ];

  // Employee self-service menu
  const employeeNavItems = [
    { name: 'Dashboard', href: '/dashboard', icon: LayoutDashboard },
    { name: 'My Attendance', href: '/attendance', icon: Clock },
    { name: 'My Leave', href: '/leave', icon: CalendarDays },
    { name: 'My Payslips', href: '/payslips', icon: FileText },
    { name: 'My Profile', href: '/settings', icon: Settings },
  ];

  const navItems = isStaff ? staffNavItems : employeeNavItems;

  return (
    <aside className="w-64 bg-white border-r border-slate-200 flex flex-col fixed h-full z-20 shadow-[4px_0_24px_rgba(0,0,0,0.02)]">
      {/* Brand Logo */}
      <div className="h-20 flex items-center px-6 border-b border-slate-100">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 bg-blue-600 rounded-xl flex items-center justify-center shadow-lg shadow-blue-600/20">
            <svg className="w-5 h-5 text-white" width="20" height="20" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M13 10V3L4 14h7v7l9-11h-7z" />
            </svg>
          </div>
          <div>
            <span className="text-xl font-black tracking-tight text-slate-900 block leading-tight">Vertex</span>
            <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider block">
              {user?.company_name || 'HR & Payroll'}
            </span>
          </div>
        </div>
      </div>

      {/* Navigation */}
      <div className="flex-1 overflow-y-auto py-6 px-4 space-y-1">
        <div className="text-[11px] font-bold text-slate-400 uppercase tracking-wider mb-4 px-3">
          {isStaff ? 'Employer Suite' : 'Employee Portal'}
        </div>
        {navItems.map((item) => {
          const isActive = pathname === item.href;
          const Icon = item.icon;
          return (
            <Link 
              key={item.name} 
              href={item.href} 
              className={`flex items-center gap-3 px-3 py-2.5 rounded-xl font-semibold transition-all duration-200 ${
                isActive 
                  ? 'bg-blue-50 text-blue-700 shadow-sm border border-blue-100/50' 
                  : 'text-slate-500 hover:bg-slate-50 hover:text-slate-900'
              }`}
            >
              <Icon className={`w-5 h-5 ${isActive ? 'text-blue-600' : 'text-slate-400'}`} />
              {item.name}
            </Link>
          );
        })}
      </div>

      {/* Footer / Logout */}
      <div className="p-4 border-t border-slate-100 bg-slate-50/50">
        <button 
          onClick={logout}
          className="flex items-center gap-3 px-3 py-2.5 rounded-xl font-semibold text-rose-600 hover:bg-rose-50 w-full transition-all text-sm"
        >
          <LogOut className="w-5 h-5 text-rose-500" />
          Sign Out
        </button>
      </div>
    </aside>
  );
}