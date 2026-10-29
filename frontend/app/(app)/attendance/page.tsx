'use client';

import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { 
  Clock, Download, CheckCircle, AlertCircle, 
  LogIn, LogOut, Check, X 
} from 'lucide-react';
import { api, AttendanceRecord, getErrorMessage } from '@/lib/api';
import { useAuth } from '@/lib/auth-context';
import { LoadingSpinner, ErrorState, EmptyState } from '@/components/FeedbackStates';

export default function AttendancePage() {
  const queryClient = useQueryClient();
  const { user, isStaff } = useAuth();

  const [date, setDate] = useState(() => new Date().toISOString().split('T')[0]);
  const [feedbackMsg, setFeedbackMsg] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  // Fetch daily attendance log
  const { data: logs, isLoading, error, refetch } = useQuery<AttendanceRecord[]>({
    queryKey: ['attendance', date],
    queryFn: async () => {
      const res = await api.get(`/attendance/daily?work_date=${date}`);
      return res.data;
    },
  });

  // Clock In mutation
  const clockInMutation = useMutation({
    mutationFn: async () => {
      const res = await api.post('/attendance/clock-in');
      return res.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['attendance'] });
      setFeedbackMsg({ type: 'success', text: 'Clocked in successfully!' });
      setTimeout(() => setFeedbackMsg(null), 4000);
    },
    onError: (err: any) => {
      setFeedbackMsg({ type: 'error', text: getErrorMessage(err) });
    },
  });

  // Clock Out mutation
  const clockOutMutation = useMutation({
    mutationFn: async () => {
      const res = await api.post('/attendance/clock-out');
      return res.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['attendance'] });
      setFeedbackMsg({ type: 'success', text: 'Clocked out successfully!' });
      setTimeout(() => setFeedbackMsg(null), 4000);
    },
    onError: (err: any) => {
      setFeedbackMsg({ type: 'error', text: getErrorMessage(err) });
    },
  });

  // Calculate live stats from logs
  const totalLogs = logs?.length || 0;
  const presentCount = logs?.filter((l) => l.status === 'On Time' || l.status === 'Late' || l.status === 'Half Day').length || 0;
  const lateCount = logs?.filter((l) => l.status === 'Late').length || 0;
  const absentCount = logs?.filter((l) => l.status === 'Absent').length || 0;

  const stats = [
    { label: 'Present Today', value: presentCount.toString(), sub: `${totalLogs ? Math.round((presentCount / totalLogs) * 100) : 0}% of recorded staff` },
    { label: 'Late Arrivals', value: lateCount.toString(), sub: 'Logged after grace period' },
    { label: 'Absent / Unmarked', value: absentCount.toString(), sub: 'Requires review or leave application' },
  ];

  return (
    <div className="space-y-8">
      {/* Page Header */}
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
        <div>
          <h1 className="text-3xl font-black text-slate-900 tracking-tight">Time & Attendance</h1>
          <p className="text-sm font-medium text-slate-500 mt-1">
            Track daily employee clock-in times, late entries, and working hours.
          </p>
        </div>
        
        {/* Actions: Date Picker & Employee Clock-in/out */}
        <div className="flex flex-wrap items-center gap-3">
          <input
            type="date"
            value={date}
            onChange={(e) => setDate(e.target.value)}
            className="bg-white border border-slate-200 text-slate-700 text-sm font-semibold rounded-xl px-4 py-2.5 outline-none focus:border-blue-600 shadow-sm"
          />

          <div className="flex items-center gap-2">
            <button
              onClick={() => clockInMutation.mutate()}
              disabled={clockInMutation.isPending}
              className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2.5 rounded-xl text-sm font-bold transition-all shadow-md flex items-center gap-2 disabled:opacity-50"
            >
              <LogIn className="w-4 h-4" /> Clock In
            </button>
            <button
              onClick={() => clockOutMutation.mutate()}
              disabled={clockOutMutation.isPending}
              className="bg-slate-900 hover:bg-slate-800 text-white px-4 py-2.5 rounded-xl text-sm font-bold transition-all shadow-md flex items-center gap-2 disabled:opacity-50"
            >
              <LogOut className="w-4 h-4" /> Clock Out
            </button>
          </div>
        </div>
      </div>

      {/* Feedback Toast */}
      {feedbackMsg && (
        <div
          className={`p-4 rounded-xl flex items-center justify-between border ${
            feedbackMsg.type === 'success'
              ? 'bg-emerald-50 border-emerald-200 text-emerald-800'
              : 'bg-rose-50 border-rose-200 text-rose-800'
          }`}
        >
          <div className="flex items-center gap-2 text-sm font-bold">
            {feedbackMsg.type === 'success' ? (
              <Check className="w-5 h-5 text-emerald-600" />
            ) : (
              <AlertCircle className="w-5 h-5 text-rose-600" />
            )}
            {feedbackMsg.text}
          </div>
          <button onClick={() => setFeedbackMsg(null)} className="p-1 opacity-70 hover:opacity-100">
            <X className="w-4 h-4" />
          </button>
        </div>
      )}

      {/* Daily Metrics */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {stats.map((stat, i) => (
          <div key={i} className="bg-white p-6 rounded-2xl border border-slate-200 shadow-sm">
            <p className="text-sm font-semibold text-slate-500 mb-1">{stat.label}</p>
            <h3 className="text-3xl font-black text-slate-900 mb-2">{stat.value}</h3>
            <p className="text-sm font-medium text-slate-400">{stat.sub}</p>
          </div>
        ))}
      </div>

      {/* Attendance Table */}
      <div className="bg-white border border-slate-200 rounded-2xl shadow-sm overflow-hidden">
        <div className="px-6 py-4 border-b border-slate-200 flex justify-between items-center bg-slate-50/50">
          <h2 className="text-lg font-bold text-slate-800">
            Attendance Log for {new Date(date).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}
          </h2>
          <span className="text-xs font-semibold text-slate-500">
            {totalLogs} entries recorded
          </span>
        </div>

        {isLoading ? (
          <LoadingSpinner text="Retrieving daily attendance entries..." />
        ) : error ? (
          <ErrorState
            title="Failed to load attendance"
            message={getErrorMessage(error)}
            onRetry={() => refetch()}
          />
        ) : !logs || logs.length === 0 ? (
          <EmptyState
            title="No records for this date"
            description="No employee attendance records have been registered for the selected date."
            icon={Clock}
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left">
              <thead>
                <tr className="text-xs font-bold text-slate-500 uppercase tracking-wider border-b border-slate-200 bg-slate-50/20">
                  <th className="py-4 px-6">Employee</th>
                  <th className="py-4 px-6">Check In</th>
                  <th className="py-4 px-6">Check Out</th>
                  <th className="py-4 px-6">Total Hours</th>
                  <th className="py-4 px-6">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {logs.map((log) => {
                  const statusColors = {
                    'On Time': 'bg-emerald-100 text-emerald-800',
                    'Late': 'bg-amber-100 text-amber-800',
                    'Absent': 'bg-rose-100 text-rose-800',
                    'Half Day': 'bg-blue-100 text-blue-800',
                    'On Leave': 'bg-purple-100 text-purple-800',
                    'Not Marked': 'bg-slate-100 text-slate-600',
                  };

                  return (
                    <tr key={log.id} className="hover:bg-slate-50/80 transition-colors">
                      <td className="py-4 px-6">
                        <p className="font-bold text-slate-900">{log.employee_name || 'Staff'}</p>
                        <p className="text-xs font-mono text-slate-400">{log.emp_code} • {log.department_name || 'General'}</p>
                      </td>
                      <td className="py-4 px-6 text-sm font-semibold text-slate-700">
                        {log.check_in || '—'}
                      </td>
                      <td className="py-4 px-6 text-sm font-semibold text-slate-700">
                        {log.check_out || '—'}
                      </td>
                      <td className="py-4 px-6 text-sm font-bold text-slate-900">
                        {log.total_hours ? `${log.total_hours.toFixed(1)} hrs` : '—'}
                      </td>
                      <td className="py-4 px-6">
                        <span
                          className={`inline-flex items-center px-2.5 py-1 rounded-full text-xs font-bold ${
                            statusColors[log.status] || 'bg-slate-100 text-slate-700'
                          }`}
                        >
                          {log.status}
                        </span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}