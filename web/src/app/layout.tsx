import type { Metadata } from "next";
import { Familjen_Grotesk, Source_Serif_4 } from "next/font/google";
import { AppShell } from "@/components/app-shell";
import { AppStateProvider } from "@/lib/app-state";
import "./globals.css";

const familjen = Familjen_Grotesk({
  variable: "--font-familjen",
  subsets: ["latin", "latin-ext"],
});

const sourceSerif = Source_Serif_4({
  variable: "--font-source-serif",
  subsets: ["latin", "latin-ext"],
});

export const metadata: Metadata = {
  title: "NordTech HR assistant",
  description: "Answers to NordTech HR and onboarding questions, from company policy.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${familjen.variable} ${sourceSerif.variable} h-full`}>
      <body className="h-full">
        <AppStateProvider>
          <AppShell>{children}</AppShell>
        </AppStateProvider>
      </body>
    </html>
  );
}
