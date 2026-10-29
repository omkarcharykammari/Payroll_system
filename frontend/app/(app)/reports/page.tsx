'use client';

import React, { useState } from 'react';
import { FileBarChart, PieChart, TrendingUp, Download, Building2, Users, FileText } from 'lucide-react';
import { api } from '@/lib/api';

export default function ReportsPage() {
  const [downloading, setDownloading] = useState<string | null>(null);

  const reportCards = [
    { 
      id: 'payroll-register', 
      title: 'Payroll Register', 
      desc: 'Complete monthly register with employee earnings, deductions, and net disbursements.', 
      icon: FileBarChart, 
      color: 'text-blue-600', 
      bg: 'bg-blue-100',
      hasCsv: true,
      hasXlsx: true,
    },
    { 
      id: 'bank-advice', 
      title: 'Bank Payment Advice', 
      desc: 'Bank disbursement instruction format with account numbers, IFSC codes, and payout totals.', 
      icon: Building2, 
      color: 'text-indigo-600', 
      bg: 'bg-indigo-100',
      hasCsv: true,
      hasXlsx: true,
    },
    { 
      id: 'epf-ecr', 
      title: 'EPF ECR Return', 
      desc: 'Statutory Provident Fund Electronic Challan cum Return compliance export format.', 
      icon: TrendingUp, 
      color: 'text-emerald-600', 
      bg: 'bg-emerald-100',
      hasCsv: true,
      hasXlsx: false,
    },
    { 
      id: 'esic-return', 
      title: 'ESIC Monthly Return', 
      desc: 'Employee State Insurance monthly wage and contribution declaration spreadsheet.', 
      icon: Users, 
      color: 'text-amber-600', 
      bg: 'bg-amber-100',
      hasCsv: true,
      hasXlsx: true,
    },
  ];

  const handleExport = async (reportId: string, format: 'csv' | 'xlsx') => {
    setDownloading(`${reportId}-${format}`);
    try {
      const res = await api.get(`/reports/${reportId}?format=${format}`, {
        responseType: 'blob',
      });
      const blob = new Blob([res.data]);
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${reportId}_export.${format}`;
      document.body.appendChild(a);
      a.click();
      a.remove();
    } catch (err) {
      alert('Report generation failed. Please ensure a completed payroll run exists.');
    } finally {
      setDownloading(null);
    }
  };

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-3xl font-black text-slate-900 tracking-tight">Compliance & Financial Reports</h1>
        <p className="text-sm font-medium text-slate-500 mt-1">
          Export audited statutory reports, bank transfer schedules, and register books.
        </p>
      </div>

      {/* Reports Grid */}
      <div className="grid md:grid-cols-2 gap-6">
        {reportCards.map((report) => {
          const Icon = report.icon;
          return (
            <div
              key={report.id}
              className="bg-white p-6 rounded-2xl border border-slate-200 shadow-sm hover:shadow-md transition-all flex flex-col justify-between"
            >
              <div className="flex items-start gap-4 mb-6">
                <div className={`w-12 h-12 rounded-xl flex items-center justify-center flex-shrink-0 ${report.bg} ${report.color}`}>
                  <Icon className="w-6 h-6" />
                </div>
                <div>
                  <h3 className="font-bold text-slate-900 text-lg">{report.title}</h3>
                  <p className="text-sm font-medium text-slate-500 mt-1">{report.desc}</p>
                </div>
              </div>

              <div className="flex gap-2 justify-end pt-4 border-t border-slate-100">
                {report.hasCsv && (
                  <button
                    onClick={() => handleExport(report.id, 'csv')}
                    disabled={downloading === `${report.id}-csv`}
                    className="bg-slate-100 hover:bg-slate-200 text-slate-700 px-3 py-1.5 rounded-lg text-xs font-bold transition-all flex items-center gap-1.5 shadow-sm disabled:opacity-50"
                  >
                    <Download className="w-3.5 h-3.5" /> CSV
                  </button>
                )}
                {report.hasXlsx && (
                  <button
                    onClick={() => handleExport(report.id, 'xlsx')}
                    disabled={downloading === `${report.id}-xlsx`}
                    className="bg-blue-50 hover:bg-blue-100 text-blue-700 px-3 py-1.5 rounded-lg text-xs font-bold transition-all flex items-center gap-1.5 shadow-sm disabled:opacity-50"
                  >
                    <Download className="w-3.5 h-3.5" /> Excel (.xlsx)
                  </button>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}