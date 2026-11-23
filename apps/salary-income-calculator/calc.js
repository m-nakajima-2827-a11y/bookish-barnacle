/*
 * 給与所得の計算ロジック（2026年（令和8年）分）
 * 仕様: skills/salary-income-calculator/SKILL.md
 * 浮動小数点の誤差を避けるため、すべて整数演算で計算する。
 */
(function (root) {
  'use strict';

  var TABLE_VERSION = '2026年（令和8年）分';
  var MAX_AMOUNT = 999999999;
  var ADJ1_THRESHOLD = 8500000;
  var ADJ1_CAP = 10000000;

  var BANDS = [
    { no: 1, min: 1, max: 740999, range: '1円以上 740,999円以下', formula: '0円' },
    { no: 2, min: 741000, max: 2190999, range: '741,000円以上 2,190,999円以下', formula: 'Ａ − 740,000円' },
    { no: 3, min: 2191000, max: 2192999, range: '2,191,000円以上 2,192,999円以下', formula: '1,451,000円' },
    { no: 4, min: 2193000, max: 2195999, range: '2,193,000円以上 2,195,999円以下', formula: '1,453,000円' },
    { no: 5, min: 2196000, max: 2199999, range: '2,196,000円以上 2,199,999円以下', formula: '1,456,000円' },
    { no: 6, min: 2200000, max: 3599999, range: '2,200,000円以上 3,599,999円以下', formula: 'Ｂ × 2.8 − 80,000円' },
    { no: 7, min: 3600000, max: 6599999, range: '3,600,000円以上 6,599,999円以下', formula: 'Ｂ × 3.2 − 440,000円' },
    { no: 8, min: 6600000, max: 8499999, range: '6,600,000円以上 8,499,999円以下', formula: 'Ａ × 0.9 − 1,100,000円' },
    { no: 9, min: 8500000, max: Infinity, range: '8,500,000円以上', formula: 'Ａ − 1,950,000円' }
  ];

  function num(n) {
    return String(n).replace(/\B(?=(\d{3})+(?!\d))/g, ',');
  }

  function yen(n) {
    return num(n) + '円';
  }

  function findBand(a) {
    for (var i = 0; i < BANDS.length; i++) {
      if (a >= BANDS[i].min && a <= BANDS[i].max) return BANDS[i];
    }
    return null;
  }

  /** 給与所得の金額（所得金額調整控除・特定支出控除の適用前） */
  function salaryIncome(a) {
    if (!Number.isInteger(a) || a < 1 || a > MAX_AMOUNT) {
      throw new RangeError('給与の収入金額は1円以上999,999,999円以下の整数で指定してください');
    }
    var band = findBand(a);
    var income;
    var b = null;
    var steps;
    switch (band.no) {
      case 1:
        income = 0;
        steps = '740,999円以下のため 0円';
        break;
      case 2:
        income = a - 740000;
        steps = yen(a) + ' − 740,000円 ＝ ' + yen(income);
        break;
      case 3:
        income = 1451000;
        steps = '表の固定額 ' + yen(income);
        break;
      case 4:
        income = 1453000;
        steps = '表の固定額 ' + yen(income);
        break;
      case 5:
        income = 1456000;
        steps = '表の固定額 ' + yen(income);
        break;
      case 6:
        b = Math.floor(Math.floor(a / 4) / 1000) * 1000;
        income = (b * 28) / 10 - 80000;
        steps = 'Ｂ ＝ ' + num(a) + ' ÷ 4 ＝ ' + yen(b) + '（千円未満切捨て） → ' +
          num(b) + ' × 2.8 − 80,000 ＝ ' + yen(income);
        break;
      case 7:
        b = Math.floor(Math.floor(a / 4) / 1000) * 1000;
        income = (b * 32) / 10 - 440000;
        steps = 'Ｂ ＝ ' + num(a) + ' ÷ 4 ＝ ' + yen(b) + '（千円未満切捨て） → ' +
          num(b) + ' × 3.2 − 440,000 ＝ ' + yen(income);
        break;
      case 8:
        income = Math.floor((a * 9) / 10) - 1100000;
        steps = num(a) + ' × 0.9 − 1,100,000 ＝ ' + yen(income);
        break;
      default:
        income = a - 1950000;
        steps = num(a) + ' − 1,950,000 ＝ ' + yen(income);
    }
    return { income: income, band: band, b: b, steps: steps };
  }

  /** 所得金額調整控除①（子育て・介護世帯） */
  function adjustment1(a, eligible) {
    if (!eligible || a <= ADJ1_THRESHOLD) return 0;
    return Math.ceil((Math.min(a, ADJ1_CAP) - ADJ1_THRESHOLD) / 10);
  }

  /** 所得金額調整控除②（給与所得と公的年金等の雑所得の両方がある場合） */
  function adjustment2(salaryIncomeAmount, pensionIncome) {
    if (salaryIncomeAmount <= 0 || pensionIncome <= 0) return 0;
    return Math.max(0, Math.min(salaryIncomeAmount, 100000) + Math.min(pensionIncome, 100000) - 100000);
  }

  /*
   * 公的年金等に係る雑所得（ユーザー提供の速算表）
   * 区分（1）他の合計所得1,000万円以下／（2）1,000万円超2,000万円以下／（3）2,000万円超
   * （2）（3）は（1）の控除額をそれぞれ10万円・20万円減らした形（表の数値と一致）。
   * rate は百分率の整数。所得 ＝ 収入 × rate ÷ 100（1円未満切捨て）− sub。
   */
  var PENSION_BASE = {
    under65: [
      { max: 1299999, rate: 100, sub: 600000, range: '130万円未満' },
      { max: 4099999, rate: 75, sub: 275000, range: '130万円以上410万円未満' },
      { max: 7699999, rate: 85, sub: 685000, range: '410万円以上770万円未満' },
      { max: 9999999, rate: 95, sub: 1455000, range: '770万円以上1千万円未満' },
      { max: Infinity, rate: 100, sub: 1955000, range: '1千万円以上' }
    ],
    over65: [
      { max: 3299999, rate: 100, sub: 1100000, range: '330万円未満' },
      { max: 4099999, rate: 75, sub: 275000, range: '330万円以上410万円未満' },
      { max: 7699999, rate: 85, sub: 685000, range: '410万円以上770万円未満' },
      { max: 9999999, rate: 95, sub: 1455000, range: '770万円以上1千万円未満' },
      { max: Infinity, rate: 100, sub: 1955000, range: '1千万円以上' }
    ]
  };
  var PENSION_BRACKETS = [
    { no: 1, max: 10000000, shift: 0, label: '（1）公的年金等以外の合計所得金額が1,000万円以下' },
    { no: 2, max: 20000000, shift: 100000, label: '（2）公的年金等以外の合計所得金額が1,000万円超2,000万円以下' },
    { no: 3, max: Infinity, shift: 200000, label: '（3）公的年金等以外の合計所得金額が2,000万円超' }
  ];

  function pensionRows(bracketNo, age65) {
    var br = PENSION_BRACKETS[bracketNo - 1];
    return PENSION_BASE[age65 ? 'over65' : 'under65'].map(function (r, i) {
      var sub = r.sub - br.shift;
      var formula = r.rate === 100
        ? '収入金額 − ' + yen(sub)
        : '収入金額 × 0.' + r.rate + ' − ' + yen(sub);
      return { row: i + 1, max: r.max, rate: r.rate, sub: sub, range: r.range, formula: formula };
    });
  }

  function pensionBracket(otherIncome) {
    for (var i = 0; i < PENSION_BRACKETS.length; i++) {
      if (otherIncome <= PENSION_BRACKETS[i].max) return PENSION_BRACKETS[i];
    }
    return PENSION_BRACKETS[PENSION_BRACKETS.length - 1];
  }

  /** 公的年金等に係る雑所得の金額 */
  function pensionIncome(revenue, age65, otherIncome) {
    if (!Number.isInteger(revenue) || revenue < 0 || revenue > MAX_AMOUNT) {
      throw new RangeError('公的年金等の収入金額は0円以上999,999,999円以下の整数で指定してください');
    }
    var bracket = pensionBracket(Math.max(0, otherIncome || 0));
    if (revenue === 0) return { income: 0, bracket: bracket, row: null, steps: '' };
    var rows = pensionRows(bracket.no, !!age65);
    var row = rows.filter(function (r) { return revenue <= r.max; })[0];
    var gross = Math.floor((revenue * row.rate) / 100);
    var raw = gross - row.sub;
    var income = Math.max(0, raw);
    var steps = (row.rate === 100 ? num(revenue) : num(revenue) + ' × 0.' + row.rate) +
      ' − ' + num(row.sub) + ' ＝ ' + (raw < 0 ? '0円（マイナスのため）' : yen(income));
    return { income: income, bracket: bracket, row: row, steps: steps };
  }

  /**
   * 所得金額の計算（給与所得＋公的年金等に係る雑所得）
   * input: revenue（給与の収入金額）, adj1Eligible, specificExpense,
   *        pensionRevenue（公的年金等の収入金額）, age65, otherIncome（給与・年金以外の合計所得金額）,
   *        pensionIncome（年金の雑所得を直接指定する場合。pensionRevenue があればそちらを優先）
   * 年金の区分判定に使う「公的年金等以外の合計所得金額」は、給与所得（所得金額調整控除①・特定支出控除の後、
   * ②の前）＋ その他の所得 で求める（②は最大10万円のため、区分境界付近以外では結果に影響しない）。
   */
  function calculate(input) {
    var a = input.revenue || 0;
    var specific = input.specificExpense || 0;
    var other = input.otherIncome || 0;
    var base = a > 0 ? salaryIncome(a) : { income: 0, band: null, b: null, steps: '' };
    var adj1 = adjustment1(a, !!input.adj1Eligible);
    var salaryBeforeAdj2 = Math.max(0, base.income - adj1 - specific);

    var pension;
    if (input.pensionRevenue != null && input.pensionRevenue > 0) {
      pension = pensionIncome(input.pensionRevenue, !!input.age65, salaryBeforeAdj2 + other);
    } else {
      pension = { income: input.pensionIncome || 0, bracket: null, row: null, steps: '' };
    }

    var adj2 = adjustment2(base.income, pension.income);
    var final = Math.max(0, base.income - adj1 - adj2 - specific);
    return {
      tableVersion: TABLE_VERSION,
      revenue: a,
      deduction: a - base.income,
      baseIncome: base.income,
      band: base.band,
      b: base.b,
      steps: base.steps,
      adjustment1: adj1,
      adjustment2: adj2,
      specificExpense: specific,
      salaryIncome: final,
      pensionRevenue: input.pensionRevenue || 0,
      age65: !!input.age65,
      pensionIncome: pension.income,
      pensionBracket: pension.bracket,
      pensionRow: pension.row,
      pensionSteps: pension.steps,
      otherIncome: other,
      totalIncome: final + pension.income + other
    };
  }

  /**
   * 金額の入力文字列を整数円に変換する。
   * 全角数字・カンマ・「円」・空白を許容し、円未満は切り捨てる。
   */
  function parseYen(text, options) {
    var opts = options || {};
    var s = String(text == null ? '' : text)
      .replace(/[０-９]/g, function (c) { return String.fromCharCode(c.charCodeAt(0) - 0xfee0); })
      .replace(/[．]/g, '.')
      .replace(/[－−ー‐]/g, '-')
      .replace(/[,，、\s　円]/g, '');
    if (s === '') {
      return opts.allowEmpty ? { value: 0 } : { error: 'empty' };
    }
    if (/^-/.test(s)) return { error: 'negative' };
    if (!/^\d+(\.\d+)?$/.test(s)) return { error: 'nan' };
    var truncated = s.indexOf('.') !== -1 && !/^\d+\.0+$/.test(s);
    var value = parseInt(s.split('.')[0], 10);
    if (value > MAX_AMOUNT) return { error: 'max' };
    if (value === 0 && !opts.allowZero) return { error: 'empty' };
    return { value: value, truncated: truncated };
  }

  var api = {
    TABLE_VERSION: TABLE_VERSION,
    MAX_AMOUNT: MAX_AMOUNT,
    ADJ1_THRESHOLD: ADJ1_THRESHOLD,
    BANDS: BANDS,
    salaryIncome: salaryIncome,
    adjustment1: adjustment1,
    adjustment2: adjustment2,
    PENSION_BRACKETS: PENSION_BRACKETS,
    pensionRows: pensionRows,
    pensionIncome: pensionIncome,
    calculate: calculate,
    parseYen: parseYen,
    formatNumber: num,
    formatYen: yen
  };

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = api;
  } else {
    root.SalaryIncome = api;
  }
})(typeof globalThis !== 'undefined' ? globalThis : this);
