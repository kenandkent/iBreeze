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
  selectedCompanyId: string | null;
  toggleSidebar: () => void;
  setTheme: (theme: 'light' | 'dark') => void;
  addNotification: (type: AppNotification['type'], message: string) => void;
  removeNotification: (id: string) => void;
  setSelectedCompany: (companyId: string | null) => void;
}

export const useAppStore = create<AppState>()((set) => ({
  sidebarCollapsed: false,
  theme: 'light',
  notifications: [],
  selectedCompanyId: null,
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
  setSelectedCompany: (companyId) => set({ selectedCompanyId: companyId }),
}));
