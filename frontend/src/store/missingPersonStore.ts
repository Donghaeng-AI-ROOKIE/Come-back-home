/** 실종자 프로필 단일 소스 (spec §2.1, §5). 전 화면이 이 스토어만 참조. */
import { create } from 'zustand';
import type { MissingPerson } from '../types/domain';
import { MISSING } from '../data/missing';

type MissingState = {
  profile: MissingPerson;
  setProfile: (p: MissingPerson) => void;
};

export const useMissingPersonStore = create<MissingState>((set) => ({
  profile: MISSING,
  setProfile: (profile) => set({ profile }),
}));
