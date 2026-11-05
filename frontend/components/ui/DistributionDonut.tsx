import { Card, CardHeader } from "@/components/ui";

export interface DistributionRow {
  key: string;
  label: string;
  count: number;
}

// Tema tonları; dilimler ayrıca numaralı metin lejantıyla tanımlanır.
const COLORS = ["var(--color-brand-600)", "var(--color-accent-500)", "#059669", "#7c3aed", "#be185d", "#64748b"];

export function DistributionDonut({ title, rows, emptyText }: {
  title: string;
  rows: DistributionRow[];
  emptyText: string;
}) {
  const positive = rows.filter((row) => Number.isFinite(row.count) && row.count > 0)
    .sort((a, b) => b.count - a.count);
  let slices = positive;
  if (positive.length > 6) {
    const named = positive.filter((row) => row.label !== "Diğer").slice(0, 5);
    const retained = new Set(named.map((row) => row.key));
    slices = [...named, { key: "__other", label: "Diğer", count: positive
      .filter((row) => !retained.has(row.key)).reduce((sum, row) => sum + row.count, 0) }];
  }
  const total = slices.reduce((sum, row) => sum + row.count, 0);
  const percentages = slices.map((row) => row.count / total * 100);

  return (
    <Card data-testid="distribution-chart" className="min-w-0">
      <CardHeader title={title} />
      {total === 0 ? (
        <p className="py-8 text-center text-sm text-slate-500">{emptyText}</p>
      ) : (
        <figure aria-label={title} className="space-y-3">
          <svg viewBox="0 0 128 128" role="img" aria-label={`${title}: toplam ${total} kayıt. Dilimlerin sayı ve yüzdeleri aşağıdaki lejantta.`} className="mx-auto h-32 w-32">
            {slices.map((row, index) => (
              <circle key={row.key} data-testid="donut-slice" cx="64" cy="64" r="48" fill="none"
                stroke={COLORS[index]} strokeWidth="22" pathLength="100"
                strokeDasharray={`${percentages[index]} ${100 - percentages[index]}`}
                strokeDashoffset={-percentages.slice(0, index).reduce((sum, value) => sum + value, 0)}
                transform="rotate(-90 64 64)">
                <title>{`${index + 1}. ${row.label}: ${row.count} (%${percentages[index].toFixed(1)})`}</title>
              </circle>
            ))}
            <text x="64" y="63" textAnchor="middle" className="fill-brand-800 text-lg font-semibold">{total}</text>
            <text x="64" y="79" textAnchor="middle" className="fill-slate-600 text-[10px]">toplam</text>
          </svg>
          <figcaption>
            <ul className="space-y-1.5" aria-label={`${title} lejantı`}>
              {slices.map((row, index) => (
                <li key={row.key} className="flex items-start gap-2 text-xs text-slate-700">
                  <span aria-hidden="true" className="mt-0.5 h-3 w-3 shrink-0 rounded-sm" style={{ backgroundColor: COLORS[index] }} />
                  <span className="min-w-0 flex-1 break-words">{index + 1}. {row.label}</span>
                  <span className="shrink-0 font-semibold text-brand-800">{row.count} <span className="font-normal text-slate-600">(%{percentages[index].toFixed(1).replace(".", ",")})</span></span>
                </li>
              ))}
            </ul>
          </figcaption>
        </figure>
      )}
    </Card>
  );
}
