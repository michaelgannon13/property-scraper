import re
import pandas as pd
from pathlib import Path
import logging

logger = logging.getLogger("derelict.pdf")

TARGET_COLUMNS = {
    "ds_ref", "reg_no", "address", "owner", "owner_address",
    "occupier", "electoral_area", "date_entered_register",
    "valuation", "valuation_date", "property_type",
}

_DS_REF_RE = re.compile(r'^(DS\d+)\s+(.+)$')


def _fix_shifted_headers(df: pd.DataFrame) -> pd.DataFrame:
    """Fix merged-cell PDFs where pdfplumber places header text one column right of the data."""
    cols = list(df.columns)
    named_idxs = [i for i, c in enumerate(cols) if c and str(c).strip()]
    if not named_idxs:
        return df
    all_empty = all(df.iloc[:, i].replace('', pd.NA).isna().all() for i in named_idxs)
    if not all_empty:
        return df
    all_left_has_data = all(
        i > 0 and not df.iloc[:, i - 1].replace('', pd.NA).isna().all()
        for i in named_idxs
    )
    if not all_left_has_data:
        return df
    new_cols = list(cols)
    for i in named_idxs:
        new_cols[i - 1] = cols[i]
        new_cols[i] = ''
    df = df.copy()
    df.columns = new_cols
    return df


def _find_header_row_idx(rows: list) -> int:
    """Return index of the first row where the majority of cells are non-None (skips title rows)."""
    for i, row in enumerate(rows[:10]):
        non_null = sum(v is not None for v in row)
        if non_null > len(row) / 2:
            return i
    return 0


def _extract_with_pdfplumber(filepath: Path) -> pd.DataFrame:
    import pdfplumber
    tables = []
    with pdfplumber.open(filepath) as pdf:
        for page in pdf.pages:
            tbl = page.extract_table()
            if tbl:
                tables.extend(tbl)
    if not tables:
        return pd.DataFrame()
    header_idx = _find_header_row_idx(tables)
    header = tables[header_idx]
    data = tables[header_idx + 1:]
    df = pd.DataFrame(data, columns=header)
    return _fix_shifted_headers(df)


def _extract_text_fallback(filepath: Path) -> pd.DataFrame:
    """Parse text-only PDFs where pdfplumber finds no table borders."""
    import pdfplumber
    rows = []
    with pdfplumber.open(filepath) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            for line in text.splitlines():
                line = line.strip()
                m = _DS_REF_RE.match(line)
                if m:
                    rows.append({"ds_ref": m.group(1), "address": m.group(2)})
    return pd.DataFrame(rows) if rows else pd.DataFrame()


