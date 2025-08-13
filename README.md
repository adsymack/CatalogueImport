
# simPRO Imports Backend — Validated

This version adds validation and clear error reporting.

## Validations
- **Required (non-empty):** Part Number
- **Required numeric (ex tax):** Cost ex Tax, Sell ex Tax
- **Tax Code:** must be one of `G`, `F`, `E` (configurable)

If any errors exist, the API returns a downloadable **`*_errors.csv`** with columns: `row, field, error`.  
If there are no errors, you get the normal `*_simpro_template.csv`.

## Deploy (Render)
- Build: `pip install -r requirements.txt`
- Start: `gunicorn -w 1 -b 0.0.0.0:$PORT app:app`

## Squarespace Integration
Same upload form. In JS, if the filename ends with `_errors.csv`, you can message the user to fix and re-upload.

Example tweak:
```js
const disp = res.headers.get('Content-Disposition') || '';
if (disp.includes('_errors.csv')) {
  alert('There are issues in your file. An error report will download now.');
}
```

## Config
All rules live in `config.json`:
- `template_columns`, `defaults`, `aliases`
- `allowed_tax_codes`
- `required_nonempty`, `required_numeric`
