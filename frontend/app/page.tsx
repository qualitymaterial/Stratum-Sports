import { redirect } from "next/navigation";

import HeroLandingPage from "@/components/public/HeroLandingPage";

export const dynamic = "force-dynamic";

export default function HomePage() {
  const landingEnabled = process.env.NEXT_PUBLIC_LANDING_V1_ENABLED === "true";
  if (!landingEnabled) {
    redirect("/login");
  }
  return <HeroLandingPage />;
}
