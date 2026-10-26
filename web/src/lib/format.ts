const dateTime = new Intl.DateTimeFormat("en-GB", {
  day: "numeric",
  month: "short",
  hour: "2-digit",
  minute: "2-digit",
});

const fullDate = new Intl.DateTimeFormat("en-GB", {
  day: "numeric",
  month: "long",
  year: "numeric",
  timeZone: "UTC",
});

// "27 Oct, 14:05" in the reader's time zone.
export function formatDateTime(iso: string): string {
  return dateTime.format(new Date(iso));
}

// "19 October 2026", for dates without a time, like a start date.
export function formatDate(isoDate: string): string {
  return fullDate.format(new Date(isoDate));
}

export function firstName(name: string): string {
  return name.split(" ")[0] ?? name;
}

export function initials(name: string): string {
  return name
    .split(" ")
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase())
    .join("");
}
