/*
 * Excel 出力（ExcelJS）
 *
 * 国税庁「年末調整計算シート（令和８年用）」のシート構成・セル番地を踏襲し、
 *   集計シート → 計算シート ①③④⑥⑫
 *   各申告書シート → 計算シート Ⓐ〜Ⓘ・⑬〜⑳・㉔・所得金額調整控除の有無・配偶者の合計所得金額
 * がすべて関数でつながったブックを作る。シート保護はかけない（全セル編集可）。
 * 入力セルは黄色、関数セルは白。WEBアプリで手入力（上書き）した欄は値で出力し橙色にする。
 *
 * ブラウザ: window.NenchoWorkbook.build(ExcelJS, employee, result)
 * Node    : require('./workbook.js').build(require('exceljs'), employee, result)
 */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else root.NenchoWorkbook = factory();
})(typeof self !== 'undefined' ? self : this, function () {
  'use strict';

  const T = "'控除テーブル'!";
  const SH = {
    calc: '計算シート', agg: '集計シート', fuyo: '扶養申告書', kiso: '基礎申告書', spouse: '配偶者申告書',
    tokutei: '特定親族申告書', chosei: '所得金額調整申告書', hoken: '保険申告書', jutaku: '住借申告書',
    boki: '源泉徴収簿', table: '控除テーブル', kakutei: '確定申告チェック', ref: '各種申告書・参考情報',
  };
  const R = (sheet, addr) => `'${sheet}'!${addr}`;

  const FILL_INPUT = { type: 'pattern', pattern: 'solid', fgColor: { argb: 'FFFFF2CC' } };
  const FILL_HEAD = { type: 'pattern', pattern: 'solid', fgColor: { argb: 'FFDDEBF7' } };
  const FILL_OVERRIDE = { type: 'pattern', pattern: 'solid', fgColor: { argb: 'FFF8CBAD' } };
  const FILL_TOTAL = { type: 'pattern', pattern: 'solid', fgColor: { argb: 'FFE2EFDA' } };
  const BORDER = { top: { style: 'thin', color: { argb: 'FFBFBFBF' } }, left: { style: 'thin', color: { argb: 'FFBFBFBF' } }, bottom: { style: 'thin', color: { argb: 'FFBFBFBF' } }, right: { style: 'thin', color: { argb: 'FFBFBFBF' } } };
  const YEN = '#,##0;[Red]-#,##0';

  const toDate = (s) => {
    const m = String(s || '').match(/^(\d{4})-(\d{2})-(\d{2})/);
    return m ? new Date(Date.UTC(+m[1], +m[2] - 1, +m[3])) : null;
  };
  const numOrBlank = (v) => (v === '' || v === null || v === undefined ? null : Number(String(v).replace(/[,円\s]/g, '')) || 0);

  function build(ExcelJS, emp, result) {
    const wb = new ExcelJS.Workbook();
    wb.creator = '年末調整WEBアプリ';
    wb.created = new Date();
    wb.calcProperties = { fullCalcOnLoad: true };
    const L = (result && result.lines) || {};
    const ov = emp.overrides || {};

    const ws = {};
    [SH.calc, SH.agg, SH.fuyo, SH.kiso, SH.spouse, SH.tokutei, SH.chosei, SH.hoken, SH.jutaku, SH.boki, SH.table, SH.kakutei, SH.ref]
      .forEach((n) => { ws[n] = wb.addWorksheet(n, { views: [{ showGridLines: true }] }); });

    // ---- helpers ----
    const put = (sheet, addr, value, opt = {}) => {
      const c = ws[sheet].getCell(addr);
      if (typeof value === 'string' && value.startsWith('=')) c.value = { formula: value.slice(1), result: opt.result };
      else if (value !== undefined) c.value = value;
      if (opt.input) c.fill = FILL_INPUT;
      if (opt.head) { c.fill = FILL_HEAD; c.font = { bold: true }; c.alignment = { wrapText: true, vertical: 'middle' }; }
      if (opt.total) c.fill = FILL_TOTAL;
      if (opt.title) c.font = { bold: true, size: 14 };
      if (opt.yen) c.numFmt = YEN;
      if (opt.date) c.numFmt = 'yyyy/mm/dd';
      if (opt.pct) c.numFmt = '0.0%';
      if (opt.border !== false && !opt.title) c.border = BORDER;
      if (opt.list) ws[sheet].dataValidations.add(addr, { type: 'list', allowBlank: true, formulae: ['"' + opt.list.join(',') + '"'] });
      if (opt.wrap) c.alignment = { wrapText: true, vertical: 'top' };
      return c;
    };
    // 計算シートの自動計算欄：WEBアプリで上書きされていれば値を出力
    const auto = (sheet, addr, formula, key, opt = {}) => {
      if (key && ov[key] !== undefined && ov[key] !== null && ov[key] !== '') {
        const c = put(sheet, addr, Number(ov[key]), { yen: true, ...opt });
        c.fill = FILL_OVERRIDE;
        c.note = 'WEBアプリで手入力（上書き）された値です。自動計算に戻す場合は関数を入れ直してください。';
        return c;
      }
      return put(sheet, addr, formula, { yen: true, result: key ? L[key] : undefined, ...opt });
    };
    const widths = (sheet, arr) => arr.forEach((w, i) => { ws[sheet].getColumn(i + 1).width = w; });

    // =====================================================================
    // 控除テーブル（法改正時はこのシートの数値を更新すれば全シートに反映）
    // =====================================================================
    const t = SH.table;
    widths(t, [30, 14, 3, 16, 14, 3, 16, 12, 12, 12, 3, 16, 14, 3, 14, 8, 12]);
    put(t, 'A1', '控除テーブル（令和8年分）', { title: true });
    put(t, 'A2', '出典：国税庁「令和8年分 年末調整のしかた」55〜56ページ、タックスアンサーNo.1410', { border: false });
    [['対象年', 2026], ['扶養親族等の所得要件（以下）', 620000], ['特定親族の所得上限（以下）', 1230000],
      ['源泉控除対象親族（特定親族）上限', 1000000], ['勤労学生の所得上限', 890000], ['寡婦・ひとり親の所得上限', 5000000]]
      .forEach(([k, v], i) => { put(t, 'A' + (3 + i), k); put(t, 'B' + (3 + i), v, { input: true, yen: i > 0 }); });
    put(t, 'A10', '控除額', { head: true }); put(t, 'B10', '金額', { head: true });
    [['一般の控除対象扶養親族', 380000], ['特定扶養親族', 630000], ['同居老親等', 580000], ['同居老親等以外の老人扶養親族', 480000],
      ['一般の障害者', 270000], ['特別障害者', 400000], ['同居特別障害者', 750000], ['寡婦', 270000], ['ひとり親', 350000], ['勤労学生', 270000]]
      .forEach(([k, v], i) => { put(t, 'A' + (11 + i), k); put(t, 'B' + (11 + i), v, { input: true, yen: true }); });

    put(t, 'D3', '基礎控除', { head: true }); put(t, 'E3', '', { head: true });
    put(t, 'D4', '合計所得（以上）', { head: true }); put(t, 'E4', '控除額', { head: true });
    [[0, 1040000], [4890001, 670000], [6550001, 620000], [23500001, 480000], [24000001, 320000], [24500001, 160000], [25000001, 0]]
      .forEach(([a, b], i) => { put(t, 'D' + (5 + i), a, { input: true, yen: true }); put(t, 'E' + (5 + i), b, { input: true, yen: true }); });

    put(t, 'G3', '配偶者（特別）控除', { head: true });
    ['配偶者の所得（以上）', 'A 900万以下', 'B 950万以下', 'C 1,000万以下'].forEach((h, i) => put(t, 'GHIJ'[i] + '4', h, { head: true }));
    [[0, 380000, 260000, 130000], [620001, 380000, 260000, 130000], [950001, 360000, 240000, 120000], [1000001, 310000, 210000, 110000],
      [1050001, 260000, 180000, 90000], [1100001, 210000, 140000, 70000], [1150001, 160000, 110000, 60000], [1200001, 110000, 80000, 40000],
      [1250001, 60000, 40000, 20000], [1300001, 30000, 20000, 10000], [1330001, 0, 0, 0]]
      .forEach((row, i) => row.forEach((v, j) => put(t, 'GHIJ'[j] + (5 + i), v, { input: true, yen: true })));
    put(t, 'G17', '老人控除対象配偶者', { head: true });
    [480000, 320000, 160000].forEach((v, j) => put(t, 'HIJ'[j] + '17', v, { input: true, yen: true }));

    put(t, 'L3', '特定親族特別控除', { head: true }); put(t, 'M3', '', { head: true });
    put(t, 'L4', '特定親族の所得（以上）', { head: true }); put(t, 'M4', '控除額', { head: true });
    [[0, 0], [620001, 630000], [850001, 610000], [900001, 510000], [950001, 410000], [1000001, 310000], [1050001, 210000],
      [1100001, 110000], [1150001, 60000], [1200001, 30000], [1230001, 0]]
      .forEach(([a, b], i) => { put(t, 'L' + (5 + i), a, { input: true, yen: true }); put(t, 'M' + (5 + i), b, { input: true, yen: true }); });

    put(t, 'O3', '算出所得税額の速算表（参考）', { head: true });
    ['課税所得（以上）', '税率', '控除額'].forEach((h, i) => put(t, 'OPQ'[i] + '4', h, { head: true }));
    [[0, 0.05, 0], [1950001, 0.1, 97500], [3300001, 0.2, 427500], [6950001, 0.23, 636000], [9000001, 0.33, 1536000], [18000001, 0.4, 2796000]]
      .forEach(([a, r, d], i) => { put(t, 'O' + (5 + i), a, { yen: true }); put(t, 'P' + (5 + i), r, { pct: true }); put(t, 'Q' + (5 + i), d, { yen: true }); });

    // =====================================================================
    // 集計シート（元ファイルと同じ番地。L列「うち小規模企業共済等掛金」を追加）
    // =====================================================================
    const a = SH.agg;
    widths(a, [2, 10, 8, 12, 14, 14, 16, 10, 12, 14, 12, 14]);
    put(a, 'B1', '集計シート', { title: true });
    ['区分', '月区分', '支給月日', '総支給金額', '社会保険料等の控除額', '社会保険料等控除後の給与等の金額', '扶養親族等の数',
      '算出税額', '年末調整による過不足税額', '差引徴収税額', 'うち小規模企業共済等掛金']
      .forEach((h, i) => put(a, String.fromCharCode(66 + i) + '2', h, { head: true }));
    ws[a].getRow(2).height = 45;
    const sal = (emp.payroll && emp.payroll.salary) || [];
    for (let i = 0; i < 12; i++) {
      const r = 3 + i, s = sal[i] || {};
      if (i === 0) put(a, 'B3', '給料・手当等');
      put(a, 'C' + r, i + 1);
      put(a, 'D' + r, toDate(s.payDate), { input: true, date: true });
      put(a, 'E' + r, numOrBlank(s.gross), { input: true, yen: true });
      put(a, 'F' + r, numOrBlank(s.social), { input: true, yen: true });
      put(a, 'G' + r, `=E${r}-F${r}`, { yen: true });
      put(a, 'H' + r, numOrBlank(s.depCount), { input: true });
      put(a, 'I' + r, numOrBlank(s.tax), { input: true, yen: true });
      put(a, 'J' + r, numOrBlank(s.adj), { input: true, yen: true });
      put(a, 'K' + r, `=I${r}+J${r}`, { yen: true });
      put(a, 'L' + r, numOrBlank(s.smallBiz), { input: true, yen: true });
    }
    put(a, 'C15', '計', { total: true });
    'EFGIJKL'.split('').forEach((col) => put(a, col + '15', `=SUM(${col}3:${col}14)`, { yen: true, total: true }));
    const bon = (emp.payroll && emp.payroll.bonus) || [];
    for (let i = 0; i < 4; i++) {
      const r = 16 + i, s = bon[i] || {};
      if (i === 0) put(a, 'B16', '賞与等');
      put(a, 'C' + r, `=IF(D${r}<>"",MONTH(D${r}),"")`);
      put(a, 'D' + r, toDate(s.payDate), { input: true, date: true });
      put(a, 'E' + r, numOrBlank(s.gross), { input: true, yen: true });
      put(a, 'F' + r, numOrBlank(s.social), { input: true, yen: true });
      put(a, 'G' + r, `=E${r}-F${r}`, { yen: true });
      put(a, 'H' + r, numOrBlank(s.depCount), { input: true });
      put(a, 'I' + r, numOrBlank(s.tax), { input: true, yen: true });
      put(a, 'J' + r, numOrBlank(s.adj), { input: true, yen: true });
      put(a, 'K' + r, `=I${r}+J${r}`, { yen: true });
      put(a, 'L' + r, numOrBlank(s.smallBiz), { input: true, yen: true });
    }
    put(a, 'C20', '計', { total: true });
    'EFGIJKL'.split('').forEach((col) => put(a, col + '20', `=SUM(${col}16:${col}19)`, { yen: true, total: true }));
    put(a, 'B22', '※ 黄色セルに入力。E15→計算シート①、I15→③、E20→④、I20→⑥、F15+F20→⑫、L列→「⑫のうち小規模企業共済等掛金の金額」に自動反映。', { border: false });
    put(a, 'B23', '※ 年末調整による過不足税額（J列）は、超過額はマイナス、不足額はプラスで入力（年末調整を行う月の行）。', { border: false });

    // =====================================================================
    // 扶養申告書
    // =====================================================================
    const f = SH.fuyo, F = emp.fuyo || {}, self = F.self || {}, SP = emp.spouse || {};
    widths(f, [2, 26, 10, 12, 9, 7, 14, 9, 16, 16, 9, 24, 13, 13, 13, 9, 9]);
    put(f, 'B1', '令和8年分 給与所得者の扶養控除等（異動）申告書（入力・自動判定）', { title: true });
    const disLabel = (d) => (d === 'general' ? '一般の障害者' : d === 'special' ? '特別障害者' : 'なし');
    put(f, 'B3', '本人の障害者区分'); put(f, 'C3', disLabel(self.disability), { input: true, list: ['なし', '一般の障害者', '特別障害者'] });
    put(f, 'B4', '寡婦・ひとり親'); put(f, 'C4', self.widow === 'widow' ? '寡婦' : self.widow === 'single_parent' ? 'ひとり親' : 'なし', { input: true, list: ['なし', '寡婦', 'ひとり親'] });
    put(f, 'B5', '勤労学生'); put(f, 'C5', self.student ? '該当' : 'なし', { input: true, list: ['なし', '該当'] });
    const spDis = SP.disability === 'general' ? '一般の障害者' : SP.disability === 'special' ? (SP.cohabit === false ? '特別障害者' : '同居特別障害者') : 'なし';
    put(f, 'B6', '同一生計配偶者の障害者区分'); put(f, 'C6', spDis, { input: true, list: ['なし', '一般の障害者', '特別障害者', '同居特別障害者'] });
    put(f, 'B7', '同一生計配偶者に該当（自動）'); put(f, 'C7', `=IF(AND(${R(SH.spouse, 'C3')}="あり",N(${R(SH.spouse, 'C7')})<=${T}$B$4),"該当","")`);
    const heads = ['氏名', '続柄', '生年月日', '直系尊属', '同居', '合計所得金額の見積額', '非居住者', '非居住者の要件（30〜69歳）', '障害者区分',
      '年末年齢', '区分（自動判定）', '扶養控除額', '特定親族特別控除額', '障害者控除額', '23歳未満の扶養親族', '源泉控除対象'];
    heads.forEach((h, i) => put(f, String.fromCharCode(66 + i) + '9', h, { head: true }));
    ws[f].getRow(9).height = 45;
    const deps = (F.dependents || []).slice(0, 10);
    const LINEAL = ['父', '母', '祖父', '祖母', '義父', '義母', '曾祖父', '曾祖母', '養父', '養母'];
    for (let i = 0; i < 10; i++) {
      const r = 10 + i, d = deps[i] || {};
      const has = !!(d.name || d.birth);
      const lineal = has ? (d.lineal === true || (d.lineal !== false && LINEAL.includes(String(d.relation || '').trim())) ? 'はい' : 'いいえ') : null;
      put(f, 'B' + r, d.name || null, { input: true });
      put(f, 'C' + r, d.relation || null, { input: true });
      put(f, 'D' + r, toDate(d.birth), { input: true, date: true });
      put(f, 'E' + r, lineal, { input: true, list: ['はい', 'いいえ'] });
      put(f, 'F' + r, has ? (d.cohabit ? 'はい' : 'いいえ') : null, { input: true, list: ['はい', 'いいえ'] });
      put(f, 'G' + r, has ? numOrBlank(d.income) || 0 : null, { input: true, yen: true });
      put(f, 'H' + r, has ? (d.nonResident ? 'はい' : 'いいえ') : null, { input: true, list: ['はい', 'いいえ'] });
      put(f, 'I' + r, has ? d.nrReason || 'なし' : null, { input: true, list: ['なし', '留学', '障害者', '38万円以上の送金'] });
      put(f, 'J' + r, has ? (d.disability === 'general' ? '一般の障害者' : d.disability === 'special' ? (d.cohabit ? '同居特別障害者' : '特別障害者') : 'なし') : null,
        { input: true, list: ['なし', '一般の障害者', '特別障害者', '同居特別障害者'] });
      put(f, 'K' + r, `=IF(D${r}="","",${T}$B$3-YEAR(D${r})+IF(AND(MONTH(D${r})=1,DAY(D${r})=1),1,0))`);
      put(f, 'L' + r, `=IF(K${r}="","",IF(N(G${r})<=${T}$B$4,IF(K${r}<16,"年少扶養親族",IF(AND(H${r}="はい",K${r}>=30,K${r}<70,OR(I${r}="",I${r}="なし")),"扶養親族（控除対象外）",IF(AND(K${r}>=19,K${r}<=22),"特定扶養親族",IF(K${r}>=70,IF(AND(E${r}="はい",F${r}="はい"),"同居老親等","老人扶養親族"),"一般の控除対象扶養親族")))),IF(AND(K${r}>=19,K${r}<=22,N(G${r})<=${T}$B$5),"特定親族","対象外")))`);
      put(f, 'M' + r, `=IF(L${r}="一般の控除対象扶養親族",${T}$B$11,IF(L${r}="特定扶養親族",${T}$B$12,IF(L${r}="同居老親等",${T}$B$13,IF(L${r}="老人扶養親族",${T}$B$14,0))))`, { yen: true });
      put(f, 'N' + r, `=IF(L${r}="特定親族",VLOOKUP(N(G${r}),${T}$L$5:$M$15,2,TRUE),0)`, { yen: true });
      put(f, 'O' + r, `=IF(AND(K${r}<>"",N(G${r})<=${T}$B$4),IF(J${r}="一般の障害者",${T}$B$15,IF(J${r}="特別障害者",${T}$B$16,IF(J${r}="同居特別障害者",${T}$B$17,0))),0)`, { yen: true });
      put(f, 'P' + r, `=IF(K${r}="",0,IF(AND(N(G${r})<=${T}$B$4,K${r}<23),1,0))`);
      put(f, 'Q' + r, `=IF(OR(M${r}>0,AND(L${r}="特定親族",N(G${r})<=${T}$B$6)),1,0)`);
    }
    const box = [
      ['Ⓐ 一般の控除対象扶養親族（人）', '=COUNTIF(L10:L19,"一般の控除対象扶養親族")'],
      ['Ⓑ 特定扶養親族（人）', '=COUNTIF(L10:L19,"特定扶養親族")'],
      ['Ⓒ 同居老親等（人）', '=COUNTIF(L10:L19,"同居老親等")'],
      ['Ⓓ 同居老親等以外の老人扶養親族（人）', '=COUNTIF(L10:L19,"老人扶養親族")'],
      ['Ⓔ 一般の障害者（人）', '=COUNTIFS(J10:J19,"一般の障害者",O10:O19,">0")+(C3="一般の障害者")*1+AND(C7="該当",C6="一般の障害者")*1'],
      ['Ⓕ 同居特別障害者以外の特別障害者（人）', '=COUNTIFS(J10:J19,"特別障害者",O10:O19,">0")+(C3="特別障害者")*1+AND(C7="該当",C6="特別障害者")*1'],
      ['Ⓖ 同居特別障害者（人）', '=COUNTIFS(J10:J19,"同居特別障害者",O10:O19,">0")+AND(C7="該当",C6="同居特別障害者")*1'],
      ['Ⓗ 寡婦・ひとり親の該当', '=IF(C4="寡婦","寡婦",IF(C4="ひとり親","ひとり親",""))'],
      ['Ⓘ 勤労学生の該当', '=IF(C5="該当","該当","")'],
    ];
    put(f, 'B20', '計算シートへの反映（自動）', { head: true }); put(f, 'C20', '', { head: true });
    box.forEach(([k, v], i) => { put(f, 'B' + (21 + i), k); put(f, 'C' + (21 + i), v, { total: true }); });
    put(f, 'B31', '23歳未満の扶養親族の有無'); put(f, 'C31', '=IF(SUM(P10:P19)>0,"有","無")', { total: true });
    put(f, 'B32', '特定親族特別控除額 合計'); put(f, 'C32', '=SUM(N10:N19)', { total: true, yen: true });
    put(f, 'B33', '源泉控除対象親族の数'); put(f, 'C33', '=SUM(Q10:Q19)', { total: true });

    // =====================================================================
    // 基礎申告書
    // =====================================================================
    const k = SH.kiso;
    widths(k, [2, 40, 16]);
    put(k, 'B1', '令和8年分 給与所得者の基礎控除申告書', { title: true });
    put(k, 'B3', '給与所得の金額（計算シート⑪から自動）'); put(k, 'C3', `=N(${R(SH.calc, 'M19')})`, { yen: true });
    put(k, 'B4', '給与所得以外の所得の合計額'); put(k, 'C4', numOrBlank((emp.kiso || {}).otherIncome) || 0, { input: true, yen: true });
    put(k, 'B5', 'あなたの本年中の合計所得金額の見積額'); put(k, 'C5', '=C3+C4', { yen: true, total: true });
    put(k, 'B6', '区分Ⅰ（配偶者控除等申告書で使用）'); put(k, 'C6', '=IF(C5<=9000000,"A",IF(C5<=9500000,"B",IF(C5<=10000000,"C","")))');
    put(k, 'B7', '基礎控除の額（計算シート⑳へ）'); put(k, 'C7', `=VLOOKUP(C5,${T}$D$5:$E$11,2,TRUE)`, { yen: true, total: true });

    // =====================================================================
    // 配偶者申告書
    // =====================================================================
    const s = SH.spouse;
    widths(s, [2, 40, 18]);
    put(s, 'B1', '令和8年分 給与所得者の配偶者控除等申告書', { title: true });
    put(s, 'B3', '配偶者の有無'); put(s, 'C3', SP.has ? 'あり' : 'なし', { input: true, list: ['あり', 'なし'] });
    put(s, 'B4', '配偶者の氏名'); put(s, 'C4', SP.name || null, { input: true });
    put(s, 'B5', 'フリガナ'); put(s, 'C5', SP.kana || null, { input: true });
    put(s, 'B6', '生年月日'); put(s, 'C6', toDate(SP.birth), { input: true, date: true });
    put(s, 'B7', '配偶者の本年中の合計所得金額の見積額'); put(s, 'C7', SP.has ? numOrBlank(SP.income) : null, { input: true, yen: true });
    put(s, 'B8', '非居住者である配偶者'); put(s, 'C8', SP.nonResident ? 'はい' : 'いいえ', { input: true, list: ['はい', 'いいえ'] });
    put(s, 'B9', '年末年齢'); put(s, 'C9', `=IF(C6="","",${T}$B$3-YEAR(C6)+IF(AND(MONTH(C6)=1,DAY(C6)=1),1,0))`);
    put(s, 'B10', 'あなたの本年中の合計所得金額の見積額'); put(s, 'C10', `=${R(SH.kiso, 'C5')}`, { yen: true });
    put(s, 'B11', '区分Ⅰ'); put(s, 'C11', `=${R(SH.kiso, 'C6')}`);
    put(s, 'B12', '区分Ⅱ'); put(s, 'C12', `=IF(C3<>"あり","",IF(N(C7)<=${T}$B$4,IF(AND(C9<>"",N(C9)>=70),"①","②"),IF(N(C7)<=950000,"③",IF(N(C7)<=1330000,"④","対象外"))))`);
    put(s, 'B13', '配偶者控除の額'); put(s, 'C13', `=IF(OR(C3<>"あり",C15=0,N(C7)>${T}$B$4),0,IF(C12="①",INDEX(${T}$H$17:$J$17,1,C15-1),VLOOKUP(N(C7),${T}$G$5:$J$15,C15,TRUE)))`, { yen: true });
    put(s, 'B14', '配偶者特別控除の額'); put(s, 'C14', `=IF(OR(C3<>"あり",C15=0,N(C7)<=${T}$B$4,N(C7)>1330000),0,VLOOKUP(N(C7),${T}$G$5:$J$15,C15,TRUE))`, { yen: true });
    put(s, 'B15', '（区分Ⅰの列番号）'); put(s, 'C15', '=IF(C11="A",2,IF(C11="B",3,IF(C11="C",4,0)))');
    put(s, 'B16', '配偶者（特別）控除額（計算シート⑰へ）'); put(s, 'C16', '=C13+C14', { yen: true, total: true });

    // =====================================================================
    // 特定親族申告書（扶養申告書で「特定親族」と判定された人を自動転記）
    // =====================================================================
    const p = SH.tokutei;
    widths(p, [2, 20, 10, 12, 18, 18]);
    put(p, 'B1', '令和8年分 給与所得者の特定親族特別控除申告書', { title: true });
    ['氏名', '続柄', '生年月日', '合計所得金額の見積額', '特定親族特別控除の額'].forEach((h, i) => put(p, 'BCDEF'[i] + '3', h, { head: true }));
    for (let i = 0; i < 10; i++) {
      const r = 4 + i, src = 10 + i, cond = `${R(SH.fuyo, '$L' + src)}="特定親族"`;
      put(p, 'B' + r, `=IF(${cond},${R(SH.fuyo, 'B' + src)},"")`);
      put(p, 'C' + r, `=IF(${cond},${R(SH.fuyo, 'C' + src)},"")`);
      put(p, 'D' + r, `=IF(${cond},${R(SH.fuyo, 'D' + src)},"")`, { date: true });
      put(p, 'E' + r, `=IF(${cond},${R(SH.fuyo, 'G' + src)},"")`, { yen: true });
      put(p, 'F' + r, `=${R(SH.fuyo, 'N' + src)}`, { yen: true });
    }
    put(p, 'B15', '合計（計算シート⑱へ）', { total: true }); put(p, 'F15', '=SUM(F4:F13)', { yen: true, total: true });

    // =====================================================================
    // 所得金額調整申告書
    // =====================================================================
    const c = SH.chosei;
    widths(c, [2, 44, 14]);
    put(c, 'B1', '令和8年分 所得金額調整控除申告書', { title: true });
    put(c, 'B3', '給与等の収入金額（計算シート⑦）'); put(c, 'C3', `=${R(SH.calc, 'M16')}`, { yen: true });
    put(c, 'B4', '要件（いずれかに該当）', { head: true }); put(c, 'C4', '', { head: true });
    put(c, 'B5', 'あなた自身が特別障害者'); put(c, 'C5', `=IF(${R(SH.fuyo, 'C3')}="特別障害者","該当","")`);
    put(c, 'B6', '同一生計配偶者が特別障害者'); put(c, 'C6', `=IF(AND(${R(SH.fuyo, 'C7')}="該当",OR(${R(SH.fuyo, 'C6')}="特別障害者",${R(SH.fuyo, 'C6')}="同居特別障害者")),"該当","")`);
    put(c, 'B7', '扶養親族が特別障害者'); put(c, 'C7', `=IF(COUNTIFS(${R(SH.fuyo, 'J10:J19')},"*特別障害者",${R(SH.fuyo, 'O10:O19')},">0")>0,"該当","")`);
    put(c, 'B8', '扶養親族が年齢23歳未満（平16.1.2以後生）'); put(c, 'C8', `=IF(${R(SH.fuyo, 'C31')}="有","該当","")`);
    const mode = (emp.chosei && emp.chosei.mode) || 'auto';
    put(c, 'B10', '適用の指定（自動／有／無）'); put(c, 'C10', mode === 'yes' ? '有' : mode === 'no' ? '無' : '自動', { input: true, list: ['自動', '有', '無'] });
    put(c, 'B11', '所得金額調整控除の適用の有無（計算シートへ）'); put(c, 'C11', '=IF(C10="有","有",IF(C10="無","無",IF(AND(C3>8500000,COUNTIF(C5:C8,"該当")>0),"有","無")))', { total: true });

    // =====================================================================
    // 保険申告書
    // =====================================================================
    const h = SH.hoken, Hk = emp.hoken || {};
    widths(h, [2, 22, 12, 8, 14, 12, 16, 12, 2, 34, 14]);
    put(h, 'B1', '令和8年分 給与所得者の保険料控除申告書', { title: true });
    put(h, 'B3', '生命保険料控除', { head: true });
    ['保険会社等の名称', '区分', '新・旧', '支払保険料等'].forEach((x, i) => put(h, 'BCDE'[i] + '4', x, { head: true }));
    const kindL = { general: '一般', care: '介護医療', pension: '個人年金' };
    for (let i = 0; i < 10; i++) {
      const r = 5 + i, e = (Hk.life || [])[i] || {};
      put(h, 'B' + r, e.company || null, { input: true });
      put(h, 'C' + r, e.kind ? kindL[e.kind] : null, { input: true, list: ['一般', '介護医療', '個人年金'] });
      put(h, 'D' + r, e.kind ? (e.kind === 'care' ? '新' : e.era === 'old' ? '旧' : '新') : null, { input: true, list: ['新', '旧'] });
      put(h, 'E' + r, numOrBlank(e.amount), { input: true, yen: true });
    }
    [['新・一般', '=SUMIFS(E5:E14,C5:C14,"一般",D5:D14,"新")'], ['旧・一般', '=SUMIFS(E5:E14,C5:C14,"一般",D5:D14,"旧")'],
      ['介護医療', '=SUMIFS(E5:E14,C5:C14,"介護医療")'], ['新・個人年金', '=SUMIFS(E5:E14,C5:C14,"個人年金",D5:D14,"新")'],
      ['旧・個人年金', '=SUMIFS(E5:E14,C5:C14,"個人年金",D5:D14,"旧")'], ['23歳未満の扶養親族', `=${R(SH.fuyo, 'C31')}`]]
      .forEach(([x, fm], i) => { put(h, 'G' + (5 + i), x); put(h, 'H' + (5 + i), fm, { yen: i < 5 }); });
    const fI = (x) => `ROUNDUP(IF(${x}<=20000,${x},IF(${x}<=40000,${x}/2+10000,IF(${x}<=80000,${x}/4+20000,40000))),0)`;
    const fII = (x) => `ROUNDUP(IF(${x}<=30000,${x},IF(${x}<=60000,${x}/2+15000,IF(${x}<=120000,${x}/4+30000,60000))),0)`;
    const fIII = (x) => `ROUNDUP(IF(${x}<=25000,${x},IF(${x}<=50000,${x}/2+12500,IF(${x}<=100000,${x}/4+25000,50000))),0)`;
    [['① 一般（新）計算式Ⅰ／23歳未満扶養ありは計算式Ⅱ', `=IF(H10="有",${fII('H5')},${fI('H5')})`],
      ['② 一般（旧）計算式Ⅲ', `=${fIII('H6')}`],
      ['③ 一般（新旧両方）①＋②（最高4万円／23歳未満扶養ありは6万円）', '=IF(AND(H5>0,H6>0),MIN(K5+K6,IF(H10="有",60000,40000)),0)'],
      ['一般の生命保険料の控除額', '=MAX(K5:K7)'],
      ['介護医療保険料の控除額', `=${fI('H7')}`],
      ['④ 個人年金（新）', `=${fI('H8')}`],
      ['⑤ 個人年金（旧）', `=${fIII('H9')}`],
      ['⑥ 個人年金（新旧両方）最高4万円', '=IF(AND(H8>0,H9>0),MIN(K10+K11,40000),0)'],
      ['個人年金保険料の控除額', '=MAX(K10:K12)'],
      ['生命保険料控除額計（最高120,000円）→計算シート⑮', '=MIN(K8+K9+K13,120000)']]
      .forEach(([x, fm], i) => { put(h, 'J' + (5 + i), x, { wrap: true }); put(h, 'K' + (5 + i), fm, { yen: true, total: i === 9 }); });

    put(h, 'B16', '地震保険料控除', { head: true });
    ['保険会社等の名称', '区分', '', '支払保険料等'].forEach((x, i) => put(h, 'BCDE'[i] + '17', x, { head: true }));
    for (let i = 0; i < 5; i++) {
      const r = 18 + i, e = (Hk.quake || [])[i] || {};
      put(h, 'B' + r, e.company || null, { input: true });
      put(h, 'C' + r, e.kind ? (e.kind === 'oldlong' ? '旧長期損害' : '地震') : null, { input: true, list: ['地震', '旧長期損害'] });
      put(h, 'E' + r, numOrBlank(e.amount), { input: true, yen: true });
    }
    put(h, 'J18', '地震保険料の合計'); put(h, 'K18', '=SUMIF(C18:C22,"地震",E18:E22)', { yen: true });
    put(h, 'J19', '旧長期損害保険料の合計（計算シート「旧長期損害保険料支払額」へ）'); put(h, 'K19', '=SUMIF(C18:C22,"旧長期損害",E18:E22)', { yen: true });
    put(h, 'J20', '地震保険料控除額（最高50,000円）→計算シート⑯'); put(h, 'K20', '=MIN(MIN(K18,50000)+ROUNDUP(IF(K19<=10000,K19,IF(K19<=20000,K19/2+5000,15000)),0),50000)', { yen: true, total: true });

    put(h, 'B24', '社会保険料控除（申告分）', { head: true });
    ['社会保険の種類', '保険料支払先', '負担する人', '支払保険料', '国民年金保険料等'].forEach((x, i) => put(h, 'BCDEF'[i] + '25', x, { head: true }));
    for (let i = 0; i < 6; i++) {
      const r = 26 + i, e = (Hk.social || [])[i] || {};
      put(h, 'B' + r, e.kind || null, { input: true });
      put(h, 'C' + r, e.payer || null, { input: true });
      put(h, 'D' + r, e.person || null, { input: true });
      put(h, 'E' + r, numOrBlank(e.amount), { input: true, yen: true });
      put(h, 'F' + r, e.amount ? (e.nationalPension ? 'はい' : 'いいえ') : null, { input: true, list: ['はい', 'いいえ'] });
    }
    put(h, 'J26', '社会保険料控除 合計 →計算シート⑬'); put(h, 'K26', '=SUM(E26:E31)', { yen: true, total: true });
    put(h, 'J27', 'うち国民年金保険料等（計算シートへ）'); put(h, 'K27', '=SUMIF(F26:F31,"はい",E26:E31)', { yen: true });

    put(h, 'B33', '小規模企業共済等掛金控除（申告分）', { head: true });
    ['掛金の種類', '', '', '支払掛金'].forEach((x, i) => put(h, 'BCDE'[i] + '34', x, { head: true }));
    for (let i = 0; i < 4; i++) {
      const r = 35 + i, e = (Hk.smallBiz || [])[i] || {};
      put(h, 'B' + r, e.kind || null, { input: true });
      put(h, 'E' + r, numOrBlank(e.amount), { input: true, yen: true });
    }
    put(h, 'J35', '小規模企業共済等掛金控除 合計 →計算シート⑭'); put(h, 'K35', '=SUM(E35:E38)', { yen: true, total: true });

    // =====================================================================
    // 住借申告書
    // =====================================================================
    const j = SH.jutaku, Ju = emp.jutaku || {};
    widths(j, [2, 52, 16]);
    put(j, 'B1', '令和8年分 給与所得者の住宅借入金等特別控除申告書', { title: true });
    put(j, 'B3', '住宅借入金等の年末残高（借入限度額適用後）'); put(j, 'C3', numOrBlank(Ju.balance), { input: true, yen: true });
    put(j, 'B4', '控除率'); put(j, 'C4', Number(Ju.rate) || 0.007, { input: true, pct: true });
    put(j, 'B5', '控除限度額（年額。税務署発行の証明書の金額）'); put(j, 'C5', numOrBlank(Ju.limit), { input: true, yen: true });
    put(j, 'B6', '控除額を直接入力（計算明細書で算出した金額。入力時は優先）'); put(j, 'C6', numOrBlank(Ju.direct), { input: true, yen: true });
    put(j, 'B7', '住宅借入金等特別控除額（100円未満切捨て・最高60万円）→計算シート㉔');
    put(j, 'C7', '=MIN(ROUNDDOWN(IF(C6<>"",C6,IF(C5="",N(C3)*C4,MIN(N(C3)*C4,C5))),-2),600000)', { yen: true, total: true });

    // =====================================================================
    // 計算シート（元ファイルのセル番地を踏襲）
    // =====================================================================
    const k2 = SH.calc;
    for (let col = 1; col <= 30; col++) ws[k2].getColumn(col).width = 4.5;
    ws[k2].getColumn(2).width = 6; ws[k2].getColumn(13).width = 14; ws[k2].getColumn(20).width = 14; ws[k2].getColumn(22).width = 14;
    ws[k2].getColumn(9).width = 6; ws[k2].getColumn(11).width = 12; ws[k2].getColumn(24).width = 12; ws[k2].getColumn(29).width = 12;
    put(k2, 'A1', '年末調整計算シート（令和８年用）', { title: true });
    put(k2, 'A3', '（フリガナ）氏名'); put(k2, 'E3', emp.profile.kana || null, { input: true }); put(k2, 'E4', emp.profile.name || null, { input: true });
    put(k2, 'N3', '備考'); put(k2, 'P3', emp.profile.note || null, { input: true });
    put(k2, 'A6', '扶養控除及び障害者控除等の控除額', { head: true });
    put(k2, 'B6', '区分', { head: true }); put(k2, 'I6', '人数', { head: true }); put(k2, 'K6', '控除額', { head: true });
    put(k2, 'O6', '区分', { head: true }); put(k2, 'V6', '人数等', { head: true }); put(k2, 'X6', '控除額', { head: true });
    const leftBox = [[7, '一般の控除対象扶養親族 Ⓐ', 'C21', 'B11'], [8, '特定扶養親族 Ⓑ', 'C22', 'B12'], [10, '同居老親等 Ⓒ', 'C23', 'B13'], [11, '同居老親等以外の老人扶養親族 Ⓓ', 'C24', 'B14']];
    leftBox.forEach(([r, lab, src, amt]) => {
      put(k2, 'C' + r, lab);
      put(k2, 'I' + r, `=${R(SH.fuyo, src)}`);
      put(k2, 'K' + r, `=IF(I${r}="","",I${r}*${T}${amt})`, { yen: true });
    });
    put(k2, 'C9', '特定親族（控除額は⑱欄）');
    const rightBox = [[7, '一般の障害者 Ⓔ', 'C25', 'B15'], [8, '同居特別障害者以外の特別障害者 Ⓕ', 'C26', 'B16'], [9, '同居特別障害者 Ⓖ', 'C27', 'B17']];
    rightBox.forEach(([r, lab, src, amt]) => {
      put(k2, 'O' + r, lab);
      put(k2, 'V' + r, `=${R(SH.fuyo, src)}`);
      put(k2, 'X' + r, `=IF(V${r}="","",V${r}*${T}${amt})`, { yen: true });
    });
    put(k2, 'O10', '寡婦・ひとり親の該当 Ⓗ'); put(k2, 'V10', `=${R(SH.fuyo, 'C28')}`);
    put(k2, 'X10', `=IF(V10="寡婦",${T}B18,IF(V10="ひとり親",${T}B19,""))`, { yen: true });
    put(k2, 'O11', '勤労学生の該当 Ⓘ'); put(k2, 'V11', `=${R(SH.fuyo, 'C29')}`);
    put(k2, 'X11', `=IF(V11="該当",${T}B20,"")`, { yen: true });
    put(k2, 'AC10', '控除額合計'); put(k2, 'AC11', '=SUM(K7,K8,K10,K11,X7,X8,X9,X10,X11)', { yen: true, result: L.r19 });

    put(k2, 'A13', '年末調整', { head: true }); put(k2, 'B13', '区分', { head: true }); put(k2, 'M13', '金額（円）', { head: true }); put(k2, 'T13', '税額（円）', { head: true });
    const lab = (r, text, mark, col) => { put(k2, 'B' + r, text); put(k2, (col || 'L') + r, mark); };
    lab(14, '給料・手当等', '①'); put(k2, 'S14', '③');
    auto(k2, 'M14', `=${R(SH.agg, 'E15')}`, 'r1'); auto(k2, 'T14', `=${R(SH.agg, 'I15')}`, 'r3');
    lab(15, '賞与等', '④'); put(k2, 'S15', '⑥');
    auto(k2, 'M15', `=${R(SH.agg, 'E20')}`, 'r4'); auto(k2, 'T15', `=${R(SH.agg, 'I20')}`, 'r6');
    lab(16, '計', '⑦'); put(k2, 'S16', '⑧');
    put(k2, 'M16', '=SUM(M14:M15)', { yen: true, result: L.r7 }); put(k2, 'T16', '=SUM(T14:T15)', { yen: true, result: L.r8 });
    lab(17, '給与所得控除後の給与等の金額', '⑨');
    put(k2, 'AC16', '給与所得控除後の計算①');
    put(k2, 'AC17', '=IF(M16<=2199999,M16,IF(M16<=6599999,M16-MOD(M16-2200000,4000),IF(M16<=20000000,M16,"")))', { yen: true });
    auto(k2, 'M17', '=IF(AC17<=740999,0,IF(AC17<=2190999,AC17-740000,IF(AC17<=2192999,1451000,IF(AC17<=2195999,1453000,IF(AC17<=2199999,1456000,IF(AC17<=3599999,QUOTIENT(AC17*7,10)-80000,IF(AC17<=6599999,QUOTIENT(AC17*8,10)-440000,IF(AC17<=8499999,QUOTIENT(AC17*9,10)-1100000,IF(AC17<=20000000,AC17-1950000,"")))))))))', 'r9');
    put(k2, 'S17', '所得金額調整控除の適用の有無');
    put(k2, 'T18', `=${R(SH.chosei, 'C11')}`);
    lab(18, '所得金額調整控除額', '⑩');
    put(k2, 'AC20', '=IF(ROUNDUP((MIN(M16,10000000)-8500000)*0.1,0)>150000,150000,ROUNDUP((MIN(M16,10000000)-8500000)*0.1,0))', { yen: true });
    auto(k2, 'M18', '=IF(AND(T18="有",M16>8500000),AC20,0)', 'r10');
    lab(19, '給与所得控除後の給与等の金額（調整控除後）', '⑪');
    auto(k2, 'M19', '=IFERROR(M17-M18,"")', 'r11');
    put(k2, 'S19', '=IF(AND(M25>0,V22=""),"「配偶者の合計所得金額」を入力してください。","")');
    lab(20, '社会保険料等控除額（給与等からの控除分）', '⑫');
    auto(k2, 'M20', `=${R(SH.agg, 'F15')}+${R(SH.agg, 'F20')}`, 'r12');
    lab(21, '社会保険料等控除額（申告による社会保険料の控除分）', '⑬');
    auto(k2, 'M21', `=${R(SH.hoken, 'K26')}`, 'r13');
    put(k2, 'U21', '配偶者の合計所得金額'); put(k2, 'V22', `=IF(${R(SH.spouse, 'C3')}="あり",${R(SH.spouse, 'C7')},"")`, { yen: true });
    lab(22, '社会保険料等控除額（申告による小規模企業共済等掛金の控除分）', '⑭');
    auto(k2, 'M22', `=${R(SH.hoken, 'K35')}`, 'r14');
    lab(23, '生命保険料の控除額', '⑮'); auto(k2, 'M23', `=${R(SH.hoken, 'K14')}`, 'r15');
    put(k2, 'U23', '旧長期損害保険料支払額'); put(k2, 'V24', `=${R(SH.hoken, 'K19')}`, { yen: true });
    lab(24, '地震保険料の控除額', '⑯'); auto(k2, 'M24', `=${R(SH.hoken, 'K20')}`, 'r16');
    lab(25, '配偶者（特別）控除額', '⑰'); auto(k2, 'M25', `=${R(SH.spouse, 'C16')}`, 'r17');
    put(k2, 'S25', '⑫のうち小規模企業共済等掛金の金額'); put(k2, 'V26', `=${R(SH.agg, 'L15')}+${R(SH.agg, 'L20')}`, { yen: true });
    lab(26, '特定親族特別控除額', '⑱'); auto(k2, 'M26', `=${R(SH.tokutei, 'F15')}`, 'r18');
    lab(27, '扶養控除額及び障害者等の控除額の合計額', '⑲'); auto(k2, 'M27', '=AC11', 'r19');
    put(k2, 'S27', '⑬のうち国民年金保険料等の金額'); put(k2, 'V28', `=${R(SH.hoken, 'K27')}`, { yen: true });
    lab(28, '基礎控除額', '⑳'); auto(k2, 'M28', `=${R(SH.kiso, 'C7')}`, 'r20');
    lab(29, '所得控除額の合計額', '㉑'); put(k2, 'M29', '=SUM(M20:M28)', { yen: true, result: L.r21 });
    lab(30, '差引課税給与所得金額（㉑−⑪、1,000円未満切捨て）', '㉒');
    auto(k2, 'M30', '=IFERROR(IF(M19<M29,0,ROUNDDOWN(M19-M29,-3)),"")', 'r22');
    put(k2, 'S30', '㉓ 算出所得税額');
    auto(k2, 'T30', '=IFERROR(IF(M30>18000000,M30*0.4-2796000,IF(M30>9000000,M30*0.33-1536000,IF(M30>6950000,M30*0.23-636000,IF(M30>3300000,M30*0.2-427500,IF(M30>1950000,M30*0.1-97500,IF(M30<=1950000,M30*0.05,0)))))),"")', 'r23');
    lab(31, '住宅借入金等特別控除額', '㉔', 'S'); auto(k2, 'T31', `=${R(SH.jutaku, 'C7')}`, 'r24');
    lab(32, '年調所得税額（㉓−㉔）', '㉕', 'S'); auto(k2, 'T32', '=IFERROR(IF((T30-T31)<0,0,T30-T31),"")', 'r25');
    lab(33, '年調年税額（㉕×102.1%、100円未満切捨て）', '㉖', 'S');
    put(k2, 'AS35', '最後のエラー'); put(k2, 'AS36', '=IF(S19<>"","×","")');
    auto(k2, 'T33', '=IFERROR(IF(AS36="×","上のエラーメッセージを確認してください。",ROUNDDOWN(T32*1.021,-2)),"")', 'r26');
    put(k2, 'B34', '=IF(OR(AND(T16="",T33=""),T16=T33),"差引超過額又は不足額",IF(T16<T33,"差引不足額","差引超過額"))', { result: result ? result.statusLabel : undefined });
    put(k2, 'S34', '㉗'); put(k2, 'T34', '=IFERROR(ABS(T33-T16),"")', { yen: true, result: L.r27 });
    const st = emp.settle || {};
    put(k2, 'B35', '超過額の精算'); put(k2, 'F35', '本年最後の給与から徴収する税額に充当する金額'); put(k2, 'S35', '㉘');
    put(k2, 'T35', numOrBlank(st.r28) || 0, { input: true, yen: true });
    put(k2, 'F36', '未払給与に係る未徴収の税額に充当する金額'); put(k2, 'S36', '㉙'); put(k2, 'T36', numOrBlank(st.r29) || 0, { input: true, yen: true });
    put(k2, 'F37', '差引還付する税額'); put(k2, 'S37', '㉚'); put(k2, 'T37', '=IFERROR(IF(B34="差引超過額",T34-T35-T36,""),"")', { yen: true, result: L.r30 });
    put(k2, 'F38', '同上のうち 本年中に還付する金額'); put(k2, 'S38', '㉛');
    if (st.r31 !== '' && st.r31 !== null && st.r31 !== undefined) put(k2, 'T38', numOrBlank(st.r31), { input: true, yen: true });
    else put(k2, 'T38', '=IF(B34="差引超過額",T37,"")', { input: true, yen: true, result: L.r31 });
    put(k2, 'J39', '翌年において還付する金額'); put(k2, 'S39', '㉜'); put(k2, 'T39', '=IFERROR(IF(B34="差引超過額",T37-T38,""),"")', { yen: true, result: L.r32 });
    put(k2, 'B40', '不足額の精算'); put(k2, 'F40', '本年最後の給与から徴収する金額'); put(k2, 'S40', '㉝');
    if (st.r33 !== '' && st.r33 !== null && st.r33 !== undefined) put(k2, 'T40', numOrBlank(st.r33), { input: true, yen: true });
    else put(k2, 'T40', '=IF(B34="差引不足額",T34,"")', { input: true, yen: true, result: L.r33 });
    put(k2, 'F41', '翌年に繰り越して徴収する金額'); put(k2, 'S41', '㉞'); put(k2, 'T41', '=IFERROR(IF(B34="差引不足額",T34-T40,""),"")', { yen: true, result: L.r34 });
    put(k2, 'B43', '※ 白セルは各シートから自動反映（関数）。上書きして手入力も可能です。黄色セルは入力欄、橙色はWEBアプリで手入力された値です。', { border: false });

    // =====================================================================
    // 源泉徴収簿（集計シート・計算シートを参照）
    // =====================================================================
    const g = SH.boki;
    widths(g, [2, 10, 12, 14, 14, 16, 10, 12, 14, 14, 3, 44, 16]);
    put(g, 'B1', '令和8年分 給与所得に対する源泉徴収簿（集計）', { title: true });
    put(g, 'B2', `=${R(SH.calc, 'E4')}`, { border: false });
    ['区分', '支給月日', '総支給金額', '社会保険料等', '差引金額', '扶養親族等の数', '算出税額', '年末調整過不足', '差引徴収税額']
      .forEach((x, i) => put(g, String.fromCharCode(66 + i) + '4', x, { head: true }));
    for (let i = 0; i < 16; i++) {
      const r = 5 + i, src = i < 12 ? 3 + i : 16 + (i - 12);
      put(g, 'B' + r, i < 12 ? `${i + 1}月` : `賞与${i - 11}`);
      put(g, 'C' + r, `=IF(${R(SH.agg, 'D' + src)}="","",${R(SH.agg, 'D' + src)})`, { date: true });
      ['E', 'F', 'G', 'H', 'I', 'J', 'K'].forEach((col, ci) => put(g, 'DEFGHIJ'[ci] + r, `=${R(SH.agg, col + src)}`, { yen: true }));
    }
    put(g, 'B21', '計', { total: true });
    'DEFHIJ'.split('').forEach((col) => put(g, col + '21', `=SUM(${col}5:${col}20)`, { yen: true, total: true }));
    put(g, 'L4', '年末調整', { head: true }); put(g, 'M4', '金額', { head: true });
    const bokiLines = [['① 給料・手当等', 'M14'], ['③ 税額', 'T14'], ['④ 賞与等', 'M15'], ['⑥ 税額', 'T15'], ['⑦ 計', 'M16'], ['⑧ 税額計', 'T16'],
      ['⑨ 給与所得控除後の給与等の金額', 'M17'], ['⑩ 所得金額調整控除額', 'M18'], ['⑪ 調整控除後', 'M19'], ['⑫ 社会保険料等（給与分）', 'M20'],
      ['⑬ 社会保険料（申告分）', 'M21'], ['⑭ 小規模企業共済等掛金（申告分）', 'M22'], ['⑮ 生命保険料控除', 'M23'], ['⑯ 地震保険料控除', 'M24'],
      ['⑰ 配偶者（特別）控除', 'M25'], ['⑱ 特定親族特別控除', 'M26'], ['⑲ 扶養控除・障害者等', 'M27'], ['⑳ 基礎控除', 'M28'],
      ['㉑ 所得控除合計', 'M29'], ['㉒ 課税給与所得金額', 'M30'], ['㉓ 算出所得税額', 'T30'], ['㉔ 住宅借入金等特別控除', 'T31'],
      ['㉕ 年調所得税額', 'T32'], ['㉖ 年調年税額', 'T33'], ['㉗ 差引超過額又は不足額', 'T34'], ['㉚ 差引還付する税額', 'T37'],
      ['㉛ 本年中に還付', 'T38'], ['㉜ 翌年において還付', 'T39'], ['㉝ 本年最後の給与から徴収', 'T40'], ['㉞ 翌年に繰越して徴収', 'T41']];
    bokiLines.forEach(([x, addr], i) => { put(g, 'L' + (5 + i), x); put(g, 'M' + (5 + i), `=${R(SH.calc, addr)}`, { yen: true }); });
    put(g, 'L36', '差引超過額又は不足額の区分'); put(g, 'M36', `=${R(SH.calc, 'B34')}`);

    // =====================================================================
    // 確定申告チェック
    // =====================================================================
    const q = SH.kakutei, Kk = emp.kakutei || {};
    widths(q, [2, 60, 14, 50]);
    put(q, 'B1', '確定申告の要否チェック（給与所得者）', { title: true });
    put(q, 'B3', '給与の収入金額が2,000万円を超える（年末調整の対象外）'); put(q, 'C3', `=IF(${R(SH.calc, 'M16')}>20000000,"要","")`);
    put(q, 'B4', '給与所得・退職所得以外の所得の合計額が20万円を超える'); put(q, 'C4', `=IF(${R(SH.kiso, 'C4')}>200000,"要","")`);
    const yn = (v) => (v ? 'はい' : 'いいえ');
    [['2か所以上から給与を受けている（年末調整されない給与＋他の所得が20万円超）', Kk.multipleEmployers],
      ['医療費控除・セルフメディケーション税制を受ける', Kk.medical],
      ['寄附金控除を受ける（ふるさと納税でワンストップ特例を使わない等）', Kk.donation],
      ['住宅借入金等特別控除の初年度', Kk.housingFirstYear],
      ['雑損控除を受ける', Kk.casualty]]
      .forEach(([x, v], i) => { put(q, 'B' + (5 + i), x); put(q, 'C' + (5 + i), yn(v), { input: true, list: ['はい', 'いいえ'] }); });
    put(q, 'B11', '判定', { head: true });
    put(q, 'C11', '=IF(COUNTIF(C3:C4,"要")+COUNTIF(C5,"はい")>0,"確定申告が必要な可能性があります",IF(COUNTIF(C6:C9,"はい")>0,"確定申告（還付申告）で控除を受けられます","年末調整で完了"))', { total: true });
    put(q, 'B13', '出典：国税庁 タックスアンサーNo.1900「給与所得者で確定申告が必要な人」、所得税の確定申告', { border: false });

    // =====================================================================
    // 各種申告書・参考情報
    // =====================================================================
    const rf = SH.ref;
    widths(rf, [4, 90]);
    put(rf, 'A2', '※ 国税庁ホームページに掲載している各種申告書や参考となる情報の一覧です。', { border: false });
    [['令和8年分 年末調整のしかた', 'https://www.nta.go.jp/publication/pamph/gensen/nencho2026/01.htm'],
      ['各種申告書（扶養控除等・基礎/配偶者/特定親族/所得金額調整・保険料控除）', 'https://www.nta.go.jp/taxes/tetsuzuki/shinsei/annai/gensen/annai/1648_01.htm'],
      ['令和8年分 年末調整チェック表', 'https://www.nta.go.jp/publication/pamph/gensen/nencho2026/pdf/206.pdf'],
      ['令和8年分 年末調整Q&A', 'https://www.nta.go.jp/publication/pamph/gensen/nencho2026/pdf/207.pdf'],
      ['所得税徴収高計算書（納付書）の記載方法', 'https://www.nta.go.jp/publication/pamph/gensen/nencho2026/pdf/111.pdf'],
      ['令和8年分 給与所得の源泉徴収票等の法定調書の作成と提出の手引', 'https://www.nta.go.jp/publication/pamph/hotei/tebiki2026/index.htm'],
      ['No.1410 給与所得控除', 'https://www.nta.go.jp/taxes/shiraberu/taxanswer/shotoku/1410.htm'],
      ['No.1900 給与所得者で確定申告が必要な人', 'https://www.nta.go.jp/taxes/shiraberu/taxanswer/shotoku/1900.htm'],
      ['所得税の確定申告', 'https://www.nta.go.jp/taxes/shiraberu/shinkoku/kakutei.htm']]
      .forEach(([x, url], i) => {
        put(rf, 'A' + (4 + i), i + 1);
        const cell = put(rf, 'B' + (4 + i), { text: x, hyperlink: url });
        cell.font = { color: { argb: 'FF0563C1' }, underline: true };
      });

    return wb;
  }

  return { build, SHEETS: SH };
});
