import { useSyncExternalStore } from "react";

const query = "(max-width: 850px)";
const snapshot = () => window.matchMedia?.(query).matches ?? false;
const subscribe = (notify: () => void) => {
  const media = window.matchMedia?.(query);
  media?.addEventListener?.("change", notify);
  return () => media?.removeEventListener?.("change", notify);
};

export const useCompactLayout = () =>
  useSyncExternalStore(subscribe, snapshot, () => false);
