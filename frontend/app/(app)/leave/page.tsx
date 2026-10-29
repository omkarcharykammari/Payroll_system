'use client';

import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { 
  CalendarDays, Check, X, Clock, Plus, 
  AlertCircle, CheckCircle, Calendar 
} from 'lucide-react';
import { api, LeaveRequestItem, LeaveBalanceItem, getErrorMessage } from '@/lib/api';
import { useAuth } from '@/lib/auth-context';
import { LoadingSpinner, ErrorState, EmptyState } from '@/components/FeedbackStates';

export default function LeavePage() {
  const queryClient = useQueryClient();
  const { user, isStaff } = useAuth();

  const [activeTab, setActiveTab] = useState<'Pending' | 'Approved' | 'All'>('Pending');
  const [showApplyModal, setShowApplyModal] = useState(false);
  const [feedbackMsg, setFeedbackMsg] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  // Application form state
  const [leaveTypeId, setLeaveTypeId] = useState<number | ''>('');
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');
  const [reason, setReason] = useState('');

  // Fetch leave types
  const { data: leaveTypes } = useQuery<{ id: number; name: string; days_per_year: number }[]>({
    queryKey: ['leaveTypes'],
    queryFn: async () => {
      const res = await api.get('/leave/types');
      return res.data;
    },
  });

  // Fetch leave balances for current employee
  const { data: balances } = useQuery<LeaveBalanceItem[]>({
    queryKey: ['leaveBalances'],
    queryFn: async () => {
      const res = await api.get('/leave/balances');
      return res.data;
    },
  });

  // Fetch leave requests
  const { data: requests, isLoading, error, refetch } = useQuery<LeaveRequestItem[]>({
    queryKey: ['leaveRequests'],
    queryFn: async () => {
      const res = await api.get('/leave/requests');
      return res.data;
    },
  });

  // Apply mutation
  const applyMutation = useMutation({
    mutationFn: async (payload: any) => {
      const res = await api.post('/leave/requests', payload);
      return res.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['leaveRequests'] });
      queryClient.invalidateQueries({ queryKey: ['leaveBalances'] });
      setShowApplyModal(false);
      setLeaveTypeId('');
      setStartDate('');
      setEndDate('');
      setReason('');
      setFeedbackMsg({ type: 'success', text: 'Leave application submitted successfully!' });
      setTimeout(() => setFeedbackMsg(null), 4000);
    },
    onError: (err: any) => {
      setFeedbackMsg({ type: 'error', text: getErrorMessage(err) });
    },
  });

  // Approve mutation
  const approveMutation = useMutation({
    mutationFn: async (id: number) => {
      const res = await api.post(`/leave/requests/${id}/approve`);
      return res.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['leaveRequests'] });
      setFeedbackMsg({ type: 'success', text: 'Leave request approved!' });
      setTimeout(() => setFeedbackMsg(null), 4000);
    },
    onError: (err: any) => {
      setFeedbackMsg({ type: 'error', text: getErrorMessage(err) });
    },
  });

  // Deny mutation
  const denyMutation = useMutation({
    mutationFn: async ({ id, note }: { id: number; note: string }) => {
      const res = await api.post(`/leave/requests/${id}/deny`, { review_note: note });
      return res.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['leaveRequests'] });
      setFeedbackMsg({ type: 'success', text: 'Leave request denied.' });
      setTimeout(() => setFeedbackMsg(null), 4000);
    },
    onError: (err: any) => {
      setFeedbackMsg({ type: 'error', text: getErrorMessage(err) });
    },
  });

  const filteredRequests = (requests || []).filter((req) => {
    if (activeTab === 'Pending') return req.status === 'Pending';
    if (activeTab === 'Approved') return req.status === 'Approved';
    return true;
  });

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
        <div>
          <h1 className="text-3xl font-black text-slate-900 tracking-tight">Leave Management</h1>
          <p className="text-sm font-medium text-slate-500 mt-1">
            Review time-off requests, balances, and submit leave applications.
          </p>
        </div>
        <button
          onClick={() => setShowApplyModal(true)}
          className="bg-blue-600 hover:bg-blue-700 text-white px-5 py-2.5 rounded-xl text-sm font-bold transition-all shadow-lg shadow-blue-600/20 flex items-center gap-2"
        >
          <Plus className="w-5 h-5" /> Apply for Leave
        </button>
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

      {/* Balances Grid */}
      {balances && balances.length > 0 && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {balances.map((b) => (
            <div key={b.id} className="bg-white p-5 rounded-2xl border border-slate-200 shadow-sm">
              <p className="text-xs font-bold text-slate-400 uppercase tracking-wider mb-1">
                {b.leave_type_name}
              </p>
              <h3 className="text-2xl font-black text-slate-900">{b.available} Days</h3>
              <p className="text-xs text-slate-500 mt-1">
                Used: {b.used} / Quota: {b.annual_quota}
              </p>
            </div>
          ))}
        </div>
      )}

      {/* Requests Container */}
      <div className="bg-white border border-slate-200 rounded-2xl shadow-sm overflow-hidden">
        {/* Tabs */}
        <div className="flex gap-6 px-6 border-b border-slate-200 bg-slate-50/50">
          {(['Pending', 'Approved', 'All'] as const).map((tab) => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={`py-4 text-sm font-bold border-b-2 transition-colors ${
                activeTab === tab
                  ? 'border-blue-600 text-blue-700'
                  : 'border-transparent text-slate-500 hover:text-slate-800'
              }`}
            >
              {tab} Requests
            </button>
          ))}
        </div>

        {/* Requests List */}
        <div className="p-6">
          {isLoading ? (
            <LoadingSpinner text="Retrieving leave applications..." />
          ) : error ? (
            <ErrorState
              title="Failed to load leave requests"
              message={getErrorMessage(error)}
              onRetry={() => refetch()}
            />
          ) : filteredRequests.length === 0 ? (
            <EmptyState
              title={`No ${activeTab.toLowerCase()} leave requests`}
              description="There are currently no requests in this status."
              icon={CalendarDays}
            />
          ) : (
            <div className="grid gap-4">
              {filteredRequests.map((req) => (
                <div
                  key={req.id}
                  className="flex flex-col sm:flex-row items-start sm:items-center justify-between p-5 rounded-xl border border-slate-200 hover:border-blue-300 transition-colors bg-white"
                >
                  <div className="flex items-center gap-4 mb-4 sm:mb-0">
                    <div
                      className={`w-12 h-12 rounded-full flex items-center justify-center ${
                        req.status === 'Pending'
                          ? 'bg-amber-100 text-amber-600'
                          : req.status === 'Approved'
                          ? 'bg-emerald-100 text-emerald-600'
                          : 'bg-rose-100 text-rose-600'
                      }`}
                    >
                      {req.status === 'Pending' ? (
                        <Clock className="w-5 h-5" />
                      ) : req.status === 'Approved' ? (
                        <Check className="w-5 h-5" />
                      ) : (
                        <X className="w-5 h-5" />
                      )}
                    </div>
                    <div>
                      <h3 className="font-bold text-slate-900">{req.employee_name}</h3>
                      <p className="text-sm font-medium text-slate-500">
                        {req.leave_type_name} • {req.days_count} Day(s)
                      </p>
                      <p className="text-xs font-semibold text-slate-400 mt-1">
                        {new Date(req.start_date).toLocaleDateString()} — {new Date(req.end_date).toLocaleDateString()}
                      </p>
                      {req.reason && (
                        <p className="text-xs text-slate-600 italic mt-1">"{req.reason}"</p>
                      )}
                    </div>
                  </div>

                  {/* Actions */}
                  {req.status === 'Pending' && isStaff ? (
                    <div className="flex gap-2 w-full sm:w-auto">
                      <button
                        onClick={() => approveMutation.mutate(req.id)}
                        disabled={approveMutation.isPending}
                        className="flex-1 sm:flex-none flex items-center justify-center gap-1 bg-emerald-50 text-emerald-700 hover:bg-emerald-100 px-4 py-2 rounded-xl text-sm font-bold transition-colors border border-emerald-200 disabled:opacity-50"
                      >
                        <Check className="w-4 h-4" /> Approve
                      </button>
                      <button
                        onClick={() => denyMutation.mutate({ id: req.id, note: 'Operational requirements' })}
                        disabled={denyMutation.isPending}
                        className="flex-1 sm:flex-none flex items-center justify-center gap-1 bg-rose-50 text-rose-700 hover:bg-rose-100 px-4 py-2 rounded-xl text-sm font-bold transition-colors border border-rose-200 disabled:opacity-50"
                      >
                        <X className="w-4 h-4" /> Deny
                      </button>
                    </div>
                  ) : (
                    <span
                      className={`px-3 py-1 rounded-full text-xs font-bold uppercase tracking-wider ${
                        req.status === 'Approved'
                          ? 'bg-emerald-100 text-emerald-700'
                          : req.status === 'Denied'
                          ? 'bg-rose-100 text-rose-700'
                          : 'bg-slate-100 text-slate-600'
                      }`}
                    >
                      {req.status}
                    </span>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Apply Leave Modal */}
      {showApplyModal && (
        <div className="fixed inset-0 bg-slate-900/50 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl shadow-2xl max-w-lg w-full border border-slate-200 overflow-hidden">
            <div className="p-6 border-b border-slate-100 flex items-center justify-between bg-slate-50/50">
              <h3 className="font-bold text-slate-900 text-lg">Apply for Leave</h3>
              <button onClick={() => setShowApplyModal(false)} className="text-slate-400 hover:text-slate-700">
                <X className="w-5 h-5" />
              </button>
            </div>
            <form
              onSubmit={(e) => {
                e.preventDefault();
                applyMutation.mutate({
                  leave_type_id: Number(leaveTypeId),
                  start_date: startDate,
                  end_date: endDate,
                  reason,
                });
              }}
              className="p-6 space-y-4"
            >
              <div>
                <label className="text-xs font-bold text-slate-700 mb-1 block">Leave Type *</label>
                <select
                  required
                  value={leaveTypeId}
                  onChange={(e) => setLeaveTypeId(Number(e.target.value))}
                  className="w-full bg-slate-50 border border-slate-200 rounded-xl px-3.5 py-2.5 text-sm font-medium outline-none focus:border-blue-600"
                >
                  <option value="">Select leave type</option>
                  {(leaveTypes || []).map((t) => (
                    <option key={t.id} value={t.id}>
                      {t.name} ({t.days_per_year} days/yr)
                    </option>
                  ))}
                </select>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="text-xs font-bold text-slate-700 mb-1 block">Start Date *</label>
                  <input
                    required
                    type="date"
                    value={startDate}
                    onChange={(e) => setStartDate(e.target.value)}
                    className="w-full bg-slate-50 border border-slate-200 rounded-xl px-3.5 py-2 text-sm outline-none focus:border-blue-600"
                  />
                </div>
                <div>
                  <label className="text-xs font-bold text-slate-700 mb-1 block">End Date *</label>
                  <input
                    required
                    type="date"
                    value={endDate}
                    onChange={(e) => setEndDate(e.target.value)}
                    className="w-full bg-slate-50 border border-slate-200 rounded-xl px-3.5 py-2 text-sm outline-none focus:border-blue-600"
                  />
                </div>
              </div>

              <div>
                <label className="text-xs font-bold text-slate-700 mb-1 block">Reason</label>
                <textarea
                  rows={3}
                  placeholder="Optional notes or reason for time off..."
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                  className="w-full bg-slate-50 border border-slate-200 rounded-xl px-3.5 py-2 text-sm outline-none focus:border-blue-600"
                />
              </div>

              <div className="flex justify-end gap-3 pt-4 border-t border-slate-100">
                <button
                  type="button"
                  onClick={() => setShowApplyModal(false)}
                  className="px-4 py-2 border border-slate-200 rounded-xl text-sm font-bold text-slate-600 hover:bg-slate-50"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={applyMutation.isPending}
                  className="bg-blue-600 hover:bg-blue-700 text-white px-5 py-2 rounded-xl text-sm font-bold shadow-md disabled:opacity-50"
                >
                  {applyMutation.isPending ? 'Submitting...' : 'Submit Application'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}