import axios from "axios";

const baseURL =
  import.meta.env.VITE_API_BASE_URL?.toString().replace(/\/$/, "") ??
  "http://127.0.0.1:8000";

export const api = axios.create({
  baseURL,
  withCredentials: false,
  paramsSerializer: (params) => {
    const searchParams = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
      if (value === undefined || value === null) {
        return;
      }
      if (Array.isArray(value)) {
        value.forEach((entry) => {
          if (entry !== undefined && entry !== null) {
            searchParams.append(key, String(entry));
          }
        });
      } else {
        searchParams.append(key, String(value));
      }
    });
    return searchParams.toString();
  },
});

export function getApiBaseUrl() {
  return baseURL;
}

export function buildAssetUrl(path?: string | null) {
  if (!path) {
    return undefined;
  }
  if (/^https?:\/\//i.test(path)) {
    return path;
  }
  return `${baseURL}${path.startsWith("/") ? path : `/${path}`}`;
}

