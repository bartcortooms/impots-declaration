# Demo

Anonymised example with fabricated taxpayer data — for showing the tool to others.

## Files

- `input/Withdrawals Report.csv` — fake sales report (made-up sales)
- `build_demo.py` — script that builds the demo output (bypasses the PDF parser
  with hand-crafted parsed data, since faking a full broker statement.pdf
  isn't practical)
- `output/declaration.html` — generated declaration report

## To rebuild

```
uv run python demo/build_demo.py [year]
```

`year` is optional and defaults to the `DEFAULT_DEMO_YEAR` constant in
`build_demo.py`.

## Numbers used (all fictional)

- **4 fictional share sales** spread across the year
- **8 quarterly dividend payments** (4 quarters × 2 share classes)
- Total fictional gain: ~$90k USD / ~€83k EUR
- Fictional abattement (65%): ~€54k
- Sale dates, order numbers, prices, and cost bases are made up.
- The sample `input/Withdrawals Report.csv` is a static illustration of the
  CSV shape; the build script does not actually parse it (it constructs
  the parsed objects directly).
