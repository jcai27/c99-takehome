import Link from "next/link";
import { getCoverageExamples, searchHtsBase } from "@/lib/queries";

export default async function HomePage({
  searchParams,
}: {
  searchParams: Promise<{ q?: string }>;
}) {
  const { q } = await searchParams;
  const query = (q ?? "").trim();
  const results = query ? await searchHtsBase(query) : [];
  const examples = query ? [] : await getCoverageExamples(6);

  return (
    <>
      <h1>Chapter 99 Explorer</h1>
      <p className="lede">
        Chapter 99 doesn&rsquo;t classify goods &mdash; it modifies the duty on
        goods already classified elsewhere in the tariff schedule. Pick a base
        HTS code (chapters 1&ndash;97) below and see every Chapter&nbsp;99
        provision that currently touches it: its resolved rate, whether
        something else excludes it, and the notes that explain why.
      </p>

      <form className="search-form" action="/" method="get">
        <input
          type="text"
          name="q"
          defaultValue={query}
          placeholder="Search by HTS code or product description (e.g. &quot;steel pipe&quot;, &quot;0402.29&quot;)"
          autoFocus
        />
        <button type="submit">Search</button>
      </form>

      {query ? (
        <>
          <h2>
            Results for &ldquo;{query}&rdquo; <span className="rule-count">({results.length})</span>
          </h2>
          {results.length === 0 ? (
            <div className="empty-state">
              No base HTS codes matched &ldquo;{query}&rdquo;. Try a shorter
              keyword, or search by code prefix (e.g. &ldquo;7306&rdquo;).
            </div>
          ) : (
            <ul className="search-results">
              {results.map((r) => (
                <li key={r.hts}>
                  <Link href={`/hts/${r.hts}`}>
                    <span className="code mono">{r.hts}</span>
                  </Link>
                  <span className="desc">{r.description}</span>
                  {r.rule_count > 0 && (
                    <span className="coverage">
                      {r.rule_count} Chapter 99 {r.rule_count === 1 ? "provision" : "provisions"}
                    </span>
                  )}
                </li>
              ))}
            </ul>
          )}
        </>
      ) : (
        <>
          <h2>Codes with the most Chapter 99 activity right now</h2>
          <p className="lede">
            Only a small fraction of base codes have any Chapter&nbsp;99
            exposure &mdash; these are good starting points.
          </p>
          <div className="example-grid">
            {examples.map((e) => (
              <Link key={e.hts} href={`/hts/${e.hts}`} className="example-card">
                <div className="code mono">{e.hts}</div>
                <div className="desc">{e.description}</div>
                <div className="meta">
                  {e.rule_count} provisions &middot; subchapter{e.subchapters.length > 1 ? "s" : ""}{" "}
                  {e.subchapters.join(", ")}
                </div>
              </Link>
            ))}
          </div>
        </>
      )}
    </>
  );
}
