// Mirrors api.py's response envelope and route_intent()'s {kind,text,data} union.

export interface ApiEnvelopeOk<T> {
  data: T;
  meta: Record<string, never>;
}

export interface ApiEnvelopeError {
  error: { code: string; message: string };
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

export interface HomeResponse {
  tasks: Task[];
  nextEvent: CalendarEvent | null;
  budgetSummary: BudgetSnapshot | null;
  reminders: Reminder[];
  quoteOfDay: QuoteOfDay;
}

export type ChatKind = "text" | "task" | "budget" | "quote";

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
  data: ChatTaskData | ChatBudgetData | null;
}

export type ChatMessage =
  | { id: string; role: "user"; text: string }
  | { id: string; role: "assistant"; kind: ChatKind; text: string; data: ChatTaskData | ChatBudgetData | null };
