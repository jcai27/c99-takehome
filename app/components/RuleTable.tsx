"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { formatRate, rateBadgeClass, type RateKind } from "@/lib/format";
import type { ApplicableRule } from "@/lib/queries";

type SortKey = "subchapter" | "rate" | "hts";
type SortDir = "asc" | "desc";

const RATE_ORDER: Record<RateKind, number> = {
  additive: 0,
  ad_valorem: 1,
  specific: 2,
  other: 3,
  no_change: 4,
  free: 5,
};

export default function RuleTable({ rules }: { rules: ApplicableRule[] }) {
  const [sortKey, setSortKey] = useState<SortKey>("subchapter");
  const [sortDir, setSortDir] = useState<SortDir>("asc");
  const [subchapterFilter, setSubchapterFilter] = useState<string>("");
  const [rateKindFilter, setRateKindFilter] = useState<string>("");
  const [hideExcluded, setHideExcluded] = useState(false);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  const subchapters = useMemo(
    () => Array.from(new Set(rules.map((r) => r.subchapter))).sort(),
    [rules],
  );
  const rateKinds = useMemo(
    () => Array.from(new Set(rules.map((r) => r.rate_kind))).sort(),
    [rules],
  );

  function toggleSort(key: SortKey) {
    if (sortKey === key) {
      setSortDir(sortDir === "asc" ? "desc" : "asc");
    } else {
      setSortKey(key);
      setSortDir("asc");
    }
  }

  function toggleExpanded(hts: string) {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(hts)) next.delete(hts);
      else next.add(hts);
      return next;
    });
  }

  const visible = useMemo(() => {
    let out = rules;
    if (subchapterFilter) out = out.filter((r) => r.subchapter === subchapterFilter);
    if (rateKindFilter) out = out.filter((r) => r.rate_kind === rateKindFilter);
    if (hideExcluded) out = out.filter((r) => !r.is_excluded);

    const dir = sortDir === "asc" ? 1 : -1;
    out = [...out].sort((a, b) => {
      if (sortKey === "subchapter") {
        return dir * (a.subchapter.localeCompare(b.subchapter) || a.hts.localeCompare(b.hts));
      }
      if (sortKey === "hts") {
        return dir * a.hts.localeCompare(b.hts);
      }
      // rate: order by kind severity first, then numeric value within kind
      const kindDiff = RATE_ORDER[a.rate_kind] - RATE_ORDER[b.rate_kind];
      if (kindDiff !== 0) return dir * kindDiff;
      const av = a.rate_value !== null ? Number(a.rate_value) : -1;
      const bv = b.rate_value !== null ? Number(b.rate_value) : -1;
      return dir * (bv - av);
    });
    return out;
  }, [rules, subchapterFilter, rateKindFilter, hideExcluded, sortKey, sortDir]);

  function arrow(key: SortKey) {
    if (sortKey !== key) return null;
    return <span className="arrow">{sortDir === "asc" ? "↑" : "↓"}</span>;
  }

  return (
    <div>
      <div className="rule-table-controls">
        <label>
          Subchapter:{" "}
          <select value={subchapterFilter} onChange={(e) => setSubchapterFilter(e.target.value)}>
            <option value="">All</option>
            {subchapters.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </label>
        <label>
          Rate kind:{" "}
          <select value={rateKindFilter} onChange={(e) => setRateKindFilter(e.target.value)}>
            <option value="">All</option>
            {rateKinds.map((k) => (
              <option key={k} value={k}>
                {k}
              </option>
            ))}
          </select>
        </label>
        <label>
          <input
            type="checkbox"
            checked={hideExcluded}
            onChange={(e) => setHideExcluded(e.target.checked)}
          />{" "}
          Hide rules excluded by another provision
        </label>
        <span className="rule-count">
          {visible.length} of {rules.length} shown
        </span>
      </div>

      <table className="rule-table">
        <thead>
          <tr>
            <th onClick={() => toggleSort("hts")}>Rule{arrow("hts")}</th>
            <th onClick={() => toggleSort("subchapter")}>Subchapter{arrow("subchapter")}</th>
            <th>Description</th>
            <th onClick={() => toggleSort("rate")}>Rate{arrow("rate")}</th>
            <th>Excluded?</th>
            <th>Notes</th>
          </tr>
        </thead>
        <tbody>
          {visible.map((r) => {
            const isExpanded = expanded.has(r.hts);
            return (
              <tr key={r.hts}>
                <td>
                  <Link href={`/rule/${r.hts}`} className="mono">
                    {r.hts}
                  </Link>
                </td>
                <td>
                  <span className="badge badge-subchapter">{r.subchapter}</span>
                </td>
                <td className="desc-cell">
                  {isExpanded ? r.context_text : truncate(r.description, 140)}
                  {r.context_text.length > 140 && (
                    <div>
                      <a
                        href="#"
                        onClick={(e) => {
                          e.preventDefault();
                          toggleExpanded(r.hts);
                        }}
                      >
                        {isExpanded ? "show less" : "show full scope"}
                      </a>
                    </div>
                  )}
                </td>
                <td>
                  <span className={rateBadgeClass(r.rate_kind)}>
                    {formatRate(r.rate_kind, r.rate_value, r.rate_text)}
                  </span>
                </td>
                <td>
                  {r.is_excluded ? (
                    <span className="badge badge-excluded">excluded by another rule</span>
                  ) : (
                    "—"
                  )}
                </td>
                <td>{r.note_count > 0 ? r.note_count : "—"}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function truncate(s: string, n: number): string {
  return s.length > n ? s.slice(0, n).trimEnd() + "…" : s;
}
