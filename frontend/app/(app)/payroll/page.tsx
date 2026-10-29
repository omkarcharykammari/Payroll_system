'use client';

import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { 
  Wallet, PlayCircle, CheckCircle2, AlertCircle, 
  ArrowRight, Check, X, RotateCcw, CreditCard 
} from 'lucide-react';
import { api, PayrollRunItem, getErrorMessage } from '@/lib/api';
import { useAuth } from '@/lib/auth-context';
import { LoadingSpinner, ErrorState, EmptyState } from '@/components/FeedbackStates';

export default function PayrollPage() {
  const queryClient = useQueryClient();
  const { user, isStaff, isAdmin } = useAuth();

  const [feedbackMsg, setFeedbackMsg] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  // Fetch current active run & history
  const { data: runs, isLoading, error, refetch } = useQuery<PayrollRunItem[]>({
    queryKey: ['payrollRuns'],
    queryFn: async () => {
      const res = await api.get('/payroll/runs');
      return res.data;
    },
  });

  const activeRun = runs && runs.length > 0 ? runs[0] : null;

  // Mutation: Start New Run
  const startRunMutation = useMutation({
    mutationFn: async () => {
      const today = new Date();
      const res = await api.post('/payroll/runs', {
        year: today.getFullYear(),
        month: today.getMonth() + 1,
      });
      return res.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['payrollRuns'] });
      setFeedbackMsg({ type: 'success', text: 'New payroll cycle started and computed!' });
      setTimeout(() => setFeedbackMsg(null), 4000);
    },
    onError: (err: any) => {
      setFeedbackMsg({ type: 'error', text: getErrorMessage(err) });
    },
  });

  // Mutation: Review Draft
  const reviewMutation = useMutation({
    mutationFn: async (id: number) => {
      const res = await api.post(`/payroll/runs/${id}/review`);
      return res.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['payrollRuns'] });
      setFeedbackMsg({ type: 'success', text: 'Payroll run marked as Reviewed!' });
      setTimeout(() => setFeedbackMsg(null), 4000);
    },
    onError: (err: any) => {
      setFeedbackMsg({ type: 'error', text: getErrorMessage(err) });
    },
  });

  // Mutation: Finalize Run (Admin/Owner only)
  const finalizeMutation = useMutation({
    mutationFn: async (id: number) => {
      const res = await api.post(`/payroll/runs/${id}/finalize`);
      return res.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['payrollRuns'] });
      setFeedbackMsg({ type: 'success', text: 'Payroll finalized and locked! Payslips ready.' });
      setTimeout(() => setFeedbackMsg(null), 4000);
    },
    onError: (err: any) => {
      setFeedbackMsg({ type: 'error', text: getErrorMessage(err) });
    },
  });

  // Mutation: Mark Paid (Admin/Owner only)
  const markPaidMutation = useMutation({
    mutationFn: async (id: number) => {
      const res = await api.post(`/payroll/runs/${id}/mark-paid`);
      return res.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['payrollRuns'] });
      setFeedbackMsg({ type: 'success', text: 'Salaries marked as Paid! Notification dispatched.' });
      setTimeout(() => setFeedbackMsg(null), 4000);
    },
    onError: (err: any) => {
      setFeedbackMsg({ type: 'error', text: getErrorMessage(err) });
    },
  });

  // Mutation: Reopen Run (Admin/Owner only)
  const reopenMutation = useMutation({
    mutationFn: async ({ id, note }: { id: number; note: string }) => {
      const res = await api.post(`/payroll/runs/${id}/reopen`, { note });
      return res.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['payrollRuns'] });
      setFeedbackMsg({ type: 'success', text: 'Payroll reopened for recalculation.' });
      setTimeout(() => setFeedbackMsg(null), 4000);
    },
    onError: (err: any) => {
      setFeedbackMsg({ type: 'error', text: getErrorMessage(err) });
    },
  });

  if (isLoading) return <LoadingSpinner text="Retrieving payroll runs..." />;
  if (error) {
    return (
      <ErrorState
        title="Failed to load payroll"
        message={getErrorMessage(error)}
        onRetry={() => refetch()}
      />
    );
  }

  const steps = activeRun?.steps || [
    { name: 'Data Sync', status: 'DONE' },
    { name: 'Calculations', status: 'DONE' },
    { name: 'Review', status: activeRun?.status === 'DRAFT' ? 'IN_PROGRESS' : 'DONE' },
    { name: 'Approval', status: activeRun?.status === 'REVIEWED' ? 'IN_PROGRESS' : activeRun?.status === 'FINALIZED' || activeRun?.status === 'PAID' ? 'DONE' : 'PENDING' },
    { name: 'Payment', status: activeRun?.status === 'PAID' ? 'DONE' : activeRun?.status === 'FINALIZED' ? 'IN_PROGRESS' : 'PENDING' },
  ];

  return (
    <div className="space-y-8">
      {/* Page Header */}
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
        <div>
          <h1 className="text-3xl font-black text-slate-900 tracking-tight">Payroll Processing</h1>
          <p className="text-sm font-medium text-slate-500 mt-1">
            Execute monthly salary calculations, statutory deductions, approvals, and payouts.
          </p>
        </div>
        {isStaff && (
          <button
            onClick={() => startRunMutation.mutate()}
            disabled={startRunMutation.isPending}
            className="bg-slate-900 hover:bg-slate-800 text-white px-5 py-2.5 rounded-xl text-sm font-bold transition-all shadow-lg shadow-slate-900/20 flex items-center gap-2 disabled:opacity-50"
          >
            <PlayCircle className="w-5 h-5" /> Calculate New Run
          </button>
        )}
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

      {/* Active Run Card */}
      {!activeRun ? (
        <EmptyState
          title="No payroll runs initialized"
          description="Click 'Calculate New Run' to execute automated salary calculations for the active month."
          actionLabel={isStaff ? 'Calculate New Run' : undefined}
          onAction={isStaff ? () => startRunMutation.mutate() : undefined}
          icon={Wallet}
        />
      ) : (
        <div className="bg-white border border-slate-200 rounded-2xl shadow-sm p-8 relative overflow-hidden">
          <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-6 mb-8">
            <div>
              <div className="inline-flex items-center px-2.5 py-1 rounded-md bg-blue-100 text-blue-700 text-xs font-bold uppercase tracking-wider mb-2">
                Status: {activeRun.status}
              </div>
              <h2 className="text-2xl font-black text-slate-900">{activeRun.label}</h2>
              <p className="text-slate-500 font-medium text-sm mt-0.5">
                Processed for {activeRun.employee_count} eligible employee(s).
              </p>
            </div>

            <div className="text-left md:text-right">
              <p className="text-xs font-bold text-slate-400 uppercase tracking-wider mb-1">
                Total Net Disbursement
              </p>
              <p className="text-3xl font-black text-blue-600">
                ₹{Number(activeRun.total_net || 0).toLocaleString('en-IN')}
              </p>
              <p className="text-xs text-slate-500 font-medium mt-0.5">
                Gross: ₹{Number(activeRun.total_gross || 0).toLocaleString('en-IN')} | Deductions: ₹{Number(activeRun.total_deductions || 0).toLocaleString('en-IN')}
              </p>
            </div>
          </div>

          {/* Stepper */}
          <div className="grid grid-cols-2 sm:grid-cols-5 gap-3 py-6 border-y border-slate-100">
            {steps.map((st: any, idx: number) => (
              <div
                key={st.name}
                className={`p-3 rounded-xl border flex flex-col items-center text-center ${
                  st.status === 'DONE'
                    ? 'bg-emerald-50/50 border-emerald-200 text-emerald-900'
                    : st.status === 'IN_PROGRESS'
                    ? 'bg-blue-50/50 border-blue-200 text-blue-900'
                    : 'bg-slate-50 border-slate-100 text-slate-400'
                }`}
              >
                <div
                  className={`w-7 h-7 rounded-full flex items-center justify-center font-bold text-xs mb-2 ${
                    st.status === 'DONE'
                      ? 'bg-emerald-600 text-white'
                      : st.status === 'IN_PROGRESS'
                      ? 'bg-blue-600 text-white'
                      : 'bg-slate-200 text-slate-600'
                  }`}
                >
                  {st.status === 'DONE' ? <Check className="w-4 h-4" /> : idx + 1}
                </div>
                <span className="text-xs font-bold text-slate-800">{st.name}</span>
                <span className="text-[10px] font-semibold uppercase tracking-wider text-slate-400 mt-0.5">
                  {st.status}
                </span>
              </div>
            ))}
          </div>

          {/* Lifecycle Action Buttons */}
          <div className="flex flex-wrap gap-3 mt-8 items-center">
            {activeRun.status === 'DRAFT' && isStaff && (
              <button
                onClick={() => reviewMutation.mutate(activeRun.id)}
                disabled={reviewMutation.isPending}
                className="bg-blue-600 hover:bg-blue-700 text-white px-5 py-2.5 rounded-xl text-sm font-bold shadow-md transition-all flex items-center gap-2"
              >
                <Check className="w-4 h-4" /> Submit for Approval
              </button>
            )}

            {activeRun.status === 'REVIEWED' && isAdmin && (
              <button
                onClick={() => finalizeMutation.mutate(activeRun.id)}
                disabled={finalizeMutation.isPending}
                className="bg-emerald-600 hover:bg-emerald-700 text-white px-5 py-2.5 rounded-xl text-sm font-bold shadow-md transition-all flex items-center gap-2"
              >
                <CheckCircle2 className="w-4 h-4" /> Approve & Finalize
              </button>
            )}

            {activeRun.status === 'FINALIZED' && isAdmin && (
              <button
                onClick={() => markPaidMutation.mutate(activeRun.id)}
                disabled={markPaidMutation.isPending}
                className="bg-blue-600 hover:bg-blue-700 text-white px-5 py-2.5 rounded-xl text-sm font-bold shadow-md transition-all flex items-center gap-2"
              >
                <CreditCard className="w-4 h-4" /> Mark as Paid
              </button>
            )}

            {(activeRun.status === 'REVIEWED' || activeRun.status === 'FINALIZED') && isAdmin && (
              <button
                onClick={() => reopenMutation.mutate({ id: activeRun.id, note: 'Adjustments required' })}
                disabled={reopenMutation.isPending}
                className="bg-white border border-slate-200 hover:bg-slate-50 text-slate-700 px-4 py-2.5 rounded-xl text-sm font-bold shadow-sm transition-all flex items-center gap-2"
              >
                <RotateCcw className="w-4 h-4" /> Reopen Run
              </button>
            )}
          </div>
        </div>
      )}

      {/* History of Past Runs */}
      {runs && runs.length > 1 && (
        <div className="bg-white border border-slate-200 rounded-2xl p-6 shadow-sm">
          <h3 className="font-bold text-slate-900 text-lg mb-4">Historical Payroll Cycles</h3>
          <div className="divide-y divide-slate-100">
            {runs.slice(1).map((r) => (
              <div key={r.id} className="py-4 flex justify-between items-center">
                <div>
                  <p className="font-bold text-slate-900">{r.label}</p>
                  <p className="text-xs text-slate-500">
                    {r.employee_count} employees • Net: ₹{Number(r.total_net || 0).toLocaleString('en-IN')}
                  </p>
                </div>
                <span className="px-2.5 py-1 bg-slate-100 text-slate-700 text-xs font-bold rounded-full">
                  {r.status}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}