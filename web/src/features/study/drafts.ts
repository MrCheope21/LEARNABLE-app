// Never lose an answer (docs/PROJECT_SPEC.md §79): what the user types is saved on every change
// and cleared only after the backend has stored the answer.

const PREFIX = "learnable.draft.question.";

export const drafts = {
  load(questionId: string): string {
    try {
      return localStorage.getItem(PREFIX + questionId) ?? "";
    } catch {
      return "";
    }
  },
  save(questionId: string, text: string): void {
    try {
      if (text) localStorage.setItem(PREFIX + questionId, text);
      else localStorage.removeItem(PREFIX + questionId);
    } catch {
      // Storage full or unavailable: the text is still in the editor.
    }
  },
  /** Signing out removes every draft: answers typed on a shared computer stay private. */
  clearAll(): void {
    try {
      const keys: string[] = [];
      for (let i = 0; i < localStorage.length; i++) {
        const key = localStorage.key(i);
        if (key?.startsWith(PREFIX)) keys.push(key);
      }
      keys.forEach((key) => localStorage.removeItem(key));
    } catch {
      // Storage unavailable: nothing to clear.
    }
  },
  clear(questionId: string): void {
    try {
      localStorage.removeItem(PREFIX + questionId);
    } catch {
      // Nothing to clear.
    }
  },
};
