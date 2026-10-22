export function apiMode(): string | undefined {
  return import.meta.env.VITE_API_MODE;
}
