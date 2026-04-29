import { Navigate } from "react-router-dom";
import { useAuth } from "../auth/useAuth";
import { Hero } from "./components/Hero";
import { PubNav } from "./components/PubNav";
import { WhySection } from "./components/WhySection";

export function LandingPage() {
  const user = useAuth((s) => s.user);
  if (user) {
    return <Navigate to="/home" replace />;
  }
  return (
    <div className="min-h-screen bg-bg">
      <PubNav />
      <Hero />
      <WhySection />
    </div>
  );
}
