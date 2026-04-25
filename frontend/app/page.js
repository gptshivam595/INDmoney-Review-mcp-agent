import { DashboardShell } from "../components/dashboard-shell";

const PRODUCTION_API_BASE_URL =
  "https://weekly-product-review-pulse-backend-production.up.railway.app";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ||
  (process.env.NODE_ENV === "production" ? PRODUCTION_API_BASE_URL : "http://127.0.0.1:8000");

export default function Page() {
  return <DashboardShell apiBaseUrl={API_BASE_URL} />;
}
