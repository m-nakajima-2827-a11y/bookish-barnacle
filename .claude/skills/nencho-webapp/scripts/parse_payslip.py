#!/usr/bin/env python3
"""給与明細PDF → 集計シート用データ（CLI）

アプリと同じ解析ロジック（assets/app/js/payslip.js）を Node で呼び出すため、ラベル辞書は1か所で管理できる。
必要なもの: pdftotext（poppler-utils）, node

使い方:
  python3 scripts/parse_payslip.py 明細/*.pdf                 # JSONを標準出力
  python3 scripts/parse_payslip.py 明細/*.pdf --csv 集計.csv  # 集計シート形式のCSVも出力
"""
import argparse
import csv
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PAYSLIP_JS = HERE.parent / "assets" / "app" / "js" / "payslip.js"
NODE_SNIPPET = (
    "const P=require(process.argv[1]);let s='';process.stdin.on('data',d=>s+=d);"
    "process.stdin.on('end',()=>process.stdout.write(JSON.stringify(P.parseText(s))));"
)


def pdf_text(path: Path) -> str:
    out = subprocess.run(["pdftotext", "-layout", str(path), "-"], capture_output=True, text=True, check=True)
    return out.stdout


def parse(path: Path) -> dict:
    text = pdf_text(path)
    if not text.strip():
        return {"file": path.name, "warnings": ["文字情報がありません（スキャン画像の可能性）"]}
    res = subprocess.run(["node", "-e", NODE_SNIPPET, str(PAYSLIP_JS)], input=text, capture_output=True, text=True, check=True)
    data = json.loads(res.stdout)
    data["file"] = path.name
    # 集計シートの「社会保険料等の控除額」は小規模企業共済等掛金（給与天引き分）を含む
    data["socialForSheet"] = (data.get("social") or 0) + (data.get("smallBiz") or 0)
    return data


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pdfs", nargs="+", type=Path)
    ap.add_argument("--csv", type=Path, help="集計シート形式のCSV出力先")
    args = ap.parse_args()

    rows = [parse(p) for p in args.pdfs]
    rows.sort(key=lambda r: (r.get("kind") != "salary", r.get("month") or 0))
    json.dump(rows, sys.stdout, ensure_ascii=False, indent=2)
    print()

    if args.csv:
        with args.csv.open("w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["区分", "月区分", "支給月日", "総支給金額", "社会保険料等の控除額", "扶養親族等の数", "算出税額", "うち小規模企業共済等掛金", "ファイル", "確認事項"])
            for r in rows:
                w.writerow([
                    "賞与等" if r.get("kind") == "bonus" else "給料・手当等", r.get("month") or "", r.get("payDate") or "",
                    r.get("gross") or "", r.get("socialForSheet") or "", r.get("depCount") or "", r.get("tax") or "",
                    r.get("smallBiz") or "", r["file"], " / ".join(r.get("warnings") or []),
                ])
    return 0 if all(not r.get("warnings") for r in rows) else 1


if __name__ == "__main__":
    sys.exit(main())
