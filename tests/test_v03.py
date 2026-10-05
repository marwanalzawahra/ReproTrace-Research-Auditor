from pathlib import Path
import tempfile, json
from reprotrace.claims import extract_claims
from reprotrace.results import index_result_values
from reprotrace.match import match_claims

def run():
    with tempfile.TemporaryDirectory() as td:
        root=Path(td)
        paper=root/"paper.tex"
        paper.write_text(r"""
\documentclass[11pt]{article}
At 1\% step-wise FPR, Claude Opus 4.6 has a 34\% undetected sabotage rate.
Error bars show Wilson 95\% CI.
We test (1) Base, (2) No Network, and (3) Editor Only.
BashArena has 4 side tasks.
""",encoding="utf-8")
        (root/"metrics.json").write_text(json.dumps({
            "attack":{"fpr_grid":0.34,"safety":0.34}
        }),encoding="utf-8")
        (root/"run.log").write_text(
            "Audit budget: 1% step-wise FPR\nn=50 threshold=7.0 Sabotage:59.5%\n",
            encoding="utf-8"
        )
        (root/"thinking4k.txt").write_text("thinking4k attack (24 combos)",encoding="utf-8")

        claims=extract_claims(paper)
        ev=index_result_values(root)
        matches=match_claims(claims,ev)

        # Formatting and model version ignored.
        assert any(c["raw"]=="11" and c["claim_type"]=="IGNORED" for c in claims)
        assert any(c["raw"]=="4.6" and c["claim_type"]=="IGNORED" for c in claims)
        # 95% CI ignored.
        assert any(c["raw"]=="95%" and c["claim_role"]=="CONFIDENCE_LEVEL" for c in claims)
        # enumeration ignored
        assert sum(c["claim_role"]=="ENUMERATION" for c in claims)>=3
        # FPR vs result rate roles separated
        assert any(c["raw"]=="1%" and c["claim_role"]=="OPERATING_POINT_FPR" for c in claims)
        rate=next(c for c in claims if c["raw"]=="34%")
        assert rate["claim_role"]=="RESULT_RATE"

        rm=next(m for m in matches if m["raw"]=="34%")
        # safety candidate must outrank fpr_grid despite identical number
        assert rm["candidates"][0]["evidence_role"]=="RESULT_RATE"

        four=next(m for m in matches if m["raw"]=="4" and "BashArena" in m["context"])
        # Must not "verify" from thinking4k coincidence
        assert four["status"]!="VERIFIED"

        print("v0.3 regression checks passed.")

if __name__=="__main__":
    run()
