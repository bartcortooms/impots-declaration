# Tax declaration notes

Reference notes on how to fill in the French tax declaration based on
foreign-broker stock-sale and dividend exports. These document the *rules*
the code applies; the code is the source of truth for *how* it applies them.

The current parsers are written for Morgan Stanley StockPlan Connect
exports — see `docs/USER_GUIDE.md` for the report-picking steps.

## Mandatory gotchas (don't forget)

These are easy to miss and have real consequences:

1. **Tick case 2OP on form 2042.** Required for BOTH the 40 % dividend
   abattement (case 2DC) AND the durée-de-détention abattement on plus-values
   (case 3SG). Without 2OP everything is taxed at the PFU 12,8 % flat rate
   with no abattement at all. See notice 2042 page 14 and notice 2074-ABT
   page 1.
2. **Declare foreign accounts via 3916 / 3916 bis.** If your broker is
   foreign (Morgan Stanley etc.), the brokerage account is a "compte
   ouvert à l'étranger". Tick case **8UU** on form 2042 (section DIVERS).
   Since 2024 the 3916 / 3916 bis is no longer in the annexes list — it's
   integrated as a sub-flow that opens once you tick 8UU (per the NOUVEAU
   note on the impots.gouv.fr annexes page). Sanction: **1 500 € per
   undeclared account** (10 000 € for non-cooperative jurisdictions),
   art. 1736 IV CGI.
3. **Moins-values aging.** Carry-forward losses are usable only for the
   **10 years following** the loss year (notice 2042 p. 15). Losses from
   before `year - 10` are forfeit. If using `--prior-losses-eur`, exclude
   the expired bucket.
4. **3VH vs 3WN-3WT.** Case **3VH** holds the residual moins-value
   *de l'année* only. Prior-year carry-forwards keep their year-of-origin
   case **3WN** (2013) … **3WT** (2024). Don't dump prior-year losses into
   3VH or they collapse into one bucket and the 10-year aging gets lost.

## Dividends → Form 2047, section 200

Path in the online declaration:

`Déclaration annexe N° 2047 (Déclaration des revenus encaissés à l'étranger)`
→ `2. Des revenus des valeurs et capitaux mobiliers imposables en France`
→ `200 DIVIDENDES ET JETONS DE PRÉSENCE`

Notice section: `notice2047.pdf` page 4, "200 Dividendes" (the form combines
the section 200 dividend rules with the §260 "jetons de présence" wording in
a single header).

Each column = one country of origin. **Not one column per payment** — if all
dividends are US-source, they should be summed into a single column with
country = États-Unis. Confirmed by form layout (`forms/form2047.pdf` page 2):
line 202 "Pays d'encaissement ou d'origine des revenus" is the column header,
and lines 203–207 are repeated per country.

The current form has 4 country slots on lines 203–207 (count the
`+ + + =` separators between input boxes). Older versions had 3 — re-count
against the current form before each filing.

### Field-by-field

Field labels below are verbatim from `forms/form2047.pdf` page 2.

| Field | Label | Content | Unit |
|---|---|---|---|
| 201 | (header) | "Revenus ouvrant droit à un crédit d'impôt égal à l'impôt payé à l'étranger" | — |
| 202 | Pays d'encaissement ou d'origine des revenus | Country dropdown (e.g. États-Unis) | — |
| 203 | Montant net encaissé | Sum of net dividends received from that country, in EUR | **EUR** |
| 204 | Taux applicable (%) | Treaty rate from the notice; for US dividends 17,6% | % |
| 205 | Résultat | `= 203 × 204%` (computed by the form) | EUR |
| 206 | Impôt supporté à l'étranger | Sum of foreign withholding tax actually borne, in EUR | **EUR** |
| 207 | Crédit d'impôt retenu | `= min(205, 206)` — the lower of result and tax-borne | EUR |
| 208 | Revenus crédit d'impôt inclus | `= 203 + 207` (across all columns) — this is what feeds the main declaration | EUR |

The `min(205, 206)` rule for field 207 is spelled out on the form itself:
*"Impôt étranger retenu de la ligne 207 : si ligne 205 < ligne 206, retenir
la ligne 205 ; si ligne 206 < ligne 205, retenir la ligne 206."*

### Conversion to EUR

For each USD dividend payment:
- Net amount (EUR) = USD net × USD→EUR rate on payment date
- Withholding (EUR) = USD withholding × USD→EUR rate on payment date

USD→EUR rate source: **Banque de France** daily reference rate (republished
from the ECB), which is what the tax authority expects. The notice only
mandates *"contre-valeur en euros, calculée d'après le cours du change à
Paris au jour de l'encaissement"* (`notice2047.pdf` page 1, left column).
The script fetches and caches the ECB daily rates automatically.

