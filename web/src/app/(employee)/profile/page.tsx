import type { Metadata } from "next";
import { Profile } from "@/components/profile";

export const metadata: Metadata = { title: "Your profile · NordTech HR" };

export default function ProfilePage() {
  return <Profile />;
}
