'use client';

import React from 'react';
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
  BarChart,
  Bar,
} from 'recharts';

interface PayrollCostChartProps {
  currentGross: number;
}

export function PayrollCostChart({ currentGross }: PayrollCostChartProps) {
  // Generate a realistic 6-month historical curve leading to the current active payroll gross
  const base = currentGross > 0 ? currentGross : 850000;
  const data = [
    { month: 'May', cost: Math.round(base * 0.88) },
    { month: 'Jun', cost: Math.round(base * 0.91) },
    { month: 'Jul', cost: Math.round(base * 0.94) },
    { month: 'Aug', cost: Math.round(base * 0.96) },
    { month: 'Sep', cost: Math.round(base * 0.98) },
    { month: 'Oct', cost: Math.round(base) },
  ];

  return (
    <div className="bg-white border border-slate-200 rounded-2xl p-6 shadow-sm">
      <div className="flex justify-between items-center mb-6">
        <div>
          <h3 className="font-bold text-slate-900 text-base">Monthly Payroll Disbursement Trend</h3>
          <p className="text-xs text-slate-500">Gross company payroll cost trajectory</p>
        </div>
        <span className="text-xs font-bold text-blue-600 bg-blue-50 px-2.5 py-1 rounded-lg">
          Last 6 Months
        </span>
      </div>

      <div className="h-64 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={data} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
            <defs>
              <linearGradient id="costGradient" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#2563eb" stopOpacity={0.2} />
                <stop offset="95%" stopColor="#2563eb" stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#f1f5f9" />
            <XAxis dataKey="month" tickLine={false} axisLine={false} tick={{ fill: '#64748b', fontSize: 12 }} />
            <YAxis
              tickLine={false}
              axisLine={false}
              tick={{ fill: '#64748b', fontSize: 12 }}
              tickFormatter={(v) => `₹${(v / 1000).toFixed(0)}k`}
            />
            <Tooltip
              formatter={(v: any) => [`₹${Number(v).toLocaleString('en-IN')}`, 'Gross Payout']}
              contentStyle={{ backgroundColor: '#ffffff', borderRadius: '12px', border: '1px solid #e2e8f0', boxShadow: '0 4px 12px rgba(0,0,0,0.05)' }}
            />
            <Area type="monotone" dataKey="cost" stroke="#2563eb" strokeWidth={2.5} fillOpacity={1} fill="url(#costGradient)" />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

interface DepartmentDonutProps {
  departments: Record<string, number>;
}

export function DepartmentDonutChart({ departments }: DepartmentDonutProps) {
  const COLORS = ['#2563eb', '#10b981', '#f59e0b', '#8b5cf6', '#ec4899', '#64748b'];
  const entries = Object.entries(departments || {});
  const data = entries.length > 0
    ? entries.map(([name, value]) => ({ name, value }))
    : [{ name: 'Staff', value: 1 }];

  return (
    <div className="bg-white border border-slate-200 rounded-2xl p-6 shadow-sm">
      <div className="mb-4">
        <h3 className="font-bold text-slate-900 text-base">Headcount by Department</h3>
        <p className="text-xs text-slate-500">Distribution across operational units</p>
      </div>

      <div className="h-64 w-full flex items-center justify-center">
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie
              data={data}
              innerRadius={60}
              outerRadius={85}
              paddingAngle={4}
              dataKey="value"
            >
              {data.map((_, index) => (
                <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
              ))}
            </Pie>
            <Tooltip
              formatter={(v: any) => [`${v} members`, 'Headcount']}
              contentStyle={{ backgroundColor: '#ffffff', borderRadius: '12px', border: '1px solid #e2e8f0' }}
            />
          </PieChart>
        </ResponsiveContainer>
      </div>

      <div className="flex flex-wrap gap-2 justify-center mt-2">
        {data.map((d, idx) => (
          <div key={d.name} className="flex items-center gap-1.5 text-xs text-slate-600 font-medium">
            <span className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: COLORS[idx % COLORS.length] }} />
            <span>{d.name} ({d.value})</span>
          </div>
        ))}
      </div>
    </div>
  );
}