### Gross vs net (important)

The broker statement's "Dividend (Cash)" line is the **gross** dividend (the full
amount declared by the issuer), and "IRS Nonresident Alien Withholding" is
15% of that gross. Field 203 ("Montant net encaissé") requires
`net × FX = (gross − withholding) × FX`, **not** gross × FX. Field 206
requires the withholding **converted to EUR**, not raw USD.

Getting either wrong inflates Field 203 (which feeds form 2042 → French
income tax) or Field 207 (foreign tax credit) — both wrong-direction errors
for the taxpayer.

### Rounding

The fiche 2074-ABT N08 totals are rounded **half-up to the nearest integer**
(not floored). The script follows the same convention for F516 / F521 /
F524 / bloc 1133. F514 / F520 keep 2 decimals (unit prices).

Open question for the online portal proper (form 2074 main / 2042-C cases):
whether input fields accept decimals or only integers. Worth verifying by
entering a decimal into a form field during filing.

### Field 204 (Taux applicable) — 17.6% for US

Per-country rate table — `notice2047.pdf` page 5:
> ÉTATS-UNIS div. 17,6%, int. 17,6%

The reason it isn't the treaty rate of 15% — `notice2047.pdf` page 1, right
column (NOTA):
> "les taux indiqués pour chaque pays dans cette notice sont déterminés par
> rapport au revenu net perçu (après déduction de l'impôt étranger) alors
> que les taux prévus dans la convention sont les taux applicables au
> revenu brut."

(Page 5 has a paraphrase at the top of the rate table.)

Math: treaty cap = 15% of gross. Since Field 203 holds *net* (gross − foreign
tax), `15 / 85 ≈ 17.647%` is the equivalent rate applied to net. Same cap,
different denominator.

US-specific paragraph on `notice2047.pdf` page 5 (under ÉTATS-UNIS) confirms
the 15% gross cap:
> "Dividendes : les dividendes de source américaine perçus par un résident
> de France ouvrent droit à un crédit d'impôt égal à l'impôt américain, dans
> la limite de 15% du montant brut des dividendes."

Field 204 = 17.6 stays hardcoded for US-source dividends. Re-verify each
year against the current notice.

## Withdrawals Report: "Cash" rows explained

The `Cash` rows in the Withdrawals Report (Plan=Cash, $1.00 price, reference
numbers starting `WBC...`) are **not separate taxable events**. They're cash
transfers from the brokerage to the user's personal bank account, where the
cash consists of *dividend payments* that had previously been credited to
the brokerage cash account.

The pattern in the Account Summary is: dividends paid into the brokerage
cash balance over several months, then later wired out in a single `WBC...`
transaction. The dividends themselves are already declared via form 2047 on
the payment dates — the wire-out is just a transfer.

**Automation rule**: filter Withdrawals to `Plan != "Cash"` (equivalently:
keep only `WRC...` references) when extracting share sales.

## Stock sales → Form 2074 + abattement annex (line 1133)

### Per-sale form fields (Form 2074)

Each stock sale produces values for fields 511, 512, 514, 515, 516, 520, 521,
524 — entered as one line per sale in cadre 5 § 510 of form 2074
(`forms/form2074.pdf` page 2).

Field semantics, from `notices/notice2074.pdf` § 510 (pages 9–11):
- **511** "Nommez les titres" + intermédiaires financiers
- **512** "Date de la cession ou du rachat" — for cotés, date de
  règlement-livraison
- **514** "Valeur unitaire de cession" — for cotés, "le cours auquel la
  transaction boursière a été conclue"
- **515** "Nombre de titres cédés"
- **516** = 514 × 515 ("Montant global", computed)
- **517** "Frais de cession" (typically 0 for stock sales) — deducted from 516
  to give 518
- **518** = 516 − 517 ("Prix de cession net")
- **520** "Prix ou valeur d'acquisition unitaire" — for *fungible* titres,
  the **PMP (prix moyen pondéré) is obligatoire**; for *identifiable* titres
  (lot-tagged stocks with known vest date/FMV per lot), use the actual per-lot
  cost. RSU-style awards typically come with per-lot vest date / FMV data,
  so per-lot cost is the right approach.
- **521** "Prix d'acquisition global" — somme des prix unitaires
  d'acquisition
- **522** "Frais d'acquisition" (typically 0 for stock vests)
- **523** = 521 + 522 ("Prix de revient")
- **524** = 518 − 523 ("Résultat") — flows to ligne 903 of cadre 9, then to
  bloc 1133 of cadre 11.

### Abattement for long-term holdings (Form 2074-ABT fiche + Form 2074 cadre 11 bloc 1133)

Two distinct artifacts:

- **Fiche 2074-ABT** (helper, `forms/form2074-abt.pdf`): each page has 2
  slots (Titre A and Titre B); use as many pages as needed. One slot = one
  sale is fine. The N08 output (montant total de l'abattement) flows into…
- **Form 2074 cadre 11 bloc 1133** (`forms/form2074.pdf` page 8): the
  actual compensation table. Has **only 3 slots ("Titres A / B / C") per
  abattement category** (droit commun col F, renforcé col G). This is where
  the 3-slot constraint bites.

"Titres A/B/C" are arbitrary groupings chosen by the filer, not predefined
categories. A single slot can mix share classes / acquisition dates.

### Eligibility and computation rules (from notice 2074-ABT)

All page references below are to `notice2074ABT.pdf`.

1. **Pre-2018 cutoff.** Abattement applies only to titres acquired/souscrits
   before 2018-01-01. Post-2018 vests are excluded — different form section,
   no abattement. (Page 1, "Régime des abattements pour durée de détention",
   opening paragraph.)
2. **Barème progressif required.** Abattement only applies if case 2OP is
   ticked on form 2042 (opt into the income-tax brackets instead of PFU/flat
   tax 30%). The output of this script assumes 2OP is ticked. (Page 1, same
   opening paragraph: "à condition que l'option globale pour le barème
   progressif soit exercée lors du dépôt de la déclaration n° 2042".)
3. **Rates by holding period:**
   - < 2 years: 0%
   - 2 to < 8 years: 50%
   - ≥ 8 years: 65%
   - "Renforcé" rates (50/65/85%) only apply for PME-specific conditions —
     not relevant here.

   (Droit commun rates: page 1, "Montant de l'abattement de droit commun et
   calcul de la durée de détention". Renforcé rates: page 2, "Montant de
   l'abattement 'renforcé' et calcul de la durée de détention".)
4. **Date calculation: "de date à date"** from acquisition/vest to sale.
   (Page 1, droit commun durée de détention paragraph.)
5. **FIFO for fungible titres.** When stocks vested on different dates are
   partially sold, the oldest lots are treated as sold first. (Page 2, field
   N04/R04: "il convient de considérer que les titres que vous avez cédés
   ou rachetés sont ceux qui avaient les dates d'acquisition les plus
   anciennes dans votre portefeuille".)
6. **Multi-lot sales straddling thresholds must be split.** If a sale's lots
   span an abattement bracket boundary (2-year or 8-year mark), the
   plus-value must be repartitioned across buckets and abattement computed
   separately per bucket. Notice example (page 2, N04/R04): 100 titres
   acquis en (N) + 60 titres parmi les 150 acquis en (N+3) treated as two
   sub-lots when 160 of the 330 are sold in (N+10).
7. **Moins-values imputed first.** Abattement applies to the net plus-value
   after offsetting losses (current year and carried-forward). (Page 1,
   "Modalités de calcul des abattements pour durée de détention" — "Les
   abattements pour durée de détention ne s'appliquent qu'aux plus-values
   réalisées, après imputation des moins-values (de l'année et antérieures).")

### Single-rate simplification (when applicable)

If every share lot in your portfolio is already older than the 8-year mark
(date-to-date from vest to *expected sale date*), then every sale draws
from lots qualifying for the 65% rate, regardless of which specific lots
FIFO assigns. In that case lot-by-lot matching is unnecessary: the script
can apply 65% across the board.

This is the regime the current code assumes. To check whether it still
holds for your portfolio: take the most recent vest date in your year-end
holdings, add 8 years; if every sale you plan to make happens after that
date, you're in the single-rate regime. Otherwise the code would need to
split sales across the 0% / 50% / 65% buckets.

**Defensive check** the script could perform: if a sale's average cost per
share exceeds the latest-known lot's FMV, the sale may have drawn from an
unexpected newer lot — flag for manual review.

### Grouping rule for automation

The 3-slot constraint is on bloc 1133 of Form 2074, **not** on the fiche
2074-ABT. When more than 3 sales need to be bucketed into the 3 bloc-1133
slots: **first-N-individual, rest-grouped**. The first 2 sales (by date)
each get their own slot (Titres A, Titres B); all remaining sales are
summed into slot Titres C. If there are ≤ 3 sales, each gets its own slot
and Titres C may be empty.

(The fiche 2074-ABT can hold one slot per sale — no grouping needed there.
The Titres A/B/C layout is the bloc-1133 view.)
