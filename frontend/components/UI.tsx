import React from 'react';
import { Loader2 } from 'lucide-react';

// --- BUTTON ---
interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'danger' | 'ghost';
  isLoading?: boolean;
  icon?: React.ReactNode;
}

export const Button = ({ variant = 'primary', isLoading, icon, children, className = '', ...props }: ButtonProps) => {
  const baseStyle = "inline-flex items-center justify-center gap-2 px-5 py-2.5 rounded-lg text-sm font-bold transition-all disabled:opacity-60 disabled:cursor-not-allowed";
  const variants = {
    primary: "bg-blue-600 hover:bg-blue-700 text-white shadow-md hover:shadow-lg shadow-blue-600/20",
    secondary: "bg-white border border-slate-200 text-slate-700 hover:bg-slate-50 shadow-sm",
    danger: "bg-rose-50 text-rose-700 hover:bg-rose-100 border border-rose-200",
    ghost: "bg-transparent text-slate-500 hover:text-slate-900 hover:bg-slate-100",
  };

  return (
    <button className={`${baseStyle} ${variants[variant]} ${className}`} disabled={isLoading || props.disabled} {...props}>
      {isLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : icon}
      {children}
    </button>
  );
};

// --- BADGE ---
interface BadgeProps {
  status: 'success' | 'warning' | 'error' | 'info' | 'neutral';
  children: React.ReactNode;
}

export const Badge = ({ status, children }: BadgeProps) => {
  const styles = {
    success: "bg-emerald-100 text-emerald-700 border-emerald-200",
    warning: "bg-amber-100 text-amber-700 border-amber-200",
    error: "bg-rose-100 text-rose-700 border-rose-200",
    info: "bg-blue-100 text-blue-700 border-blue-200",
    neutral: "bg-slate-100 text-slate-600 border-slate-200",
  };

  return (
    <span className={`inline-flex items-center px-2.5 py-1 rounded-md text-xs font-bold border ${styles[status]}`}>
      {children}
    </span>
  );
};