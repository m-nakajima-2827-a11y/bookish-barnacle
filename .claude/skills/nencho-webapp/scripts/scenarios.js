// テスト用の従業員データ（実在の人物ではありません）
const path = require('path');
const N = require(path.join(__dirname, '../assets/app/js/engine.js'));

// 元Excel（keisansheet.xlsm）の集計シートに入っていたサンプル値
const SAMPLE_GROSS = [263129, 311123, 257125, 309071, 301413, 334686, 279125, 338823, 319518, 281114, 281114, 281114];
const SAMPLE_SOCIAL = [18021, 19885, 18208, 19205, 19379, 22825, 20557, 42506, 21409, 21783, 21783, 21783];

function withPayroll(e, gross, social, tax, opts = {}) {
  e.payroll.salary.forEach((r, i) => {
    r.payDate = `2026-${String(i + 1).padStart(2, '0')}-25`;
    r.gross = gross[i]; r.social = social[i]; r.tax = tax[i]; r.depCount = opts.depCount ?? 1;
    r.smallBiz = opts.smallBiz ? opts.smallBiz[i] : '';
  });
  return e;
}

function scenarios() {
  const list = [];

  // 1) 元Excelのサンプル給与＋配偶者特別控除＋特定親族＋生命保険（23歳未満特例）
  let e = withPayroll(N.blankEmployee('サンプル 太郎'), SAMPLE_GROSS, SAMPLE_SOCIAL, Array(12).fill(5200));
  e.profile.kana = 'サンプル タロウ';
  e.spouse = { has: true, name: '花子', birth: '1985-03-03', income: 1000000, disability: 'none', cohabit: true };
  e.fuyo.dependents = [
    { name: '一郎', relation: '子', birth: '2008-04-01', income: 0, cohabit: true, disability: 'none' },
    { name: '二郎', relation: '子', birth: '2005-05-01', income: 900000, cohabit: true, disability: 'none' },
    { name: '三子', relation: '子', birth: '2015-07-07', income: 0, cohabit: true, disability: 'general' },
  ];
  e.hoken.life = [
    { company: 'A生命', kind: 'general', era: 'new', amount: 100000 },
    { company: 'B生命', kind: 'general', era: 'old', amount: 30000 },
    { company: 'C生命', kind: 'care', era: 'new', amount: 50000 },
    { company: 'D生命', kind: 'pension', era: 'old', amount: 120000 },
  ];
  e.hoken.quake = [{ company: 'E損保', kind: 'quake', amount: 30000 }, { company: 'F損保', kind: 'oldlong', amount: 15000 }];
  list.push({ name: 'excel-sample', emp: e });

  // 2) 高所得：所得金額調整控除・配偶者控除なし・住宅ローン・賞与・申告社保（国民年金）
  e = withPayroll(N.blankEmployee('高所得 次郎'), Array(12).fill(700000), Array(12).fill(98000), Array(12).fill(45000), { smallBiz: Array(12).fill(10000) });
  e.payroll.bonus[0] = { payDate: '2026-06-30', gross: 1200000, social: 170000, tax: 120000, smallBiz: '' };
  e.payroll.bonus[1] = { payDate: '2026-12-10', gross: 1300000, social: 180000, tax: 130000, smallBiz: '' };
  e.spouse = { has: true, birth: '1980-01-01', income: 0, disability: 'none', cohabit: true };
  e.fuyo.dependents = [{ name: '長女', relation: '子', birth: '2012-02-02', income: 0, cohabit: true, disability: 'none' }];
  e.hoken.social = [{ kind: '国民年金', payer: '日本年金機構', person: '妻', amount: 210000, nationalPension: true }];
  e.hoken.smallBiz = [{ kind: '個人型確定拠出年金', amount: 144000 }];
  e.jutaku = { balance: 25000000, rate: 0.007, limit: '', direct: '' };
  list.push({ name: 'high-income', emp: e });

  // 3) 低所得・同居老親・特別障害者・ひとり親・勤労学生なし・不足額
  e = withPayroll(N.blankEmployee('同居 花子'), Array(12).fill(180000), Array(12).fill(26000), Array(12).fill(100));
  e.fuyo.self = { disability: 'none', widow: 'single_parent', student: false };
  e.fuyo.dependents = [
    { name: '母', relation: '母', birth: '1950-08-08', income: 400000, cohabit: true, disability: 'special' },
    { name: '長男', relation: '子', birth: '2010-10-10', income: 0, cohabit: true, disability: 'none' },
  ];
  list.push({ name: 'low-income', emp: e });

  // 4) 年の途中まで・不足額（扶養なし、源泉不足）
  e = withPayroll(N.blankEmployee('不足 三郎'), Array(12).fill(450000), Array(12).fill(65000), Array(12).fill(8000));
  e.kiso.otherIncome = 300000;
  e.kakutei.medical = true;
  list.push({ name: 'shortage', emp: e });

  return list;
}

module.exports = { scenarios, SAMPLE_GROSS, SAMPLE_SOCIAL };
