import type { IndexFile } from "../types";

/** Race picker from index.json. A simple list is enough at this scale. */
export function RacePicker({
  index,
  onSelect,
}: {
  index: IndexFile;
  onSelect: (slug: string) => void;
}) {
  const races = [...index.races].sort((a, b) =>
    b.slug.localeCompare(a.slug),
  );
  return (
    <div className="picker">
      <h2>Elige una carrera</h2>
      <ul>
        {races.map((r) => (
          <li key={r.slug}>
            <button type="button" onClick={() => onSelect(r.slug)}>
              <span className="picker-event">{r.event}</span>
              <span className="picker-meta">
                {r.date} · {r.drivers.length} pilotos · {r.n_samples.toLocaleString("es-ES")} muestras
              </span>
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
