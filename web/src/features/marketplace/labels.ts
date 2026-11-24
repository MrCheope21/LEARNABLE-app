import type { Schemas } from "../../api/client";
import type { IconName } from "../../components/Icon";

// What a listing's category is, in icon form. Names live in the interface language (useLabels).
export const categoryIcon: Record<Schemas["Category"], IconName> = {
  law: "law",
  economics_business: "trend",
  accounting_finance: "receipt",
  medicine_health: "health",
  sciences: "flask",
  mathematics: "math",
  engineering: "gear",
  computer_science: "code",
  languages: "chat",
  humanities: "columns",
  arts: "palette",
  professional_exams: "cap",
  other: "book",
};

export const CATEGORIES = Object.keys(categoryIcon) as Schemas["Category"][];
export const LEVELS: Schemas["Level"][] = ["all", "beginner", "intermediate", "advanced"];
