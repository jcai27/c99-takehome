import Link from "next/link";
import { notFound } from "next/navigation";
import sql from "@/lib/db";
import { formatRate, rateBadgeClass } from "@/lib/format";
import {
  getApplicableRules,
  getHtsBaseWithAncestors,
  getLatestImportRun,
  type HtsBaseRow,
} from "@/lib/queries";
import RuleTable from "@/components/RuleTable";

export default async function HtsCodePage({
  params,
}: {
  params: Promise<{ code: string }>;
}) {
  const { code: rawCode } = await params;
  const code = decodeURIComponent(rawCode);

  let chain = await getHtsBaseWithAncestors(code);

  if (chain.length === 0) {
    // Maybe the user typed a shorter prefix than the exact stored code
    // (e.g. "0402.29.50" when the row is "0402.29.50.00"). Offer the real
    // matches instead of a bare 404.
    const candidates = await sql<{ hts: string; description: string }[]>`
      SELECT hts, description FROM hts_base
      WHERE is_group = false AND hts LIKE ${code + ".%"}
      ORDER BY hts LIMIT 25
    `;
    if (candidates.length > 0) {
      return (
        <>
          <h1 className="mono">{code}</h1>
          <p className="lede">
            That&rsquo;s not a complete HTS code on its own &mdash; here&rsquo;s
            what it expands to:
          </p>
          <ul className="search-results">
            {candidates.map((c) => (
              <li key={c.hts}>
                <Link href={`/hts/${c.hts}`}>
                  <span className="code mono">{c.hts}</span>
                </Link>
                <span className="desc">{c.description}</span>
              </li>
            ))}
          </ul>
        </>
      );
    }
    notFound();
  }

  const leaf = chain[chain.length - 1] as HtsBaseRow;
  const applicable = await getApplicableRules(leaf.hts);
  const importRun = await getLatestImportRun();

  return (
    <>
      <div className="breadcrumb">
        <Link href="/">search</Link>
        {chain.map((a, i) => (
          <span key={a.hts}>
            <span className="sep"> / </span>
            {i === chain.length - 1 ? (
              <span className="mono">{a.hts}</span>
            ) : (
              <Link href={`/hts/${a.hts}`} className="mono">
                {a.hts}
              </Link>
            )}
          </span>
        ))}
      </div>

      <h1 className="mono">{leaf.hts}</h1>
      <p className="lede">{leaf.description}</p>

      <div className="card">
        <h3 style={{ marginTop: 0 }}>Base MFN rate</h3>
        {leaf.is_group ? (
          <p>
            This is a heading/subheading grouping, not a declarable line
            &mdash; it has no rate of its own.
          </p>
        ) : (
          <p>
            <span className={rateBadgeClass(leaf.rate_kind)}>
              {formatRate(leaf.rate_kind, leaf.mfn_rate_pct, leaf.rate_text)}
            </span>{" "}
            {leaf.rate_inherited && (
              <span className="lede" style={{ display: "inline" }}>
                &nbsp;(inherited from {leaf.parent_hts} &mdash; this is a
                statistical subdivision with no rate of its own)
              </span>
            )}
          </p>
        )}
      </div>

      <h2>Chapter 99 provisions that apply to this code</h2>

      {applicable.length === 0 ? (
        <div className="empty-state">
          No Chapter 99 provision on record currently references this code.
          That&rsquo;s the common case &mdash; only a small fraction of base
          codes have any Chapter 99 exposure.
        </div>
      ) : (
        <>
          <div className="disclaimer">
            This is every Chapter 99 provision on record that cites this
            code &mdash; it is <strong>not</strong> a determination of which
            one currently governs your entry. Multiple provisions can be
            listed for the same code across years of trade actions, and this
            dataset has no reliable signal for which are still in force
            (CBP&rsquo;s filing instructions, which state stacking order,
            aren&rsquo;t part of this data). Use the &ldquo;excluded
            by&rdquo; column and each provision&rsquo;s own notes to narrow
            it down.
          </div>
          <RuleTable rules={applicable} />
        </>
      )}

      {importRun && (
        <div className="provenance">
          Data as of HTS revision <strong>{importRun.revision}</strong>,
          imported {new Date(importRun.imported_at).toLocaleString()}. Source:{" "}
          <code>{importRun.manifest_path}</code>.
        </div>
      )}
    </>
  );
}
