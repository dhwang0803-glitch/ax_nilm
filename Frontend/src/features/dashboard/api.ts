import { useQuery } from "@tanstack/react-query";
import { apiClient } from "../../services/apiClient";
import type { DashboardSummary } from "./types";

export async function fetchDashboardSummary(): Promise<DashboardSummary> {
  const res = await apiClient.get<DashboardSummary>("/api/dashboard/summary");
  return res.data;
}

export function useDashboardSummary() {
  return useQuery({
    queryKey: ["dashboard", "summary"],
    queryFn: fetchDashboardSummary,
  });
}
