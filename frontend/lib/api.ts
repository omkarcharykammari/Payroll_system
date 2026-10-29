import axios, { AxiosError } from 'axios';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api/v1';

export const api = axios.create({
  baseURL: API_BASE,
  headers: {
    'Content-Type': 'application/json',
  },
  withCredentials: true,
});

// Request Interceptor: Attach bearer token if stored in localStorage
api.interceptors.request.use(
  (config) => {
    if (typeof window !== 'undefined') {
      const token = localStorage.getItem('vertex_token');
      if (token && config.headers) {
        config.headers.Authorization = `Bearer ${token}`;
      }
    }
    return config;
  },
  (error) => Promise.reject(error)
);

// Response Interceptor: 401 handling & error formatting
api.interceptors.response.use(
  (response) => response,
  (error: AxiosError<any>) => {
    if (error.response?.status === 401) {
      if (typeof window !== 'undefined') {
        const isAuthRoute = window.location.pathname.startsWith('/login') ||
                            window.location.pathname.startsWith('/signup') ||
                            window.location.pathname.startsWith('/accept-invite') ||
                            window.location.pathname.startsWith('/forgot-password') ||
                            window.location.pathname.startsWith('/reset-password');
        if (!isAuthRoute) {
          localStorage.removeItem('vertex_token');
          localStorage.removeItem('vertex_user');
          window.location.href = '/login';
        }
      }
    }
    return Promise.reject(error);
  }
);

// Formatted Error Extractor
export function getErrorMessage(error: any): string {
  if (!error) return 'An unexpected error occurred.';
  if (typeof error === 'string') return error;
  if (error.response?.data) {
    const data = error.response.data;
    if (typeof data.detail === 'string') return data.detail;
    if (data.errors && Array.isArray(data.errors)) {
      return data.errors.map((e: any) => `${e.field ? e.field + ': ' : ''}${e.message}`).join(', ');
    }
    if (Array.isArray(data.detail)) {
      return data.detail.map((d: any) => d.msg || JSON.stringify(d)).join(', ');
    }
    return JSON.stringify(data);
  }
  return error.message || 'Network error. Please try again.';
}

// --------------------------------------------------------------------------- //
// TypeScript API Types
// --------------------------------------------------------------------------- //
export interface CurrentUser {
  id: number;
  email: string;
  role: 'owner' | 'admin' | 'hr' | 'employee';
  company_id?: number | null;
  /** Nested company object returned by /auth/me */
  company?: { id: number; name: string; legal_name?: string | null } | null;
  /** Convenience accessor — use this instead of company?.name everywhere */
  company_name?: string | null;
  employee_id?: number | null;
  first_name?: string | null;
  last_name?: string | null;
  full_name?: string | null;
  permissions: string[];
  employee?: {
    id: number;
    emp_code: string;
    name: string;
    designation?: string | null;
    department?: string | null;
  } | null;
}

export interface CompanyDetails {
  id: number;
  name: string;
  legal_name?: string | null;
  state?: string | null;
  pan?: string | null;
  tan?: string | null;
  gstin?: string | null;
  pf_establishment_code?: string | null;
  address?: string | null;
  logo_url?: string | null;
}

export interface EmployeeItem {
  id: number;
  emp_code: string;
  first_name: string;
  last_name: string;
  work_email: string;
  phone?: string | null;
  designation?: string | null;
  department_id?: number | null;
  department?: { id: number; name: string } | null;
  status: 'Active' | 'Inactive' | 'Terminated';
  employment_type?: string | null;
  date_of_joining?: string | null;
  avatar_url?: string | null;
  annual_ctc?: number | null;
  bank_account_number?: string | null;
  bank_name?: string | null;
  bank_ifsc?: string | null;
  pan_number?: string | null;
  uan_number?: string | null;
}

export interface DashboardReport {
  next_payroll_run: { date: string; days_remaining: number };
  banner: {
    title: string;
    message: string;
    action?: string | null;
    action_label?: string | null;
    run_id?: number | null;
  };
  current_run?: any;
  stats: {
    total_gross_pay: number;
    taxes_and_deductions: number;
    net_pay: number;
    total_cost_to_company: number;
    gross_change_percent?: number | null;
  };
  payroll_status: {
    status: string;
    label: string;
    current_step: number;
    steps: { name: string; description: string; status: string }[];
  };
  employees: {
    total_active: number;
    by_department: Record<string, number>;
  };
  recent_changes?: any[];
  pending_leave_count?: number;
}

export interface AttendanceRecord {
  id: number;
  employee_id: number;
  employee_name: string;
  emp_code: string;
  department_name?: string;
  work_date: string;
  status: 'On Time' | 'Late' | 'Absent' | 'Half Day' | 'On Leave' | 'Not Marked';
  check_in?: string | null;
  check_out?: string | null;
  total_hours?: number | null;
}

export interface LeaveRequestItem {
  id: number;
  employee_id: number;
  employee_name: string;
  leave_type_id: number;
  leave_type_name: string;
  start_date: string;
  end_date: string;
  days_count: number;
  status: 'Pending' | 'Approved' | 'Denied' | 'Cancelled';
  reason?: string | null;
  review_note?: string | null;
  applied_at: string;
}

export interface LeaveBalanceItem {
  id: number;
  leave_type_name: string;
  annual_quota: number;
  used: number;
  available: number;
}

export interface PayrollRunItem {
  id: number;
  year: number;
  month: number;
  label: string;
  status: 'DRAFT' | 'REVIEWED' | 'FINALIZED' | 'PAID';
  current_step: number;
  total_gross: number;
  total_deductions: number;
  total_net: number;
  employee_count: number;
  steps: { name: string; description: string; status: string }[];
}

export interface PayslipItem {
  id: number;
  employee_id: number;
  employee_name: string;
  emp_code: string;
  department?: string;
  payslip_number: string;
  year: number;
  month: number;
  gross_pay: number;
  total_deductions: number;
  net_pay: number;
  status: 'Draft' | 'Published';
}

export interface NotificationItem {
  id: number;
  title: string;
  message: string;
  type: string;
  link?: string | null;
  is_read: boolean;
  created_at: string;
}

export interface SearchResult {
  category: 'employee' | 'payslip' | 'page';
  title: string;
  subtitle?: string;
  link: string;
}