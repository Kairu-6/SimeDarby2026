import Constants from 'expo-constants';
import { Platform } from 'react-native';

const host = Constants.expoConfig?.hostUri?.split(':')[0] || 'localhost';
const webHost = typeof window !== 'undefined' ? window.location.hostname : 'localhost';
export const DEFAULT_API =
  process.env.EXPO_PUBLIC_API_URL ||
  (Platform.OS === 'web'
    ? typeof window !== 'undefined' && window.location.port !== '8081'
      ? window.location.origin
      : `http://${webHost}:8000`
    : `http://${host}:8000`);

export async function request<T>(
  base: string,
  path: string,
  token?: string | null,
  body?: unknown,
  method?: string,
): Promise<T> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), path.includes('vision') ? 120000 : 15000);
  const isForm = body instanceof FormData;
  try {
    const response = await fetch(`${base.replace(/\/$/, '')}${path}`, {
      method: method || (body === undefined ? 'GET' : 'POST'),
      headers: {
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...(!isForm && body !== undefined ? { 'Content-Type': 'application/json' } : {}),
      },
      body: body === undefined ? undefined : isForm ? body : JSON.stringify(body),
      signal: controller.signal,
    });
    const data = await response.json();
    if (!response.ok)
      throw new Error(
        typeof data.detail === 'string' ? data.detail : 'Please check your input and try again.',
      );
    return data;
  } catch (error) {
    if (
      error instanceof Error &&
      (error.name === 'AbortError' ||
        error.message.includes('fetch') ||
        error.message.includes('Network'))
    ) {
      throw new Error(
        'Cannot reach the bin service. Check the API address and your Wi-Fi, then try again.',
      );
    }
    throw error;
  } finally {
    clearTimeout(timer);
  }
}

export const requestId = () =>
  `${Date.now()}-${Math.random().toString(36).slice(2)}-${Math.random().toString(36).slice(2)}`;
