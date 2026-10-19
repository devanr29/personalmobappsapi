// Mirrors api.py's response envelope and route_intent()'s {kind,text,data} union.

export interface ApiEnvelopeOk<T> {
  data: T;
  meta: Record<string, never>;
}

export interface ApiEnvelopeError {
  error: { code: string; message: string; details?: Record<string, unknown> };
  meta: Record<string, never>;
}

export type ApiEnvelope<T> = ApiEnvelopeOk<T> | ApiEnvelopeError;

export type BudgetStatusLevel = "short" | "tight" | "manageable" | "comfortable";

export interface BudgetSnapshot {
  remaining: number;
  deductions: number;
  free: number;
  dailyBudget: number;
  daysToPayday: number;
  statusLevel: BudgetStatusLevel;
  computedAt: string;
}

export interface Task {
  id: string;
  title: string;
  status: "needsAction" | "completed";
}

export interface CalendarEvent {
  id: string;
  title: string;
  start: string | null;
  /** Timed: ISO instant. All-day: "YYYY-MM-DD", exclusive (day after the last day). */
  end: string | null;
  allDay: boolean;
}

export interface Reminder {
  id: number;
  content: string;
  remindAt: string;
}

export interface NoteOrIdea {
  index: number;
  content: string;
  timestamp: string;
}

export interface SearchResult {
  sourceType: string;
  content: string;
  score: number;
}

export interface NewsArticle {
  title: string;
  source: string;
  publishedAt: string;
  url: string;
  description: string;
}

export interface QuoteOfDay {
  quote: string;
  author: string;
}

// features/quran.py get_verse_of_day() — the last pushed verse; null only
// when alquran.cloud was unreachable and nothing had been pushed yet.
export interface VerseOfDay {
  ref: string;
  surah: string;
  translation: string;
}

export interface HomeResponse {
  tasks: Task[];
  nextEvent: CalendarEvent | null;
  budgetSummary: BudgetSnapshot | null;
  reminders: Reminder[];
  quoteOfDay: QuoteOfDay;
  verseOfDay: VerseOfDay | null;
}

export type ChatKind = "text" | "task" | "budget" | "quote" | "quran";

// features/quran.py get_verse(). Arabic and translation come from
// alquran.cloud; context/reflection are a Gemini summary of Tafsir Ibn
// Kathir and are null when that step failed.
export interface ChatQuranData {
  ref: string;
  surah: string;
  surahNumber: number;
  ayah: number;
  arabic: string;
  translation: string;
  passage: {
    range: string;
    verses: { ref: string; translation: string }[];
    isMidPassage: boolean;
    note: string | null;
  };
  context: string | null;
  reflection: string[] | null;
  sources: { translation: string; tafsir: string | null };
}

export interface ChatTaskData {
  content: string;
}

export interface ChatBudgetData {
  remaining: number;
  deductions: number;
  free: number;
  dailyBudget: number;
  daysToPayday: number;
  statusLevel: BudgetStatusLevel;
  deductionBreakdown: BudgetDeductionItem[];
}

// Line items that sum to ChatBudgetData.deductions — fixed expenses still
// owed and remaining variable-budget headroom, same set intents.py's
// "Total deductions" summary lists.
export interface BudgetDeductionItem {
  name: string;
  amount: number;
}

export interface ChatResponse {
  kind: ChatKind;
  text: string;
  data: ChatTaskData | ChatBudgetData | ChatQuranData | null;
}

export type ChatMessage =
  | { id: string; role: "user"; text: string }
  | { id: string; role: "assistant"; kind: ChatKind; text: string; data: ChatTaskData | ChatBudgetData | ChatQuranData | null };
