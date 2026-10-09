import { PlaceholderCard } from "@/components/PlaceholderCard";
import { fetchCrmSuggestions } from "@/lib/api";

export const metadata = { title: "CRM Önerileri | Miço Usta" };

const PRIORITY_BADGE = {
  high: "bg-red-100 text-red-700",
  medium: "bg-yellow-100 text-yellow-700",
  low: "bg-gray-100 text-gray-600",
} as const;

const PRIORITY_LABEL = {
  high: "Yüksek",
  medium: "Orta",
  low: "Düşük",
} as const;

export default async function CrmPage() {
  const suggestions = await fetchCrmSuggestions();

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-gray-900">CRM Önerileri</h1>
      <p className="text-sm text-gray-500">
        AI tarafından üretilen sonraki en iyi eylem önerileri. Öncelikli
        müşterilere odaklanın.
      </p>

      <div className="space-y-3">
        {suggestions.map((s) => (
          <div
            key={s.callId}
            className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm flex items-start gap-4"
          >
            <span
              className={`mt-0.5 inline-flex shrink-0 rounded-full px-2 py-0.5 text-xs font-semibold ${PRIORITY_BADGE[s.priority]}`}
            >
              {PRIORITY_LABEL[s.priority]}
            </span>
            <div>
              <p className="text-sm font-semibold text-gray-900">{s.caller}</p>
              <p className="mt-1 text-sm text-gray-600">{s.suggestion}</p>
              <p className="mt-1 text-xs text-gray-400">Çağrı: {s.callId}</p>
            </div>
          </div>
        ))}
      </div>

      {/* Gelecekte CRM entegrasyon alanı */}
      <PlaceholderCard title="CRM Entegrasyonu (Yakında)">
        <p className="text-sm text-gray-500">
          Salesforce / HubSpot bağlantısı Miço Usta backend entegrasyonu ile
          eklenecektir.
        </p>
      </PlaceholderCard>
    </div>
  );
}
