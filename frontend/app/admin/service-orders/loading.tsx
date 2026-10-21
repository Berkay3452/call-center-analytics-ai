import { ServiceOrdersTableSkeleton } from "@/components/skeletons";

export default function ServiceOrdersLoading() {
  return (
    <div className="space-y-6">
      <div className="h-10 w-64 bg-slate-200 dark:bg-slate-800 rounded-lg animate-pulse" />
      <div className="h-9 w-full max-w-lg bg-slate-100 dark:bg-slate-800/60 rounded-xl animate-pulse" />
      <ServiceOrdersTableSkeleton />
    </div>
  );
}
