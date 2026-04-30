import { useQuery } from "@tanstack/react-query";
import { apiClient } from "../../services/apiClient";
import type {
  AccountResponse,
  AnomalyEventsResponse,
  NotificationsResponse,
  SecurityResponse,
} from "./types";

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

export async function fetchSecurity(): Promise<SecurityResponse> {
  const res = await apiClient.get<SecurityResponse>("/api/settings/security");
  return res.data;
}

export function useSecurity() {
  return useQuery({
    queryKey: ["settings", "security"],
    queryFn: fetchSecurity,
  });
}

export async function fetchAnomalyEvents(): Promise<AnomalyEventsResponse> {
  const res = await apiClient.get<AnomalyEventsResponse>(
    "/api/settings/anomaly-events"
  );
  return res.data;
}

export function useAnomalyEvents() {
  return useQuery({
    queryKey: ["settings", "anomaly-events"],
    queryFn: fetchAnomalyEvents,
  });
}
