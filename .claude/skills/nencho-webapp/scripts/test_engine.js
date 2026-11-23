#!/usr/bin/env node
// 計算エンジンの単体テスト（国税庁の表の境界値＋手計算のシナリオ）
// 実行: node scripts/test_engine.js
const path = require('path');
const assert = require('assert');
const N = require(path.join(__dirname, '../assets/app/js/engine.js'));
const P = require(path.join(__dirname, '../assets/app/js/payslip.js'));
const { scenarios } = require('./scenarios.js');

let pass = 0;
const t = (name, fn) => { try { fn(); pass++; } catch (e) { console.error('NG', name, '\n', e.message); process.exitCode = 1; } };

// --- 給与所得控除（No.1410 令和8年分） ---
t('給与所得 境界値', () => {
  const cases = [[690000, 0], [740999, 0], [741000, 1000], [1000000, 260000], [2190999, 1450999], [2191000, 1451000],
    [2193000, 1453000], [2196000, 1456000], [2199999, 1456000], [2200000, 1460000], [2203999, 1460000],
    [3600000, 2440000], [5000000, 3560000], [6600000, 4840000], [8500000, 6550000], [10000000, 8050000], [20000000, 18050000]];
  cases.forEach(([x, y]) => assert.strictEqual(N.salaryIncomeAfterDeduction(x), y, `収入${x}`));
  assert.strictEqual(N.salaryIncomeAfterDeduction(20000001), null);
});

// --- 基礎控除（令和8年分 基礎控除額の表） ---
t('基礎控除', () => {
  [[4890000, 1040000], [4890001, 670000], [6550000, 670000], [6550001, 620000], [23500001, 480000], [24500001, 160000], [25000001, 0]]
    .forEach(([x, y]) => assert.strictEqual(N.basicDeduction(x), y, `所得${x}`));
});

// --- 配偶者（特別）控除一覧表 ---
t('配偶者控除', () => {
  assert.strictEqual(N.spouseDeduction(5000000, 620000, 50).amount, 380000);
  assert.strictEqual(N.spouseDeduction(5000000, 0, 70).amount, 480000);
  assert.strictEqual(N.spouseDeduction(9200000, 0, 70).amount, 320000);
  assert.strictEqual(N.spouseDeduction(9800000, 950000, 40).amount, 130000);
  assert.strictEqual(N.spouseDeduction(5000000, 950001, 40).amount, 360000);
  assert.strictEqual(N.spouseDeduction(5000000, 1330000, 40).amount, 30000);
  assert.strictEqual(N.spouseDeduction(5000000, 1330001, 40).amount, 0);
  assert.strictEqual(N.spouseDeduction(10000001, 0, 40).amount, 0);
});

// --- 特定親族特別控除 ---
t('特定親族特別控除', () => {
  [[620000, 0], [620001, 630000], [850000, 630000], [850001, 610000], [1000000, 410000], [1230000, 30000], [1230001, 0]]
    .forEach(([x, y]) => assert.strictEqual(N.tokuteiShinzokuDeduction(x), y, `所得${x}`));
});

// --- 年齢・区分 ---
t('年末年齢と区分', () => {
  assert.strictEqual(N.ageAtYearEnd('2004-01-01', 2026), 23);
  assert.strictEqual(N.ageAtYearEnd('2004-01-02', 2026), 22);
  assert.strictEqual(N.ageAtYearEnd('1957-01-01', 2026), 70);
  assert.strictEqual(N.classifyDependent({ birth: '2008-01-01', income: 0 }).category, '特定扶養親族');
  assert.strictEqual(N.classifyDependent({ birth: '2008-01-02', income: 0 }).category, '一般の控除対象扶養親族');
  assert.strictEqual(N.classifyDependent({ birth: '2011-01-02', income: 0 }).category, '年少扶養親族');
  assert.strictEqual(N.classifyDependent({ birth: '1957-01-01', income: 0, relation: '父', cohabit: true }).category, '同居老親等');
  assert.strictEqual(N.classifyDependent({ birth: '1957-01-01', income: 0, relation: '叔父', cohabit: true }).category, '老人扶養親族');
  assert.strictEqual(N.classifyDependent({ birth: '2005-06-01', income: 1000000 }).category, '特定親族');
  assert.strictEqual(N.classifyDependent({ birth: '1990-06-01', income: 1000000 }).category, '対象外');
  assert.strictEqual(N.classifyDependent({ birth: '1990-06-01', income: 0, nonResident: true }).category, '扶養親族（控除対象外）');
});

// --- 生命保険料・地震保険料 ---
t('生命保険料控除', () => {
  const L = (e, u) => N.lifeInsuranceDeduction(e, u).total;
  assert.strictEqual(L([{ kind: 'general', era: 'new', amount: 80000 }], false), 40000);
  assert.strictEqual(L([{ kind: 'general', era: 'new', amount: 120000 }], true), 60000);
  assert.strictEqual(L([{ kind: 'general', era: 'new', amount: 50000 }], true), 40000);
  assert.strictEqual(L([{ kind: 'general', era: 'old', amount: 100001 }], false), 50000);
  assert.strictEqual(L([{ kind: 'general', era: 'new', amount: 30000 }, { kind: 'general', era: 'old', amount: 30000 }], false), 40000);
  assert.strictEqual(L([{ kind: 'general', era: 'new', amount: 30001 }], false), 25001); // 1円未満切上げ
  assert.strictEqual(L([{ kind: 'general', era: 'old', amount: 200000 }, { kind: 'care', amount: 200000 }, { kind: 'pension', era: 'old', amount: 200000 }], false), 120000);
});
t('地震保険料控除', () => {
  assert.strictEqual(N.quakeDeduction([{ kind: 'quake', amount: 70000 }]).total, 50000);
  assert.strictEqual(N.quakeDeduction([{ kind: 'oldlong', amount: 15000 }]).total, 12500);
  assert.strictEqual(N.quakeDeduction([{ kind: 'oldlong', amount: 30000 }]).total, 15000);
  assert.strictEqual(N.quakeDeduction([{ kind: 'quake', amount: 40000 }, { kind: 'oldlong', amount: 30000 }]).total, 50000);
});

