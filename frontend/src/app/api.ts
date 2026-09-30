import { requestJson } from "./apiClient";

export const api = <T>(path: string) => requestJson<T>(path);
