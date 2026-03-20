import { create } from 'zustand'
import { persist } from 'zustand/middleware'

interface PreferencesState {
  notificationsEnabled: boolean
  setNotificationsEnabled: (v: boolean) => void
}

export const usePreferencesStore = create<PreferencesState>()(
  persist(
    (set) => ({
      notificationsEnabled: true,
      setNotificationsEnabled: (v) => set({ notificationsEnabled: v }),
    }),
    { name: 'nexuspkm-preferences' }
  )
)
