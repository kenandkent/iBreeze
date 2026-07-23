import { create } from 'zustand';
import type { Profile } from '../types';

interface ProfileState {
  currentProfile: Profile | null;
  profiles: Profile[];
  setProfile: (profile: Profile | null) => void;
  setProfiles: (profiles: Profile[]) => void;
  switchProfile: (profileId: string) => void;
}

export const useProfileStore = create<ProfileState>()((set, get) => ({
  currentProfile: null,
  profiles: [],
  setProfile: (profile) => set({ currentProfile: profile }),
  setProfiles: (profiles) => set({ profiles }),
  switchProfile: (profileId) => {
    const { profiles } = get();
    const target = profiles.find((p) => p.id === profileId);
    if (target) set({ currentProfile: target });
  },
}));
