import Link from "next/link";
import { fetchCalls } from "@/lib/api";
import type { Sentiment } from "@/lib/types";

export const metadata = { title: "Çağrılar | Miço Usta" };

const SENTIMENT_BADGE: Record<Sentiment, string> = {
  positive: "bg-green-100 text-green-700",
  neutral: "bg-gray-100 text-gray-600",
  negative: "bg-red-100 text-red-700",
};

const SENTIMENT_LABEL: Record<Sentiment, string> = {
  positive: "Pozitif",
  neutral: "Nötr",
  negative: "Negatif",
};

function formatDuration(sec: number): string {
  if (sec === 0) return "—";
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  return `${m}:${String(s).padStart(2, "0")}`;
}

export default async function CallsPage() {
  const calls = await fetchCalls();

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-gray-900">Çağrılar</h1>

      <div className="overflow-hidden rounded-xl border border-gray-200 bg-white shadow-sm">
        <table className="min-w-full divide-y divide-gray-200">
          <thead className="bg-gray-50">
            <tr>
              {["Arayan", "Tarih", "Süre", "Durum", "Duygu", ""].map((h) => (
                <th
                  key={h}
                  className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-gray-500"
                >
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {calls.map((call) => (
              <tr key={call.id} className="hover:bg-gray-50 transition-colors">
                <td className="px-4 py-3 text-sm font-medium text-gray-900">
                  {call.caller}
                </td>
                <td className="px-4 py-3 text-sm text-gray-500">
                  {new Date(call.startedAt).toLocaleString("tr-TR")}
                </td>
                <td className="px-4 py-3 text-sm text-gray-500">
                  {formatDuration(call.durationSec)}
                </td>
                <td className="px-4 py-3 text-sm text-gray-500 capitalize">
                  {call.status}
                </td>
                <td className="px-4 py-3">
                  <span
                    className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${SENTIMENT_BADGE[call.sentiment]}`}
                  >
                    {SENTIMENT_LABEL[call.sentiment]}
                  </span>
                </td>
                <td className="px-4 py-3 text-right text-sm">
                  <Link
                    href={`/admin/calls/${call.id}`}
                    className="text-blue-600 hover:underline"
                  >
                    Detay →
                  </Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
