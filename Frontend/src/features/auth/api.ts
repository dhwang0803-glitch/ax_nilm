import { apiClient } from "../../services/apiClient";
import type { AuthUser } from "./useAuth";

export type LoginPayload = { email: string; password: string };

export type SignupPayload = {
  email: string;
  password: string;
  name: string;
  agreeTerms: boolean;
  kepcoCustomerNumber: string | null;
};

export type AuthResponse = { user: AuthUser };

export async function login(payload: LoginPayload): Promise<AuthResponse> {
  const res = await apiClient.post<AuthResponse>("/auth/login", payload);
  return res.data;
}

export async function signup(payload: SignupPayload): Promise<AuthResponse> {
  const res = await apiClient.post<AuthResponse>("/auth/signup", payload);
  return res.data;
}

export async function logout(): Promise<void> {
  await apiClient.post("/auth/logout");
}

export async function oauthLogin(
  provider: "kakao" | "naver" | "google"
): Promise<AuthResponse> {
  const res = await apiClient.post<AuthResponse>(`/auth/oauth/${provider}`);
  return res.data;
}
