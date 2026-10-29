import { TrendingUp, TrendingDown, Minus } from 'lucide-react';
import { LucideIcon } from 'lucide-react';

interface StatCardProps {
  title: string;
  value: string | number;
  trendValue?: string;
  trend?: 'up' | 'down' | 'neutral';
  icon: LucideIcon;
  iconBg?: string;
  iconColor?: string;
}

export default function StatCard({ 
  title, 
  value, 
  trendValue, 
  trend = 'neutral', 
  icon: Icon,
  iconBg = 'bg-blue-50',
  iconColor = 'text-blue-600'
}: StatCardProps) {
  
  const TrendIcon = trend === 'up' ? TrendingUp : trend === 'down' ? TrendingDown : Minus;
  const trendColor = trend === 'up' ? 'text-emerald-600' : trend === 'down' ? 'text-rose-600' : 'text-slate-500';

  return (
    <div className="bg-white p-6 rounded-2xl border border-slate-200 shadow-sm hover:shadow-md hover:border-blue-200 transition-all group">
      <div className="flex items-start justify-between mb-4">
        <div className={`w-12 h-12 rounded-xl flex items-center justify-center ${iconBg} ${iconColor} group-hover:scale-110 transition-transform`}>
          <Icon className="w-6 h-6" />
        </div>
        {trendValue && (
          <div className={`flex items-center gap-1 text-xs font-bold px-2 py-1 rounded-full bg-slate-50 ${trendColor}`}>
            <TrendIcon className="w-3 h-3" />
            {trendValue}
          </div>
        )}
      </div>
      <div>
        <h3 className="text-3xl font-black text-slate-900 tracking-tight">{value}</h3>
        <p className="text-sm font-semibold text-slate-500 mt-1">{title}</p>
      </div>
    </div>
  );
}