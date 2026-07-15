import { ApiError, getCurrentUser, type UserProfile } from "./api";
import { clearAuth, getUser, saveAuth, type AuthUser } from "./auth";

let verifiedSession = false;
let pendingSession: Promise<AuthUser | null> | null = null;

export async function ensureAuthenticated(): Promise<AuthUser | null> {
  if (verifiedSession) {
    const cachedUser = getUser();
    if (cachedUser) {
      return cachedUser;
    }
    verifiedSession = false;
  }
  return hydrateCurrentSession();
}

export async function hydrateCurrentSession(): Promise<AuthUser | null> {
  if (pendingSession) {
    return pendingSession;
  }

  pendingSession = getCurrentUser()
    .then((profile) => {
      const user = toAuthUser(profile);
      saveAuth(user);
      verifiedSession = true;
      return user;
    })
    .catch((error) => {
      if (error instanceof ApiError && error.status === 401) {
        clearAuth();
      }
      verifiedSession = false;
      return null;
    })
    .finally(() => {
      pendingSession = null;
    });

  return pendingSession;
}

export function markSessionUnverified(): void {
  verifiedSession = false;
}

function toAuthUser(profile: UserProfile): AuthUser {
  return {
    id: profile.id,
    username: profile.username,
    display_name: profile.display_name,
    avatar_url: profile.avatar_url
  };
}
