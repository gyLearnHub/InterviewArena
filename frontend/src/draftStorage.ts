const CREATE_INTERVIEW_DRAFT_PREFIX = "interview_arena_create_draft";
const ROUND_ANSWER_DRAFT_PREFIX = "multi_round_draft:";

export function createInterviewDraftKey(userId: number): string {
  return `${CREATE_INTERVIEW_DRAFT_PREFIX}:${userId}`;
}

export function clearSensitiveDrafts(userId: number | null): void {
  try {
    if (userId !== null) {
      window.localStorage.removeItem(createInterviewDraftKey(userId));
    }
    window.localStorage.removeItem(CREATE_INTERVIEW_DRAFT_PREFIX);

    const roundDraftKeys: string[] = [];
    for (let index = 0; index < window.localStorage.length; index += 1) {
      const key = window.localStorage.key(index);
      if (key?.startsWith(ROUND_ANSWER_DRAFT_PREFIX)) {
        roundDraftKeys.push(key);
      }
    }
    roundDraftKeys.forEach((key) => window.localStorage.removeItem(key));
  } catch {
    // Cookie logout remains authoritative when browser storage is unavailable.
  }
}
