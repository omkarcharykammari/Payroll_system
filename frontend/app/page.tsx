// frontend/app/page.tsx
import Link from 'next/link';
import { ArrowRight, CheckCircle2, BarChart3, Users, Wallet, Shield, ChevronRight } from 'lucide-react';

export default function LandingPage() {
  return (
    <div className="min-h-screen bg-[#F8FAFC] text-slate-900 font-sans selection:bg-blue-600 selection:text-white">
      {/* Navigation */}
      <nav className="fixed w-full z-50 bg-white/80 backdrop-blur-lg border-b border-slate-200/80">
        <div className="max-w-7xl mx-auto px-6 h-20 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 bg-blue-600 rounded-xl flex items-center justify-center shadow-lg shadow-blue-600/20">
              <svg className="w-6 h-6 text-white" width="24" height="24" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M13 10V3L4 14h7v7l9-11h-7z" />
              </svg>
            </div>
            <span className="text-2xl font-black tracking-tight text-slate-900">Vertex</span>
          </div>
          <div className="hidden md:flex items-center gap-8 font-medium text-slate-600">
            <a href="#platform" className="hover:text-blue-600 transition-colors">Platform</a>
            <a href="#solutions" className="hover:text-blue-600 transition-colors">Solutions</a>
            <a href="#pricing" className="hover:text-blue-600 transition-colors">Pricing</a>
            <a href="#resources" className="hover:text-blue-600 transition-colors">Resources</a>
          </div>
          <div className="flex items-center gap-4">
            <Link href="/login" className="font-semibold text-slate-600 hover:text-slate-900 transition-colors">
              Log in
            </Link>
            <Link href="/login" className="bg-slate-900 hover:bg-slate-800 text-white px-5 py-2.5 rounded-lg font-semibold transition-all shadow-md hover:shadow-xl hover:-translate-y-0.5">
              Book Demo
            </Link>
          </div>
        </div>
      </nav>

      {/* Hero Section */}
      <section className="relative pt-40 pb-32 overflow-hidden">
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top_right,_var(--tw-gradient-stops))] from-blue-100 via-transparent to-transparent opacity-60" />
        <div className="max-w-7xl mx-auto px-6 relative z-10 grid lg:grid-cols-2 gap-16 items-center">
          <div className="max-w-2xl">
            <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-blue-50 border border-blue-100 text-blue-700 font-semibold text-sm mb-6 shadow-sm">
              <span className="flex h-2 w-2 rounded-full bg-blue-600 animate-pulse"></span>
              Vertex Payroll 2.0 is live
            </div>
            <h1 className="text-6xl sm:text-7xl font-extrabold tracking-tight leading-[1.1] mb-8 text-slate-900">
              Run global payroll with <span className="text-transparent bg-clip-text bg-gradient-to-r from-blue-600 to-indigo-600">zero errors.</span>
            </h1>
            <p className="text-xl text-slate-600 leading-relaxed mb-10 max-w-xl">
              The modern, automated HR and payroll platform built for forward-thinking enterprises. Manage compliance, taxes, and benefits in one unified dashboard.
            </p>
            <div className="flex flex-col sm:flex-row items-center gap-4">
              <Link href="/dashboard" className="w-full sm:w-auto bg-blue-600 hover:bg-blue-700 text-white text-lg font-semibold px-8 py-4 rounded-xl transition-all shadow-xl shadow-blue-600/30 flex items-center justify-center gap-2 hover:-translate-y-0.5">
                Explore Dashboard <ArrowRight className="w-5 h-5" />
              </Link>
              <p className="text-sm text-slate-500 font-medium px-4">No credit card required</p>
            </div>
          </div>

          {/* Hero Visual Mockup */}
          <div className="relative w-full aspect-square md:aspect-auto md:h-[600px] perspective-1000">
            <div className="absolute inset-0 bg-gradient-to-tr from-slate-100 to-blue-50 rounded-3xl transform rotate-3 scale-105 border border-slate-200 shadow-2xl" />
            <div className="absolute inset-0 bg-white rounded-3xl border border-slate-200 shadow-xl overflow-hidden flex flex-col">
              <div className="h-12 border-b border-slate-100 flex items-center px-4 gap-2 bg-slate-50/50">
                <div className="flex gap-1.5">
                  <div className="w-3 h-3 rounded-full bg-rose-400" />
                  <div className="w-3 h-3 rounded-full bg-amber-400" />
                  <div className="w-3 h-3 rounded-full bg-emerald-400" />
                </div>
              </div>
              <div className="flex-1 p-6 bg-slate-50">
                <div className="flex justify-between items-center mb-6">
                  <div>
                    <div className="h-4 w-32 bg-slate-200 rounded-md mb-2" />
                    <div className="h-8 w-48 bg-slate-300 rounded-lg" />
                  </div>
                  <div className="h-10 w-32 bg-blue-600 rounded-lg" />
                </div>
                <div className="grid grid-cols-3 gap-4 mb-6">
                  {[1, 2, 3].map((i) => (
                    <div key={i} className="h-24 bg-white rounded-xl border border-slate-100 shadow-sm p-4 flex flex-col justify-between">
                      <div className="h-3 w-16 bg-slate-100 rounded" />
                      <div className="h-6 w-24 bg-slate-200 rounded" />
                    </div>
                  ))}
                </div>
                <div className="h-48 bg-white rounded-xl border border-slate-100 shadow-sm p-4">
                   <div className="h-4 w-full bg-slate-100 rounded mb-3" />
                   <div className="h-4 w-5/6 bg-slate-100 rounded mb-3" />
                   <div className="h-4 w-4/6 bg-slate-100 rounded" />
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Trust & Features */}
      <section className="py-24 bg-white border-y border-slate-200">
        <div className="max-w-7xl mx-auto px-6">
          <div className="text-center mb-20">
            <h2 className="text-4xl font-extrabold text-slate-900 mb-6">Everything HR, centralized.</h2>
            <p className="text-xl text-slate-600 max-w-2xl mx-auto">Replace fragmented tools with a single source of truth for your entire workforce lifecycle.</p>
          </div>
          
          <div className="grid md:grid-cols-3 gap-10">
            {[
              {
                icon: Wallet,
                title: "1-Click Payroll",
                desc: "Automate tax calculations, deductions, and direct deposits across 150+ countries with complete compliance.",
                color: "bg-emerald-100 text-emerald-600"
              },
              {
                icon: Users,
                title: "Core HR & Benefits",
                desc: "Manage employee records, time-off requests, and health benefits from intuitive self-service portals.",
                color: "bg-blue-100 text-blue-600"
              },
              {
                icon: Shield,
                title: "Enterprise Security",
                desc: "Bank-grade encryption, SOC 2 Type II compliance, and granular role-based access control.",
                color: "bg-indigo-100 text-indigo-600"
              }
            ].map((feature, i) => (
              <div key={i} className="group p-8 rounded-3xl bg-slate-50 border border-slate-100 hover:bg-white hover:shadow-xl hover:shadow-slate-200/50 transition-all duration-300">
                <div className={`w-14 h-14 rounded-2xl flex items-center justify-center mb-6 ${feature.color}`}>
                  <feature.icon className="w-7 h-7" />
                </div>
                <h3 className="text-2xl font-bold text-slate-900 mb-3">{feature.title}</h3>
                <p className="text-slate-600 leading-relaxed">{feature.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>
    </div>
  );
}