import type { Schemas } from "../../api/client";

// What a listing's category is, in icon form. Names live in the interface language (useLabels).
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

export const CATEGORIES = Object.keys(categoryIcon) as Schemas["Category"][];
export const LEVELS: Schemas["Level"][] = ["all", "beginner", "intermediate", "advanced"];
