'use client';

import { create } from 'zustand';
import { persist } from 'zustand/middleware';

type Density = 'comfortable' | 'compact';
export type ColorMode = 'light' | 'dark';

type UiState = {
  density: Density;
  setDensity: (d: Density) => void;
  colorMode: ColorMode;
  setColorMode: (m: ColorMode) => void;
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
      colorMode: 'dark',
      setColorMode: (m) => set({ colorMode: m }),
      drawerOpen: false,
      drawerTitle: '',
      drawerContent: null,
      openDrawer: (title, content) =>
        set({ drawerOpen: true, drawerTitle: title, drawerContent: content }),
      closeDrawer: () => set({ drawerOpen: false }),
    }),
    { name: 'cip-ui', partialize: (s) => ({ density: s.density, colorMode: s.colorMode }) }
  )
);
