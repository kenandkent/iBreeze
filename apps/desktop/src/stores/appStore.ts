import { create } from 'zustand';
import type { PageKey } from '../types';

interface AppState {
  currentPage: PageKey;
  currentCompanyId: string | null;
  sidebarOpen: boolean;
  setCurrentPage: (page: PageKey) => void;
  setCurrentCompany: (id: string | null) => void;
  toggleSidebar: () => void;
}

export const useAppStore = create<AppState>((set) => ({
  currentPage: 'dashboard',
  currentCompanyId: null,
  sidebarOpen: true,
  setCurrentPage: (page) => set({ currentPage: page }),
  setCurrentCompany: (id) => set({ currentCompanyId: id }),
  toggleSidebar: () => set((s) => ({ sidebarOpen: !s.sidebarOpen })),
}));
