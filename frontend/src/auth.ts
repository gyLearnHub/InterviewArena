const TOKEN_KEY = "interview_arena_token";
const USER_KEY = "interview_arena_user";
export const AUTH_CHANGED_EVENT = "interview-arena:auth-changed";

export type AuthUser = {
  id: number;
  username: string;
  display_name?: string;
  avatar_url?: string | null;
};

export function getToken(): string {
  localStorage.removeItem(TOKEN_KEY);
  return "";
}

export function getUser(): AuthUser | null {
  const raw = localStorage.getItem(USER_KEY);
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

export function saveAuth(_token: string, user: AuthUser): void {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.setItem(USER_KEY, JSON.stringify(user));
  emitAuthChanged();
}

export function clearAuth(): void {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
  emitAuthChanged();
}

export function isLoggedIn(): boolean {
  return Boolean(getUser());
}

function emitAuthChanged(): void {
  window.dispatchEvent(new CustomEvent(AUTH_CHANGED_EVENT));
}
