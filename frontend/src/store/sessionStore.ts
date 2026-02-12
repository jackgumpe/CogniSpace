import { create } from "zustand";

export type SessionState = {
  sessionId: string | null;
  setSessionId: (sessionId: string) => void;
};

export const useSessionStore = create<SessionState>((set) => ({
  sessionId: null,
  setSessionId: (sessionId) => set({ sessionId })
}));
