import { useQuery } from "@tanstack/react-query";
import { apiClient } from "../../services/apiClient";
import type { AccountResponse } from "./types";

export async function fetchAccount(): Promise<AccountResponse> {
  const res = await apiClient.get<AccountResponse>("/api/settings/account");
  return res.data;
}

export function useAccount() {
  return useQuery({
    queryKey: ["settings", "account"],
    queryFn: fetchAccount,
  });
}
