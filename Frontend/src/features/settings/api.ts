import { useQuery } from "@tanstack/react-query";
import { apiClient } from "../../services/apiClient";
import type { AccountResponse, NotificationsResponse } from "./types";

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

export async function fetchNotifications(): Promise<NotificationsResponse> {
  const res = await apiClient.get<NotificationsResponse>(
    "/api/settings/notifications"
  );
  return res.data;
}

export function useNotifications() {
  return useQuery({
    queryKey: ["settings", "notifications"],
    queryFn: fetchNotifications,
  });
}
