import type { EmployeeContext } from "./types";

export type Office = {
  id: string;
  label: string;
  greeting: string;
  context: EmployeeContext;
};

// The greeting follows the office's local language: the one playful touch in the UI.
export const OFFICES: Office[] = [
  {
    id: "tallinn",
    label: "Tallinn, Estonia",
    greeting: "Tere",
    context: { employee_country: "Estonia", office_country: "Estonia", office_location: "Tallinn" },
  },
  {
    id: "tampere",
    label: "Tampere, Finland",
    greeting: "Hei",
    context: { employee_country: "Finland", office_country: "Finland", office_location: "Tampere" },
  },
  {
    id: "porto",
    label: "Porto, Portugal",
    greeting: "Olá",
    context: { employee_country: "Portugal", office_country: "Portugal", office_location: "Porto" },
  },
  {
    id: "remote",
    label: "Remote",
    greeting: "Hello",
    context: { office_country: "Remote" },
  },
];

export const DEFAULT_OFFICE = OFFICES[0];

export function findOffice(id: string | null | undefined): Office {
  return OFFICES.find((office) => office.id === id) ?? DEFAULT_OFFICE;
}
