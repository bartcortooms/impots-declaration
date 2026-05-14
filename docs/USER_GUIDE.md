# User guide

Step-by-step walkthrough for using this tool to prepare your French tax
declaration of foreign-broker stock holdings (sales + dividends).

> **Scope.** Built for French tax residents declaring foreign-source
> dividends and foreign-broker share sales. Out of the box it handles
> US-source dividends (17.6% taux applicable) and applies the
> *abattement de droit commun pour durée de détention* (0% / 50% / 65%)
> to the plus-values. Stock acquisition era is configurable per run
> (see [Acquisition dates](#acquisition-dates) below). Currently parses
> one broker's export format — see step 1 below.

---

## 1. Download the two inputs from your broker

You need two files for the tax year you're declaring:

| File | What it contains |
|---|---|
| `statement.pdf` | Annual account statement: sales with cost basis, dividend payments with foreign withholding, year-end lot table. |
| `<sales-report>.csv` | Per-sale line items: execution date, order number, quantity, price, plan/share class. |

The current parser is written for **Morgan Stanley StockPlan Connect** —
specifically, the **Account Summary** report (PDF, "Full" type, both
*Share & Cash Holdings* and *Equity Awards* products checked,
*Last Calendar Year* period) and the **Activity Report** (CSV, *Previous
fiscal year* period).

If you use a different broker, the math doesn't change — but the parsers
in `script/src/impots/statement.py` and
`script/src/impots/withdrawals.py` would need to be adapted to your
broker's export shape.

---

## 2. Put the files in the right place

Create the directory and copy your two inputs in:

```
personal-data/<year>/input/
├── statement.pdf            ← annual statement (this exact filename)
└── *.csv                    ← per-sale CSV (any filename — auto-discovered)
```

Replace `<year>` with the tax year you're declaring (e.g., `2025` for the
declaration you file in spring 2026).

> You can use any directory — pass `--data-dir /some/other/path` to the
> tool. `personal-data/` is just the default and is gitignored.
>
> The CSV name doesn't matter (the tool picks up whatever *.csv lives in
> `input/`). If you have more than one CSV in that directory you'll need
> to pass `--sales-csv path/to/file.csv` explicitly.

---

## 3. Run the tool

From the `script/` directory, run the tool with
`--all-acquired-before YYYY-MM-DD` set to a date you can confidently say
is *after* your most recent share acquisition (e.g. `2018-01-01` if you
stopped acquiring shares before 2018):

```bash
uv run build-declaration <year> --all-acquired-before 2018-01-01
```