def _extract_with_word_coords(filepath: Path) -> pd.DataFrame:
    """Word-coordinate fallback: infers column boundaries from header row words,
    then groups entries (lines starting with a DS reference) into columns."""
    import pdfplumber
    from collections import defaultdict

    all_words: list = []
    with pdfplumber.open(filepath) as pdf:
        for page in pdf.pages:
            all_words.extend(page.extract_words() or [])

    if not all_words:
        return pd.DataFrame()

    line_buckets: dict = {}
    for w in all_words:
        key = round(w["top"] / 3) * 3
        line_buckets.setdefault(key, []).append(w)
    sorted_lines = [sorted(ws, key=lambda w: w["x0"]) for _, ws in sorted(line_buckets.items())]

    _HDR_KWS = {"ref", "address", "owner", "date", "market", "value", "valuation"}
    best_hdr_idx, best_hdr_count = 0, 0
    for i, line in enumerate(sorted_lines[:15]):
        count = sum(1 for w in line if w["text"].lower().strip(".,") in _HDR_KWS)
        if count > best_hdr_count:
            best_hdr_count, best_hdr_idx = count, i
    if best_hdr_count < 2:
        return pd.DataFrame()

    _DS_RE = re.compile(r'^DS[/]?\d+', re.IGNORECASE)

    hdr_words: list = []
    for j in range(best_hdr_idx, min(best_hdr_idx + 6, len(sorted_lines))):
        if _DS_RE.match(" ".join(w["text"] for w in sorted_lines[j])):
            break
        hdr_words.extend(sorted_lines[j])

    hdr_words.sort(key=lambda w: w["x0"])
    col_clusters: list = []
    if hdr_words:
        current = [hdr_words[0]]
        for w in hdr_words[1:]:
            if w["x0"] - current[-1]["x1"] > 20:
                col_clusters.append(current)
                current = [w]
            else:
                current.append(w)
        col_clusters.append(current)

    if not col_clusters:
        return pd.DataFrame()

    col_info = []
    for cluster in col_clusters:
        x_min = min(w["x0"] for w in cluster)
        x_max = max(w["x1"] for w in cluster)
        label = " ".join(w["text"] for w in sorted(cluster, key=lambda w: (w["top"], w["x0"])))
        col_info.append((x_min, x_max, label))

    # Build split boundaries: midpoint between right edge of col[i] and left edge of col[i+1]
    boundaries = [
        (col_info[i][1] + col_info[i + 1][0]) / 2
        for i in range(len(col_info) - 1)
    ]

    def _nearest_col(x0: float) -> int:
        for i, b in enumerate(boundaries):
            if x0 < b:
                return i
        return len(col_info) - 1

    data_start = best_hdr_idx + 1
    for j in range(best_hdr_idx, min(best_hdr_idx + 8, len(sorted_lines))):
        if _DS_RE.match(" ".join(w["text"] for w in sorted_lines[j])):
            data_start = j
            break

    entries: list = []
    cur: dict = defaultdict(list)
    in_entry = False
    for line in sorted_lines[data_start:]:
        if _DS_RE.match(" ".join(w["text"] for w in line)):
            if in_entry and cur:
                entries.append(dict(cur))
            cur = defaultdict(list)
            in_entry = True
        if in_entry:
            for w in line:
                cur[_nearest_col(w["x0"])].append(w["text"])
    if in_entry and cur:
        entries.append(dict(cur))

    if not entries:
        return pd.DataFrame()

    col_labels = [label for _, _, label in col_info]
    rows = [{col_labels[i]: " ".join(words) for i, words in entry.items()} for entry in entries]
    return pd.DataFrame(rows)


def _extract_with_tabula(filepath: Path) -> pd.DataFrame:
    try:
        import tabula
        dfs = tabula.read_pdf(str(filepath), pages="all", multiple_tables=True, silent=True)
        if dfs:
            return pd.concat(dfs, ignore_index=True)
    except Exception as exc:
        logger.warning("tabula fallback failed: %s", exc)
    return pd.DataFrame()


def _apply_column_map(df: pd.DataFrame, column_map: dict) -> pd.DataFrame:
    df.columns = [re.sub(r'\s+', ' ', str(c)).strip() if c else "" for c in df.columns]
    df = df.rename(columns=column_map)
    keep = [c for c in df.columns if c in TARGET_COLUMNS]
    if not keep:
        return pd.DataFrame()
    result = df[keep].replace("", pd.NA).dropna(how="all").reset_index(drop=True)
    return result


def parse(filepath: Path, column_map: dict) -> pd.DataFrame:
    _extractors = [
        ("pdfplumber", _extract_with_pdfplumber),
        ("text", _extract_text_fallback),
        ("word-coords", _extract_with_word_coords),
        ("tabula", _extract_with_tabula),
    ]
    for label, extractor in _extractors:
        raw = extractor(filepath)
        if raw.empty:
            logger.info("%s found nothing, trying next extractor", label)
            continue
        result = _apply_column_map(raw, column_map)
        if not result.empty:
            return result
        logger.info("%s yielded no data rows after column mapping, trying next extractor", label)

    raise ValueError("Could not extract any usable data from PDF")
