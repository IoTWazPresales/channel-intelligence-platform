'use client';

import { create } from 'zustand';
import { persist } from 'zustand/middleware';

type Density = 'comfortable' | 'compact';

type UiState = {
  density: Density;
  setDensity: (d: Density) => void;
  drawerOpen: boolean;
  drawerTitle: string;
  drawerContent: string | null;
  openDrawer: (title: string, content: string) => void;
  closeDrawer: () => void;
};

export const useUiStore = create<UiState>()(
  persist(
    (set) => ({
      density: 'comfortable',
      setDensity: (d) => set({ density: d }),
      drawerOpen: false,
      drawerTitle: '',
      drawerContent: null,
      openDrawer: (title, content) =>
        set({ drawerOpen: true, drawerTitle: title, drawerContent: content }),
      closeDrawer: () => set({ drawerOpen: false }),
    }),
    { name: 'cip-ui', partialize: (s) => ({ density: s.density }) }
  )
);
