# ReproTrace v0.3

v0.3 moves from value-aware matching to **role-aware scientific evidence matching**.

## Main changes

- Sentence/clause-local claim classification rather than oversized context windows.
- Numerical roles:
  - `RESULT_RATE`
  - `OPERATING_POINT_FPR`
  - `COUNT`
  - `STEP_CAP`
  - `THRESHOLD`
  - `SEED`
  - `CONFIDENCE_LEVEL`
  - `ENUMERATION`
  - `OTHER`
- Ignores:
  - LaTeX layout values
  - model versions
  - enumerations `(1)`, `(2)`, `(3)`
  - confidence levels such as `95% CI`
- Smart log extraction:
  - `n=50` → COUNT
  - `Sabotage:59.5%` → RESULT_RATE
  - `1% step-wise FPR` → OPERATING_POINT_FPR
- Thousand separators supported in evidence text.
- Evidence-role compatibility prevents:
  - `34% sabotage` from being verified by an `fpr_grid≈0.34`
  - `50% rate` from being verified by `n=50`
- `VERIFIED` now requires both:
  - compatible numerical role
  - semantic/metric anchor
- Candidate report shows claim role and evidence role.

## Install

```powershell
cd C:\path\to\ReproTrace_v0_3
pip install -e .
```

## LinuxArena test

```powershell
reprotrace "C:\Users\Marwan\Desktop\ReproTrace\LinuxArenaTest\linuxarena-paper-main" `
  --manuscript "C:\Users\Marwan\Desktop\ReproTrace\LinuxArenaTest\linuxarena-paper-main\src\paper\main.tex" `
  --output "C:\Users\Marwan\Desktop\ReproTrace\LinuxArenaTest\audit_v03"
```

## Goal of v0.3

Not to maximize VERIFIED count.

The goal is to reduce **false verification** and make the top evidence candidate scientifically plausible.

The next milestone after v0.3 is a manually labelled 50-claim benchmark.
