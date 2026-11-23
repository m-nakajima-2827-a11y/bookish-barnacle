#!/usr/bin/env node
// ブラウザでの動作確認（Playwright）。CDN の pdf.js / ExcelJS はローカルの node_modules に差し替える。
// 実行: NODE_MODULES=/path/to/node_modules node scripts/e2e_test.js <PDFディレクトリ> [スクリーンショット出力先]
//   NODE_MODULES に pdfjs-dist@3.11.174 と exceljs@4.4.0 が入っていること。playwright は require できること。
const path = require('path');
const fs = require('fs');
const { chromium } = require('playwright');
const NM = process.env.NODE_MODULES;
const ExcelJS = require(path.join(NM, 'exceljs'));
const pdfDir = process.argv[2];
const shotDir = process.argv[3] || pdfDir;
const appUrl = 'file://' + path.join(__dirname, '../assets/app/index.html');

const assert = (c, m) => { if (!c) throw new Error('NG: ' + m); console.log('OK: ' + m); };
const num = (s) => Number(String(s).replace(/[^0-9-]/g, ''));

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1400, height: 900 }, acceptDownloads: true });
  const errors = [];
  page.on('pageerror', (e) => errors.push(e.message));
  page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()); });
  const local = {
    'pdf.min.js': path.join(NM, 'pdfjs-dist/build/pdf.min.js'),
    'pdf.worker.min.js': path.join(NM, 'pdfjs-dist/build/pdf.worker.min.js'),
    'exceljs.min.js': path.join(NM, 'exceljs/dist/exceljs.min.js'),
  };
  await page.route('https://cdnjs.cloudflare.com/**', (route) => {
    const f = local[route.request().url().split('/').pop()];
    return f ? route.fulfill({ path: f, contentType: 'application/javascript' }) : route.abort();
  });
  await page.goto(appUrl);

  // 1) サンプル従業員を追加 → 一覧に表示
  await page.click('[data-action="sample"]');
  await page.waitForSelector('[data-emp-row]');
  assert((await page.textContent('#summary')).includes('年調年税額'), 'サマリーが表示される');

  // 2) 新規従業員 → 給与明細PDFを取込
  await page.click('.appbar [data-action="new-employee"]');
  await page.fill('[data-bind="profile.name"]', 'テスト 花子');
  await page.click('[data-tab="import"]');
  const pdfs = fs.readdirSync(pdfDir).filter((f) => f.endsWith('.pdf')).map((f) => path.join(pdfDir, f));
  await page.setInputFiles('#pdfFile', pdfs);
  await page.waitForFunction((n) => document.querySelectorAll('[data-action="apply-parsed"]').length === n, pdfs.length, { timeout: 30000 });
  const rows = await page.$$eval('tbody tr', (trs) => trs.map((tr) => Array.from(tr.querySelectorAll('input,select')).map((i) => i.value)));
  console.log('読取り結果', JSON.stringify(rows));
  if (shotDir) await page.screenshot({ path: path.join(shotDir, 'e2e-import.png'), fullPage: true });
  await page.click('[data-action="apply-all"]');

  // 3) 集計シートへ反映されたか
  await page.click('[data-tab="agg"]');
  const apr = await page.inputValue('[data-bind="payroll.salary.3.gross"]');
  const aprSoc = await page.inputValue('[data-bind="payroll.salary.3.social"]');
  const bonus = await page.inputValue('[data-bind="payroll.bonus.0.gross"]');
  assert(num(apr) === 302000, `4月の総支給金額 302,000（実際 ${apr}）`);
  assert(num(aprSoc) === 49752, `4月の社会保険料等＝社保44,752＋確定拠出5,000（実際 ${aprSoc}）`);
  assert(num(bonus) === 400000, `賞与 400,000（実際 ${bonus}）`);

  // 4) 残りの月を入力 → 計算シートの結果が engine と一致
  for (let i = 0; i < 12; i++) {
    if (i === 3 || i === 11) continue;
    await page.fill(`[data-bind="payroll.salary.${i}.gross"]`, '300000');
    await page.fill(`[data-bind="payroll.salary.${i}.social"]`, '45000');
    await page.fill(`[data-bind="payroll.salary.${i}.tax"]`, '5500');
  }
  // 5) 扶養親族を追加（特定扶養）
  await page.click('[data-tab="fuyo"]');
  await page.click('[data-action="add-dep"]');
  await page.fill('[data-bind="fuyo.dependents.0.name"]', '長男');
  await page.fill('[data-bind="fuyo.dependents.0.birth"]', '2006-05-05');
  await page.fill('[data-bind="fuyo.dependents.0.income"]', '0');
  await page.waitForFunction(() => document.querySelector('[data-depcls="0"][data-k="cat"]').textContent === '特定扶養親族');
  assert(true, '扶養親族の区分が「特定扶養親族」に自動判定');
  // 6) 保険料
  await page.click('[data-tab="hoken"]');
  await page.click('[data-action="add-row"][data-list="hoken.life"]');
  await page.fill('[data-bind="hoken.life.0.amount"]', '100000');
  const r15 = await page.textContent('[data-out="lines.r15"]');
  assert(num(r15) === 55000, `生命保険料控除（23歳未満扶養あり・計算式Ⅱ）55,000（実際 ${r15}）`);

  // 7) 計算シート：手入力で上書き → 解除
  await page.click('[data-tab="calc"]');
  const before = await page.textContent('[data-out="lines.r26"]');
  await page.fill('[data-bind="overrides.r20"]', '620000');
  const after = await page.textContent('[data-out="lines.r26"]');
  assert(before !== after, `⑳を上書きすると㉖が変わる（${before} → ${after}）`);
  await page.click('[data-action="clear-overrides"]');
  assert((await page.textContent('[data-out="lines.r26"]')) === before, '手入力の解除で自動計算に戻る');
  if (shotDir) await page.screenshot({ path: path.join(shotDir, 'e2e-calc.png'), fullPage: true });

  // engine の結果と画面の一致
  await page.waitForTimeout(600); // localStorage への保存は250ms遅延
  const state = await page.evaluate(() => JSON.parse(localStorage.getItem('nencho-r8-v1')));
  const N = require(path.join(__dirname, '../assets/app/js/engine.js'));
  const emp = state.employees.find((e) => e.profile.name === 'テスト 花子');
  const res = N.calculate(emp);
  assert(num(before) === res.lines.r26, `画面の㉖とエンジンの㉖が一致（${res.lines.r26}）`);

  // 8) Excel出力 → 関数入りで、計算シート①が集計シートを参照
  await page.click('[data-tab="data"]');
  const [dl] = await Promise.all([page.waitForEvent('download'), page.click('[data-action="excel"]')]);
  const xlsx = path.join(shotDir || pdfDir, 'e2e-export.xlsx');
  await dl.saveAs(xlsx);
  const wb = new ExcelJS.Workbook();
  await wb.xlsx.readFile(xlsx);
  const calc = wb.getWorksheet('計算シート');
  assert(calc.getCell('M14').value.formula === "'集計シート'!E15", '計算シート①＝集計シートE15（関数）');
  assert(calc.getCell('M23').value.formula === "'保険申告書'!K14", '計算シート⑮＝保険申告書（関数）');
  assert(calc.getCell('T33').value.result === res.lines.r26, 'Excelの㉖キャッシュ値がエンジンと一致');
  assert(wb.worksheets.every((ws) => !ws.sheetProtection), '全シート保護なし（編集可能）');
  assert(wb.worksheets.length === 13, `シート数 13（実際 ${wb.worksheets.length}）`);

  // 9) 一覧画面とスマホ幅
  await page.click('[data-tab="dashboard"]');
  await page.setViewportSize({ width: 390, height: 844 });
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1);
  assert(!overflow, 'スマホ幅で横スクロールが出ない');
  if (shotDir) await page.screenshot({ path: path.join(shotDir, 'e2e-mobile.png'), fullPage: false });

  assert(errors.length === 0, 'コンソールエラーなし ' + errors.join(' | '));
  await browser.close();
})().catch((e) => { console.error(e); process.exit(1); });
