import type { User } from "./types";

// The greeting follows the office's local language: the one playful touch in the UI.
const GREETINGS: Record<string, string> = {
  Tallinn: "Tere",
  Tampere: "Hei",
  Porto: "Olá",
};

export function greetingFor(user: User): string {
  return GREETINGS[user.office] ?? "Hello";
}

// "Tallinn, Estonia", or "Remote (Finland)": remote employees keep their country's rules.
export function officeLabel(place: { office: string | null; country: string | null }): string {
  if (place.office === "Remote") return place.country ? `Remote (${place.country})` : "Remote";
  return [place.office, place.country].filter(Boolean).join(", ") || "Not given";
}
