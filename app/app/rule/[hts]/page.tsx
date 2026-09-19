import Link from "next/link";
import { notFound } from "next/navigation";
import { formatRate, rateBadgeClass } from "@/lib/format";
import {
  getLatestImportRun,
  getRule,
  getRuleExcludedBy,
  getRuleExcludes,
  getRuleNotes,
  getRuleReferences,
} from "@/lib/queries";

export default async function RulePage({
  params,
}: {
  params: Promise<{ hts: string }>;
}) {
  const { hts: rawHts } = await params;
  const hts = decodeURIComponent(rawHts);

  const rule = await getRule(hts);
  if (!rule) notFound();

  const [references, excludes, excludedBy, notes, importRun] = await Promise.all([
    getRuleReferences(hts),
    getRuleExcludes(hts),
    getRuleExcludedBy(hts),
    getRuleNotes(hts),
    getLatestImportRun(),
  ]);

  return (
    <>
      <div className="breadcrumb">
        <Link href="/">search</Link>
        <span className="sep"> / </span>
        <span className="badge badge-subchapter">subchapter {rule.subchapter}</span>
      </div>

      <h1 className="mono">{rule.hts}</h1>

      <div className="card">
        <h3 style={{ marginTop: 0 }}>Full scope</h3>
        <p>{rule.context_text}</p>
      </div>

      <h2>Rates</h2>
      <div className="card">
        <p>
          <strong>General:</strong>{" "}
          <span className={rateBadgeClass(rule.rate_kind)}>
            {formatRate(rule.rate_kind, rule.rate_value, rule.rate_text)}
          </span>
        </p>
        {rule.special_text && (
          <p>
            <strong>Special (preferential/FTA):</strong> {rule.special_text}
          </p>
        )}
        {rule.other_text && (
          <p>
            <strong>Other (column 2):</strong> {rule.other_text}
          </p>
        )}
      </div>

      <h2>References into the base schedule</h2>
      {references.length === 0 ? (
        <p className="lede">This provision doesn&rsquo;t cite a specific base code.</p>
      ) : (
        <ul className="edge-list">
          {references.map(({ target_hts, resolved }) => (
            <li key={target_hts}>
              <div className="mono">{target_hts}</div>
              {resolved.length === 0 ? (
                <span className="lede">
                  Not found in the current base schedule &mdash; likely renumbered
                  or removed since this provision was written.
                </span>
              ) : (
                <ul style={{ margin: "0.4rem 0 0", paddingLeft: "1.1rem" }}>
                  {resolved.map((r) => (
                    <li key={r.hts}>
                      <Link href={`/hts/${r.hts}`} className="mono">
                        {r.hts}
                      </Link>{" "}
                      <span className="lede" style={{ display: "inline" }}>
                        {r.description}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </li>
          ))}
        </ul>
      )}

      {excludes.length > 0 && (
        <>
          <h2>Excludes</h2>
          <p className="lede">
            This provision carves out the following &mdash; they&rsquo;re
            handled by their own, more specific provision instead:
          </p>
          <ul className="edge-list">
            {excludes.map((r) => (
              <li key={r.hts}>
                <Link href={`/rule/${r.hts}`} className="mono">
                  {r.hts}
                </Link>{" "}
                <span className="lede" style={{ display: "inline" }}>
                  {r.description}
                </span>
              </li>
            ))}
          </ul>
        </>
      )}

      {excludedBy.length > 0 && (
        <>
          <h2>Excluded by</h2>
          <p className="lede">
            These provisions carve this one out of their own broader scope:
          </p>
          <ul className="edge-list">
            {excludedBy.map((r) => (
              <li key={r.hts}>
                <Link href={`/rule/${r.hts}`} className="mono">
                  {r.hts}
                </Link>{" "}
                <span className="lede" style={{ display: "inline" }}>
                  {r.description}
                </span>
              </li>
            ))}
          </ul>
        </>
      )}

      <h2>Notes cited</h2>
      {notes.length === 0 ? (
        <p className="lede">No notes cited.</p>
      ) : (
        <ul className="notes-list">
          {notes.map((n) => (
            <li key={n.id}>
              <div className="note-label">
                {n.scope_type === "chapter" ? "Chapter 99" : `Subchapter ${n.subchapter}`}{" "}
                {n.note_type === "us" ? "U.S." : "Statistical"} note {n.number}
              </div>
              <p style={{ margin: 0 }}>{n.text}</p>
            </li>
          ))}
        </ul>
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
