'use client';

import React from 'react';
import { Loader2, AlertCircle, RefreshCw } from 'lucide-react';

export function LoadingSpinner({ text = 'Loading...' }: { text?: string }) {
  return (
    <div className="flex flex-col items-center justify-center p-12 text-slate-500">
      <Loader2 className="w-8 h-8 animate-spin text-blue-600 mb-3" />
      <p className="text-sm font-medium">{text}</p>
    </div>
  );
}

export function ErrorState({
  title = 'Something went wrong',
  message,
  onRetry,
}: {
  title?: string;
  message?: string;
  onRetry?: () => void;
}) {
  return (
    <div className="bg-rose-50 border border-rose-200 rounded-2xl p-8 text-center max-w-lg mx-auto my-8">
      <div className="w-12 h-12 rounded-full bg-rose-100 text-rose-600 flex items-center justify-center mx-auto mb-4">
        <AlertCircle className="w-6 h-6" />
      </div>
      <h3 className="text-base font-bold text-rose-900 mb-1">{title}</h3>
      {message && <p className="text-sm font-medium text-rose-600 mb-4">{message}</p>}
      {onRetry && (
        <button
          onClick={onRetry}
          className="inline-flex items-center gap-2 bg-rose-600 hover:bg-rose-700 text-white px-4 py-2 rounded-xl text-sm font-bold transition-all shadow-sm shadow-rose-600/20"
        >
          <RefreshCw className="w-4 h-4" /> Try Again
        </button>
      )}
    </div>
  );
}

export function EmptyState({
  title = 'No records found',
  description = 'There is currently no data to display.',
  actionLabel,
  onAction,
  icon: Icon,
}: {
  title?: string;
  description?: string;
  actionLabel?: string;
  onAction?: () => void;
  icon?: React.ElementType;
}) {
  return (
    <div className="border border-dashed border-slate-200 rounded-2xl p-12 text-center bg-white/50 my-6">
      {Icon && (
        <div className="w-12 h-12 rounded-full bg-slate-100 text-slate-500 flex items-center justify-center mx-auto mb-3">
          <Icon className="w-6 h-6" />
        </div>
      )}
      <h3 className="text-base font-bold text-slate-800 mb-1">{title}</h3>
      <p className="text-sm text-slate-500 max-w-sm mx-auto mb-4">{description}</p>
      {actionLabel && onAction && (
        <button
          onClick={onAction}
          className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-xl text-sm font-bold transition-all shadow-sm shadow-blue-600/20"
        >
          {actionLabel}
        </button>
      )}
    </div>
  );
}
