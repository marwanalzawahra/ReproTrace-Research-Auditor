from pathlib import Path
import typer
from .scan import inventory
from .claims import extract_claims
from .results import index_result_values
from .match import match_claims
from .report import write_reports, build_summary

app=typer.Typer(help="ReproTrace: role-aware paper ↔ code ↔ results provenance auditor.")

@app.command()
def scan(
    project:Path=typer.Argument(...,exists=True,file_okay=False,dir_okay=True),
    manuscript:Path=typer.Option(...,"--manuscript","-m",exists=True,dir_okay=False),
    output:Path=typer.Option(Path("."),"--output","-o"),
):
    project=project.resolve()
    manuscript=manuscript.resolve()
    inv=inventory(project)
    claims=extract_claims(manuscript)
    evidence=index_result_values(project)
    matches=match_claims(claims,evidence)
    summary=build_summary(matches)
    jp,hp=write_reports(output.resolve(),inv,matches)
    typer.echo(f"Files indexed: {len(inv)}")
    typer.echo(f"Numeric tokens extracted: {len(claims)}")
    typer.echo(f"Considered claims: {summary['considered_claims']}")
    typer.echo(
        f"Verified: {summary['verified']} | Likely: {summary['likely']} | "
        f"Ambiguous: {summary['ambiguous']} | Unsupported: {summary['unsupported']} | "
        f"Ignored: {summary['ignored']}"
    )
    typer.echo(f"JSON report: {jp}")
    typer.echo(f"HTML report: {hp}")

if __name__=="__main__":
    app()
