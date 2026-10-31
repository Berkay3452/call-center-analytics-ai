import { Suspense } from "react";
import AnalyticsDashboard from "./AnalyticsDashboard";
import { AnalyticsDashboardSkeleton } from "@/components/skeletons";


export const metadata = { title: "Çağrı Analitiği | Miço Usta" };

export default function AnalyticsPage() {
  return (
    <Suspense fallback={<AnalyticsDashboardSkeleton />}>
      <AnalyticsDashboard />
    </Suspense>
  );
}
