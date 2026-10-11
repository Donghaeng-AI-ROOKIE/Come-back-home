import { useQuery } from '@tanstack/react-query';
import { getTargetingPolicy } from '../api/client';
import { useAuthStore } from '../store/authStore';
import { targetingResolution } from '../utils/targetingPolicy';

export function useTargetingPolicy(enabled = true) {
  const owner = useAuthStore(s => s.userId);
  const query = useQuery({
    queryKey: ['targetingPolicy', owner],
    queryFn: getTargetingPolicy,
    enabled,
    staleTime: 60_000,
    refetchInterval: 60_000,
    refetchOnWindowFocus: true,
  });
  return { ...query, resolution: query.isError ? null : targetingResolution(query.data) };
}
