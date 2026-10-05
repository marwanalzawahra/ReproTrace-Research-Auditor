from pathlib import Path
from html import escape
import json

STATUSES=["VERIFIED","LIKELY","AMBIGUOUS","UNSUPPORTED","IGNORED"]

def build_summary(matches):
    counts={s:0 for s in STATUSES}
    for m in matches:
        counts[m["status"]]=counts.get(m["status"],0)+1
    considered=sum(counts[s] for s in ["VERIFIED","LIKELY","AMBIGUOUS","UNSUPPORTED"])
    return {
        "total_numeric_tokens":len(matches),
        "considered_claims":considered,
        **{s.lower():counts[s] for s in STATUSES},
        "strict_verification_rate":counts["VERIFIED"]/considered if considered else 0.0,
    }

def write_reports(output_dir:Path, inventory, matches):
    output_dir.mkdir(parents=True,exist_ok=True)
    summary=build_summary(matches)
    payload={"summary":summary,"inventory":inventory,"claims":matches}
    jp=output_dir/"audit_report.json"
    jp.write_text(json.dumps(payload,indent=2),encoding="utf-8")

    rows=[]
    for m in matches:
        cand="<br>".join(
            f"{escape(c['source'])} — {escape(c['locator'])} — {c['value']} "
            f"— role <b>{c['evidence_role']}</b> — score {c['evidence_score']:.3f} "
            f"(role {c['role_score']:.2f}, anchor {c['anchor_score']:.2f})"
            for c in m["candidates"][:5]
        ) or "—"
        rows.append(
            "<tr>"
            f"<td>{m['line']}</td><td>{escape(m['display_value'])}</td>"
            f"<td>{escape(m['claim_type'])}</td><td><b>{escape(m['claim_role'])}</b></td>"
            f"<td>{escape(m['context'])}</td>"
            f"<td><b>{escape(m['status'])}</b><br><small>{escape(m['status_reason'])}</small></td>"
            f"<td>{cand}</td></tr>"
        )

    cards="".join(
        f'<div class="card"><b>{k.replace("_"," ").title()}</b><br>{v}</div>'
        for k,v in [
            ("considered_claims",summary["considered_claims"]),
            ("verified",summary["verified"]),("likely",summary["likely"]),
            ("ambiguous",summary["ambiguous"]),("unsupported",summary["unsupported"]),
            ("ignored",summary["ignored"])
        ]
    )

    html=f"""<!doctype html><html><head><meta charset="utf-8">
<title>ReproTrace v0.3</title>
<style>
body{{font-family:system-ui,sans-serif;max-width:1600px;margin:36px auto;padding:0 18px}}
table{{border-collapse:collapse;width:100%;font-size:13px}}
th,td{{border:1px solid #ddd;padding:7px;vertical-align:top;text-align:left}}
th{{background:#f5f5f5;position:sticky;top:0}}
.summary{{display:flex;gap:12px;flex-wrap:wrap;margin:20px 0}}
.card{{border:1px solid #ddd;border-radius:8px;padding:12px 16px;min-width:115px}}
small{{color:#555}}
</style></head><body>
<h1>ReproTrace v0.3</h1>
<p>Role-aware conservative scientific evidence audit.</p>
<div class="summary">{cards}</div>
<p><b>Strict verification rate:</b> {summary['strict_verification_rate']:.1%}</p>
<h2>Claim audit</h2>
<table><thead><tr><th>Line</th><th>Value</th><th>Type</th><th>Role</th>
<th>Context</th><th>Status</th><th>Ranked evidence</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table>
<h2>Project inventory</h2><p>{len(inventory)} files indexed with SHA-256 fingerprints.</p>
</body></html>"""
    hp=output_dir/"audit_report.html"
    hp.write_text(html,encoding="utf-8")
    return jp,hp
