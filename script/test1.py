from __future__ import annotations

import json
import sys
from pathlib import Path
from zipfile import ZipFile
import posixpath
import xml.etree.ElementTree as ET

from openpyxl import load_workbook


ROOT = Path(__file__).resolve().parents[1]
XLSX_PATH = ROOT / "test_file" / "demo1.xlsx"
OUTPUT_DIR = ROOT / "test_file" / "json_data"
OUTPUT_PATH = OUTPUT_DIR / "demo1.json"

NS_MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
NS_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
NS_XDR = "http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing"
NS_A = "http://schemas.openxmlformats.org/drawingml/2006/main"
DRAWING_REL_TYPE = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/drawing"


def column_letter(column_number: int) -> str:
    """Convert a 1-based Excel column number to A, B, ..., AA, AB, ..."""
    result = ""
    while column_number:
        column_number, remainder = divmod(column_number - 1, 26)
        result = chr(65 + remainder) + result
    return result


def normalize_text(value) -> str:
    if value is None:
        return ""
    return str(value).strip()


def resolve_target(source_path: str, target: str) -> str:
    """Resolve an OOXML relationship target to a normalized package path."""
    if target.startswith("/"):
        return target.lstrip("/")
    return posixpath.normpath(posixpath.join(posixpath.dirname(source_path), target)).lstrip("./")


def get_sheet_drawing_paths(xlsx_path: Path) -> dict[str, str]:
    """Map worksheet XML paths to their DrawingML XML paths."""
    result: dict[str, str] = {}

    with ZipFile(xlsx_path) as zf:
        names = set(zf.namelist())
        workbook = ET.fromstring(zf.read("xl/workbook.xml"))
        workbook_rels = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
        rel_map = {rel.attrib["Id"]: rel.attrib["Target"] for rel in workbook_rels}

        sheets = workbook.find(f"{{{NS_MAIN}}}sheets")
        if sheets is None:
            return result

        for sheet in sheets:
            rid = sheet.attrib.get(f"{{{NS_REL}}}id")
            target = rel_map.get(rid)
            if not target:
                continue

            sheet_path = resolve_target("xl/workbook.xml", target)
            if sheet_path not in names:
                continue

            rels_path = posixpath.join(
                posixpath.dirname(sheet_path),
                "_rels",
                posixpath.basename(sheet_path) + ".rels",
            )
            if rels_path not in names:
                continue

            sheet_rels = ET.fromstring(zf.read(rels_path))
            for rel in sheet_rels:
                if rel.attrib.get("Type") != DRAWING_REL_TYPE:
                    continue
                drawing_target = rel.attrib.get("Target")
                if not drawing_target:
                    continue
                drawing_path = resolve_target(sheet_path, drawing_target)
                if drawing_path in names:
                    result[sheet_path] = drawing_path
                break

    return result


def get_drawing_texts(xlsx_path: Path) -> dict[str, list[tuple[int, int, str]]]:
    """Read Shape/TextBox text and its starting cell without OCR.

    Only xdr:sp (DrawingML shapes/text boxes) are processed. xdr:pic image
    objects are ignored, so text is not extracted from images.
    """
    result: dict[str, list[tuple[int, int, str]]] = {}
    sheet_drawing_paths = get_sheet_drawing_paths(xlsx_path)

    with ZipFile(xlsx_path) as zf:
        for sheet_path, drawing_path in sheet_drawing_paths.items():
            try:
                root = ET.fromstring(zf.read(drawing_path))
            except (KeyError, ET.ParseError):
                continue

            entries = result.setdefault(sheet_path, [])

            for anchor in root:
                # Only process actual DrawingML shapes/text boxes.
                shape = anchor.find(f"{{{NS_XDR}}}sp")
                if shape is None:
                    continue

                from_node = anchor.find(f"{{{NS_XDR}}}from")
                if from_node is None:
                    continue

                row_node = from_node.find(f"{{{NS_XDR}}}row")
                col_node = from_node.find(f"{{{NS_XDR}}}col")
                if row_node is None or col_node is None:
                    continue

                try:
                    line = int(row_node.text or 0) + 1
                    column = int(col_node.text or 0) + 1
                except ValueError:
                    continue

                tx_body = shape.find(f"{{{NS_XDR}}}txBody")
                if tx_body is None:
                    continue

                texts = [
                    node.text
                    for node in tx_body.iter(f"{{{NS_A}}}t")
                    if node.text
                ]
                text = normalize_text("".join(texts))
                if text:
                    entries.append((line, column, text))

            if not entries:
                result.pop(sheet_path, None)

    return result


def extract_workbook() -> list[dict]:
    if not XLSX_PATH.exists():
        raise FileNotFoundError(f"Excel file not found: {XLSX_PATH}")

    workbook = load_workbook(XLSX_PATH, data_only=True, read_only=False)
    drawing_texts = get_drawing_texts(XLSX_PATH)
    sheet_drawing_paths = get_sheet_drawing_paths(XLSX_PATH)

    sheets = []
    for ws in workbook.worksheets:
        context = []

        # Normal worksheet cell text.
        for row in ws.iter_rows():
            for cell in row:
                text = normalize_text(cell.value)
                if text:
                    context.append({
                        "cell": f"{column_letter(cell.column)}{cell.row}",
                        "text": text,
                    })

        # Shape/TextBox text. Use the shape's top-left/start cell.
        sheet_xml = next(
            (path for path, drawing_path in sheet_drawing_paths.items()
             if drawing_path and path.endswith(f"/worksheets/sheet{ws._id}.xml")),
            None,
        )
        if sheet_xml is None:
            # Fallback: match the worksheet by XML relationship order.
            sheet_xml = f"xl/worksheets/sheet{ws._id}.xml"

        for line, column, text in drawing_texts.get(sheet_xml, []):
            context.append({
                "cell": f"{column_letter(column)}{line}",
                "text": text,
            })

        context.sort(key=lambda item: (int(''.join(c for c in item["cell"] if c.isdigit())),
                                       ''.join(c for c in item["cell"] if c.isalpha())))
        sheets.append({
            "name": ws.title,
            "context": context,
        })

    return sheets


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    data = {"sheet": extract_workbook()}
    OUTPUT_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Generated: {OUTPUT_PATH}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise
