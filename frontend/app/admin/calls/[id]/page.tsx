import Link from "next/link";
import { notFound } from "next/navigation";
import { fetchCallById, fetchCalls } from "@/lib/api";
import { PlaceholderCard } from "@/components/PlaceholderCard";

interface Props {
  params: Promise<{ id: string }>;
}

/**
 * Build sırasında bilinen tüm call ID'lerini statik olarak üret.
 * Yeni çağrılar (backend entegrasyonundan gelen) ISR/on-demand revalidation ile ele alınacaktır.
 */
export async function generateStaticParams() {
  const calls = await fetchCalls();
  return calls.map((c) => ({ id: c.id }));
}

export async function generateMetadata({ params }: Props) {
  const { id } = await params;
  return { title: `Çağrı ${id} | Miço Usta` };
}

export default async function CallDetailPage({ params }: Props) {
  const { id } = await params;
  const call = await fetchCallById(id);

  if (!call) notFound();

  return (
    <div className="space-y-6">
      {/* Geri */}
      <Link
        href="/admin/calls"
        className="text-sm text-blue-600 hover:underline"
      >
        ← Çağrı listesine dön
      </Link>

      <h1 className="text-2xl font-bold text-gray-900">
        Çağrı Detayı — {call.caller}
      </h1>

      {/* Meta bilgiler */}
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        {[
          { label: "Tarih", value: new Date(call.startedAt).toLocaleString("tr-TR") },
          { label: "Süre", value: call.durationSec ? `${Math.floor(call.durationSec / 60)}dk ${call.durationSec % 60}sn` : "—" },
          { label: "Durum", value: call.status },
          { label: "Duygu", value: call.sentiment },
        ].map((item) => (
          <div
            key={item.label}
            className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm"
          >
            <p className="text-xs text-gray-500">{item.label}</p>
            <p className="mt-1 text-sm font-semibold text-gray-900 capitalize">
              {item.value}
            </p>
          </div>
        ))}
      </div>

      {/* Özet */}
      <PlaceholderCard title="AI Özeti">
        <p className="text-sm text-gray-700">{call.summary || "Özet yok."}</p>
      </PlaceholderCard>

      {/* Transkript */}
      <PlaceholderCard title="Transkript">
        <p className="text-sm text-gray-700 whitespace-pre-wrap">
          {call.transcript || "Transkript mevcut değil."}
        </p>
      </PlaceholderCard>

      {/* Etiketler */}
      <PlaceholderCard title="Etiketler">
        <div className="flex flex-wrap gap-2">
          {call.tags.length > 0 ? (
            call.tags.map((tag) => (
              <span
                key={tag}
                className="rounded-full bg-blue-50 px-3 py-1 text-xs font-medium text-blue-700"
              >
                {tag}
              </span>
            ))
          ) : (
            <span className="text-sm text-gray-400">Etiket yok.</span>
          )}
        </div>
      </PlaceholderCard>
    </div>
  );
}
