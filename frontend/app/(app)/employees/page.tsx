'use client';

import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { 
  Search, Plus, Filter, Mail, Phone, Upload, 
  Check, X, AlertCircle, FileUp, Download, Send 
} from 'lucide-react';
import { api, EmployeeItem, getErrorMessage } from '@/lib/api';
import { useAuth } from '@/lib/auth-context';
import { LoadingSpinner, ErrorState, EmptyState } from '@/components/FeedbackStates';

export default function EmployeesPage() {
  const queryClient = useQueryClient();
  const { user, isStaff } = useAuth();

  const [searchQuery, setSearchQuery] = useState('');
  const [selectedDept, setSelectedDept] = useState('ALL');
  const [showAddModal, setShowAddModal] = useState(false);
  const [showImportModal, setShowImportModal] = useState(false);
  const [feedbackMsg, setFeedbackMsg] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  // Form states for adding employee
  const [formData, setFormData] = useState({
    emp_code: '',
    first_name: '',
    last_name: '',
    work_email: '',
    phone: '',
    designation: '',
    employment_type: 'Full-time',
    annual_ctc: '',
    date_of_joining: new Date().toISOString().split('T')[0],
  });

  // Bulk import file state
  const [csvFile, setCsvFile] = useState<File | null>(null);
  const [importResult, setImportResult] = useState<any>(null);

  // Fetch employees
  const { data: employees, isLoading, error, refetch } = useQuery<EmployeeItem[]>({
    queryKey: ['employees'],
    queryFn: async () => {
      const res = await api.get('/employees');
      return res.data;
    },
  });

  // Create employee mutation
  const createMutation = useMutation({
    mutationFn: async (payload: any) => {
      const res = await api.post('/employees', payload);
      return res.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['employees'] });
      setShowAddModal(false);
      setFormData({
        emp_code: '',
        first_name: '',
        last_name: '',
        work_email: '',
        phone: '',
        designation: '',
        employment_type: 'Full-time',
        annual_ctc: '',
        date_of_joining: new Date().toISOString().split('T')[0],
      });
      setFeedbackMsg({ type: 'success', text: 'Employee added successfully!' });
      setTimeout(() => setFeedbackMsg(null), 4000);
    },
    onError: (err: any) => {
      setFeedbackMsg({ type: 'error', text: getErrorMessage(err) });
    },
  });

  // Send invite mutation
  const inviteMutation = useMutation({
    mutationFn: async (empId: number) => {
      const res = await api.post(`/employees/${empId}/invite`);
      return res.data;
    },
    onSuccess: (data) => {
      setFeedbackMsg({ 
        type: 'success', 
        text: `Invitation sent! In dev mode, check Mailpit or use invite link: ${data.invite_url || ''}` 
      });
      setTimeout(() => setFeedbackMsg(null), 6000);
    },
    onError: (err: any) => {
      setFeedbackMsg({ type: 'error', text: getErrorMessage(err) });
    },
  });

  // Bulk CSV Import mutation
  const importMutation = useMutation({
    mutationFn: async (file: File) => {
      const form = new FormData();
      form.append('file', file);
      const res = await api.post('/employees/bulk-import', form, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      return res.data;
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['employees'] });
      setImportResult(data);
      setCsvFile(null);
      setFeedbackMsg({
        type: 'success',
        text: `Import completed! Created: ${data.created_count}, Skipped: ${data.errors?.length || 0}`,
      });
    },
    onError: (err: any) => {
      setFeedbackMsg({ type: 'error', text: getErrorMessage(err) });
    },
  });

  // Filtered employees list
  const filteredEmployees = (employees || []).filter((emp) => {
    const fullName = `${emp.first_name} ${emp.last_name}`.toLowerCase();
    const query = searchQuery.toLowerCase();
    const matchesSearch =
      fullName.includes(query) ||
      (emp.emp_code && emp.emp_code.toLowerCase().includes(query)) ||
      (emp.work_email && emp.work_email.toLowerCase().includes(query)) ||
      (emp.designation && emp.designation.toLowerCase().includes(query));

    const matchesDept =
      selectedDept === 'ALL' ||
      (emp.department?.name && emp.department.name === selectedDept);

    return matchesSearch && matchesDept;
  });

  // Unique departments for filter
  const departments = Array.from(
    new Set(
      (employees || [])
        .map((e) => e.department?.name)
        .filter((d): d is string => Boolean(d))
    )
  );

  return (
    <div className="space-y-8">
      {/* Page Header */}
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
        <div>
          <h1 className="text-3xl font-black text-slate-900 tracking-tight">Employee Directory</h1>
          <p className="text-sm font-medium text-slate-500 mt-1">
            Manage employee records, statutory details, and send platform invites.
          </p>
        </div>
        {isStaff && (
          <div className="flex items-center gap-3">
            <button
              onClick={() => {
                setShowImportModal(true);
                setImportResult(null);
              }}
              className="bg-white border border-slate-200 hover:bg-slate-50 text-slate-700 px-4 py-2.5 rounded-xl text-sm font-bold transition-all shadow-sm flex items-center gap-2"
            >
              <Upload className="w-4 h-4" /> Bulk Import
            </button>
            <button
              onClick={() => setShowAddModal(true)}
              className="bg-blue-600 hover:bg-blue-700 text-white px-5 py-2.5 rounded-xl text-sm font-bold transition-all shadow-lg shadow-blue-600/20 flex items-center gap-2"
            >
              <Plus className="w-5 h-5" /> Add Employee
            </button>
          </div>
        )}
      </div>

      {/* Feedback Alert Toast */}
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

      {/* Directory Table Card */}
      <div className="bg-white border border-slate-200 rounded-2xl shadow-sm overflow-hidden">
        {/* Toolbar */}
        <div className="p-5 border-b border-slate-100 bg-slate-50/50 flex flex-col sm:flex-row gap-4 justify-between items-center">
          <div className="relative w-full sm:w-96">
            <Search className="absolute left-3.5 top-2.5 w-4 h-4 text-slate-400" />
            <input
              type="text"
              placeholder="Search by name, role, email, or code..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full bg-white border border-slate-200 rounded-xl pl-10 pr-4 py-2 text-sm font-medium focus:ring-2 focus:ring-blue-600/20 focus:border-blue-600 outline-none transition-all shadow-sm"
            />
          </div>
          <div className="flex items-center gap-3 w-full sm:w-auto">
            <select
              value={selectedDept}
              onChange={(e) => setSelectedDept(e.target.value)}
              className="bg-white border border-slate-200 text-slate-700 text-sm font-bold rounded-xl px-4 py-2 outline-none focus:border-blue-600 shadow-sm w-full sm:w-auto"
            >
              <option value="ALL">All Departments</option>
              {departments.map((dept) => (
                <option key={dept} value={dept}>
                  {dept}
                </option>
              ))}
            </select>
          </div>
        </div>

        {/* Content View */}
        {isLoading ? (
          <LoadingSpinner text="Fetching employee roster..." />
        ) : error ? (
          <ErrorState
            title="Failed to load employee list"
            message={getErrorMessage(error)}
            onRetry={() => refetch()}
          />
        ) : filteredEmployees.length === 0 ? (
          <EmptyState
            title="No employees found"
            description={searchQuery ? `No employees matched "${searchQuery}".` : 'No employee records registered yet.'}
            actionLabel={isStaff ? 'Add New Employee' : undefined}
            onAction={isStaff ? () => setShowAddModal(true) : undefined}
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left">
              <thead>
                <tr className="text-xs font-bold text-slate-500 uppercase tracking-wider border-b border-slate-200 bg-slate-50/20">
                  <th className="py-4 px-6">Employee</th>
                  <th className="py-4 px-6">Code</th>
                  <th className="py-4 px-6">Role & Department</th>
                  <th className="py-4 px-6">Contact</th>
                  <th className="py-4 px-6">Status</th>
                  {isStaff && <th className="py-4 px-6 text-right">Actions</th>}
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {filteredEmployees.map((emp) => {
                  const initials = `${emp.first_name?.[0] || ''}${emp.last_name?.[0] || ''}`.toUpperCase() || 'E';
                  return (
                    <tr key={emp.id} className="hover:bg-slate-50/80 transition-colors">
                      <td className="py-4 px-6">
                        <div className="flex items-center gap-3">
                          <div className="w-10 h-10 rounded-full bg-blue-100 text-blue-700 font-bold flex items-center justify-center text-sm border border-blue-200">
                            {initials}
                          </div>
                          <div>
                            <p className="font-bold text-slate-900">{emp.first_name} {emp.last_name}</p>
                            <p className="text-xs text-slate-400">{emp.employment_type || 'Full-time'}</p>
                          </div>
                        </div>
                      </td>
                      <td className="py-4 px-6 font-mono text-xs font-bold text-slate-600">
                        {emp.emp_code}
                      </td>
                      <td className="py-4 px-6">
                        <p className="font-semibold text-sm text-slate-800">{emp.designation || 'Staff'}</p>
                        <p className="text-xs text-slate-400">{emp.department?.name || 'General'}</p>
                      </td>
                      <td className="py-4 px-6">
                        <p className="text-xs font-medium text-slate-700 flex items-center gap-1.5">
                          <Mail className="w-3.5 h-3.5 text-slate-400" /> {emp.work_email}
                        </p>
                        {emp.phone && (
                          <p className="text-xs font-medium text-slate-500 flex items-center gap-1.5 mt-0.5">
                            <Phone className="w-3.5 h-3.5 text-slate-400" /> {emp.phone}
                          </p>
                        )}
                      </td>
                      <td className="py-4 px-6">
                        <span
                          className={`inline-flex items-center px-2.5 py-1 rounded-full text-xs font-bold ${
                            emp.status === 'Active'
                              ? 'bg-emerald-100 text-emerald-700'
                              : 'bg-slate-100 text-slate-600'
                          }`}
                        >
                          {emp.status}
                        </span>
                      </td>
                      {isStaff && (
                        <td className="py-4 px-6 text-right">
                          <button
                            onClick={() => inviteMutation.mutate(emp.id)}
                            className="bg-slate-100 hover:bg-blue-50 hover:text-blue-600 text-slate-600 px-3 py-1.5 rounded-lg text-xs font-bold transition-all inline-flex items-center gap-1.5 shadow-sm"
                            title="Send platform invitation email"
                          >
                            <Send className="w-3.5 h-3.5" /> Invite
                          </button>
                        </td>
                      )}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Add Employee Modal */}
      {showAddModal && (
        <div className="fixed inset-0 bg-slate-900/50 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl shadow-2xl max-w-xl w-full border border-slate-200 overflow-hidden">
            <div className="p-6 border-b border-slate-100 flex items-center justify-between bg-slate-50/50">
              <h3 className="font-bold text-slate-900 text-lg">Add New Employee</h3>
              <button onClick={() => setShowAddModal(false)} className="text-slate-400 hover:text-slate-700">
                <X className="w-5 h-5" />
              </button>
            </div>
            <form
              onSubmit={(e) => {
                e.preventDefault();
                createMutation.mutate({
                  ...formData,
                  annual_ctc: formData.annual_ctc ? Number(formData.annual_ctc) : undefined,
                });
              }}
              className="p-6 space-y-4"
            >
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="text-xs font-bold text-slate-700 mb-1 block">Employee Code *</label>
                  <input
                    required
                    type="text"
                    placeholder="EMP001"
                    value={formData.emp_code}
                    onChange={(e) => setFormData({ ...formData, emp_code: e.target.value })}
                    className="w-full bg-slate-50 border border-slate-200 rounded-xl px-3.5 py-2 text-sm outline-none focus:border-blue-600"
                  />
                </div>
                <div>
                  <label className="text-xs font-bold text-slate-700 mb-1 block">Joining Date *</label>
                  <input
                    required
                    type="date"
                    value={formData.date_of_joining}
                    onChange={(e) => setFormData({ ...formData, date_of_joining: e.target.value })}
                    className="w-full bg-slate-50 border border-slate-200 rounded-xl px-3.5 py-2 text-sm outline-none focus:border-blue-600"
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="text-xs font-bold text-slate-700 mb-1 block">First Name *</label>
                  <input
                    required
                    type="text"
                    placeholder="First Name"
                    value={formData.first_name}
                    onChange={(e) => setFormData({ ...formData, first_name: e.target.value })}
                    className="w-full bg-slate-50 border border-slate-200 rounded-xl px-3.5 py-2 text-sm outline-none focus:border-blue-600"
                  />
                </div>
                <div>
                  <label className="text-xs font-bold text-slate-700 mb-1 block">Last Name *</label>
                  <input
                    required
                    type="text"
                    placeholder="Last Name"
                    value={formData.last_name}
                    onChange={(e) => setFormData({ ...formData, last_name: e.target.value })}
                    className="w-full bg-slate-50 border border-slate-200 rounded-xl px-3.5 py-2 text-sm outline-none focus:border-blue-600"
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="text-xs font-bold text-slate-700 mb-1 block">Work Email *</label>
                  <input
                    required
                    type="email"
                    placeholder="name@company.com"
                    value={formData.work_email}
                    onChange={(e) => setFormData({ ...formData, work_email: e.target.value })}
                    className="w-full bg-slate-50 border border-slate-200 rounded-xl px-3.5 py-2 text-sm outline-none focus:border-blue-600"
                  />
                </div>
                <div>
                  <label className="text-xs font-bold text-slate-700 mb-1 block">Phone</label>
                  <input
                    type="text"
                    placeholder="+91 9876543210"
                    value={formData.phone}
                    onChange={(e) => setFormData({ ...formData, phone: e.target.value })}
                    className="w-full bg-slate-50 border border-slate-200 rounded-xl px-3.5 py-2 text-sm outline-none focus:border-blue-600"
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="text-xs font-bold text-slate-700 mb-1 block">Designation</label>
                  <input
                    type="text"
                    placeholder="Software Engineer"
                    value={formData.designation}
                    onChange={(e) => setFormData({ ...formData, designation: e.target.value })}
                    className="w-full bg-slate-50 border border-slate-200 rounded-xl px-3.5 py-2 text-sm outline-none focus:border-blue-600"
                  />
                </div>
                <div>
                  <label className="text-xs font-bold text-slate-700 mb-1 block">Annual CTC (₹)</label>
                  <input
                    type="number"
                    placeholder="1200000"
                    value={formData.annual_ctc}
                    onChange={(e) => setFormData({ ...formData, annual_ctc: e.target.value })}
                    className="w-full bg-slate-50 border border-slate-200 rounded-xl px-3.5 py-2 text-sm outline-none focus:border-blue-600"
                  />
                </div>
              </div>

              <div className="flex justify-end gap-3 pt-4 border-t border-slate-100">
                <button
                  type="button"
                  onClick={() => setShowAddModal(false)}
                  className="px-4 py-2 border border-slate-200 rounded-xl text-sm font-bold text-slate-600 hover:bg-slate-50"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={createMutation.isPending}
                  className="bg-blue-600 hover:bg-blue-700 text-white px-5 py-2 rounded-xl text-sm font-bold shadow-md disabled:opacity-50"
                >
                  {createMutation.isPending ? 'Saving...' : 'Add Employee'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Bulk CSV Import Modal */}
      {showImportModal && (
        <div className="fixed inset-0 bg-slate-900/50 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl shadow-2xl max-w-lg w-full border border-slate-200 overflow-hidden">
            <div className="p-6 border-b border-slate-100 flex items-center justify-between bg-slate-50/50">
              <h3 className="font-bold text-slate-900 text-lg">Bulk Employee CSV Import</h3>
              <button onClick={() => setShowImportModal(false)} className="text-slate-400 hover:text-slate-700">
                <X className="w-5 h-5" />
              </button>
            </div>
            <div className="p-6 space-y-4">
              <p className="text-xs text-slate-500">
                Upload a CSV file containing columns: <code className="bg-slate-100 px-1 py-0.5 rounded font-mono text-[11px]">emp_code, first_name, last_name, work_email, designation, annual_ctc</code>.
              </p>

              <div className="border-2 border-dashed border-slate-200 rounded-2xl p-6 text-center hover:border-blue-400 transition-colors">
                <FileUp className="w-8 h-8 text-blue-600 mx-auto mb-2" />
                <input
                  type="file"
                  accept=".csv"
                  onChange={(e) => setCsvFile(e.target.files?.[0] || null)}
                  className="block w-full text-xs text-slate-500 file:mr-4 file:py-2 file:px-4 file:rounded-xl file:border-0 file:text-xs file:font-semibold file:bg-blue-50 file:text-blue-700 hover:file:bg-blue-100 cursor-pointer"
                />
              </div>

              {importResult && (
                <div className="bg-slate-50 border border-slate-200 rounded-xl p-4 text-xs space-y-2">
                  <p className="font-bold text-slate-900">
                    Import Summary: {importResult.created_count} employees added successfully.
                  </p>
                  {importResult.errors?.length > 0 && (
                    <div className="text-rose-600 space-y-1">
                      <p className="font-semibold">Row Validation Warnings:</p>
                      {importResult.errors.slice(0, 4).map((err: any, idx: number) => (
                        <p key={idx}>Row {err.row}: {err.error}</p>
                      ))}
                    </div>
                  )}
                </div>
              )}

              <div className="flex justify-end gap-3 pt-4 border-t border-slate-100">
                <button
                  type="button"
                  onClick={() => setShowImportModal(false)}
                  className="px-4 py-2 border border-slate-200 rounded-xl text-sm font-bold text-slate-600 hover:bg-slate-50"
                >
                  Close
                </button>
                <button
                  type="button"
                  disabled={!csvFile || importMutation.isPending}
                  onClick={() => csvFile && importMutation.mutate(csvFile)}
                  className="bg-blue-600 hover:bg-blue-700 text-white px-5 py-2 rounded-xl text-sm font-bold shadow-md disabled:opacity-50"
                >
                  {importMutation.isPending ? 'Importing...' : 'Upload & Process'}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}