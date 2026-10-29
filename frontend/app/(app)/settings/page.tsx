'use client';

import React, { useState, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { 
  User, Shield, Building, Save, Check, AlertCircle, 
  X, Upload, FileText, Send, Clock, CheckCircle 
} from 'lucide-react';
import { api, getErrorMessage } from '@/lib/api';
import { useAuth } from '@/lib/auth-context';
import { LoadingSpinner, ErrorState } from '@/components/FeedbackStates';

export default function SettingsPage() {
  const queryClient = useQueryClient();
  const { user, isStaff, isAdmin, refreshUser } = useAuth();

  const [activeTab, setActiveTab] = useState('profile');
  const [feedbackMsg, setFeedbackMsg] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  // Profile Form state
  const [profileData, setProfileData] = useState({
    first_name: '',
    last_name: '',
    phone: '',
    current_address: '',
    gender: 'Other',
    emergency_contact: '',
  });

  // Sensitive change request state
  const [changeField, setChangeField] = useState('bank_account_number');
  const [newValue, setNewValue] = useState('');
  const [changeReason, setChangeReason] = useState('');

  // Company Form state (Admin only)
  const [companyData, setCompanyData] = useState({
    name: '',
    legal_name: '',
    state: '',
    pan: '',
    tan: '',
    gstin: '',
    pf_establishment_code: '',
    address: '',
  });

  // Load employee profile
  const { data: employeeProfile, isLoading: profileLoading } = useQuery({
    queryKey: ['myProfile'],
    queryFn: async () => {
      const res = await api.get('/employees/me');
      return res.data;
    },
    enabled: Boolean(user?.employee_id),
  });

  // Load company details (Admin only)
  const { data: companyDetails } = useQuery({
    queryKey: ['companySettings'],
    queryFn: async () => {
      const res = await api.get('/settings/company');
      return res.data;
    },
    enabled: Boolean(isAdmin),
  });

  // Load profile change requests
  const { data: changeRequests } = useQuery({
    queryKey: ['changeRequests'],
    queryFn: async () => {
      const endpoint = isStaff ? '/change-requests' : '/employees/me/change-requests';
      const res = await api.get(endpoint);
      return res.data;
    },
  });

  // Synchronize state
  useEffect(() => {
    if (employeeProfile) {
      setProfileData({
        first_name: employeeProfile.first_name || '',
        last_name: employeeProfile.last_name || '',
        phone: employeeProfile.phone || '',
        current_address: employeeProfile.current_address || '',
        gender: employeeProfile.gender || 'Other',
        emergency_contact: employeeProfile.emergency_contact || '',
      });
    }
  }, [employeeProfile]);

  useEffect(() => {
    if (companyDetails) {
      setCompanyData({
        name: companyDetails.name || '',
        legal_name: companyDetails.legal_name || '',
        state: companyDetails.state || '',
        pan: companyDetails.pan || '',
        tan: companyDetails.tan || '',
        gstin: companyDetails.gstin || '',
        pf_establishment_code: companyDetails.pf_establishment_code || '',
        address: companyDetails.address || '',
      });
    }
  }, [companyDetails]);

  // Update profile mutation
  const updateProfileMutation = useMutation({
    mutationFn: async (payload: any) => {
      const res = await api.patch('/employees/me', payload);
      return res.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['myProfile'] });
      refreshUser();
      setFeedbackMsg({ type: 'success', text: 'Profile details updated successfully!' });
      setTimeout(() => setFeedbackMsg(null), 4000);
    },
    onError: (err: any) => {
      setFeedbackMsg({ type: 'error', text: getErrorMessage(err) });
    },
  });

  // Submit sensitive change request mutation
  const submitRequestMutation = useMutation({
    mutationFn: async (payload: any) => {
      const res = await api.post('/employees/me/change-requests', payload);
      return res.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['changeRequests'] });
      setNewValue('');
      setChangeReason('');
      setFeedbackMsg({ type: 'success', text: 'Change request submitted for HR approval!' });
      setTimeout(() => setFeedbackMsg(null), 4000);
    },
    onError: (err: any) => {
      setFeedbackMsg({ type: 'error', text: getErrorMessage(err) });
    },
  });

  // Review change request mutation (Staff only)
  const reviewRequestMutation = useMutation({
    mutationFn: async ({ id, action, note }: { id: number; action: string; note: string }) => {
      const res = await api.post(`/change-requests/${id}/review`, { action, note });
      return res.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['changeRequests'] });
      queryClient.invalidateQueries({ queryKey: ['myProfile'] });
      setFeedbackMsg({ type: 'success', text: 'Request reviewed successfully!' });
      setTimeout(() => setFeedbackMsg(null), 4000);
    },
    onError: (err: any) => {
      setFeedbackMsg({ type: 'error', text: getErrorMessage(err) });
    },
  });

  // Update company mutation (Admin only)
  const updateCompanyMutation = useMutation({
    mutationFn: async (payload: any) => {
      const res = await api.put('/settings/company', payload);
      return res.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['companySettings'] });
      setFeedbackMsg({ type: 'success', text: 'Company details updated successfully!' });
      setTimeout(() => setFeedbackMsg(null), 4000);
    },
    onError: (err: any) => {
      setFeedbackMsg({ type: 'error', text: getErrorMessage(err) });
    },
  });

  const tabs = [
    { id: 'profile', label: 'My Profile', icon: User },
    { id: 'requests', label: 'Change Requests', icon: Shield },
    ...(isAdmin ? [{ id: 'company', label: 'Company Profile', icon: Building }] : []),
  ];

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-3xl font-black text-slate-900 tracking-tight">Settings & Profile</h1>
        <p className="text-slate-500 font-medium mt-1">
          Manage personal self-service data, sensitive change approvals, and company config.
        </p>
      </div>

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

      <div className="flex flex-col lg:flex-row gap-8">
        {/* Navigation Sidebar */}
        <aside className="w-full lg:w-64 flex-shrink-0">
          <nav className="flex flex-row lg:flex-col gap-1 overflow-x-auto pb-4 lg:pb-0">
            {tabs.map((tab) => {
              const Icon = tab.icon;
              const isActive = activeTab === tab.id;
              return (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id)}
                  className={`flex items-center gap-3 px-4 py-3 rounded-xl font-bold text-sm transition-all whitespace-nowrap ${
                    isActive
                      ? 'bg-white text-blue-700 shadow-sm border border-slate-200'
                      : 'text-slate-500 hover:text-slate-900 hover:bg-slate-100/50'
                  }`}
                >
                  <Icon className={`w-5 h-5 ${isActive ? 'text-blue-600' : 'text-slate-400'}`} />
                  {tab.label}
                </button>
              );
            })}
          </nav>
        </aside>

        {/* Content Tabs */}
        <div className="flex-1 space-y-6">
          {/* 1. My Profile Tab */}
          {activeTab === 'profile' && (
            <div className="bg-white border border-slate-200 rounded-2xl shadow-sm overflow-hidden p-6">
              <div className="border-b border-slate-100 pb-4 mb-6">
                <h2 className="text-lg font-bold text-slate-900">Personal Information</h2>
                <p className="text-xs text-slate-500">
                  Update your contact details, emergency information, and address.
                </p>
              </div>

              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  updateProfileMutation.mutate(profileData);
                }}
                className="space-y-4 max-w-2xl"
              >
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="text-xs font-bold text-slate-700 mb-1 block">First Name</label>
                    <input
                      type="text"
                      value={profileData.first_name}
                      onChange={(e) => setProfileData({ ...profileData, first_name: e.target.value })}
                      className="w-full bg-slate-50 border border-slate-200 rounded-xl px-3.5 py-2 text-sm outline-none focus:border-blue-600"
                    />
                  </div>
                  <div>
                    <label className="text-xs font-bold text-slate-700 mb-1 block">Last Name</label>
                    <input
                      type="text"
                      value={profileData.last_name}
                      onChange={(e) => setProfileData({ ...profileData, last_name: e.target.value })}
                      className="w-full bg-slate-50 border border-slate-200 rounded-xl px-3.5 py-2 text-sm outline-none focus:border-blue-600"
                    />
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="text-xs font-bold text-slate-700 mb-1 block">Phone Number</label>
                    <input
                      type="text"
                      value={profileData.phone}
                      onChange={(e) => setProfileData({ ...profileData, phone: e.target.value })}
                      className="w-full bg-slate-50 border border-slate-200 rounded-xl px-3.5 py-2 text-sm outline-none focus:border-blue-600"
                    />
                  </div>
                  <div>
                    <label className="text-xs font-bold text-slate-700 mb-1 block">Emergency Contact</label>
                    <input
                      type="text"
                      placeholder="Name: +91 9876543210"
                      value={profileData.emergency_contact}
                      onChange={(e) => setProfileData({ ...profileData, emergency_contact: e.target.value })}
                      className="w-full bg-slate-50 border border-slate-200 rounded-xl px-3.5 py-2 text-sm outline-none focus:border-blue-600"
                    />
                  </div>
                </div>

                <div>
                  <label className="text-xs font-bold text-slate-700 mb-1 block">Residential Address</label>
                  <textarea
                    rows={2}
                    value={profileData.current_address}
                    onChange={(e) => setProfileData({ ...profileData, current_address: e.target.value })}
                    className="w-full bg-slate-50 border border-slate-200 rounded-xl px-3.5 py-2 text-sm outline-none focus:border-blue-600"
                  />
                </div>

                <div className="flex justify-end pt-4">
                  <button
                    type="submit"
                    disabled={updateProfileMutation.isPending}
                    className="bg-blue-600 hover:bg-blue-700 text-white px-5 py-2.5 rounded-xl text-sm font-bold shadow-md transition-all flex items-center gap-2 disabled:opacity-50"
                  >
                    <Save className="w-4 h-4" /> Save Profile
                  </button>
                </div>
              </form>
            </div>
          )}

          {/* 2. Change Requests Tab */}
          {activeTab === 'requests' && (
            <div className="space-y-6">
              {/* Employee Submission Form */}
              <div className="bg-white border border-slate-200 rounded-2xl p-6 shadow-sm">
                <div className="border-b border-slate-100 pb-3 mb-4">
                  <h3 className="font-bold text-slate-900 text-base">Request Sensitive Data Update</h3>
                  <p className="text-xs text-slate-500">
                    Bank accounts, PAN, and UAN require HR approval before taking effect.
                  </p>
                </div>

                <form
                  onSubmit={(e) => {
                    e.preventDefault();
                    submitRequestMutation.mutate({
                      field_name: changeField,
                      new_value: newValue,
                      reason: changeReason,
                    });
                  }}
                  className="space-y-4 max-w-xl"
                >
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <label className="text-xs font-bold text-slate-700 mb-1 block">Field to Update</label>
                      <select
                        value={changeField}
                        onChange={(e) => setChangeField(e.target.value)}
                        className="w-full bg-slate-50 border border-slate-200 rounded-xl px-3 py-2 text-sm outline-none focus:border-blue-600"
                      >
                        <option value="bank_account_number">Bank Account Number</option>
                        <option value="pan_number">PAN Card Number</option>
                        <option value="uan_number">UAN Number</option>
                      </select>
                    </div>
                    <div>
                      <label className="text-xs font-bold text-slate-700 mb-1 block">New Value *</label>
                      <input
                        required
                        type="text"
                        placeholder="Enter updated number"
                        value={newValue}
                        onChange={(e) => setNewValue(e.target.value)}
                        className="w-full bg-slate-50 border border-slate-200 rounded-xl px-3.5 py-2 text-sm outline-none focus:border-blue-600"
                      />
                    </div>
                  </div>

                  <div>
                    <label className="text-xs font-bold text-slate-700 mb-1 block">Reason for Change</label>
                    <input
                      type="text"
                      placeholder="e.g. Switched primary salary account"
                      value={changeReason}
                      onChange={(e) => setChangeReason(e.target.value)}
                      className="w-full bg-slate-50 border border-slate-200 rounded-xl px-3.5 py-2 text-sm outline-none focus:border-blue-600"
                    />
                  </div>

                  <button
                    type="submit"
                    disabled={submitRequestMutation.isPending}
                    className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-xl text-sm font-bold shadow-md disabled:opacity-50 flex items-center gap-2"
                  >
                    <Send className="w-4 h-4" /> Submit Request
                  </button>
                </form>
              </div>

              {/* Pending / Historical Requests List */}
              <div className="bg-white border border-slate-200 rounded-2xl p-6 shadow-sm">
                <h3 className="font-bold text-slate-900 text-base mb-4">
                  {isStaff ? 'Pending Review Requests' : 'My Change Requests'}
                </h3>

                {(!changeRequests || changeRequests.length === 0) ? (
                  <p className="text-sm text-slate-400 py-4 text-center">No change requests found.</p>
                ) : (
                  <div className="divide-y divide-slate-100">
                    {changeRequests.map((req: any) => (
                      <div key={req.id} className="py-4 flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
                        <div>
                          <p className="font-bold text-slate-900 text-sm">
                            {req.field_name}: <span className="font-mono text-blue-600">{req.new_value}</span>
                          </p>
                          <p className="text-xs text-slate-500">
                            Status: <span className="font-semibold">{req.status}</span> • Reason: {req.reason || 'None specified'}
                          </p>
                        </div>

                        {isStaff && req.status === 'pending' && (
                          <div className="flex gap-2">
                            <button
                              onClick={() => reviewRequestMutation.mutate({ id: req.id, action: 'approve', note: 'Approved by HR' })}
                              className="px-3 py-1.5 bg-emerald-50 text-emerald-700 text-xs font-bold rounded-lg border border-emerald-200 hover:bg-emerald-100"
                            >
                              Approve
                            </button>
                            <button
                              onClick={() => reviewRequestMutation.mutate({ id: req.id, action: 'reject', note: 'Insufficient documentation' })}
                              className="px-3 py-1.5 bg-rose-50 text-rose-700 text-xs font-bold rounded-lg border border-rose-200 hover:bg-rose-100"
                            >
                              Reject
                            </button>
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          )}

          {/* 3. Company Profile Tab (Admin only) */}
          {activeTab === 'company' && isAdmin && (
            <div className="bg-white border border-slate-200 rounded-2xl shadow-sm p-6">
              <div className="border-b border-slate-100 pb-4 mb-6">
                <h2 className="text-lg font-bold text-slate-900">Company Legal & Statutory Details</h2>
                <p className="text-xs text-slate-500">
                  Configure corporate identifiers and registered address for compliance documents.
                </p>
              </div>

              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  updateCompanyMutation.mutate(companyData);
                }}
                className="space-y-4 max-w-2xl"
              >
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="text-xs font-bold text-slate-700 mb-1 block">Brand Name *</label>
                    <input
                      required
                      type="text"
                      value={companyData.name}
                      onChange={(e) => setCompanyData({ ...companyData, name: e.target.value })}
                      className="w-full bg-slate-50 border border-slate-200 rounded-xl px-3.5 py-2 text-sm outline-none focus:border-blue-600"
                    />
                  </div>
                  <div>
                    <label className="text-xs font-bold text-slate-700 mb-1 block">Legal Entity Name</label>
                    <input
                      type="text"
                      value={companyData.legal_name}
                      onChange={(e) => setCompanyData({ ...companyData, legal_name: e.target.value })}
                      className="w-full bg-slate-50 border border-slate-200 rounded-xl px-3.5 py-2 text-sm outline-none focus:border-blue-600"
                    />
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="text-xs font-bold text-slate-700 mb-1 block">State (for PTax)</label>
                    <input
                      type="text"
                      placeholder="Maharashtra"
                      value={companyData.state}
                      onChange={(e) => setCompanyData({ ...companyData, state: e.target.value })}
                      className="w-full bg-slate-50 border border-slate-200 rounded-xl px-3.5 py-2 text-sm outline-none focus:border-blue-600"
                    />
                  </div>
                  <div>
                    <label className="text-xs font-bold text-slate-700 mb-1 block">Company PAN</label>
                    <input
                      type="text"
                      placeholder="AAACV1234F"
                      value={companyData.pan}
                      onChange={(e) => setCompanyData({ ...companyData, pan: e.target.value })}
                      className="w-full bg-slate-50 border border-slate-200 rounded-xl px-3.5 py-2 text-sm outline-none focus:border-blue-600"
                    />
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="text-xs font-bold text-slate-700 mb-1 block">TAN Number</label>
                    <input
                      type="text"
                      placeholder="MUMA12345B"
                      value={companyData.tan}
                      onChange={(e) => setCompanyData({ ...companyData, tan: e.target.value })}
                      className="w-full bg-slate-50 border border-slate-200 rounded-xl px-3.5 py-2 text-sm outline-none focus:border-blue-600"
                    />
                  </div>
                  <div>
                    <label className="text-xs font-bold text-slate-700 mb-1 block">GSTIN</label>
                    <input
                      type="text"
                      value={companyData.gstin}
                      onChange={(e) => setCompanyData({ ...companyData, gstin: e.target.value })}
                      className="w-full bg-slate-50 border border-slate-200 rounded-xl px-3.5 py-2 text-sm outline-none focus:border-blue-600"
                    />
                  </div>
                </div>

                <div>
                  <label className="text-xs font-bold text-slate-700 mb-1 block">PF Establishment Code</label>
                  <input
                    type="text"
                    placeholder="MH/BAN/0012345/000"
                    value={companyData.pf_establishment_code}
                    onChange={(e) => setCompanyData({ ...companyData, pf_establishment_code: e.target.value })}
                    className="w-full bg-slate-50 border border-slate-200 rounded-xl px-3.5 py-2 text-sm outline-none focus:border-blue-600"
                  />
                </div>

                <div className="flex justify-end pt-4">
                  <button
                    type="submit"
                    disabled={updateCompanyMutation.isPending}
                    className="bg-blue-600 hover:bg-blue-700 text-white px-5 py-2.5 rounded-xl text-sm font-bold shadow-md transition-all flex items-center gap-2 disabled:opacity-50"
                  >
                    <Save className="w-4 h-4" /> Save Company Details
                  </button>
                </div>
              </form>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}