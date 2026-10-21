import { ServiceOrderDetailSkeleton } from "@/components/skeletons";

export default function ServiceOrderDetailLoading() {
  return (
    <div className="max-w-5xl mx-auto py-2">
      <ServiceOrderDetailSkeleton />
    </div>
  );
}
