"""Aggregate benchmark metrics into markdown tables.  python3 bench_table.py <workdir> <code> ...
env NEW_TAG / NEW_LABEL / OLD_TAG / OLD_LABEL name the two Quadre columns (as in bench_report.sh)."""
import json, os, sys
W = sys.argv[1]; codes = sys.argv[2:]
NEW_TAG, NEW_LABEL = os.environ.get('NEW_TAG', 'quadre047'), os.environ.get('NEW_LABEL', 'Quadre 0.4.7')
OLD_TAG, OLD_LABEL = os.environ.get('OLD_TAG', 'quadre043'), os.environ.get('OLD_LABEL', 'Quadre 0.4.3')
TOOLS = [('exoside', 'Exoside 1.4'), (NEW_TAG, NEW_LABEL), (OLD_TAG, OLD_LABEL), ('autoremesher', 'AutoRemesher 1.2'), ('quadriflow', 'QuadriFlow')]
COLS = [('faces', 'Quads', 0), ('nonquads', 'Non-quads', 0), ('singular', 'Poles', 0), ('curv_misalign_strong_mean_deg', 'Loops off form', 1), ('angle_dev_mean', 'Corner error', 1),
        ('angle_bad_pct', 'Bent corners %', 2), ('nbr_area_ratio_p95', 'Size jump', 2), ('fid_fwd_mean_pm', 'Off sculpt ‰', 2), ('fid_rev_mean_pm', 'Detail lost ‰', 2), ('fid_rev_max_pm', 'Worst spot ‰', 1)]
rows = {}
for code in codes:
    p = os.path.join(W, 'bench', code + '_metrics.json')
    res = json.load(open(p)) if os.path.exists(p) else []
    for r in res:
        r['nonquads'] = r['tris'] + r['ngons']
        for key, _ in TOOLS:
            if key in r['file']:
                rows[(code, key)] = r
def fmt(v, d): return f"{v:,.{d}f}"
for code in codes:
    meta = json.load(open(os.path.join(W, 'input', code + '.json')))
    print(f"\n### {code} — {meta['note']} ({meta['tris']:,} triangles in, symmetry {meta['sym'] or 'off'})\n")
    print("| Tool | " + " | ".join(c[1] for c in COLS) + " |")
    print("|---|" + "---|" * len(COLS))
    for key, label in TOOLS:
        r = rows.get((code, key))
        print(f"| {label} | " + (" | ".join(fmt(r[c[0]], c[2]) for c in COLS) if r else "**no result** " + "| " * (len(COLS) - 1)) + " |")
print("\n### Averages over the shapes every tool finished\n")
common = [c for c in codes if all((c, k) in rows for k, _ in TOOLS)]
print(f"Shapes counted: {len(common)} of {len(codes)} ({', '.join(common)})\n")
print("| Tool | Finished | " + " | ".join(c[1] for c in COLS[2:]) + " |")
print("|---|---|" + "---|" * len(COLS[2:]))
for key, label in TOOLS:
    done = sum(1 for c in codes if (c, key) in rows)
    vals = [sum(rows[(c, key)][col[0]] for c in common) / max(len(common), 1) for col in COLS[2:]]
    print(f"| {label} | {done}/{len(codes)} | " + " | ".join(fmt(v, col[2]) for v, col in zip(vals, COLS[2:])) + " |")
print(f"\n### Exoside vs {NEW_LABEL} on every shape both finished\n")
both = [c for c in codes if (c, 'exoside') in rows and (c, NEW_TAG) in rows]
print("| Shape | Loops off form (E / Q) | Corner error (E / Q) | Detail lost (E / Q) | Poles (E / Q) | Quads (E / Q) |")
print("|---|---|---|---|---|---|")
for c in both:
    e, q = rows[(c, 'exoside')], rows[(c, NEW_TAG)]
    print(f"| {c} | {e['curv_misalign_strong_mean_deg']:.1f} / {q['curv_misalign_strong_mean_deg']:.1f} | {e['angle_dev_mean']:.1f} / {q['angle_dev_mean']:.1f} | {e['fid_rev_mean_pm']:.2f} / {q['fid_rev_mean_pm']:.2f} | {e['singular']} / {q['singular']} | {e['faces']:,} / {q['faces']:,} |")
