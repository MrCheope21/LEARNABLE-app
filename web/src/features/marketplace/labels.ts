import type { Schemas } from "../../api/client";

export const categoryLabel: Record<Schemas["Category"], string> = {
  law: "Law",
  economics_business: "Economics & business",
  accounting_finance: "Accounting & finance",
  medicine_health: "Medicine & health",
  sciences: "Sciences",
  mathematics: "Mathematics",
  engineering: "Engineering",
  computer_science: "Computer science",
  languages: "Languages",
  humanities: "History & humanities",
  arts: "Arts & music",
  professional_exams: "Professional exams",
  other: "Other",
};

export const categoryIcon: Record<Schemas["Category"], string> = {
  law: "⚖️",
  economics_business: "📈",
  accounting_finance: "🧾",
  medicine_health: "🩺",
  sciences: "🧪",
  mathematics: "➗",
  engineering: "⚙️",
  computer_science: "💻",
  languages: "🗣️",
  humanities: "🏛️",
  arts: "🎨",
  professional_exams: "🎓",
  other: "📚",
};

export const levelLabel: Record<Schemas["Level"], string> = {
  all: "All levels",
  beginner: "Beginner",
  intermediate: "Intermediate",
  advanced: "Advanced",
};

export const sizeLabel = {
  small: "Short (under 50 questions)",
  medium: "Medium (50–299 questions)",
  large: "Large (300+ questions)",
} as const;

export const sortLabel: Record<Schemas["ListingSort"], string> = {
  popular: "Most taken",
  newest: "Newest",
  largest: "Most questions",
};

export const languageLabel: Record<string, string> = { it: "Italian", en: "English" };

export const CATEGORIES = Object.keys(categoryLabel) as Schemas["Category"][];
export const LEVELS = Object.keys(levelLabel) as Schemas["Level"][];

export function count(n: number, one: string, many: string): string {
  return `${n} ${n === 1 ? one : many}`;
}

export function priceLabel(listing: { price_cents: number; currency: string }): string {
  if (listing.price_cents === 0) return "Free";
  return new Intl.NumberFormat(undefined, { style: "currency", currency: listing.currency }).format(listing.price_cents / 100);
}