// --- 速算表・年税額 ---
t('算出所得税額', () => {
  assert.strictEqual(N.incomeTax(1950000), 97500);
  assert.strictEqual(N.incomeTax(3300000), 232500);
  assert.strictEqual(N.incomeTax(5000000), 572500);
});

// --- シナリオ（手計算で確認した値） ---
const R = Object.fromEntries(scenarios().map((s) => [s.name, N.calculate(s.emp)]));
t('excel-sample', () => {
  const L = R['excel-sample'].lines;
  assert.strictEqual(L.r1, 3557355);
  assert.strictEqual(L.r9, 2409200);             // 3,557,355→4,000円単位 3,556,000×0.7−80,000
  assert.strictEqual(L.r12, 267344);
  assert.strictEqual(L.r15, 120000);
  assert.strictEqual(L.r16, 42500);
  assert.strictEqual(L.r17, 360000);             // 配偶者所得100万円・本人A
  assert.strictEqual(L.r18, 610000);             // 特定親族 所得90万円
  assert.strictEqual(L.r19, 380000 + 270000);    // 一般扶養＋年少の障害者
  assert.strictEqual(L.r20, 1040000);
  assert.strictEqual(L.r22, 0);
  assert.strictEqual(R['excel-sample'].status, 'refund');
  assert.strictEqual(L.r30, 62400);
});
t('high-income', () => {
  const r = R['high-income'], L = r.lines;
  assert.strictEqual(L.r7, 10900000);
  assert.strictEqual(L.r9, 8950000);
  assert.strictEqual(r.choseiApplicable, true);  // 23歳未満の扶養親族
  assert.strictEqual(L.r10, 150000);
  assert.strictEqual(L.r11, 8800000);
  assert.strictEqual(L.r17, 380000);             // 本人A（880万）・配偶者所得0
  assert.strictEqual(L.r12, 98000 * 12 + 350000);
  assert.strictEqual(L.r13, 210000);
  assert.strictEqual(L.r14, 144000);
  assert.strictEqual(L.r20, 620000);
  assert.strictEqual(L.r24, 175000);
  // ㉒=8,800,000−(1,526,000+210,000+144,000+380,000+620,000)=5,920,000 → ㉓=5,920,000×20%−427,500=756,500
  assert.strictEqual(L.r22, 5920000);
  assert.strictEqual(L.r23, 756500);
  assert.strictEqual(L.r26, Math.floor((756500 - 175000) * 1.021 / 100) * 100);
});
t('low-income', () => {
  const r = R['low-income'], L = r.lines;
  assert.strictEqual(r.fuyo.box.C, 1);
  assert.strictEqual(r.fuyo.box.G, 1);
  assert.strictEqual(r.fuyo.box.H, 'ひとり親');
  assert.strictEqual(L.r19, 580000 + 750000 + 350000 + 380000); // 同居老親＋同居特障＋ひとり親＋一般扶養（16歳）
});
t('shortage', () => {
  const r = R['shortage'];
  assert.strictEqual(r.status, 'shortage');
  assert.ok(r.kakuteiRequired);                  // 給与以外の所得30万円
  assert.strictEqual(r.yearEndAdjustment, r.lines.r27);
});
t('override', () => {
  const s = scenarios()[0].emp;
  s.overrides = { r15: 50000 };
  const r = N.calculate(s);
  assert.strictEqual(r.lines.r15, 50000);
});

// --- 給与明細パーサー（平文） ---
t('payslip text', () => {
  const txt = [
    '株式会社サンプル   給与明細書   令和8年4月分',
    '支給日 令和8年4月25日   扶養人数 1',
    '基本給     役職手当    通勤手当    総支給額',
    '280,000    10,000      12,000      302,000',
    '健康保険   介護保険   厚生年金   雇用保険   子ども・子育て支援金   社会保険料合計',
    '14,800     0          27,450     1,812      690                   44,752',
    '所得税  5,620   住民税  12,300   控除合計  62,672   差引支給額  239,328',
  ].join('\n');
  const r = P.parseText(txt);
  assert.strictEqual(r.gross, 302000);
  assert.strictEqual(r.social, 44752);
  assert.strictEqual(r.tax, 5620);
  assert.strictEqual(r.payDate, '2026-04-25');
  assert.strictEqual(r.month, 4);
  assert.strictEqual(r.kind, 'salary');
  assert.strictEqual(r.depCount, 1);
  assert.deepStrictEqual(r.warnings, []);
});

console.log(`engine tests: ${pass} passed${process.exitCode ? ' (with failures)' : ''}`);
