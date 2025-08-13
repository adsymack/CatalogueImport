import io
import os
import csv
import json
from datetime import datetime
from typing import Dict, List, Tuple

from flask import Flask, request, jsonify, send_file
import pandas as pd

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

try:
    from flask_cors import CORS  # optional
    _cors_available = True
except Exception:
    _cors_available = False

app = Flask(__name__)
if _cors_available:
    CORS(app)

# -------- Config --------
CONFIG_PATH = os.environ.get("CONFIG_PATH", "config.json")
if os.path.exists(CONFIG_PATH):
    with open(CONFIG_PATH, "r", encoding="utf-8") as cf:
        _cfg = json.load(cf)
else:
    _cfg = {}

TEMPLATE_COLUMNS: List[str] = _cfg.get("template_columns", [
    "Part Number","Description","Supplier","Supplier Part Number",
    "Cost ex Tax","Sell ex Tax","Tax Code","UOM",
    "Barcode","Manufacturer","Brand","Location","Minimum Stock","Maximum Stock","Notes"
])
ALIASES: Dict[str, str] = _cfg.get("aliases", {})
DEFAULTS: Dict[str, str] = _cfg.get("defaults", {"Tax Code": "G", "UOM": "ea"})
ALLOWED_TAX: List[str] = _cfg.get("allowed_tax_codes", ["G","F","E"])  # Enforce set

REQUIRED_NONEMPTY: List[str] = _cfg.get("required_nonempty", ["Part Number"])
REQUIRED_NUMERIC: List[str] = _cfg.get("required_numeric", ["Cost ex Tax","Sell ex Tax"])

# -------- Helpers --------
def normalize(s: str) -> str:
    return (s or "").strip().lower().replace("-", " ").replace("_", " ")

def read_dataframe_from_upload(file_storage) -> pd.DataFrame:
    filename = file_storage.filename or ""
    data = file_storage.read()
    if not data:
        raise ValueError("Uploaded file is empty.")
    if filename.lower().endswith((".xlsx", ".xls")):
        df = pd.read_excel(io.BytesIO(data), dtype=str)
    else:
        try:
            df = pd.read_csv(io.BytesIO(data), dtype=str, keep_default_na=False)
        except UnicodeDecodeError:
            df = pd.read_csv(io.BytesIO(data), dtype=str, keep_default_na=False, encoding="latin-1")
    for col in df.columns:
        df[col] = df[col].astype(str).map(lambda x: x.strip())
    return df

def auto_map_headers(cols: List[str]) -> Tuple[Dict[str, str], List[str]]:
    mapping: Dict[str, str] = {}
    used_targets = set()
    for c in cols:
        for t in TEMPLATE_COLUMNS:
            if normalize(c) == normalize(t):
                mapping[c] = t
                used_targets.add(t)
                break
    for c in cols:
        if c in mapping:
            continue
        tgt = ALIASES.get(normalize(c))
        if tgt and tgt not in used_targets:
            mapping[c] = tgt
            used_targets.add(tgt)
    missing_targets = [t for t in TEMPLATE_COLUMNS if t not in used_targets]
    return mapping, missing_targets

def clean_currency_str(s: str) -> str:
    return (s or "").replace(",", "").strip()

def to_numeric_or_none(s: str):
    s2 = clean_currency_str(s)
    s2 = "".join(ch for ch in s2 if (ch.isdigit() or ch in ".-"))
    if s2 in ("", ".", "-", "-.", ".-"):
        return None
    try:
        return float(s2)
    except Exception:
        return None

def build_template_frame(df: pd.DataFrame) -> pd.DataFrame:
    mapping, missing = auto_map_headers(list(df.columns))
    out = pd.DataFrame(columns=TEMPLATE_COLUMNS)
    for src, tgt in mapping.items():
        out[tgt] = df[src]
    for col, val in DEFAULTS.items():
        if col in out.columns:
            out[col] = out.get(col, pd.Series([""] * len(df)))
            out[col] = out[col].mask(out[col].eq(""), val).fillna(val)
    for col in TEMPLATE_COLUMNS:
        if col not in out.columns:
            out[col] = DEFAULTS.get(col, "")
    # scrub currency-like strings
    for col in ["Cost ex Tax","Sell ex Tax"]:
        if col in out.columns:
            out[col] = out[col].astype(str).map(clean_currency_str)
    # reorder
    out = out[TEMPLATE_COLUMNS]
    return out

def validate_frame(out: pd.DataFrame) -> List[Dict]:
    errors: List[Dict] = []
    n = len(out)
    for i in range(n):
        rownum = i + 2  # 1-based with header (CSV-style)
        # Required non-empty
        for col in REQUIRED_NONEMPTY:
            if col in out.columns:
                if str(out.at[i, col]).strip() == "":
                    errors.append({"row": rownum, "field": col, "error": "Required"})
        # Required numeric
        for col in REQUIRED_NUMERIC:
            if col in out.columns:
                val = to_numeric_or_none(str(out.at[i, col]))
                if val is None:
                    errors.append({"row": rownum, "field": col, "error": "Must be numeric ex tax"})
        # Tax Code
        if "Tax Code" in out.columns:
            tc = str(out.at[i, "Tax Code"]).strip().upper()
            if tc not in ALLOWED_TAX:
                errors.append({"row": rownum, "field": "Tax Code", "error": f"Must be one of {ALLOWED_TAX}"})
    return errors

def errors_to_csv_bytes(errs: List[Dict]) -> io.BytesIO:
    import csv
    sio = io.StringIO()
    w = csv.DictWriter(sio, fieldnames=["row","field","error"])
    w.writeheader()
    for e in errs:
        w.writerow(e)
    return io.BytesIO(sio.getvalue().encode("utf-8-sig"))

# -------- Routes --------
@app.route("/", methods=["GET"])
def health():
    return jsonify({
        "ok": True,
        "service": "simPRO Imports Backend",
        "version": "2.0.0",
        "time": datetime.utcnow().isoformat() + "Z",
        "template_columns": TEMPLATE_COLUMNS,
        "allowed_tax": ALLOWED_TAX,
        "required_nonempty": REQUIRED_NONEMPTY,
        "required_numeric": REQUIRED_NUMERIC
    })

@app.route("/process", methods=["POST"])
def process():
    if "file" not in request.files:
        return jsonify({"ok": False, "error": "No file uploaded. Use form field 'file'."}), 400
    try:
        df = read_dataframe_from_upload(request.files["file"])
        out = build_template_frame(df)
        errs = validate_frame(out)

        base = os.path.splitext(request.files["file"].filename or "input")[0]

        if errs:
            csv_err = errors_to_csv_bytes(errs)
            return send_file(
                csv_err,
                mimetype="text/csv",
                as_attachment=True,
                download_name=f"{base}_errors.csv",
            )

        csv_buf = io.StringIO()
        out.to_csv(csv_buf, index=False)
        csv_bytes = io.BytesIO(csv_buf.getvalue().encode("utf-8-sig"))
        return send_file(
            csv_bytes,
            mimetype="text/csv",
            as_attachment=True,
            download_name=f"{base}_simpro_template.csv",
        )
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "8000")), debug=True)