This computes the *abattement de durée de détention* per sale from
`sale_date − cutoff_date`. See [Acquisition dates](#acquisition-dates)
below for the three modes (default, cutoff flag, per-lot CSV) and how
to pick the right cutoff.

Concrete example for tax year 2025:

```bash
uv run build-declaration 2025 --all-acquired-before 2017-01-01
```

This produces:

```
personal-data/<year>/output/
├── declaration.html             ← open in a browser
├── audit.txt                    ← cross-check vs broker withholding summary
├── form_2047.csv
├── form_2074.csv
├── fiche_2074_abt.csv
└── bloc_1133.csv
```

Open `declaration.html` in your browser (works over `file://` — no server
needed). It walks you page by page through the online declaration with
the correct values pre-filled and a copy button next to each field.

> Omitting `--all-acquired-before` falls back to assuming everything
> qualifies for 65% — only safe if you've verified every sold share came
> from a lot vested ≥ 8 years before the sale date. The tool will print
> a warning when you run without the flag.

---

## Acquisition dates

The *abattement de durée de détention* (form 2074-ABT) depends on how
long each lot was held before sale. The rates are:

| Holding period | Rate |
|---|---|
| < 2 years | 0% |
| 2 to < 8 years | 50% |
| ≥ 8 years | 65% |

Only lots acquired **before 2018-01-01** are eligible. Post-2018 lots
get no abattement at all.

The tool offers three modes:

**(a) Default — assumes everything qualifies for 65%.**
This is the zero-config path. Use only if all the shares you sold this
year came from lots vested ≥ 8 years before the sale date *and* before
2018-01-01. The tool does not verify this — you do, by checking the
lot table in `statement.pdf`.

**(b) `--all-acquired-before YYYY-MM-DD` — conservative bracket logic.**
Declare a single cutoff date: the latest possible acquisition date in
your portfolio. The tool then computes per-sale rate as
`sale_date − cutoff_date` and assigns 0% / 50% / 65% accordingly.
Safe (you'll never over-claim) but may under-claim vs. true FIFO if
your sales actually drew from older lots than the cutoff suggests.

**(c) Per-lot CSV (not yet implemented)** — for portfolios mixing
pre-/post-2018 lots, or sales straddling a rate bracket. Will need a
manual `acquisitions.csv` listing each block.

---

## 4. Cross-check against the broker's withholding summary

US brokers issue a yearly **1042-S** (gross foreign-source dividend +
withholding totals). Compare against:

- `audit.txt` — reports both totals.
- The dividend section of `declaration.html`.

If they don't agree to the cent, something is off — investigate before
submitting.

---

## 5. File on impots.gouv.fr

`declaration.html` mirrors each impots.gouv.fr page in order:

1. **Rubriques** — page where you tick categories on the main
   declaration. Most are auto-checked from your previous-year carry-over;
   the only manual tick needed is *Plus-values et gains divers* (for the
   stock sales).
2. **Annexes** — tick the three annexes: **N° 2047**, **N° 2074**, and
   **N° 2074 ABT**.
3. **Form 2047** (foreign income) — section 200 dividends, country
   États-Unis, taux 17.6% (for US-source).
4. **Form 2074** (plus-values) — cadre 5 § 510 for each sale (one form
   slot per sale, continuation pages for sale #4 and beyond).
5. **Form 2074 ABT** (abattement) — one *cas* per sale, computing the
   per-bracket allowance.
6. **Form 2042** (main) — synthesizes everything; should auto-populate.
   Cadre 11 *bloc 1133* on form 2042 C may need manual entry.

Each page in the report shows what to copy, with thousand-separator-aware
copy buttons that strip the spaces (impots.gouv.fr fields don't accept
them).

---

## 6. Year-over-year

For next year's declaration, repeat steps 1–3 with `<year>+1`:

```bash
personal-data/<next-year>/input/{statement.pdf,<sales-report>.csv}
uv run build-declaration <next-year>
```

The tool fetches and caches **ECB / Banque de France** USD→EUR daily
rates automatically. No code changes are needed across years (assuming
your broker's export formats don't change).

---

## Troubleshooting

**"No records found" / empty PDF.** Some brokers offer multiple report
types under similar names. For Morgan Stanley specifically, make sure
you pick **Account Summary** rather than a vesting-only report (the
right one is described as "a printable summary of your activity for a
time period of your choosing"; the wrong-looking one is described as
"a detailed income and tax breakdown of vesting activity").

**Empty CSV.** Same root cause for many brokers — pick the report that
covers historical activity, not the one that covers only current
vesting.

**Tool errors on missing FX rate.** ECB doesn't publish on weekends or
French bank holidays. The tool walks back to the previous publication
date automatically; if it still fails, check
[ECB Statistical Data Warehouse](https://sdw-wsrest.ecb.europa.eu) is
reachable.

**Numbers don't match my own calculation.** Open `audit.txt` — it shows
the per-sale gain in USD and EUR, the FX rate used, and the abattement
applied. Verify against the statement line by line.

---

## What this tool does *not* do

- It does not file the declaration for you. You still have to type the
  values into impots.gouv.fr (the copy buttons help).
- It does not handle stock options (only RSUs / unit-style awards).
- It does not yet handle mixed pre-2018 / post-2018 portfolios at a
  per-lot level — see [Acquisition dates](#acquisition-dates).
- It supports one broker's export format out of the box; other brokers
  would need a parser added.
- It does not constitute tax advice. **Verify every value before
  submitting.**
