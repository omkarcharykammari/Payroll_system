'use client';

import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { FileText, Send, Download, Search, Check, AlertCircle, X } from 'lucide-react';
import { api, PayslipItem, getErrorMessage } from '@/lib/api';
import { useAuth } from '@/lib/auth-context';
import { LoadingSpinner, ErrorState, EmptyState } from '@/components/FeedbackStates';

export default function PayslipsPage() {
  const queryClient = useQueryClient();
  const { user, isStaff } = useAuth();

  const [searchQuery, setSearchQuery] = useState('');
  const [selectedPeriod, setSelectedPeriod] = useState('');
  const [feedbackMsg, setFeedbackMsg] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  // Fetch payslips
  const { data: slips, isLoading, error, refetch } = useQuery<PayslipItem[]>({
    queryKey: ['payslips'],
    queryFn: async () => {
      const res = await api.get('/payslips');
      return res.data;
    },
  });

  // Publish All mutation (Staff only)
  const publishMutation = useMutation({
    mutationFn: async () => {
      const res = await api.post('/payslips/publish-all');
      return res.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['payslips'] });
      setFeedbackMsg({ type: 'success', text: 'All draft payslips published to employees!' });
      setTimeout(() => setFeedbackMsg(null), 4000);
    },
    onError: (err: any) => {
      setFeedbackMsg({ type: 'error', text: getErrorMessage(err) });
    },
  });

  // Download authenticated PDF payslip
  const downloadPayslip = async (slipId: number) => {
    try {
      const res = await api.get(`/payslips/${slipId}/pdf`, {
        responseType: 'blob',
      });
      const blob = new Blob([res.data], { type: 'application/pdf' });
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', `payslip_${slipId}.pdf`);
      document.body.appendChild(link);
      link.click();
      link.remove();
    } catch (err: any) {
      setFeedbackMsg({ type: 'error', text: 'Could not download payslip PDF.' });
    }
  };

  const filteredSlips = (slips || []).filter((s) => {
    const q = searchQuery.toLowerCase();
    const matchesSearch =
      (s.employee_name && s.employee_name.toLowerCase().includes(q)) ||
      (s.emp_code && s.emp_code.toLowerCase().includes(q)) ||
      (s.payslip_number && s.payslip_number.toLowerCase().includes(q));

    const matchesPeriod = !selectedPeriod || `${s.year}-${s.month}` === selectedPeriod;
    return matchesSearch && matchesPeriod;
  });

  // Unique periods
  const periods = Array.from(
    new Set((slips || []).map((s) => `${s.year}-${s.month}`))
  );

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex flex-col sm:flex-row justify-between sm:items-center gap-4">
        <div>
          <h1 className="text-3xl font-black text-slate-900 tracking-tight">Payslip Distribution</h1>
          <p className="text-sm font-medium text-slate-500 mt-1">
            Access official stamped PDF salary slips with statutory breakdowns.
          </p>
        </div>
        {isStaff && (
          <div className="flex gap-3">
            <button
              onClick={() => publishMutation.mutate()}
              disabled={publishMutation.isPending}
              className="bg-slate-900 hover:bg-slate-800 text-white px-5 py-2.5 rounded-xl text-sm font-bold transition-all shadow-md flex items-center gap-2 disabled:opacity-50"
            >
              <Send className="w-4 h-4" /> Publish All Drafts
            </button>
          </div>
        )}
      </div>

      {/* Feedback Alert */}
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

      {/* Payslips Container */}
      <div className="bg-white border border-slate-200 rounded-2xl shadow-sm overflow-hidden">
        {/* Toolbar */}
        <div className="p-4 border-b border-slate-200 bg-slate-50/50 flex flex-col sm:flex-row justify-between gap-4">
          <div className="relative max-w-md w-full">
            <Search className="absolute left-3.5 top-2.5 w-4 h-4 text-slate-400" />
            <input
              type="text"
              placeholder="Search by employee name or payslip #..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full bg-white border border-slate-200 rounded-xl pl-10 pr-4 py-2 text-sm font-medium focus:ring-2 focus:ring-blue-600/20 focus:border-blue-600 outline-none"
            />
          </div>
          {periods.length > 0 && (
            <select
              value={selectedPeriod}
              onChange={(e) => setSelectedPeriod(e.target.value)}
              className="bg-white border border-slate-200 text-slate-700 text-sm font-bold rounded-xl px-4 py-2 outline-none focus:border-blue-600"
            >
              <option value="">All Periods</option>
              {periods.map((p) => {
                const [y, m] = p.split('-');
                return (
                  <option key={p} value={p}>
                    {new Date(Number(y), Number(m) - 1).toLocaleString('default', { month: 'long', year: 'numeric' })}
                  </option>
                );
              })}
            </select>
          )}
        </div>

        {/* Content View */}
        {isLoading ? (
          <LoadingSpinner text="Retrieving payslips..." />
        ) : error ? (
          <ErrorState
            title="Failed to load payslips"
            message={getErrorMessage(error)}
            onRetry={() => refetch()}
          />
        ) : filteredSlips.length === 0 ? (
          <EmptyState
            title="No payslips available"
            description="Payslips are generated once a payroll cycle has been calculated and finalized."
            icon={FileText}
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left">
              <thead>
                <tr className="text-xs font-bold text-slate-500 uppercase tracking-wider border-b border-slate-200 bg-slate-50/20">
                  <th className="py-4 px-6">Employee</th>
                  <th className="py-4 px-6">Period</th>
                  <th className="py-4 px-6">Gross Pay</th>
                  <th className="py-4 px-6">Net Pay</th>
                  <th className="py-4 px-6">Status</th>
                  <th className="py-4 px-6 text-right">PDF</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {filteredSlips.map((slip) => (
                  <tr key={slip.id} className="hover:bg-slate-50/80 transition-colors">
                    <td className="py-4 px-6">
                      <div className="font-bold text-slate-900">{slip.employee_name}</div>
                      <div className="text-xs font-mono text-slate-400">
                        {slip.emp_code} • #{slip.payslip_number || slip.id}
                      </div>
                    </td>
                    <td className="py-4 px-6 text-sm font-semibold text-slate-700">
                      {new Date(slip.year, slip.month - 1).toLocaleString('default', { month: 'short', year: 'numeric' })}
                    </td>
                    <td className="py-4 px-6 font-medium text-slate-600 text-sm">
                      ₹{Number(slip.gross_pay || 0).toLocaleString('en-IN')}
                    </td>
                    <td className="py-4 px-6 font-black text-slate-900 text-base">
                      ₹{Number(slip.net_pay || 0).toLocaleString('en-IN')}
                    </td>
                    <td className="py-4 px-6">
                      <span
                        className={`inline-flex items-center px-2.5 py-1 rounded-full text-xs font-bold ${
                          slip.status === 'Published'
                            ? 'bg-emerald-100 text-emerald-700'
                            : 'bg-amber-100 text-amber-700'
                        }`}
                      >
                        {slip.status}
                      </span>
                    </td>
                    <td className="py-4 px-6 text-right">
                      <button
                        onClick={() => downloadPayslip(slip.id)}
                        className="bg-blue-50 hover:bg-blue-100 text-blue-700 px-3.5 py-1.5 rounded-lg text-xs font-bold transition-colors inline-flex items-center gap-1.5 shadow-sm"
                        title="Download authenticated salary slip PDF"
                      >
                        <Download className="w-3.5 h-3.5" /> PDF
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}