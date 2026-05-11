import { useQuery } from "@tanstack/react-query";
import { apiClient } from "../../services/apiClient";
import type { InsightsResponse } from "./types";

export async function fetchInsights(): Promise<InsightsResponse> {
  const res = await apiClient.get<InsightsResponse>("/api/insights/summary");
  return res.data;
}

export function useInsights() {
  return useQuery({
    queryKey: ["insights", "summary"],
    queryFn: fetchInsights,
  });
}
