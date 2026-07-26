import { create } from 'zustand';

interface ProfileState {
  selectedProfileId: string | null;
  setSelectedProfileId: (profileId: string | null) => void;
}

export const useProfileStore = create<ProfileState>()((set) => ({
  selectedProfileId: null,
  setSelectedProfileId: (profileId) => set({ selectedProfileId: profileId }),
}));
