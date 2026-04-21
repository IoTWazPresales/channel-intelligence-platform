/** Normalize TanStack Query `error` for UI components that expect `Error | null`. */
export function toQueryError(error: unknown): Error | null {
  if (error == null) return null;
  if (error instanceof Error) return error;
  if (typeof error === 'string') return new Error(error);
  try {
    return new Error(JSON.stringify(error));
  } catch {
    return new Error('Request failed');
  }
}
