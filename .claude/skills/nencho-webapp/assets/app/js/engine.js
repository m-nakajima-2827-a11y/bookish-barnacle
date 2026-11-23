/*
 * 年末調整 計算エンジン（令和8年分）
 *
 * 国税庁「年末調整計算シート（令和８年用）」の計算ロジックを踏襲し、
 * 集計シート → 各申告書 → 計算シート（①〜㉞）を自動計算する。
 *
 * 出典（2026-11 確認）:
 *  - 給与所得控除 No.1410  https://www.nta.go.jp/taxes/shiraberu/taxanswer/shotoku/1410.htm
 *  - 令和8年分 年末調整のしかた https://www.nta.go.jp/publication/pamph/gensen/nencho2026/01.htm
 *    （Ⅰ 変わった点 / 速算表・配偶者控除額一覧・基礎控除額表・特定親族特別控除額表・扶養控除額等の表 / 保険料控除）
 *  - 給与所得者で確定申告が必要な人 No.1900 https://www.nta.go.jp/taxes/shiraberu/taxanswer/shotoku/1900.htm
 *
 * 法改正時は TABLES だけを書き換える（references/annual-update.md 参照）。
 * ブラウザでは window.Nencho、Node では require() で使える（UMD）。
 */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else root.Nencho = factory();
})(typeof self !== 'undefined' ? self : this, function () {
  'use strict';

  // ------------------------------------------------------------------
  // 1. 令和8年分の控除テーブル（法改正時はここを更新）
  // ------------------------------------------------------------------
  const TABLES = {
    year: 2026,
    label: '令和8年分',
    // 給与所得控除後の金額（別表第五の考え方を関数化。計算シート M17/AC17 と同一）
    salaryIncome: {
      noIncomeUpTo: 740999,          // 74万999円以下は 0（69.1万〜74.1万未満は「なし」）
      minDeduction: 740000,          // 最低保障額 74万円（令和8・9年分）
      fixedBands: [                  // 219.1万〜220万未満の固定額
        { upTo: 2192999, income: 1451000 },
        { upTo: 2195999, income: 1453000 },
        { upTo: 2199999, income: 1456000 },
      ],
      roundFrom: 2200000, roundTo: 6599999, roundUnit: 4000, // 220万〜660万未満は4,000円単位で切捨て
      maxSalary: 20000000,           // 2,000万円超は年末調整の対象外
    },
    // 基礎控除（合計所得金額の上限 → 控除額）
    basic: [
      [4890000, 1040000],   // 62万 + 特例加算42万
      [6550000, 670000],    // 62万 + 特例加算5万
      [23500000, 620000],
      [24000000, 480000],
      [24500000, 320000],
      [25000000, 160000],
      [Infinity, 0],
    ],
    // 配偶者（特別）控除：配偶者の合計所得金額の上限 → [A(本人900万以下), B(950万以下), C(1,000万以下)]
    spouseElderly: [480000, 320000, 160000], // 配偶者控除・老人控除対象配偶者（配偶者62万以下かつ70歳以上）
    spouse: [
      [620000, [380000, 260000, 130000]],   // 配偶者控除（一般）
      [950000, [380000, 260000, 130000]],   // 以下 配偶者特別控除
      [1000000, [360000, 240000, 120000]],
      [1050000, [310000, 210000, 110000]],
      [1100000, [260000, 180000, 90000]],
      [1150000, [210000, 140000, 70000]],
      [1200000, [160000, 110000, 60000]],
      [1250000, [110000, 80000, 40000]],
      [1300000, [60000, 40000, 20000]],
      [1330000, [30000, 20000, 10000]],
    ],
    spouseTaxpayerBands: [9000000, 9500000, 10000000], // 本人の合計所得金額 区分Ⅰ A/B/C
    // 特定親族特別控除（特定親族の合計所得金額の上限 → 控除額）。62万円以下は扶養控除（特定扶養親族）
    tokuteiShinzoku: [
      [850000, 630000], [900000, 610000], [950000, 510000], [1000000, 410000],
      [1050000, 310000], [1100000, 210000], [1150000, 110000], [1200000, 60000], [1230000, 30000],
    ],
    dependentIncomeLimit: 620000,       // 扶養親族・同一生計配偶者の所得要件（改正前58万）
    tokuteiShinzokuIncomeLimit: 1230000,
    withholdingRelativeLimit: 1000000,  // 源泉控除対象親族（特定親族のうち100万円以下）
    withholdingSpouseLimit: 950000,     // 源泉控除対象配偶者
    workingStudentIncomeLimit: 890000,  // 勤労学生（改正前85万）
    widowIncomeLimit: 5000000,          // 寡婦・ひとり親
    deductions: {
      general: 380000, specific: 630000, elderly: 480000, elderlyCohabit: 580000,
      disabled: 270000, specialDisabled: 400000, cohabitSpecialDisabled: 750000,
      widow: 270000, singleParent: 350000, workingStudent: 270000,
    },
    // 所得金額調整控除（子ども・特別障害者等を有する場合）
    adjustment: { threshold: 8500000, cap: 10000000, rate: 0.1, max: 150000 },
    // 年末調整のための算出所得税額の速算表（上限, 税率, 控除額）
    taxRates: [
      [1950000, 0.05, 0], [3300000, 0.10, 97500], [6950000, 0.20, 427500],
      [9000000, 0.23, 636000], [18000000, 0.33, 1536000], [Infinity, 0.40, 2796000],
    ],
    reconstructionRate: 1.021,          // 復興特別所得税を含む年調年税額 = ㉕×102.1%（100円未満切捨て）
    // 生命保険料控除（計算式Ⅰ・Ⅱ・Ⅲ）
    life: {
      formulaI: [[20000, 1, 0], [40000, 0.5, 10000], [80000, 0.25, 20000], [Infinity, 0, 40000]],
      formulaII: [[30000, 1, 0], [60000, 0.5, 15000], [120000, 0.25, 30000], [Infinity, 0, 60000]], // 23歳未満の扶養親族あり・新生命保険料
      formulaIII: [[25000, 1, 0], [50000, 0.5, 12500], [100000, 0.25, 25000], [Infinity, 0, 50000]],
      bothCap: 40000, bothCapUnder23: 60000, totalCap: 120000,
    },
    quake: { cap: 50000, oldLong: [[10000, 1, 0], [20000, 0.5, 5000], [Infinity, 0, 15000]] },
    housingLoanMax: 600000,
    kakutei: { salaryOver: 20000000, otherIncomeOver: 200000 },
  };

  // ------------------------------------------------------------------
  // 2. ユーティリティ
  // ------------------------------------------------------------------
  const num = (v) => {
    if (v === null || v === undefined || v === '') return 0;
    if (typeof v === 'number') return isFinite(v) ? v : 0;
    const s = String(v).replace(/[０-９]/g, (c) => String.fromCharCode(c.charCodeAt(0) - 0xfee0))
      .replace(/[,，円\s]/g, '').replace(/[−ー－]/g, '-');
    const n = Number(s);
    return isFinite(n) ? n : 0;
  };
  const sum = (arr, f) => arr.reduce((a, x) => a + num(f ? f(x) : x), 0);
  const floorTo = (v, unit) => Math.floor(v / unit) * unit;
  const ceil = (v) => Math.ceil(v - 1e-9);
  const isSet = (v) => v !== null && v !== undefined && v !== '';

  /** 年末（12/31）時点の年齢。1月1日生まれは前日（12/31）に加齢する民法・年齢計算法の扱い。 */
  function ageAtYearEnd(birth, year) {
    if (!birth) return null;
    const m = String(birth).match(/^(\d{4})-(\d{1,2})-(\d{1,2})/);
    if (!m) return null;
    const y = +m[1], mo = +m[2], d = +m[3];
    return year - y + (mo === 1 && d === 1 ? 1 : 0);
  }

  function bracket(table, x) {
    for (const row of table) if (x <= row[0]) return row;
    return table[table.length - 1];
  }
  function piecewise(table, x) {
    if (x <= 0) return 0;
    const [, rate, add] = bracket(table, x);
    return ceil(rate === 0 ? add : x * rate + add); // 1円未満切上げ
  }

  // ------------------------------------------------------------------
  // 3. 個別計算
  // ------------------------------------------------------------------
  /** ⑨ 給与所得控除後の給与等の金額（計算シート M17 と同じ） */
  function salaryIncomeAfterDeduction(total, T = TABLES) {
    const s = T.salaryIncome;
    if (total > s.maxSalary) return null; // 対象外
    let x = total;
    if (x >= s.roundFrom && x <= s.roundTo) x = x - ((x - s.roundFrom) % s.roundUnit);
    if (x <= s.noIncomeUpTo) return 0;
    if (x <= 2190999) return x - s.minDeduction;
    for (const b of s.fixedBands) if (x <= b.upTo) return b.income;
    if (x <= 3599999) return Math.floor((x * 7) / 10) - 80000;
    if (x <= 6599999) return Math.floor((x * 8) / 10) - 440000;
    if (x <= 8499999) return Math.floor((x * 9) / 10) - 1100000;
    return x - 1950000;
  }

  function incomeAdjustment(total, applicable, T = TABLES) {
    const a = T.adjustment;
    if (!applicable || total <= a.threshold) return 0;
    return Math.min(ceil((Math.min(total, a.cap) - a.threshold) * a.rate), a.max);
  }

  function basicDeduction(totalIncome, T = TABLES) {
    return bracket(T.basic, totalIncome)[1];
  }

  function taxpayerBand(totalIncome, T = TABLES) {
    const b = T.spouseTaxpayerBands;
    if (totalIncome <= b[0]) return 0;
    if (totalIncome <= b[1]) return 1;
    if (totalIncome <= b[2]) return 2;
    return -1;
  }

  function spouseDeduction(taxpayerIncome, spouseIncome, spouseAge, T = TABLES) {
    const band = taxpayerBand(taxpayerIncome, T);
    if (band < 0) return { amount: 0, kind: '', band: '', reason: '本人の合計所得金額が1,000万円超のため適用なし' };
    const bandLabel = 'ABC'[band];
    if (spouseIncome > T.spouse[T.spouse.length - 1][0])
      return { amount: 0, kind: '', band: bandLabel, reason: '配偶者の合計所得金額が133万円超のため適用なし' };
    if (spouseIncome <= T.dependentIncomeLimit) {
      const elderly = spouseAge !== null && spouseAge >= 70;
      return {
        amount: (elderly ? T.spouseElderly : T.spouse[0][1])[band],
        kind: elderly ? '配偶者控除（老人控除対象配偶者）' : '配偶者控除', band: bandLabel,
        class2: elderly ? '①' : '②',
      };
    }
    let idx = 1;
    while (spouseIncome > T.spouse[idx][0]) idx++;
    return { amount: T.spouse[idx][1][band], kind: '配偶者特別控除', band: bandLabel, class2: idx === 1 ? '③' : '④' };
  }

  function tokuteiShinzokuDeduction(income, T = TABLES) {
    if (income <= T.dependentIncomeLimit || income > T.tokuteiShinzokuIncomeLimit) return 0;
    return bracket(T.tokuteiShinzoku, income)[1];
  }

  function incomeTax(taxable, T = TABLES) {
    const [, rate, sub] = bracket(T.taxRates, taxable);
    return Math.max(0, Math.round(taxable * rate - sub));
  }

  /** 生命保険料控除（⑮） */
  function lifeInsuranceDeduction(entries, hasUnder23Dependent, T = TABLES) {
    const L = T.life;
    const s = (kind, era) => sum(entries.filter((e) => e.kind === kind && (era ? e.era === era : true)), (e) => e.amount);
    const newGen = s('general', 'new'), oldGen = s('general', 'old');
    const care = s('care');
    const newPen = s('pension', 'new'), oldPen = s('pension', 'old');
    const g1 = hasUnder23Dependent ? piecewise(L.formulaII, newGen) : piecewise(L.formulaI, newGen);
    const g2 = piecewise(L.formulaIII, oldGen);
    const g3 = newGen > 0 && oldGen > 0 ? Math.min(g1 + g2, hasUnder23Dependent ? L.bothCapUnder23 : L.bothCap) : 0;
    const general = Math.max(g1, g2, g3);
    const p1 = piecewise(L.formulaI, newPen), p2 = piecewise(L.formulaIII, oldPen);
    const p3 = newPen > 0 && oldPen > 0 ? Math.min(p1 + p2, L.bothCap) : 0;
    const pension = Math.max(p1, p2, p3);
    const careDed = piecewise(L.formulaI, care);
    return {
      newGen, oldGen, care, newPen, oldPen,
      general, careDed, pension, g1, g2, g3, p1, p2, p3,
      total: Math.min(general + careDed + pension, L.totalCap),
      under23Rule: hasUnder23Dependent,
    };
  }

  /** 地震保険料控除（⑯） */
  function quakeDeduction(entries, T = TABLES) {
    const quakePaid = sum(entries.filter((e) => e.kind === 'quake'), (e) => e.amount);
    const oldLongPaid = sum(entries.filter((e) => e.kind === 'oldlong'), (e) => e.amount);
    const q = Math.min(quakePaid, T.quake.cap);
    const o = piecewise(T.quake.oldLong, oldLongPaid);
    return { quakePaid, oldLongPaid, quake: q, oldLong: o, total: Math.min(q + o, T.quake.cap) };
  }

  // ------------------------------------------------------------------
  // 4. 扶養控除等申告書の自動区分
  // ------------------------------------------------------------------
  const LINEAL_ASCENDANTS = ['父', '母', '祖父', '祖母', '義父', '義母', '曾祖父', '曾祖母', '養父', '養母'];

  function classifyDependent(d, T = TABLES) {
    const age = ageAtYearEnd(d.birth, T.year);
    const income = num(d.income);
    const out = { age, income, category: '対象外', deduction: 0, tokutei: 0, disability: 0, isFuyo: false, under23: false, notes: [] };
    if (age === null) { out.notes.push('生年月日が未入力です'); return out; }
    const lineal = d.lineal === true || (d.lineal !== false && LINEAL_ASCENDANTS.includes(String(d.relation || '').trim()));
    const nrExcluded = d.nonResident && age >= 30 && age < 70 && !d.nrReason;
    if (income <= T.dependentIncomeLimit) {
      out.isFuyo = true; // 扶養親族（障害者控除・所得金額調整控除・生保特例の判定に使う）
      out.under23 = age < 23;
      if (age < 16) out.category = '年少扶養親族';
      else if (nrExcluded) { out.category = '扶養親族（控除対象外）'; out.notes.push('30歳以上70歳未満の非居住者は留学・障害者・38万円以上の送金のいずれかが必要'); }
      else if (age >= 19 && age <= 22) { out.category = '特定扶養親族'; out.deduction = T.deductions.specific; }
      else if (age >= 70) {
        if (lineal && d.cohabit) { out.category = '同居老親等'; out.deduction = T.deductions.elderlyCohabit; }
        else { out.category = '老人扶養親族'; out.deduction = T.deductions.elderly; }
      } else { out.category = '一般の控除対象扶養親族'; out.deduction = T.deductions.general; }
      const dis = d.disability || 'none';
      if (dis === 'general') out.disability = T.deductions.disabled;
      else if (dis === 'special') out.disability = d.cohabit ? T.deductions.cohabitSpecialDisabled : T.deductions.specialDisabled;
      out.disabilityKind = dis === 'none' ? '' : dis === 'general' ? '一般の障害者' : d.cohabit ? '同居特別障害者' : '特別障害者';
    } else if (age >= 19 && age <= 22 && income <= T.tokuteiShinzokuIncomeLimit) {
      out.category = '特定親族';
      out.tokutei = tokuteiShinzokuDeduction(income, T);
      out.notes.push('特定親族特別控除申告書の提出が必要');
      if (d.disability && d.disability !== 'none') out.notes.push('合計所得62万円超のため障害者控除の対象外');
    } else {
      out.notes.push('所得要件を満たさないため控除対象外');
    }
    out.withholdingTarget = (out.deduction > 0) || (out.category === '特定親族' && income <= T.withholdingRelativeLimit);
    return out;
  }

  // ------------------------------------------------------------------
  // 5. メイン：1人分の年末調整
  // ------------------------------------------------------------------
  const LINE_LABELS = {
    r1: '① 給料・手当等 金額', r3: '③ 給料・手当等 税額', r4: '④ 賞与等 金額', r6: '⑥ 賞与等 税額',
    r7: '⑦ 金額 計', r8: '⑧ 税額 計', r9: '⑨ 給与所得控除後の給与等の金額', r10: '⑩ 所得金額調整控除額',
    r11: '⑪ 給与所得控除後の給与等の金額（調整控除後）', r12: '⑫ 社会保険料等控除額（給与等からの控除分）',
    r13: '⑬ 申告による社会保険料の控除分', r14: '⑭ 申告による小規模企業共済等掛金の控除分',
    r15: '⑮ 生命保険料の控除額', r16: '⑯ 地震保険料の控除額', r17: '⑰ 配偶者（特別）控除額',
    r18: '⑱ 特定親族特別控除額', r19: '⑲ 扶養控除額及び障害者等の控除額の合計額', r20: '⑳ 基礎控除額',
    r21: '㉑ 所得控除額の合計額', r22: '㉒ 差引課税給与所得金額', r23: '㉓ 算出所得税額',
    r24: '㉔ 住宅借入金等特別控除額', r25: '㉕ 年調所得税額', r26: '㉖ 年調年税額（㉕×102.1%）',
    r27: '㉗ 差引超過額又は不足額', r28: '㉘ 本年最後の給与から徴収する税額に充当する金額',
    r29: '㉙ 未払給与に係る未徴収の税額に充当する金額', r30: '㉚ 差引還付する税額',
    r31: '㉛ 本年中に還付する金額', r32: '㉜ 翌年において還付する金額',
    r33: '㉝ 本年最後の給与から徴収する金額', r34: '㉞ 翌年に繰り越して徴収する金額',
  };

  function calculate(emp, T = TABLES) {
    const ov = emp.overrides || {};
    const pick = (key, auto) => (isSet(ov[key]) ? num(ov[key]) : auto);
    const warnings = [];
    const P = emp.payroll || {};
    const salary = (P.salary || []).filter(Boolean);
    const bonus = (P.bonus || []).filter(Boolean);

    // --- 集計シート ---
    const agg = (rows) => ({
      gross: sum(rows, (r) => r.gross), social: sum(rows, (r) => r.social), smallBiz: sum(rows, (r) => r.smallBiz),
      tax: sum(rows, (r) => r.tax), adj: sum(rows, (r) => r.adj),
    });
    const S = agg(salary), B = agg(bonus);

    const L = {};
    L.r1 = pick('r1', S.gross); L.r3 = pick('r3', S.tax);
    L.r4 = pick('r4', B.gross); L.r6 = pick('r6', B.tax);
    L.r7 = L.r1 + L.r4; L.r8 = L.r3 + L.r6;
    const outOfScope = L.r7 > T.salaryIncome.maxSalary;
    if (outOfScope) warnings.push({ level: 'error', msg: '給与等の総額が2,000万円を超えるため年末調整の対象外です（本人が確定申告）。' });

    // --- 扶養控除等申告書 ---
    const F = emp.fuyo || {};
    const self = F.self || {};
    const deps = (F.dependents || []).filter((d) => d && (d.name || d.birth));
    const depResults = deps.map((d) => ({ input: d, ...classifyDependent(d, T) }));
    const hasUnder23Dependent = depResults.some((r) => r.isFuyo && r.under23);

    // --- 配偶者 ---
    const SP = emp.spouse || {};
    const hasSpouse = !!SP.has;
    const spouseIncome = num(SP.income);
    const spouseAge = hasSpouse ? ageAtYearEnd(SP.birth, T.year) : null;
    const sameLivelihoodSpouse = hasSpouse && spouseIncome <= T.dependentIncomeLimit;

    // --- 所得金額調整控除の判定 ---
    const anySpecial = (d) => d === 'special';
    const choseiAuto =
      anySpecial(self.disability) ||
      (sameLivelihoodSpouse && anySpecial(SP.disability)) ||
      depResults.some((r) => r.isFuyo && (anySpecial(r.input.disability) || r.under23));
    const choseiMode = (emp.chosei && emp.chosei.mode) || 'auto';
    const choseiApplicable = choseiMode === 'yes' ? true : choseiMode === 'no' ? false : choseiAuto;

    const r9 = salaryIncomeAfterDeduction(L.r7, T);
    L.r9 = pick('r9', r9 === null ? 0 : r9);
    L.r10 = pick('r10', incomeAdjustment(L.r7, choseiApplicable, T));
    L.r11 = pick('r11', Math.max(0, L.r9 - L.r10));

    // --- 本人の合計所得金額（基礎控除申告書） ---
    const otherIncome = num((emp.kiso || {}).otherIncome);
    const totalIncome = L.r11 + otherIncome;

    // --- 保険料控除申告書 ---
    const H = emp.hoken || {};
    const life = lifeInsuranceDeduction(H.life || [], hasUnder23Dependent, T);
    const quake = quakeDeduction(H.quake || [], T);
    const socialDeclared = sum(H.social || [], (e) => e.amount);
    const nationalPension = sum((H.social || []).filter((e) => e.nationalPension), (e) => e.amount);
    const smallBizDeclared = sum(H.smallBiz || [], (e) => e.amount);

    L.r12 = pick('r12', S.social + B.social);
    L.r13 = pick('r13', socialDeclared);
    L.r14 = pick('r14', smallBizDeclared);
    L.r15 = pick('r15', life.total);
    L.r16 = pick('r16', quake.total);

    const sp = hasSpouse ? spouseDeduction(totalIncome, spouseIncome, spouseAge, T) : { amount: 0, kind: '', band: '' };
    L.r17 = pick('r17', sp.amount);
    L.r18 = pick('r18', sum(depResults, (r) => r.tokutei));

    // --- ⑲ 扶養控除・障害者等（計算シート Ⓐ〜Ⓘ） ---
    const cnt = (cat) => depResults.filter((r) => r.category === cat).length;
    const fuyoBox = { A: cnt('一般の控除対象扶養親族'), B: cnt('特定扶養親族'), C: cnt('同居老親等'), D: cnt('老人扶養親族'), E: 0, F: 0, G: 0, H: '', I: '' };
    const addDis = (kind) => { if (kind === '一般の障害者') fuyoBox.E++; else if (kind === '特別障害者') fuyoBox.F++; else if (kind === '同居特別障害者') fuyoBox.G++; };
    if (self.disability === 'general') fuyoBox.E++;
    if (self.disability === 'special') fuyoBox.F++;
    if (sameLivelihoodSpouse && SP.disability && SP.disability !== 'none')
      addDis(SP.disability === 'general' ? '一般の障害者' : SP.cohabit !== false ? '同居特別障害者' : '特別障害者');
    depResults.forEach((r) => r.isFuyo && r.disabilityKind && addDis(r.disabilityKind));
    if (self.widow === 'widow') fuyoBox.H = '寡婦';
    if (self.widow === 'single_parent') fuyoBox.H = 'ひとり親';
    if (self.student) fuyoBox.I = '該当';
    const D = T.deductions;
    const fuyoAmounts = {
      A: fuyoBox.A * D.general, B: fuyoBox.B * D.specific, C: fuyoBox.C * D.elderlyCohabit, D: fuyoBox.D * D.elderly,
      E: fuyoBox.E * D.disabled, F: fuyoBox.F * D.specialDisabled, G: fuyoBox.G * D.cohabitSpecialDisabled,
      H: fuyoBox.H === '寡婦' ? D.widow : fuyoBox.H === 'ひとり親' ? D.singleParent : 0,
      I: fuyoBox.I ? D.workingStudent : 0,
    };
    L.r19 = pick('r19', Object.values(fuyoAmounts).reduce((a, b) => a + b, 0));
    L.r20 = pick('r20', basicDeduction(totalIncome, T));
    L.r21 = L.r12 + L.r13 + L.r14 + L.r15 + L.r16 + L.r17 + L.r18 + L.r19 + L.r20;
    L.r22 = pick('r22', L.r11 < L.r21 ? 0 : floorTo(L.r11 - L.r21, 1000));
    L.r23 = pick('r23', incomeTax(L.r22, T));

    // --- 住宅借入金等特別控除 ---
    const J = emp.jutaku || {};
    let housing = 0;
    if (isSet(J.direct)) housing = num(J.direct);
    else if (num(J.balance) > 0) housing = Math.min(num(J.balance) * (num(J.rate) || 0.007), num(J.limit) || Infinity);
    housing = Math.min(floorTo(housing, 100), T.housingLoanMax);
    L.r24 = pick('r24', housing);
    L.r25 = pick('r25', Math.max(0, L.r23 - L.r24));
    L.r26 = pick('r26', floorTo(L.r25 * T.reconstructionRate + 1e-9, 100));

    const diff = L.r26 - L.r8;
    const status = diff === 0 ? 'none' : diff < 0 ? 'refund' : 'shortage';
    L.r27 = Math.abs(diff);
    const st = emp.settle || {};
    L.r28 = status === 'refund' ? num(st.r28) : 0;
    L.r29 = status === 'refund' ? num(st.r29) : 0;
    L.r30 = status === 'refund' ? Math.max(0, L.r27 - L.r28 - L.r29) : 0;
    L.r31 = status === 'refund' ? (isSet(st.r31) ? num(st.r31) : L.r30) : 0;
    L.r32 = status === 'refund' ? L.r30 - L.r31 : 0;
    L.r33 = status === 'shortage' ? (isSet(st.r33) ? num(st.r33) : L.r27) : 0;
    L.r34 = status === 'shortage' ? L.r27 - L.r33 : 0;

    // --- チェック（計算シートのエラーメッセージ相当 + 追加） ---
    if (hasSpouse && !isSet(SP.income)) warnings.push({ level: 'error', msg: '「配偶者の合計所得金額」を入力してください。' });
    if (isSet(ov.r17) && hasSpouse && num(ov.r17) !== sp.amount)
      warnings.push({ level: 'error', msg: '「配偶者の合計所得金額」と「配偶者（特別）控除額（⑰欄）」の金額が対応していません。受理した配偶者控除等申告書の内容を確認してください。' });
    if (self.widow && self.widow !== 'none' && totalIncome > T.widowIncomeLimit)
      warnings.push({ level: 'warn', msg: '寡婦・ひとり親は合計所得金額500万円以下が要件です。' });
    if (self.student && totalIncome > T.workingStudentIncomeLimit)
      warnings.push({ level: 'warn', msg: '勤労学生は合計所得金額89万円以下（令和8年分）が要件です。' });
    if (L.r24 > L.r23) warnings.push({ level: 'info', msg: '住宅借入金等特別控除額が算出所得税額を超えています（控除しきれない額は翌年度の住民税で控除される場合があります）。' });
    if (L.r31 > L.r30) warnings.push({ level: 'error', msg: '㉛ 本年中に還付する金額が ㉚ 差引還付する税額を超えています。' });
    if (L.r33 > L.r27 && status === 'shortage') warnings.push({ level: 'error', msg: '㉝ が ㉗ 不足額を超えています。' });
    const months = salary.filter((r) => num(r.gross) > 0).length;
    if (months > 0 && months < 12) warnings.push({ level: 'info', msg: `給与の入力が${months}ヶ月分です。12月分（年末調整を行う月）までの見込額を入力してください。` });
    depResults.forEach((r) => r.notes.forEach((n) => warnings.push({ level: 'info', msg: `${r.input.name || '扶養親族'}：${n}` })));

    // --- 源泉徴収 扶養親族等の数（参考） ---
    let withholdingCount = depResults.filter((r) => r.withholdingTarget).length;
    if (hasSpouse && spouseIncome <= T.withholdingSpouseLimit && totalIncome <= T.spouseTaxpayerBands[0]) withholdingCount++;
    if (self.disability && self.disability !== 'none') withholdingCount++;
    if (self.widow && self.widow !== 'none') withholdingCount++;
    if (self.student) withholdingCount++;
    withholdingCount += fuyoBox.E + fuyoBox.F + fuyoBox.G * 2 - (self.disability && self.disability !== 'none' ? 1 : 0);

    // --- 確定申告の要否 ---
    const K = emp.kakutei || {};
    const kakutei = [];
    if (L.r7 > T.kakutei.salaryOver) kakutei.push({ need: true, msg: '給与の収入金額が2,000万円を超える' });
    if (otherIncome > T.kakutei.otherIncomeOver) kakutei.push({ need: true, msg: '給与所得・退職所得以外の所得が20万円を超える' });
    if (K.multipleEmployers) kakutei.push({ need: true, msg: '2か所以上から給与を受けている（年末調整されなかった給与＋他の所得が20万円超の場合）' });
    if (K.medical) kakutei.push({ need: false, msg: '医療費控除・セルフメディケーション税制は年末調整では控除できない（還付申告）' });
    if (K.donation) kakutei.push({ need: false, msg: '寄附金控除（ワンストップ特例を使わないふるさと納税等）は確定申告で控除' });
    if (K.housingFirstYear) kakutei.push({ need: false, msg: '住宅借入金等特別控除の初年度は確定申告が必要' });
    if (K.casualty) kakutei.push({ need: false, msg: '雑損控除は確定申告で控除' });
    if (outOfScope) kakutei.push({ need: true, msg: '年末調整の対象外' });

    return {
      year: T.year, outOfScope, lines: L, labels: LINE_LABELS, status,
      statusLabel: status === 'refund' ? '差引超過額' : status === 'shortage' ? '差引不足額' : '差引超過額又は不足額',
      aggregate: { salary: S, bonus: B },
      totalIncome, otherIncome, choseiAuto, choseiApplicable,
      fuyo: { box: fuyoBox, amounts: fuyoAmounts, dependents: depResults },
      spouse: { ...sp, age: spouseAge, income: hasSpouse ? spouseIncome : null, sameLivelihood: sameLivelihoodSpouse },
      hasUnder23Dependent, life, quake, socialDeclared, nationalPension, smallBizDeclared,
      smallBizFromPayroll: S.smallBiz + B.smallBiz, housing,
      withholdingCount, kakutei, kakuteiRequired: kakutei.some((k) => k.need), warnings,
      yearEndAdjustment: status === 'refund' ? -L.r27 : L.r27,
    };
  }

  // ------------------------------------------------------------------
  // 6. 新規従業員のひな形
  // ------------------------------------------------------------------
  function blankEmployee(name) {
    return {
      id: 'e' + Date.now().toString(36) + Math.random().toString(36).slice(2, 6),
      profile: { name: name || '', kana: '', birth: '', address: '', employer: '', employerAddress: '', corpNo: '', note: '' },
      payroll: {
        salary: Array.from({ length: 12 }, (_, i) => ({ month: i + 1, payDate: '', gross: '', social: '', smallBiz: '', depCount: '', tax: '', adj: '' })),
        bonus: Array.from({ length: 4 }, () => ({ payDate: '', gross: '', social: '', smallBiz: '', depCount: '', tax: '', adj: '' })),
      },
      fuyo: { self: { disability: 'none', widow: 'none', student: false }, dependents: [] },
      kiso: { otherIncome: '' },
      spouse: { has: false, name: '', kana: '', birth: '', income: '', nonResident: false, disability: 'none', cohabit: true },
      chosei: { mode: 'auto' },
      hoken: { life: [], quake: [], social: [], smallBiz: [] },
      jutaku: { balance: '', rate: 0.007, limit: '', direct: '' },
      settle: { r28: '', r29: '', r31: '', r33: '' },
      kakutei: { multipleEmployers: false, medical: false, donation: false, housingFirstYear: false, casualty: false },
      overrides: {},
      updatedAt: new Date().toISOString(),
    };
  }

  return {
    TABLES, LINE_LABELS, calculate, blankEmployee, classifyDependent, ageAtYearEnd,
    salaryIncomeAfterDeduction, incomeAdjustment, basicDeduction, spouseDeduction,
    tokuteiShinzokuDeduction, incomeTax, lifeInsuranceDeduction, quakeDeduction, num,
  };
});
