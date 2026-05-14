# script/

The `impots` Python package.

See the top-level [README.md](../README.md) and
[docs/USER_GUIDE.md](../docs/USER_GUIDE.md) for an end-user walkthrough.

## Layout

```
src/impots/
├── cli.py                ← entry point: `build-declaration <year>`
├── statement.py          ← Morgan Stanley Account Summary PDF parser
├── withdrawals.py        ← Activity Report CSV parser
├── fx.py                 ← ECB daily USD→EUR rates (cached)
├── sales.py              ← per-sale gain / EUR conversion
├── abattement.py         ← 65% abattement grouping (form 2074-ABT)
├── dividends.py          ← form 2047 § 200 dividends
├── output.py             ← CSVs + audit.txt
└── web/                  ← Jinja templates + JS + CSS for declaration.html
```

## Run tests

```
uv run pytest                  # all
uv run pytest tests/regression # only the personal-data regression tests
```

Regression tests skip automatically when
`../personal-data/{year}/input/` files aren't present.

## Run the tool

```
uv run build-declaration 2025
```

See `cli.py --help` for `--data-dir` and other flags.
