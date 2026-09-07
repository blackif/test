from __future__ import annotations

import json
import sys
from pathlib import Path
from zipfile import ZipFile
import xml.etree.ElementTree as ET

from openpyxl import load_workbook


ROOT = Path(__file__).resolve().parents[1]
XLSX_PATH = ROOT / "test_file" / "demo1.xlsx"
OUTPUT_DIR = ROOT / "test_file" / "json_data"
OUTPUT_PATH = OUTPUT_DIR / "demo1.json"

NS = {"main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
DRAWING_REL_TYPE = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/drawing"
V_DRAWING_REL_TYPE = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/vmlDrawing"


def col_to_number(cell_ref: str) -> int:
    letters = "".join(c for c in cell_ref if c.isalpha())
    value = 0
    for char in letters.upper():
        value = value * 26 + ord(char) - ord("A") + 1
    return value


def normalize_text(value) -> str:
    if value is None:
        return ""
    return str(value).strip()


def get_drawing_texts(xlsx_path: Path) -> dict[str, list[tuple[int, str]]]:
    """Read text from DrawingML text boxes/shapes without OCR.

    Returns a mapping of worksheet XML path to (column, text) entries.
    The column is taken from the shape's two-cell anchor or one-cell anchor
    position, allowing the shape text to be associated with a worksheet line.
    """
    result: dict[str, list[tuple[int, str]]] = {}

    with ZipFile(xlsx_path) as zf:
        names = set(zf.namelist())
        workbook = ET.fromstring(zf.read("xl/workbook.xml"))
        rels = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))

        workbook_rels = {}
        for rel in rels:
            workbook_rels[rel.attrib["Id"]] = rel.attrib["Target"]

        for sheet in workbook.find("main:sheets", NS):
            sheet_name = sheet.attrib.get("name", "")
            rid = sheet.attrib.get(f"{{{REL_NS}}}id")
            target = workbook_rels.get(rid)
            if not target:
                continue

            sheet_path = target.lstrip("/")
            if not sheet_path.startswith("xl/"):
                sheet_path = "xl/" + sheet_path
            sheet_path = sheet_path.replace("xl//", "xl/")
            if sheet_path not in names:
                continue

            sheet_rels_path = "xl/worksheets/_rels/" + Path(sheet_path).name + ".rels"
            if sheet_rels_path not in names:
                continue

            sheet_rels = ET.fromstring(zf.read(sheet_rels_path))
            drawing_target = None
            for rel in sheet_rels:
                rel_type = rel.attrib.get("Type", "")
                if rel_type in (DRAWING_REL_TYPE, V_DRAWING_REL_TYPE):
                    drawing_target = rel.attrib.get("Target")
                    break
            if not drawing_target:
                continue

            if drawing_target.startswith("/"):
                drawing_path = drawing_target.lstrip("/")
            else:
                drawing_path = str((Path(sheet_path).parent / drawing_target).as_posix())
                while "../" in drawing_path:
                    drawing_path = drawing_path.replace("../", "", 1)
                    drawing_path = "xl/" + drawing_path if not drawing_path.startswith("xl/") else drawing_path

            if drawing_path not in names:
                continue

            try:
                root = ET.fromstring(zf.read(drawing_path))
            except ET.ParseError:
                continue

            entries = result.setdefault(sheet_path, [])
            for anchor in list(root):
                from_node = anchor.find("{http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing}from")
                if from_node is None:
                    continue
                row_node = from_node.find("{http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing}row")
                col_node = from_node.find("{http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing}col")
                if row_node is None or col_node is None:
                    continue

                try:
                    row = int(row_node.text or 0) + 1
                    col = int(col_node.text or 0) + 1
                except ValueError:
                    continue

                texts = []
                for t in anchor.iter("{http://schemas.openxmlformats.org/drawingml/2006/main}t"):
                    if t.text:
                        texts.append(t.text)
                text = normalize_text("".join(texts))
                if text:
                    entries.append((row, text))

            if entries:
                result[sheet_path] = entries

    return result


def extract_workbook() -> list[dict]:
    if not XLSX_PATH.exists():
        raise FileNotFoundError(f"Excel file not found: {XLSX_PATH}")

    workbook = load_workbook(XLSX_PATH, data_only=True, read_only=False)
    drawing_texts = get_drawing_texts(XLSX_PATH)

    # Map sheet name to worksheet XML path in workbook order.
    with ZipFile(XLSX_PATH) as zf:
        workbook_xml = ET.fromstring(zf.read("xl/workbook.xml"))
        rels_xml = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
        rel_map = {r.attrib["Id"]: r.attrib["Target"] for r in rels_xml}
        sheet_xml_by_name = {}
        for sheet in workbook_xml.find("main:sheets", NS):
            rid = sheet.attrib.get(f"{{{REL_NS}}}id")
            target = rel_map.get(rid, "")
            target = target.lstrip("/")
            if not target.startswith("xl/"):
                target = "xl/" + target
            sheet_xml_by_name[sheet.attrib["name"]] = target

    sheets = []
    for ws in workbook.worksheets:
        context = []

        # Normal worksheet cell text.
        for row in ws.iter_rows():
            for cell in row:
                text = normalize_text(cell.value)
                if text:
                    context.append({
                        "row": cell.row,
                        "line": cell.column,
                        "text": text,
                    })

        # DrawingML Shape/TextBox text. Images are intentionally ignored.
        sheet_xml = sheet_xml_by_name.get(ws.title)
        for row, text in drawing_texts.get(sheet_xml, []):
            context.append({
                "row": row,
                "line": None,
                "text": text,
            })

        context.sort(key=lambda x: (x["row"], x["line"] if x["line"] is not None else 10**9))
        sheets.append({
            "name": ws.title,
            "context": context,
        })

    return sheets


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    data = {"sheet": extract_workbook()}
    OUTPUT_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Generated: {OUTPUT_PATH}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise
