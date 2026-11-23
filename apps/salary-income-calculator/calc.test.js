// 実行: node apps/salary-income-calculator/calc.test.js
// テストケースは skills/salary-income-calculator/SKILL.md の「7. テストケース」と同じ。
'use strict';
const assert = require('node:assert/strict');
const { salaryIncome, calculate, parseYen } = require('./calc.js');

let passed = 0;
function check(name, fn) {
  fn();
  passed++;
  console.log('ok  ' + name);
}

// 7-1. 調整前の給与所得の金額
const baseCases = [
  [500000, 1, 0],
  [740999, 1, 0],
  [741000, 2, 1000],
  [1500000, 2, 760000],
  [2190999, 2, 1450999],
  [2191500, 3, 1451000],
  [2194000, 4, 1453000],
  [2198000, 5, 1456000],
  [2200000, 6, 1460000],
  [3000000, 6, 2020000],
  [3001999, 6, 2020000],
  [3600000, 7, 2440000],
  [5000000, 7, 3560000],
  [6600000, 8, 4840000],
  [8000000, 8, 6100000],
  [8500000, 9, 6550000],
  [9000000, 9, 7050000],
  [12000000, 9, 10050000]
];
for (const [a, band, expected] of baseCases) {
  check(`収入 ${a} → 区分No.${band} ${expected}`, () => {
    const r = salaryIncome(a);
    assert.equal(r.band.no, band);
    assert.equal(r.income, expected);
  });
}

// 7-2. 所得金額調整控除を含む最終結果
const finalCases = [
  [{ revenue: 9000000, adj1Eligible: true }, 50000, 0, 7000000],
  [{ revenue: 12000000, adj1Eligible: true }, 150000, 0, 9900000],
  [{ revenue: 9000000, adj1Eligible: false }, 0, 0, 7050000],
  [{ revenue: 1500000, pensionIncome: 300000 }, 0, 100000, 660000],
  [{ revenue: 790000, pensionIncome: 30000 }, 0, 0, 50000],
  [{ revenue: 5000000, specificExpense: 200000 }, 0, 0, 3360000]
];
for (const [input, adj1, adj2, expected] of finalCases) {
  check(`最終結果 ${JSON.stringify(input)} → ${expected}`, () => {
    const r = calculate(input);
    assert.equal(r.adjustment1, adj1);
    assert.equal(r.adjustment2, adj2);
    assert.equal(r.salaryIncome, expected);
    assert.equal(r.deduction + r.baseIncome, input.revenue);
  });
}

// 控除①はＡが850万円以下なら0円、特定支出控除で0円未満にはならない
check('控除①: 850万円ちょうどは対象外', () => {
  assert.equal(calculate({ revenue: 8500000, adj1Eligible: true }).adjustment1, 0);
});
check('最終結果は0円未満にならない', () => {
  assert.equal(calculate({ revenue: 1000000, specificExpense: 999999 }).salaryIncome, 0);
});

// 6. 入力チェック
check('入力: 全角・カンマ・円を許容', () => {
  assert.deepEqual(parseYen('５，０００，０００円'), { value: 5000000, truncated: false });
});
check('入力: 小数は円未満切捨て', () => {
  assert.deepEqual(parseYen('1234567.8'), { value: 1234567, truncated: true });
});
check('入力: エラー判定', () => {
  assert.equal(parseYen('').error, 'empty');
  assert.equal(parseYen('0').error, 'empty');
  assert.equal(parseYen('abc').error, 'nan');
  assert.equal(parseYen('-100').error, 'negative');
  assert.equal(parseYen('1000000000').error, 'max');
  assert.deepEqual(parseYen('', { allowEmpty: true }), { value: 0 });
  assert.equal(parseYen('0', { allowZero: true }).value, 0);
});

// 区分の境界が隙間なく連続していること（全区分の上下限を総当たり）
check('区分の境界で金額が連続する', () => {
  const { BANDS } = require('./calc.js');
  for (let i = 1; i < BANDS.length; i++) {
    assert.equal(BANDS[i].min, BANDS[i - 1].max + 1);
  }
});

// 公的年金等に係る雑所得（速算表）
const { pensionIncome, pensionRows } = require('./calc.js');
const pensionCases = [
  // [収入, 65歳以上, 年金以外の合計所得, 期待値]
  [695065, true, 0, 0],
  [500000, true, 0, 0],
  [2500000, true, 0, 1400000],
  [3299999, true, 0, 2199999],
  [3300000, true, 0, 2200000],
  [1000000, false, 0, 400000],
  [1299999, false, 0, 699999],
  [1300000, false, 0, 700000],
  [2000000, false, 0, 1225000],
  [4099999, false, 0, 2799999],
  [4100000, false, 0, 2800000],
  [7700000, false, 0, 5860000],
  [10000000, false, 0, 8045000],
  [2000000, true, 10000000, 900000],
  [2000000, true, 10000001, 1000000],
  [2000000, true, 20000000, 1000000],
  [1000000, false, 25000000, 600000],
  [5000000, true, 25000000, 3765000]
];
for (const [rev, age65, other, expected] of pensionCases) {
  check(`年金 ${rev}（${age65 ? '65歳以上' : '65歳未満'}・他${other}）→ ${expected}`, () => {
    assert.equal(pensionIncome(rev, age65, other).income, expected);
  });
}
check('年金の表: 区分（2）（3）の控除額がユーザー提供の表と一致', () => {
  assert.deepEqual(pensionRows(2, false).map(r => r.sub), [500000, 175000, 585000, 1355000, 1855000]);
  assert.deepEqual(pensionRows(2, true).map(r => r.sub), [1000000, 175000, 585000, 1355000, 1855000]);
  assert.deepEqual(pensionRows(3, false).map(r => r.sub), [400000, 75000, 485000, 1255000, 1755000]);
  assert.deepEqual(pensionRows(3, true).map(r => r.sub), [900000, 75000, 485000, 1255000, 1755000]);
});

// 給与と年金の組み合わせ（所得金額調整控除②を年金収入から自動計算）
check('給与150万円＋年金150万円（65歳以上）→ 合計所得1,060,000円', () => {
  const r = calculate({ revenue: 1500000, pensionRevenue: 1500000, age65: true });
  assert.equal(r.pensionIncome, 400000);
  assert.equal(r.adjustment2, 100000);
  assert.equal(r.salaryIncome, 660000);
  assert.equal(r.totalIncome, 1060000);
});
check('年金のみ（給与0円）でも計算できる', () => {
  const r = calculate({ revenue: 0, pensionRevenue: 695065, age65: true });
  assert.equal(r.salaryIncome, 0);
  assert.equal(r.totalIncome, 0);
});
check('事例: 給与3,061,715円のみ → 合計所得2,062,000円', () => {
  assert.equal(calculate({ revenue: 3061715 }).totalIncome, 2062000);
});

console.log(`\n${passed} tests passed`);
