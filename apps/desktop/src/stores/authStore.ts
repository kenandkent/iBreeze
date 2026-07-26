import { create } from "zustand";

export interface AuthViewState {
  profileOpened: boolean;
  profileDirectoryId: string | null;
  backendOrigin: string | null;
  appUserId: string | null;
  maskedIdentifier: string | null;
  mode: "online" | "offline" | null;
  catalogReleaseSequence: number | null;
}

interface AuthActions {
  setBackendOrigin: (origin: string | null) => void;
  setAppUserId: (userId: string | null) => void;
  openProfile: (state: {
    profileDirectoryId: string;
    maskedIdentifier: string;
    mode: "online" | "offline";
    catalogReleaseSequence: number;
  }) => void;
  closeProfile: () => void;
}

export const useAuthStore = create<AuthViewState & AuthActions>()((set) => ({
  profileOpened: false,
  profileDirectoryId: null,
  backendOrigin: null,
  appUserId: null,
  maskedIdentifier: null,
  mode: null,
  catalogReleaseSequence: null,
  setBackendOrigin: (origin) => set({ backendOrigin: origin }),
  setAppUserId: (userId) => set({ appUserId: userId }),
  openProfile: (state) =>
    set({
      profileOpened: true,
      profileDirectoryId: state.profileDirectoryId,
      maskedIdentifier: state.maskedIdentifier,
      mode: state.mode,
      catalogReleaseSequence: state.catalogReleaseSequence,
    }),
  closeProfile: () =>
    set({
      profileOpened: false,
      profileDirectoryId: null,
      maskedIdentifier: null,
      mode: null,
      catalogReleaseSequence: null,
    }),
}));
