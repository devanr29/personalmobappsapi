// Backend replies use lightweight WhatsApp-style markup (*bold*, _italic_)
// intended for a text-only channel; native bubbles render plain text instead.
export function stripMarkdown(text: string): string {
  return text.replace(/\*(.+?)\*/g, "$1").replace(/_(.+?)_/g, "$1");
}

// features/quotes.py's generate_daily_quote() returns "_{quote}_\n{author}".
export function parseQuote(text: string): { quote: string; author: string } {
  const [first, ...rest] = text.split("\n");
  const quote = first.replace(/^_/, "").replace(/_$/, "");
  const author = rest.join(" ").trim() || "Unknown";
  return { quote, author };
}
