import { create } from 'zustand';

export interface AppNotification {
  id: string;
  type: 'info' | 'success' | 'warning' | 'error';
  message: string;
  timestamp: number;
}

interface AppState {
  sidebarCollapsed: boolean;
  theme: 'light' | 'dark';
  notifications: AppNotification[];
  toggleSidebar: () => void;
  setTheme: (theme: 'light' | 'dark') => void;
  addNotification: (type: AppNotification['type'], message: string) => void;
  removeNotification: (id: string) => void;
}

export const useAppStore = create<AppState>()((set) => ({
  sidebarCollapsed: false,
  theme: 'light',
  notifications: [],
  toggleSidebar: () => set((s) => ({ sidebarCollapsed: !s.sidebarCollapsed })),
  setTheme: (theme) => set({ theme }),
  addNotification: (type, message) =>
    set((s) => ({
      notifications: [
        ...s.notifications,
        { id: `${Date.now()}-${Math.random()}`, type, message, timestamp: Date.now() },
      ],
    })),
  removeNotification: (id) =>
    set((s) => ({
      notifications: s.notifications.filter((n) => n.id !== id),
    })),
}));
