# simPRO Imports Backend — Patched
This patch guarantees the output has the **same number of rows** as the input, even when headers don't map perfectly. It also adds tougher header normalization and a fuzzy fallback so real-world column names still map.
## Changes
- Output frame is initialized with `len(input)` rows — no more "headers-only" CSVs.
- Header normalization now strips BOM, punctuation, hyphens/underscores, and collapses whitespace.
- Fuzzy mapping: if alias/exact match fails, we try a contains-style match against template names.
- CSV reader tries multiple encodings including `utf-8-sig` to handle odd files.
- `pandas` bumped to `2.2.3` (Python 3.13 compatible).
## Deploy
Replace your repo files with these and redeploy on Render.
