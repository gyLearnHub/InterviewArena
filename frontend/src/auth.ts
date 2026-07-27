import { clearSensitiveDrafts } from "./draftStorage";

const LEGACY_TOKEN_KEY = "interview_arena_token";
const USER_KEY = "interview_arena_user";
export const AUTH_CHANGED_EVENT = "interview-arena:auth-changed";

export type AuthUser = {
  id: number;
  username: string;
  display_name?: string;
  avatar_url?: string | null;
  external_model_consent?: boolean;
};

export function getUser(): AuthUser | null {
  const raw = readStorage(USER_KEY);
  if (!raw) {
    return null;
  }

  try {
    return JSON.parse(raw) as AuthUser;
  } catch {
    clearAuth();
    return null;
  }
}

export function saveAuth(user: AuthUser): void {
  removeStorage(LEGACY_TOKEN_KEY);
  writeStorage(USER_KEY, JSON.stringify(user));
  emitAuthChanged();
}

export function clearAuth(): void {
  clearSensitiveDrafts(readStoredUserId());
  removeStorage(LEGACY_TOKEN_KEY);
  removeStorage(USER_KEY);
  emitAuthChanged();
}

export function isLoggedIn(): boolean {
  return Boolean(getUser());
}

function emitAuthChanged(): void {
  window.dispatchEvent(new CustomEvent(AUTH_CHANGED_EVENT));
}

function readStorage(key: string): string | null {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

function writeStorage(key: string, value: string): void {
  try {
    window.localStorage.setItem(key, value);
  } catch {
    // The cookie session remains authoritative when browser storage is unavailable.
  }
}

function removeStorage(key: string): void {
  try {
    window.localStorage.removeItem(key);
  } catch {
    // Keep authentication flows usable in restricted storage contexts.
  }
}

function readStoredUserId(): number | null {
  const raw = readStorage(USER_KEY);
  if (!raw) {
    return null;
  }
  try {
    const user = JSON.parse(raw) as { id?: unknown };
    return typeof user.id === "number" && Number.isInteger(user.id) ? user.id : null;
  } catch {
    return null;
  }
}
