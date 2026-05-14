# impots-declaration

Tool for preparing the **French annual tax declaration** when you hold
foreign-broker stock — turns your broker's annual statement + sales report
into the exact values to type into the online forms 2047, 2074, and
2074-ABT on impots.gouv.fr.

**Live demo** (anonymised fictional data):
<https://bartcortooms.github.io/impots-declaration/>

## What it does

Given a broker's annual statement (PDF) and a sales report (CSV) for a
given tax year, it produces:

- A single self-contained **`declaration.html`** that mirrors each page of
  the online declaration with the right values pre-filled, plus per-field
  copy-to-clipboard buttons.
- A set of CSV files for the form-2074 sections, form-2047 dividends,
  fiche 2074-ABT, and the cadre 11 bloc 1133 compensation table.
- An `audit.txt` cross-checking against the broker's withholding summary.

It handles the per-payment USD→EUR conversion (using the ECB / Banque de
France daily reference rates) and the durée-de-détention abattement
(0% / 50% / 65%) on long-held lots.

## Quick start

1. Place your inputs in `personal-data/<year>/input/`:
   ```
   personal-data/<year>/input/<sales-report>.csv
   personal-data/<year>/input/statement.pdf
   ```
2. From the `script/` directory, run the tool with the cutoff date for
   your acquisitions — i.e. a date you can confidently say is *after*
   your most recent share acquisition:
   ```bash
   uv run build-declaration <year> --all-acquired-before 2018-01-01
   ```
   The tool then computes the *abattement de durée de détention* (0% /
   50% / 65%) per sale, conservatively, from `sale_date − cutoff_date`.
   See [docs/USER_GUIDE.md](docs/USER_GUIDE.md#acquisition-dates) for the
   three modes and how to pick the cutoff.
3. Open the generated declaration in your browser:
   ```
   personal-data/<year>/output/declaration.html
   ```

See [docs/USER_GUIDE.md](docs/USER_GUIDE.md) for the full walkthrough,
including where to find the right exports from your broker and which
checkboxes to tick during the online declaration flow.

## Layout

```
impots-declaration/
├── README.md
├── docs/
│   └── USER_GUIDE.md          ← step-by-step guide
├── script/                    ← Python tool
│   ├── pyproject.toml
│   ├── src/impots/            ← parsers + computation + HTML renderer
│   └── tests/
├── demo/                      ← anonymised example you can share
│   ├── build_demo.py
│   ├── input/
│   └── output/declaration.html
├── forms/                     ← blank PDFs of the relevant tax forms
├── notices/                   ← the official notices for forms 2047 / 2074 / 2074-ABT
├── notes.md                   ← annotated notes on tax rules, rounding, gotchas
└── personal-data/             ← (gitignored) your year-by-year inputs and outputs
    └── <year>/
        ├── input/             ← put your CSV + PDF here
        └── output/            ← generated declaration.html + CSVs
```

## Requirements

- Python 3.12+
- [uv](https://github.com/astral-sh/uv) (or pip if you prefer)

Dependencies are pinned in `script/pyproject.toml` and locked in `uv.lock`.

## Scope

Built for:

- French tax residents
- with foreign-source dividends (US-source supported out of the box —
  17.6% taux applicable; other countries via per-country table in the
  notice)
- and foreign-broker share sales eligible for the
  *abattement de droit commun pour durée de détention*

Stock-acquisition era is configurable per run (see USER_GUIDE for the
`--all-acquired-before` flag). Currently the parsers read one broker
export format — see the USER_GUIDE for which one and how to extend.

## Status

Personal tool. **Verify every value** before submitting your declaration.
