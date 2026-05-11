import { useQuery } from "@tanstack/react-query";
import { apiClient } from "../../services/apiClient";
import type { UsageAnalysis } from "./types";

export async function fetchUsageAnalysis(): Promise<UsageAnalysis> {
  const res = await apiClient.get<UsageAnalysis>("/api/usage/analysis");
  return res.data;
}

export function useUsageAnalysis() {
  return useQuery({
    queryKey: ["usage", "analysis"],
    queryFn: fetchUsageAnalysis,
  });
}
