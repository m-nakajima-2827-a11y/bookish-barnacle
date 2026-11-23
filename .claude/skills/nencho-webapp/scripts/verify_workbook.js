#!/usr/bin/env node
// Excel出力の関数が計算エンジンと同じ結果になるかを LibreOffice で再計算して検証する。
// 実行: EXCELJS=/path/to/node_modules/exceljs node scripts/verify_workbook.js [出力先ディレクトリ]
//   - exceljs が require できること（npm i exceljs@4.4.0）
//   - soffice（LibreOffice）が PATH にあること
const path = require('path');
const fs = require('fs');
const os = require('os');
const { execFileSync } = require('child_process');
const ExcelJS = require(process.env.EXCELJS || 'exceljs');
const N = require(path.join(__dirname, '../assets/app/js/engine.js'));
const W = require(path.join(__dirname, '../assets/app/js/workbook.js'));
const { scenarios } = require('./scenarios.js');

const outDir = process.argv[2] || fs.mkdtempSync(path.join(os.tmpdir(), 'nencho-wb-'));
const recalcDir = path.join(outDir, 'recalc');
fs.mkdirSync(recalcDir, { recursive: true });

// LibreOffice を「読込時に常に再計算」で動かすための一時プロファイル
const profile = path.join(outDir, 'lo-profile');
const userDir = path.join(profile, 'user');
fs.mkdirSync(userDir, { recursive: true });
fs.writeFileSync(path.join(userDir, 'registrymodifications.xcu'), `<?xml version="1.0" encoding="UTF-8"?>
<oor:items xmlns:oor="http://openoffice.org/2001/registry" xmlns:xs="http://www.w3.org/2001/XMLSchema" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
<item oor:path="/org.openoffice.Office.Calc/Formula/Load"><prop oor:name="OOXMLRecalcMode" oor:op="fuse"><value>0</value></prop></item>
<item oor:path="/org.openoffice.Office.Calc/Formula/Load"><prop oor:name="ODFRecalcMode" oor:op="fuse"><value>0</value></prop></item>
</oor:items>`);

const CELL = {
  r1: 'M14', r3: 'T14', r4: 'M15', r6: 'T15', r7: 'M16', r8: 'T16', r9: 'M17', r10: 'M18', r11: 'M19', r12: 'M20', r13: 'M21',
  r14: 'M22', r15: 'M23', r16: 'M24', r17: 'M25', r18: 'M26', r19: 'M27', r20: 'M28', r21: 'M29', r22: 'M30', r23: 'T30',
  r24: 'T31', r25: 'T32', r26: 'T33', r27: 'T34', r30: 'T37', r31: 'T38', r32: 'T39', r33: 'T40', r34: 'T41',
};

(async () => {
  const list = scenarios();
  const files = [];
  for (const s of list) {
    const wb = W.build(ExcelJS, s.emp, null); // キャッシュ値なしで出力 → 再計算結果だけで比較
    const f = path.join(outDir, `${s.name}.xlsx`);
    await wb.xlsx.writeFile(f);
    files.push(f);
  }
  execFileSync('soffice', [`-env:UserInstallation=file://${profile}`, '--headless', '--calc', '--convert-to', 'xlsx', '--outdir', recalcDir, ...files], { stdio: 'pipe' });

  let ng = 0;
  for (const s of list) {
    const res = N.calculate(s.emp);
    const wb = new ExcelJS.Workbook();
    await wb.xlsx.readFile(path.join(recalcDir, `${s.name}.xlsx`));
    const ws = wb.getWorksheet('計算シート');
    // LibreOffice は結果が 0 や "" のセルにキャッシュ値を書かないため、値なしの関数は空として扱う
    const val = (addr) => { const v = ws.getCell(addr).value; return v && typeof v === 'object' && 'formula' in v ? v.result ?? '' : v; };
    const diffs = [];
    for (const [k, addr] of Object.entries(CELL)) {
      let x = val(addr); if (x === '' || x === null || x === undefined) x = 0;
      if (Math.round(Number(x)) !== res.lines[k]) diffs.push(`${k}(${addr}) excel=${x} engine=${res.lines[k]}`);
    }
    const label = val('B34');
    if (label !== res.statusLabel) diffs.push(`B34 excel=${label} engine=${res.statusLabel}`);
    if (diffs.length) { ng++; console.log(`NG ${s.name}\n  ` + diffs.join('\n  ')); }
    else console.log(`OK ${s.name}: ㉖年調年税額=${res.lines.r26.toLocaleString()} ${res.statusLabel} ㉗=${res.lines.r27.toLocaleString()}`);
  }
  console.log(`出力: ${outDir}`);
  process.exit(ng ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(2); });
