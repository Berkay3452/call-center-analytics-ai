import { notFound } from "next/navigation";
import { getServiceOrderById, getServiceOrders } from "@/lib/api/client";
import { ServiceOrderDetailCard } from "@/components/service-orders";
import { formatOrderCode } from "@/lib/types";
import mockServiceOrdersList from "@/mocks/servis_emirleri.json";

interface ServiceOrderDetailPageProps {
  params: Promise<{ id: string }>;
}

export async function generateStaticParams() {
  try {
    const res = await getServiceOrders({ page_size: 100 });
    if (res?.items && res.items.length > 0) {
      return res.items.map((o) => ({ id: o.id }));
    }
  } catch {
    // Derleme anında backend kapalıysa mock fallback
  }
  return mockServiceOrdersList.items.map((o) => ({ id: o.id }));
}

export async function generateMetadata({ params }: ServiceOrderDetailPageProps) {
  try {
    const { id } = await params;
    const code = formatOrderCode(id);
    return { title: `${code} Servis Emri Detayı | Miço Usta` };
  } catch {
    return { title: "Servis Emri Detayı | Miço Usta" };
  }
}

export default async function ServiceOrderDetailPage({
  params,
}: ServiceOrderDetailPageProps) {
  const { id } = await params;

  let order;
  try {
    order = await getServiceOrderById(id);
  } catch {
    notFound();
  }

  if (!order) {
    notFound();
  }

  return (
    <div className="max-w-5xl mx-auto py-2">
      <ServiceOrderDetailCard order={order} showBackLink={true} />
    </div>
  );
}
