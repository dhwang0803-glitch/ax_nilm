import axios, { AxiosError } from "axios";

const baseURL = import.meta.env.VITE_API_BASE_URL ?? "";

export const apiClient = axios.create({
  baseURL,
  withCredentials: true,
});

apiClient.interceptors.response.use(
  (response) => response,
  (error: AxiosError) => {
    // 인증 엔드포인트 자체의 401(잘못된 자격증명 등)은 폼이 직접 처리한다.
    // 보호 라우트의 401만 로그인 화면으로 강제 redirect.
    const url = error.config?.url ?? "";
    const isAuthEndpoint = url.startsWith("/auth/");
    if (error.response?.status === 401 && !isAuthEndpoint && typeof window !== "undefined") {
      window.location.assign("/auth/login");
    }
    return Promise.reject(error);
  }
);
