import { useQuery } from "@tanstack/react-query";
import { apiClient } from "../../services/apiClient";
import type { CashbackTracker } from "./types";

export async function fetchCashbackTracker(): Promise<CashbackTracker> {
  const res = await apiClient.get<CashbackTracker>("/api/cashback/tracker");
  return res.data;
}

export function useCashbackTracker() {
  return useQuery({
    queryKey: ["cashback", "tracker"],
    queryFn: fetchCashbackTracker,
  });
}
