import { create } from "zustand";

export interface AuthViewState {
  profileOpened: boolean;
  profileDirectoryId: string | null;
  maskedIdentifier: string | null;
  mode: "online" | "offline" | null;
  catalogReleaseSequence: number | null;
}

interface AuthActions {
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
  maskedIdentifier: null,
  mode: null,
  catalogReleaseSequence: null,
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
