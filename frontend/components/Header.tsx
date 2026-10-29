'use client';

import React, { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { Search, Bell, Command, X, Check, FileText, User as UserIcon, LayoutDashboard, Clock, CalendarDays, Wallet, Settings } from 'lucide-react';
import { useAuth } from '@/lib/auth-context';
import { api, NotificationItem, SearchResult } from '@/lib/api';

export default function Header() {
  const { user, logout } = useAuth();
  const router = useRouter();

  // Search modal state
  const [searchOpen, setSearchOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<SearchResult[]>([]);
  const [searching, setSearching] = useState(false);

  // Notification popover state
  const [notifOpen, setNotifOpen] = useState(false);
  const [notifications, setNotifications] = useState<NotificationItem[]>([]);
  const [unreadCount, setUnreadCount] = useState(0);

  // Keyboard shortcut for Cmd+K / Ctrl+K
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault();
        setSearchOpen((prev) => !prev);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  // Fetch notifications
  const fetchNotifications = async () => {
    try {
      const res = await api.get('/notifications?limit=15');
      if (Array.isArray(res.data)) {
        setNotifications(res.data);
        setUnreadCount(res.data.filter((n: NotificationItem) => !n.is_read).length);
      }
    } catch (e) {
      // ignore
    }
  };

  useEffect(() => {
    if (user) {
      fetchNotifications();
    }
  }, [user]);

  // Omni Search query
  useEffect(() => {
    if (!searchQuery.trim()) {
      setSearchResults([]);
      return;
    }
    const timer = setTimeout(async () => {
      setSearching(true);
      try {
        const res = await api.get(`/search?q=${encodeURIComponent(searchQuery)}`);
        setSearchResults(res.data || []);
      } catch (err) {
        setSearchResults([]);
      } finally {
        setSearching(false);
      }
    }, 250);
    return () => clearTimeout(timer);
  }, [searchQuery]);

  const markNotificationRead = async (id: number) => {
    try {
      await api.post(`/notifications/${id}/read`);
      setNotifications((prev) =>
        prev.map((n) => (n.id === id ? { ...n, is_read: true } : n))
      );
      setUnreadCount((prev) => Math.max(0, prev - 1));
    } catch (e) {}
  };

  const markAllRead = async () => {
    try {
      await api.post('/notifications/read-all');
      setNotifications((prev) => prev.map((n) => ({ ...n, is_read: true })));
      setUnreadCount(0);
    } catch (e) {}
  };

  const userName = user?.first_name ? `${user.first_name} ${user.last_name || ''}`.trim() : (user?.email?.split('@')[0] || 'User');
  const userRole = user?.role ? user.role.toUpperCase() : 'GUEST';
  const initials = userName.substring(0, 2).toUpperCase();

  return (
    <>
      <header className="h-20 bg-white/80 backdrop-blur-lg border-b border-slate-200 flex items-center justify-between px-8 sticky top-0 z-30">
        <div className="flex-1 max-w-xl">
          <div
            onClick={() => setSearchOpen(true)}
            className="relative group cursor-pointer"
          >
            <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400 group-hover:text-blue-600 transition-colors" />
            <div className="w-full bg-slate-100/70 hover:bg-white border border-slate-200 hover:border-blue-400 rounded-xl pl-10 pr-12 py-2.5 text-sm text-slate-400 font-medium transition-all shadow-sm">
              Search employees, payslips, or pages...
            </div>
            <div className="absolute right-3 top-1/2 -translate-y-1/2 hidden sm:flex items-center gap-1">
              <kbd className="inline-flex items-center justify-center rounded border border-slate-200 bg-white px-1.5 py-0.5 text-[10px] font-medium text-slate-400">
                <Command className="w-3 h-3" />
              </kbd>
              <kbd className="inline-flex items-center justify-center rounded border border-slate-200 bg-white px-1.5 py-0.5 text-[10px] font-medium text-slate-400">
                K
              </kbd>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-5 ml-4">
          {/* Notification Bell */}
          <div className="relative">
            <button
              onClick={() => {
                setNotifOpen((prev) => !prev);
                if (!notifOpen) fetchNotifications();
              }}
              className="relative p-2 text-slate-500 hover:text-slate-900 transition-colors rounded-full hover:bg-slate-100"
              title="Notifications"
            >
              <Bell className="w-5 h-5" />
              {unreadCount > 0 && (
                <span className="absolute top-1 right-1 w-2.5 h-2.5 bg-rose-500 rounded-full ring-2 ring-white" />
              )}
            </button>

            {/* Notification Dropdown */}
            {notifOpen && (
              <div className="absolute right-0 mt-3 w-80 sm:w-96 bg-white border border-slate-200 rounded-2xl shadow-2xl z-50 overflow-hidden">
                <div className="p-4 border-b border-slate-100 flex items-center justify-between bg-slate-50/50">
                  <div className="flex items-center gap-2">
                    <h4 className="font-bold text-slate-900 text-sm">Notifications</h4>
                    {unreadCount > 0 && (
                      <span className="px-2 py-0.5 bg-blue-100 text-blue-700 text-[10px] font-bold rounded-full">
                        {unreadCount} new
                      </span>
                    )}
                  </div>
                  {unreadCount > 0 && (
                    <button
                      onClick={markAllRead}
                      className="text-xs font-semibold text-blue-600 hover:text-blue-800"
                    >
                      Mark all read
                    </button>
                  )}
                </div>

                <div className="max-h-80 overflow-y-auto divide-y divide-slate-100">
                  {notifications.length === 0 ? (
                    <div className="p-6 text-center text-sm text-slate-400">
                      No notifications right now.
                    </div>
                  ) : (
                    notifications.map((n) => (
                      <div
                        key={n.id}
                        className={`p-4 hover:bg-slate-50 transition-colors flex items-start gap-3 ${
                          !n.is_read ? 'bg-blue-50/30' : ''
                        }`}
                      >
                        <div className="flex-1">
                          <p className="text-xs font-bold text-slate-900">{n.title}</p>
                          <p className="text-xs text-slate-600 mt-0.5">{n.message}</p>
                          <span className="text-[10px] text-slate-400 mt-1 inline-block">
                            {n.created_at ? new Date(n.created_at).toLocaleDateString() : ''}
                          </span>
                        </div>
                        {!n.is_read && (
                          <button
                            onClick={() => markNotificationRead(n.id)}
                            className="text-slate-400 hover:text-blue-600 p-1"
                            title="Mark as read"
                          >
                            <Check className="w-4 h-4" />
                          </button>
                        )}
                      </div>
                    ))
                  )}
                </div>
              </div>
            )}
          </div>

          <div className="h-8 w-px bg-slate-200" />

          {/* User Profile Info */}
          <div
            onClick={() => router.push('/settings')}
            className="flex items-center gap-3 cursor-pointer group"
          >
            <div className="text-right hidden sm:block">
              <p className="text-sm font-bold text-slate-900 group-hover:text-blue-600 transition-colors">
                {userName}
              </p>
              <p className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider">
                {userRole} • {user?.company_name || 'Vertex'}
              </p>
            </div>
            <div className="w-10 h-10 rounded-full border-2 border-slate-200 bg-blue-600 flex items-center justify-center group-hover:border-blue-500 transition-colors shadow-sm">
              <span className="text-white font-bold text-sm">{initials}</span>
            </div>
          </div>
        </div>
      </header>

      {/* ⌘K Global Omni-Search Modal */}
      {searchOpen && (
        <div className="fixed inset-0 bg-slate-900/50 backdrop-blur-sm z-50 flex items-start justify-center pt-20 px-4">
          <div className="bg-white rounded-2xl shadow-2xl max-w-2xl w-full border border-slate-200 overflow-hidden animate-in fade-in zoom-in-95 duration-150">
            <div className="p-4 border-b border-slate-100 flex items-center gap-3 bg-slate-50/50">
              <Search className="w-5 h-5 text-slate-400" />
              <input
                type="text"
                autoFocus
                placeholder="Search employees, payslips, pages..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="flex-1 bg-transparent border-none outline-none text-base font-semibold text-slate-800 placeholder:text-slate-400"
              />
              <button
                onClick={() => setSearchOpen(false)}
                className="text-slate-400 hover:text-slate-700 p-1 rounded-lg"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="max-h-96 overflow-y-auto p-2">
              {searching ? (
                <div className="p-8 text-center text-sm font-medium text-slate-400">
                  Searching across records...
                </div>
              ) : searchQuery && searchResults.length === 0 ? (
                <div className="p-8 text-center text-sm font-medium text-slate-400">
                  No matching records found for "{searchQuery}".
                </div>
              ) : (
                <div className="space-y-1">
                  {searchResults.map((item, idx) => (
                    <div
                      key={idx}
                      onClick={() => {
                        setSearchOpen(false);
                        router.push(item.link);
                      }}
                      className="p-3 hover:bg-blue-50 rounded-xl cursor-pointer flex items-center gap-3 transition-colors"
                    >
                      <div className="w-8 h-8 rounded-lg bg-slate-100 flex items-center justify-center text-slate-500">
                        {item.category === 'employee' ? (
                          <UserIcon className="w-4 h-4 text-blue-600" />
                        ) : item.category === 'payslip' ? (
                          <FileText className="w-4 h-4 text-emerald-600" />
                        ) : (
                          <LayoutDashboard className="w-4 h-4 text-purple-600" />
                        )}
                      </div>
                      <div className="flex-1">
                        <p className="text-sm font-bold text-slate-900">{item.title}</p>
                        {item.subtitle && (
                          <p className="text-xs text-slate-500">{item.subtitle}</p>
                        )}
                      </div>
                      <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider px-2 py-1 bg-slate-100 rounded-md">
                        {item.category}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>
            <div className="p-3 bg-slate-50 border-t border-slate-100 flex justify-between text-xs text-slate-400 font-medium">
              <span>Press ESC to close</span>
              <span>Vertex Omni-Search</span>
            </div>
          </div>
        </div>
      )}
    </>
  );
}