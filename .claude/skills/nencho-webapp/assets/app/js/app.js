/* 年末調整 一元管理 WEBアプリ（UI）
 * データの流れ：給与明細PDF → 集計シート → 各申告書 → 計算シート（自動）→ 源泉徴収簿・Excel出力
 * 依存：engine.js（Nencho）, payslip.js（Payslip）, workbook.js（NenchoWorkbook）, pdf.js, ExcelJS
 */
(function () {
  'use strict';
  const N = window.Nencho, P = window.Payslip, W = window.NenchoWorkbook;
  const STORE_KEY = 'nencho-r8-v1';
  const $ = (sel, el = document) => el.querySelector(sel);
  const $$ = (sel, el = document) => Array.from(el.querySelectorAll(sel));
  const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const yen = (v) => (v === null || v === undefined || v === '' ? '' : Number(v).toLocaleString('ja-JP'));
  const fmtIn = (v) => (v === null || v === undefined || v === '' ? '' : Number(v).toLocaleString('ja-JP'));
  const getPath = (o, p) => p.split('.').reduce((a, k) => (a == null ? a : a[k]), o);
  const setPath = (o, p, v) => {
    const ks = p.split('.'); let a = o;
    for (let i = 0; i < ks.length - 1; i++) { if (a[ks[i]] == null) a[ks[i]] = /^\d+$/.test(ks[i + 1]) ? [] : {}; a = a[ks[i]]; }
    a[ks[ks.length - 1]] = v;
  };

  // ------------------------------------------------------------------ 状態
  let state = load();
  let tab = 'dashboard';
  let parsed = []; // 給与明細の読取り結果（反映前）
  let result = null;

  function load() {
    try { const s = JSON.parse(localStorage.getItem(STORE_KEY)); if (s && Array.isArray(s.employees)) return s; } catch (e) { /* 初回・閲覧制限 */ }
    return { employees: [], currentId: null };
  }
  let saveTimer = null;
  function save() {
    clearTimeout(saveTimer);
    saveTimer = setTimeout(() => {
      try { localStorage.setItem(STORE_KEY, JSON.stringify(state)); } catch (e) { /* 保存不可環境 */ }
    }, 250);
  }
  const emp = () => state.employees.find((e) => e.id === state.currentId) || null;

  // ------------------------------------------------------------------ 入力部品
  const numIn = (path, extra = '') => `<input class="num" data-bind="${path}" data-type="num" inputmode="numeric" value="${esc(fmtIn(getPath(emp(), path)))}" ${extra}>`;
  const txtIn = (path, extra = '') => `<input data-bind="${path}" data-type="text" value="${esc(getPath(emp(), path))}" ${extra}>`;
  const dateIn = (path) => `<input type="date" data-bind="${path}" data-type="text" value="${esc(getPath(emp(), path))}">`;
  const sel = (path, options) => {
    const v = getPath(emp(), path);
    return `<select data-bind="${path}" data-type="select">${options.map(([k, l]) => `<option value="${esc(k)}" ${String(v) === String(k) ? 'selected' : ''}>${esc(l)}</option>`).join('')}</select>`;
  };
  const chk = (path, label) => `<label class="check"><input type="checkbox" data-bind="${path}" data-type="bool" ${getPath(emp(), path) ? 'checked' : ''}> ${esc(label)}</label>`;
  const field = (label, input) => `<label class="field"><span>${esc(label)}</span>${input}</label>`;
  const out = (path, cls = 'n') => `<span class="${cls}" data-out="${path}"></span>`;

  // ------------------------------------------------------------------ タブ
  const TABS = [
    ['dashboard', '従業員一覧'], ['profile', '基本情報'], ['import', '給与明細取込'], ['agg', '集計シート'],
    ['fuyo', '扶養控除等申告書'], ['kiso', '基礎・配偶者・特定親族・所得金額調整'], ['hoken', '保険料控除申告書'],
    ['jutaku', '住宅借入金等特別控除'], ['calc', '計算シート'], ['boki', '源泉徴収簿'], ['kakutei', '確定申告チェック'], ['data', 'Excel出力・データ管理'],
  ];
  function renderTabs() {
    $('#tabs').innerHTML = TABS.map(([k, l]) => `<button role="tab" data-tab="${k}" aria-selected="${tab === k}">${l}</button>`).join('');
    const s = $('#empSelect');
    s.innerHTML = state.employees.length
      ? state.employees.map((e) => `<option value="${e.id}" ${e.id === state.currentId ? 'selected' : ''}>${esc(e.profile.name || '（氏名未入力）')}</option>`).join('')
      : '<option value="">従業員が未登録です</option>';
  }

  function render() {
    renderTabs();
    const e = emp();
    const main = $('#main');
    if (!e && tab !== 'dashboard' && tab !== 'data') tab = 'dashboard';
    const views = { dashboard, profile, import: importView, agg, fuyo, kiso, hoken, jutaku, calc, boki, kakutei, data };
    main.innerHTML = views[tab]();
    if (tab === 'import') bindDrop();
    recompute();
  }

  // ------------------------------------------------------------------ 再計算と出力欄の更新
  function recompute() {
    const e = emp();
    result = e ? N.calculate(e) : null;
    if (result) extraOutputs();
    $$('[data-out]').forEach((el) => {
      const v = result ? getPath(result, el.dataset.out) : '';
      el.textContent = typeof v === 'number' ? yen(v) : v ?? '';
    });
    $$('[data-depcls]').forEach((el) => {
      const d = e.fuyo.dependents[+el.dataset.depcls];
      const c = d && (d.name || d.birth) ? N.classifyDependent(d) : null;
      const k = el.dataset.k;
      el.textContent = !c ? '' : k === 'age' ? (c.age ?? '') : k === 'cat' ? c.category : yen(c[k] || 0);
    });
    $$('[data-calc-auto]').forEach((el) => {
      const key = el.dataset.calcAuto;
      const ov = { ...(e.overrides || {}) }; delete ov[key];
      el.textContent = yen(N.calculate({ ...e, overrides: ov }).lines[key]);
    });
    $$('input[data-bind^="overrides."]').forEach((el) => el.classList.toggle('override', el.value !== ''));
    renderSummary();
    if (result) updateAggRows();
    if (tab === 'dashboard') $$('[data-emp-row]').forEach(updateDashRow);
  }

  function renderSummary() {
    const box = $('#summary');
    const e = emp();
    if (!e || !result) { box.innerHTML = '<div class="card"><p class="note">従業員を追加すると、ここに年末調整の結果が表示されます。</p></div>'; return; }
    const L = result.lines;
    const cls = result.status === 'refund' ? 'result-refund' : result.status === 'shortage' ? 'result-shortage' : '';
    const msgs = result.warnings.map((w) => `<li class="${w.level}">${esc(w.msg)}</li>`).join('');
    box.innerHTML = `<div class="card">
      <div class="note">${esc(e.profile.name || '（氏名未入力）')} ／ 令和8年分</div>
      ${result.outOfScope ? '<p class="pill err">年末調整の対象外（2,000万円超）</p>' : ''}
      <div class="kv"><span>⑦ 給与等の金額</span><span>${yen(L.r7)}</span></div>
      <div class="kv"><span>⑪ 給与所得</span><span>${yen(L.r11)}</span></div>
      <div class="kv"><span>㉑ 所得控除合計</span><span>${yen(L.r21)}</span></div>
      <div class="kv"><span>㉒ 課税給与所得</span><span>${yen(L.r22)}</span></div>
      <div class="kv"><span>㉖ 年調年税額</span><span>${yen(L.r26)}</span></div>
      <div class="kv"><span>⑧ 源泉徴収済み税額</span><span>${yen(L.r8)}</span></div>
      <p style="margin:10px 0 0">${esc(result.statusLabel)}</p>
      <div class="big ${cls}">${yen(L.r27)} 円</div>
      <p class="note">${result.status === 'refund' ? '本人へ還付' : result.status === 'shortage' ? '本人から追加徴収' : ''}
      ${result.kakuteiRequired ? '<br><span class="pill warn">確定申告が必要な可能性</span>' : ''}</p>
      <h3>チェック（${result.warnings.length}件）</h3>
      <ul class="msgs">${msgs || '<li class="info">指摘事項はありません</li>'}</ul>
    </div>`;
  }

  // ------------------------------------------------------------------ 各画面
  function dashboard() {
    const rows = state.employees.map((e) => `<tr data-emp-row="${e.id}">
      <td>${esc(e.profile.name || '（氏名未入力）')}</td><td class="n" data-c="r7"></td><td class="n" data-c="r21"></td>
      <td class="n" data-c="r26"></td><td class="n" data-c="r8"></td><td data-c="status"></td><td class="n" data-c="r27"></td>
      <td data-c="kakutei"></td><td data-c="warn"></td>
      <td><button class="btn small" data-action="open" data-id="${e.id}">開く</button>
          <button class="btn small" data-action="dup" data-id="${e.id}">複製</button>
          <button class="btn small danger" data-action="del" data-id="${e.id}">削除</button></td></tr>`).join('');
    return `<section>
      <h2>従業員一覧（令和8年分）</h2>
      <p class="lead">従業員ごとに 給与明細 → 集計シート → 各申告書 → 計算シート を自動連携します。行の「開く」で各画面へ。</p>
      <div class="toolbar"><button class="btn primary" data-action="new-employee">＋ 従業員を追加</button>
      <button class="btn" data-action="sample">サンプルデータを追加</button>
      <button class="btn" data-action="export-list">一覧をCSVで出力</button></div>
      <div class="table-wrap"><table><thead><tr><th>氏名</th><th class="n">⑦給与等</th><th class="n">㉑所得控除</th><th class="n">㉖年調年税額</th>
      <th class="n">⑧徴収済</th><th>区分</th><th class="n">㉗過不足額</th><th>確定申告</th><th>チェック</th><th>操作</th></tr></thead>
      <tbody>${rows || '<tr><td colspan="10">従業員が未登録です。「従業員を追加」から始めてください。</td></tr>'}</tbody></table></div>
      <div class="flex" style="margin-top:12px">
        <div class="card"><h3>年末調整の手順（このアプリでの操作）</h3><ol class="note">
          <li>基本情報を入力し、給与明細PDF（12ヶ月分・賞与）を取り込む → 集計シートに反映</li>
          <li>扶養控除等申告書：扶養親族の生年月日・所得・同居を入力（区分は自動判定）</li>
          <li>基礎・配偶者・特定親族・所得金額調整：その他の所得・配偶者情報を入力（控除額は自動計算）</li>
          <li>保険料控除・住宅借入金等特別控除を入力</li>
          <li>計算シートで①〜㉞を確認（必要なら手入力で上書き）→ 超過・不足額を精算</li>
          <li>Excel出力（関数付き・全シート編集可）／源泉徴収簿を印刷</li></ol></div>
        <div class="card"><h3>集計</h3><div id="dashTotals" class="note"></div></div>
      </div></section>`;
  }
  function updateDashRow(tr) {
    const e = state.employees.find((x) => x.id === tr.dataset.empRow);
    if (!e) return;
    const r = N.calculate(e), L = r.lines;
    const set = (k, v) => { const td = $(`[data-c="${k}"]`, tr); if (td) td.innerHTML = v; };
    ['r7', 'r21', 'r26', 'r8', 'r27'].forEach((k) => set(k, yen(L[k])));
    set('status', `<span class="pill ${r.status === 'refund' ? 'ok' : r.status === 'shortage' ? 'err' : ''}">${esc(r.statusLabel)}</span>`);
    set('kakutei', r.kakuteiRequired ? '<span class="pill warn">要確認</span>' : '');
    const errs = r.warnings.filter((w) => w.level !== 'info').length;
    set('warn', errs ? `<span class="pill warn">${errs}件</span>` : '<span class="pill ok">OK</span>');
    const tot = $('#dashTotals');
    if (tot) {
      const all = state.employees.map((x) => N.calculate(x));
      const refund = all.filter((x) => x.status === 'refund').reduce((a, x) => a + x.lines.r27, 0);
      const short = all.filter((x) => x.status === 'shortage').reduce((a, x) => a + x.lines.r27, 0);
      tot.innerHTML = `対象 ${all.length} 名 ／ 還付合計 <b>${yen(refund)}</b> 円 ／ 追加徴収合計 <b>${yen(short)}</b> 円 ／ 確定申告要確認 ${all.filter((x) => x.kakuteiRequired).length} 名`;
    }
  }

  function profile() {
    return `<section><h2>基本情報</h2><p class="lead">計算シート上部（氏名）と各申告書の共通項目です。</p>
      <div class="grid">
        ${field('氏名', txtIn('profile.name'))}${field('フリガナ', txtIn('profile.kana'))}${field('生年月日', dateIn('profile.birth'))}
        ${field('住所又は居所', txtIn('profile.address'))}${field('給与の支払者の名称', txtIn('profile.employer'))}
        ${field('給与の支払者の所在地', txtIn('profile.employerAddress'))}${field('給与の支払者の法人番号', txtIn('profile.corpNo'))}
        ${field('備考', txtIn('profile.note'))}
      </div></section>`;
  }

  // ---- 給与明細取込 ----
  function importView() {
    const rows = parsed.map((p, i) => `<tr>
      <td>${esc(p.file)}</td>
      <td><select data-parsed="${i}" data-k="kind"><option value="salary" ${p.kind === 'salary' ? 'selected' : ''}>給料・手当等</option><option value="bonus" ${p.kind === 'bonus' ? 'selected' : ''}>賞与等</option></select></td>
      <td><input class="num" style="min-width:48px" data-parsed="${i}" data-k="month" value="${esc(p.month ?? '')}"></td>
      <td><input type="date" data-parsed="${i}" data-k="payDate" value="${esc(p.payDate ?? '')}"></td>
      ${['gross', 'socialTotal', 'smallBiz', 'tax', 'depCount'].map((k) => `<td><input class="num" data-parsed="${i}" data-k="${k}" value="${esc(fmtIn(p[k]))}"></td>`).join('')}
      <td>${p.warnings.map((w) => `<div class="pill warn">${esc(w)}</div>`).join('') || '<span class="pill ok">OK</span>'}</td>
      <td><button class="btn small primary" data-action="apply-parsed" data-i="${i}">反映</button></td></tr>`).join('');
    return `<section><h2>給与明細取込（PDF）</h2>
      <p class="lead">給与明細・賞与明細のPDFをまとめてドロップすると、支給日・総支給金額・社会保険料等・所得税を読み取り、確認後に集計シートへ反映します。
      文字情報のないスキャンPDFは読み取れません（下の「テキスト貼り付け」か手入力を使用）。</p>
      <div class="drop no-print" id="drop" tabindex="0">ここにPDFをドロップ、またはクリックして選択（複数可）
        <input type="file" id="pdfFile" accept="application/pdf" multiple hidden></div>
      <details style="margin-top:12px"><summary>テキスト貼り付けで読み取る</summary>
        <textarea id="pasteText" placeholder="給与明細のテキストを貼り付け"></textarea>
        <button class="btn" data-action="parse-text">読み取る</button></details>
      <h3>読取り結果（反映前に確認・修正できます）</h3>
      <p class="note">「社会保険料等」は健康保険・介護保険・厚生年金・雇用保険・子ども・子育て支援金の合計です。
      反映時は「社会保険料等＋小規模共済等掛金」を集計シートの「社会保険料等の控除額」に、掛金を「うち小規模企業共済等掛金」に入れます。</p>
      <div class="table-wrap"><table><thead><tr><th>ファイル</th><th>区分</th><th>月</th><th>支給月日</th><th class="n">総支給金額</th>
        <th class="n">社会保険料等</th><th class="n">小規模共済等掛金</th><th class="n">所得税</th><th class="n">扶養人数</th><th>確認事項</th><th></th></tr></thead>
        <tbody>${rows || '<tr><td colspan="11">まだ読み取ったPDFはありません。</td></tr>'}</tbody></table></div>
      <div class="toolbar">${parsed.length ? '<button class="btn primary" data-action="apply-all">すべて集計シートへ反映</button><button class="btn" data-action="clear-parsed">読取り結果をクリア</button>' : ''}</div>
      </section>`;
  }
  function bindDrop() {
    const drop = $('#drop'), file = $('#pdfFile');
    if (!drop) return;
    drop.addEventListener('click', () => file.click());
    drop.addEventListener('keydown', (ev) => { if (ev.key === 'Enter' || ev.key === ' ') file.click(); });
    drop.addEventListener('dragover', (ev) => { ev.preventDefault(); drop.classList.add('over'); });
    drop.addEventListener('dragleave', () => drop.classList.remove('over'));
    drop.addEventListener('drop', (ev) => { ev.preventDefault(); drop.classList.remove('over'); readPdfs(ev.dataTransfer.files); });
    file.addEventListener('change', () => readPdfs(file.files));
  }
  async function readPdfs(files) {
    if (!window.pdfjsLib) { alert('PDF読取りライブラリ（pdf.js）を読み込めませんでした。ネットワーク接続を確認してください。'); return; }
    if (!pdfjsLib.GlobalWorkerOptions.workerSrc)
      pdfjsLib.GlobalWorkerOptions.workerSrc = 'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js';
    for (const f of Array.from(files)) {
      try {
        const items = await pdfItems(await f.arrayBuffer());
        if (!items.length) { parsed.push(emptyParsed(f.name, '文字情報がありません（スキャン画像の可能性）。手入力してください')); continue; }
        parsed.push(toParsed(f.name, P.parseItems(items)));
      } catch (err) { parsed.push(emptyParsed(f.name, 'PDFを読み取れませんでした：' + err.message)); }
    }
    parsed.sort((a, b) => (a.kind === b.kind ? (a.month || 0) - (b.month || 0) : a.kind === 'salary' ? -1 : 1));
    render();
  }
  async function pdfItems(buf) {
    const doc = await pdfjsLib.getDocument({ data: buf }).promise;
    const items = [];
    for (let p = 1; p <= doc.numPages; p++) {
      const page = await doc.getPage(p);
      const vp = page.getViewport({ scale: 1 });
      const tc = await page.getTextContent();
      tc.items.forEach((it) => {
        if (!it.str || !it.str.trim()) return;
        const [, , , d, x, y] = it.transform;
        const h = Math.abs(d) || it.height || 10;
        items.push({ str: it.str, x, y: vp.height - y - h, w: it.width, h, page: p });
      });
    }
    return items;
  }
  const toParsed = (file, r) => ({
    file, kind: r.kind, month: r.month, payDate: r.payDate, gross: r.gross, socialTotal: r.social, smallBiz: r.smallBiz,
    tax: r.tax, depCount: r.depCount, warnings: r.warnings,
  });
  const emptyParsed = (file, msg) => ({ file, kind: 'salary', month: null, payDate: '', gross: null, socialTotal: null, smallBiz: null, tax: null, depCount: null, warnings: [msg] });

  function applyParsed(i) {
    const p = parsed[i], e = emp();
    if (!p) return false;
    const n = (v) => (v === null || v === undefined || v === '' ? '' : N.num(v));
    const row = { payDate: p.payDate || '', gross: n(p.gross), social: n(p.socialTotal) === '' && n(p.smallBiz) === '' ? '' : (n(p.socialTotal) || 0) + (n(p.smallBiz) || 0),
      smallBiz: n(p.smallBiz), tax: n(p.tax), depCount: n(p.depCount) };
    if (p.kind === 'salary') {
      const m = N.num(p.month);
      if (!(m >= 1 && m <= 12)) { alert(`${p.file}：月（1〜12）を入力してください`); return false; }
      Object.assign(e.payroll.salary[m - 1], row);
    } else {
      let idx = e.payroll.bonus.findIndex((b) => b.payDate && b.payDate === row.payDate);
      if (idx < 0) idx = e.payroll.bonus.findIndex((b) => !N.num(b.gross));
      if (idx < 0) { alert('賞与等の行（4行）が埋まっています'); return false; }
      Object.assign(e.payroll.bonus[idx], row);
    }
    p.applied = true;
    return true;
  }

  // ---- 集計シート ----
  function agg() {
    const row = (base, r, label) => `<tr><td>${label}</td><td>${dateIn(`${base}.payDate`)}</td><td>${numIn(`${base}.gross`)}</td>
      <td>${numIn(`${base}.social`)}</td><td class="n" data-g="${base}"></td><td>${numIn(`${base}.depCount`, 'style="min-width:48px"')}</td>
      <td>${numIn(`${base}.tax`)}</td><td>${numIn(`${base}.adj`)}</td><td class="n" data-kk="${base}"></td><td>${numIn(`${base}.smallBiz`)}</td></tr>`;
    const sal = emp().payroll.salary.map((_, i) => row(`payroll.salary.${i}`, i, `${i + 1}月`)).join('');
    const bon = emp().payroll.bonus.map((_, i) => row(`payroll.bonus.${i}`, i, `賞与${i + 1}`)).join('');
    const tot = (k) => `<td class="n">${out(`aggregate.${k}`, '')}</td>`;
    return `<section><h2>集計シート</h2>
      <p class="lead">給料・手当等（12ヶ月）と賞与等を入力します。合計は計算シートの ①③④⑥⑫ に自動反映します（元Excelと同じ列構成）。</p>
      <div class="toolbar no-print"><button class="btn" data-action="fill-dep">扶養親族等の数を全月に入力（参考値）</button>
      <button class="btn" data-action="write-adj">年末調整の過不足税額を12月に記入</button></div>
      <div class="table-wrap"><table><thead><tr><th>月区分</th><th>支給月日</th><th class="n">総支給金額</th><th class="n">社会保険料等の控除額</th>
      <th class="n">社会保険料等控除後</th><th class="n">扶養親族等の数</th><th class="n">算出税額</th><th class="n">年末調整による過不足税額</th>
      <th class="n">差引徴収税額</th><th class="n">うち小規模企業共済等掛金</th></tr></thead>
      <tbody>${sal}<tr class="total"><td>計</td><td></td>${tot('salary.gross')}${tot('salary.social')}<td></td><td></td>${tot('salary.tax')}${tot('salary.adj')}<td></td>${tot('salary.smallBiz')}</tr>
      ${bon}<tr class="total"><td>計</td><td></td>${tot('bonus.gross')}${tot('bonus.social')}<td></td><td></td>${tot('bonus.tax')}${tot('bonus.adj')}<td></td>${tot('bonus.smallBiz')}</tr></tbody></table></div>
      <p class="note">過不足税額は超過額をマイナス、不足額をプラスで入力（元Excelの「入力のしかた（集計シート）」と同じ）。③⑥は「算出税額」の合計を使います。</p></section>`;
  }
  function updateAggRows() {
    $$('[data-g]').forEach((td) => { const r = getPath(emp(), td.dataset.g); td.textContent = r && (r.gross !== '' || r.social !== '') ? yen(N.num(r.gross) - N.num(r.social)) : ''; });
    $$('td[data-kk]').forEach((td) => { const r = getPath(emp(), td.dataset.kk); td.textContent = r && (r.tax !== '' || r.adj !== '') ? yen(N.num(r.tax) + N.num(r.adj)) : ''; });
  }

  // ---- 扶養控除等申告書 ----
  function fuyo() {
    const deps = emp().fuyo.dependents;
    const rows = deps.map((d, i) => `<tr>
      <td>${txtIn(`fuyo.dependents.${i}.name`)}</td><td>${txtIn(`fuyo.dependents.${i}.relation`, 'list="relations" style="min-width:64px"')}</td>
      <td>${dateIn(`fuyo.dependents.${i}.birth`)}</td><td class="n" data-depcls="${i}" data-k="age"></td>
      <td>${numIn(`fuyo.dependents.${i}.income`)}</td>
      <td style="text-align:center"><input type="checkbox" data-bind="fuyo.dependents.${i}.cohabit" data-type="bool" ${d.cohabit ? 'checked' : ''} aria-label="同居"></td>
      <td>${sel(`fuyo.dependents.${i}.disability`, [['none', 'なし'], ['general', '一般の障害者'], ['special', '特別障害者']])}</td>
      <td style="text-align:center"><input type="checkbox" data-bind="fuyo.dependents.${i}.nonResident" data-type="bool" ${d.nonResident ? 'checked' : ''} aria-label="非居住者"></td>
      <td>${sel(`fuyo.dependents.${i}.nrReason`, [['', '—'], ['留学', '留学'], ['障害者', '障害者'], ['38万円以上の送金', '38万円以上の送金']])}</td>
      <td data-depcls="${i}" data-k="cat"></td><td class="n" data-depcls="${i}" data-k="deduction"></td>
      <td class="n" data-depcls="${i}" data-k="tokutei"></td><td class="n" data-depcls="${i}" data-k="disability"></td>
      <td><button class="btn small danger" data-action="del-row" data-list="fuyo.dependents" data-i="${i}">削除</button></td></tr>`).join('');
    return `<section><h2>扶養控除等（異動）申告書</h2>
      <p class="lead">生年月日（令和8年12月31日時点の年齢）・合計所得金額の見積額・同居の有無から、控除区分を自動判定し計算シートⓐ〜Ⓘに反映します。
      扶養親族の所得要件は令和8年分から <b>62万円以下</b>（給与収入のみなら136万円以下）です。</p>
      <h3>本人</h3><div class="grid">
        ${field('障害者', sel('fuyo.self.disability', [['none', 'なし'], ['general', '一般の障害者'], ['special', '特別障害者']]))}
        ${field('寡婦・ひとり親', sel('fuyo.self.widow', [['none', 'なし'], ['widow', '寡婦'], ['single_parent', 'ひとり親']]))}
        <div class="field"><span>勤労学生</span>${chk('fuyo.self.student', '勤労学生に該当')}</div></div>
      <h3>控除対象扶養親族・特定親族・16歳未満の扶養親族</h3>
      <datalist id="relations">${['子', '父', '母', '祖父', '祖母', '義父', '義母', '孫', '兄', '姉', '弟', '妹', 'その他'].map((r) => `<option value="${r}">`).join('')}</datalist>
      <div class="table-wrap"><table><thead><tr><th>氏名</th><th>続柄</th><th>生年月日</th><th class="n">年齢</th><th class="n">合計所得見積額</th><th>同居</th>
      <th>障害者</th><th>非居住者</th><th>非居住者の要件</th><th>区分（自動）</th><th class="n">扶養控除</th><th class="n">特定親族特別控除</th><th class="n">障害者控除</th><th></th></tr></thead>
      <tbody>${rows || '<tr><td colspan="14">扶養親族は未登録です。</td></tr>'}</tbody></table></div>
      <div class="toolbar"><button class="btn" data-action="add-dep">＋ 扶養親族を追加</button></div>
      <p class="note">同居老親等＝70歳以上で本人又は配偶者の直系尊属（父母・祖父母等）かつ同居。障害者で同居の「特別障害者」は同居特別障害者（75万円）として計算します。
      配偶者は「基礎・配偶者…」画面で入力します（同一生計配偶者の障害者控除も同画面）。</p></section>
      <section><h3>計算シートへの反映</h3><div class="table-wrap"><table><tbody>
      <tr><th>Ⓐ 一般の控除対象扶養親族</th><td class="n">${out('fuyo.box.A', '')} 人</td><td class="n">${out('fuyo.amounts.A', '')}</td>
          <th>Ⓔ 一般の障害者</th><td class="n">${out('fuyo.box.E', '')} 人</td><td class="n">${out('fuyo.amounts.E', '')}</td></tr>
      <tr><th>Ⓑ 特定扶養親族</th><td class="n">${out('fuyo.box.B', '')} 人</td><td class="n">${out('fuyo.amounts.B', '')}</td>
          <th>Ⓕ 同居特別障害者以外の特別障害者</th><td class="n">${out('fuyo.box.F', '')} 人</td><td class="n">${out('fuyo.amounts.F', '')}</td></tr>
      <tr><th>Ⓒ 同居老親等</th><td class="n">${out('fuyo.box.C', '')} 人</td><td class="n">${out('fuyo.amounts.C', '')}</td>
          <th>Ⓖ 同居特別障害者</th><td class="n">${out('fuyo.box.G', '')} 人</td><td class="n">${out('fuyo.amounts.G', '')}</td></tr>
      <tr><th>Ⓓ 同居老親等以外の老人扶養親族</th><td class="n">${out('fuyo.box.D', '')} 人</td><td class="n">${out('fuyo.amounts.D', '')}</td>
          <th>Ⓗ 寡婦・ひとり親</th><td>${out('fuyo.box.H', '')}</td><td class="n">${out('fuyo.amounts.H', '')}</td></tr>
      <tr><th></th><td></td><td></td><th>Ⓘ 勤労学生</th><td>${out('fuyo.box.I', '')}</td><td class="n">${out('fuyo.amounts.I', '')}</td></tr>
      <tr class="total"><td colspan="4">⑲ 扶養控除額及び障害者等の控除額の合計額</td><td colspan="2" class="n">${out('lines.r19', '')}</td></tr>
      </tbody></table></div><p class="note">源泉徴収税額表の「扶養親族等の数」（参考）：${out('withholdingCount', '')} 人</p></section>`;
  }

  // ---- 基礎・配偶者・特定親族・所得金額調整 ----
  function kiso() {
    return `<section><h2>基礎控除申告書</h2><p class="lead">本人の合計所得金額の見積額から基礎控除額（令和8年分：489万円以下は104万円）を自動判定し、⑳に反映します。</p>
      <div class="grid">${field('給与所得の金額（⑪から自動）', `<input class="num" disabled data-out-val="lines.r11">`)}
        ${field('給与所得以外の所得の合計額', numIn('kiso.otherIncome'))}
        <div class="field"><span>合計所得金額の見積額</span><b class="n">${out('totalIncome', '')} 円</b></div>
        <div class="field"><span>基礎控除の額 ⑳</span><b class="n">${out('lines.r20', '')} 円</b></div></div></section>
      <section><h2>配偶者控除等申告書</h2><p class="lead">本人の合計所得（区分Ⅰ）と配偶者の合計所得・年齢（区分Ⅱ）から配偶者（特別）控除額を自動計算し、⑰に反映します。</p>
      <div class="grid"><div class="field"><span>配偶者</span>${chk('spouse.has', '配偶者がいる')}</div>
        ${field('配偶者の氏名', txtIn('spouse.name'))}${field('生年月日', dateIn('spouse.birth'))}
        ${field('配偶者の合計所得金額の見積額', numIn('spouse.income'))}
        ${field('障害者（同一生計配偶者の場合）', sel('spouse.disability', [['none', 'なし'], ['general', '一般の障害者'], ['special', '特別障害者']]))}
        <div class="field"><span>同居</span>${chk('spouse.cohabit', '同居している')}</div>
        <div class="field"><span>非居住者</span>${chk('spouse.nonResident', '非居住者である配偶者')}</div></div>
      <div class="table-wrap" style="margin-top:10px"><table><tbody>
        <tr><th>区分Ⅰ（本人）</th><td>${out('spouse.band', '')}</td><th>区分Ⅱ（配偶者）</th><td>${out('spouse.class2', '')}</td>
        <th>種類</th><td>${out('spouse.kind', '')}</td><th>⑰ 控除額</th><td class="n">${out('lines.r17', '')}</td></tr></tbody></table></div>
      <p class="note">${out('spouse.reason', '')}</p></section>
      <section><h2>特定親族特別控除申告書</h2><p class="lead">扶養控除等申告書で「特定親族」（19〜22歳・合計所得62万円超123万円以下）と判定された人を自動転記し、⑱に反映します。</p>
      <div class="table-wrap"><table><thead><tr><th>氏名</th><th>続柄</th><th class="n">年齢</th><th class="n">合計所得見積額</th><th class="n">特定親族特別控除の額</th></tr></thead>
      <tbody>${tokuteiRows()}</tbody></table></div><p class="note">⑱ 合計：<b>${out('lines.r18', '')}</b> 円</p></section>
      <section><h2>所得金額調整控除申告書</h2><p class="lead">給与収入850万円超で、本人・同一生計配偶者・扶養親族が特別障害者、又は23歳未満の扶養親族がいる場合に適用（最高15万円）。</p>
      <div class="grid">${field('適用の判定', sel('chosei.mode', [['auto', '自動判定'], ['yes', '有（手動）'], ['no', '無（手動）']]))}
        <div class="field"><span>自動判定の結果</span><span data-out="choseiAutoLabel"></span></div>
        <div class="field"><span>⑩ 所得金額調整控除額</span><b class="n">${out('lines.r10', '')} 円</b></div></div></section>`;
  }
  function tokuteiRows() {
    const deps = emp().fuyo.dependents.filter((d) => d && (d.name || d.birth));
    const rows = deps.map((d) => ({ d, c: N.classifyDependent(d) })).filter((x) => x.c.category === '特定親族');
    return rows.map(({ d, c }) => `<tr><td>${esc(d.name)}</td><td>${esc(d.relation)}</td><td class="n">${c.age}</td><td class="n">${yen(c.income)}</td><td class="n">${yen(c.tokutei)}</td></tr>`).join('')
      || '<tr><td colspan="5">該当者はいません。</td></tr>';
  }

  // ---- 保険料控除申告書 ----
  function hoken() {
    const H = emp().hoken;
    const lifeRows = H.life.map((x, i) => `<tr><td>${txtIn(`hoken.life.${i}.company`)}</td>
      <td>${sel(`hoken.life.${i}.kind`, [['general', '一般の生命保険料'], ['care', '介護医療保険料'], ['pension', '個人年金保険料']])}</td>
      <td>${sel(`hoken.life.${i}.era`, [['new', '新'], ['old', '旧']])}</td><td>${numIn(`hoken.life.${i}.amount`)}</td>
      <td><button class="btn small danger" data-action="del-row" data-list="hoken.life" data-i="${i}">削除</button></td></tr>`).join('');
    const quakeRows = H.quake.map((x, i) => `<tr><td>${txtIn(`hoken.quake.${i}.company`)}</td>
      <td>${sel(`hoken.quake.${i}.kind`, [['quake', '地震保険料'], ['oldlong', '旧長期損害保険料']])}</td><td>${numIn(`hoken.quake.${i}.amount`)}</td>
      <td><button class="btn small danger" data-action="del-row" data-list="hoken.quake" data-i="${i}">削除</button></td></tr>`).join('');
    const socRows = H.social.map((x, i) => `<tr><td>${txtIn(`hoken.social.${i}.kind`)}</td><td>${txtIn(`hoken.social.${i}.payer`)}</td>
      <td>${txtIn(`hoken.social.${i}.person`)}</td><td>${numIn(`hoken.social.${i}.amount`)}</td>
      <td style="text-align:center"><input type="checkbox" data-bind="hoken.social.${i}.nationalPension" data-type="bool" ${x.nationalPension ? 'checked' : ''} aria-label="国民年金保険料等"></td>
      <td><button class="btn small danger" data-action="del-row" data-list="hoken.social" data-i="${i}">削除</button></td></tr>`).join('');
    const sbRows = H.smallBiz.map((x, i) => `<tr><td>${sel(`hoken.smallBiz.${i}.kind`, [['小規模企業共済', '独立行政法人中小企業基盤整備機構の共済契約の掛金'], ['個人型確定拠出年金', '確定拠出年金法に規定する個人型年金加入者掛金'], ['心身障害者扶養共済', '心身障害者扶養共済制度に関する契約の掛金']])}</td>
      <td>${numIn(`hoken.smallBiz.${i}.amount`)}</td><td><button class="btn small danger" data-action="del-row" data-list="hoken.smallBiz" data-i="${i}">削除</button></td></tr>`).join('');
    return `<section><h2>保険料控除申告書</h2>
      <p class="lead">支払保険料等を入力すると、控除額を国税庁の計算式（Ⅰ・Ⅱ・Ⅲ）で自動計算し ⑬〜⑯ に反映します。
      令和8年分は <b>23歳未満の扶養親族がいる場合</b>、新生命保険料（一般）に計算式Ⅱ（最高6万円）を自動適用します。</p>
      <h3>生命保険料控除 → ⑮</h3>
      <div class="table-wrap"><table><thead><tr><th>保険会社等の名称</th><th>区分</th><th>新・旧</th><th class="n">支払保険料等</th><th></th></tr></thead><tbody>${lifeRows}</tbody></table></div>
      <div class="toolbar"><button class="btn" data-action="add-row" data-list="hoken.life">＋ 追加</button></div>
      <div class="table-wrap"><table><tbody>
        <tr><th>一般の生命保険料（新/旧）</th><td class="n">${out('life.newGen', '')} ／ ${out('life.oldGen', '')}</td><th>控除額</th><td class="n">${out('life.general', '')}</td></tr>
        <tr><th>介護医療保険料</th><td class="n">${out('life.care', '')}</td><th>控除額</th><td class="n">${out('life.careDed', '')}</td></tr>
        <tr><th>個人年金保険料（新/旧）</th><td class="n">${out('life.newPen', '')} ／ ${out('life.oldPen', '')}</td><th>控除額</th><td class="n">${out('life.pension', '')}</td></tr>
        <tr class="total"><td colspan="3">生命保険料控除額計（最高120,000円）⑮　<span class="note">23歳未満の扶養親族：<span data-out="under23Label"></span></span></td><td class="n">${out('lines.r15', '')}</td></tr></tbody></table></div>
      <h3>地震保険料控除 → ⑯</h3>
      <div class="table-wrap"><table><thead><tr><th>保険会社等の名称</th><th>区分</th><th class="n">支払保険料等</th><th></th></tr></thead><tbody>${quakeRows}</tbody></table></div>
      <div class="toolbar"><button class="btn" data-action="add-row" data-list="hoken.quake">＋ 追加</button></div>
      <p class="note">地震保険料 ${out('quake.quakePaid', '')} 円 ／ 旧長期損害保険料 ${out('quake.oldLongPaid', '')} 円 → 控除額 <b>${out('lines.r16', '')}</b> 円（最高50,000円）</p>
      <h3>社会保険料控除（本人が直接支払った分）→ ⑬</h3>
      <div class="table-wrap"><table><thead><tr><th>社会保険の種類</th><th>保険料支払先</th><th>負担する人</th><th class="n">支払保険料</th><th>国民年金保険料等</th><th></th></tr></thead><tbody>${socRows}</tbody></table></div>
      <div class="toolbar"><button class="btn" data-action="add-row" data-list="hoken.social">＋ 追加</button></div>
      <p class="note">合計 <b>${out('lines.r13', '')}</b> 円（うち国民年金保険料等 ${out('nationalPension', '')} 円）</p>
      <h3>小規模企業共済等掛金控除（本人が直接支払った分）→ ⑭</h3>
      <div class="table-wrap"><table><thead><tr><th>種類</th><th class="n">支払掛金</th><th></th></tr></thead><tbody>${sbRows}</tbody></table></div>
      <div class="toolbar"><button class="btn" data-action="add-row" data-list="hoken.smallBiz">＋ 追加</button></div>
      <p class="note">合計 <b>${out('lines.r14', '')}</b> 円。給与から天引きされた掛金は集計シートの「社会保険料等」に含めます（⑫）。</p></section>`;
  }

  function jutaku() {
    return `<section><h2>住宅借入金等特別控除申告書</h2>
      <p class="lead">税務署から送付された「年末調整のための（特定増改築等）住宅借入金等特別控除証明書」と金融機関の「年末残高証明書」から入力します。
      控除額は100円未満切捨て・最高60万円。計算明細書で算出した金額がある場合は「直接入力」を優先します。2年目以降のみ年末調整で控除できます（初年度は確定申告）。</p>
      <div class="grid">${field('住宅借入金等の年末残高（限度額適用後）', numIn('jutaku.balance'))}
        ${field('控除率', sel('jutaku.rate', [['0.007', '0.7%（令和4年以後居住）'], ['0.01', '1.0%（令和3年以前居住）']]))}
        ${field('控除限度額（証明書の金額）', numIn('jutaku.limit'))}${field('控除額を直接入力', numIn('jutaku.direct'))}
        <div class="field"><span>㉔ 住宅借入金等特別控除額</span><b class="n">${out('lines.r24', '')} 円</b></div></div>
      <div class="card" style="margin-top:12px"><div class="check">${chk('kakutei.housingFirstYear', '今年が控除の初年度（確定申告が必要）')}</div></div></section>`;
  }

  // ---- 計算シート ----
  const CALC_ROWS = [
    ['r1', '①', '給料・手当等（金額）', true], ['r3', '③', '給料・手当等（税額）', true], ['r4', '④', '賞与等（金額）', true], ['r6', '⑥', '賞与等（税額）', true],
    ['r7', '⑦', '金額 計', false], ['r8', '⑧', '税額 計', false], ['r9', '⑨', '給与所得控除後の給与等の金額', true], ['r10', '⑩', '所得金額調整控除額', true],
    ['r11', '⑪', '給与所得控除後の給与等の金額（調整控除後）', true], ['r12', '⑫', '社会保険料等控除額（給与等からの控除分）', true],
    ['r13', '⑬', '社会保険料等控除額（申告による社会保険料の控除分）', true], ['r14', '⑭', '社会保険料等控除額（申告による小規模企業共済等掛金の控除分）', true],
    ['r15', '⑮', '生命保険料の控除額', true], ['r16', '⑯', '地震保険料の控除額', true], ['r17', '⑰', '配偶者（特別）控除額', true], ['r18', '⑱', '特定親族特別控除額', true],
    ['r19', '⑲', '扶養控除額及び障害者等の控除額の合計額', true], ['r20', '⑳', '基礎控除額', true], ['r21', '㉑', '所得控除額の合計額', false],
    ['r22', '㉒', '差引課税給与所得金額（1,000円未満切捨て）', true], ['r23', '㉓', '算出所得税額', true], ['r24', '㉔', '住宅借入金等特別控除額', true],
    ['r25', '㉕', '年調所得税額（㉓−㉔）', true], ['r26', '㉖', '年調年税額（㉕×102.1%、100円未満切捨て）', true],
  ];
  function calc() {
    const rows = CALC_ROWS.map(([k, mark, label, editable]) => `<tr><td class="mark">${mark}</td><td class="label">${label}</td>
      <td class="n" data-calc-auto="${k}"></td><td>${editable ? numIn(`overrides.${k}`, 'placeholder="自動"') : ''}</td><td class="n"><b>${out(`lines.${k}`, '')}</b></td></tr>`).join('');
    return `<section><h2>年末調整計算シート（令和８年用）</h2>
      <p class="lead">各シート・申告書から自動計算した値です。「手入力」欄に金額を入れると自動計算より優先されます（空欄に戻すと自動計算）。元Excelの欄番号①〜㉞に対応しています。</p>
      <div class="toolbar no-print"><button class="btn" data-action="clear-overrides">手入力をすべて解除</button><button class="btn" data-action="print">印刷</button></div>
      <div class="table-wrap"><table class="calc-table"><thead><tr><th>欄</th><th>区分</th><th class="n">自動計算</th><th class="n">手入力（上書き）</th><th class="n">採用値</th></tr></thead>
      <tbody>${rows}
      <tr class="total"><td class="mark">㉗</td><td class="label">${out('statusLabel', '')}（㉖−⑧）</td><td></td><td></td><td class="n"><b>${out('lines.r27', '')}</b></td></tr>
      </tbody></table></div>
      <h3>過不足額の精算</h3>
      <div class="table-wrap"><table class="calc-table"><tbody>
        <tr><td class="mark">㉘</td><td class="label">超過額：本年最後の給与から徴収する税額に充当する金額</td><td>${numIn('settle.r28')}</td><td class="n">${out('lines.r28', '')}</td></tr>
        <tr><td class="mark">㉙</td><td class="label">超過額：未払給与に係る未徴収の税額に充当する金額</td><td>${numIn('settle.r29')}</td><td class="n">${out('lines.r29', '')}</td></tr>
        <tr><td class="mark">㉚</td><td class="label">差引還付する税額</td><td></td><td class="n">${out('lines.r30', '')}</td></tr>
        <tr><td class="mark">㉛</td><td class="label">同上のうち本年中に還付する金額（空欄＝㉚の全額）</td><td>${numIn('settle.r31', 'placeholder="自動"')}</td><td class="n">${out('lines.r31', '')}</td></tr>
        <tr><td class="mark">㉜</td><td class="label">同上のうち翌年において還付する金額</td><td></td><td class="n">${out('lines.r32', '')}</td></tr>
        <tr><td class="mark">㉝</td><td class="label">不足額：本年最後の給与から徴収する金額（空欄＝㉗の全額）</td><td>${numIn('settle.r33', 'placeholder="自動"')}</td><td class="n">${out('lines.r33', '')}</td></tr>
        <tr><td class="mark">㉞</td><td class="label">不足額：翌年に繰り越して徴収する金額</td><td></td><td class="n">${out('lines.r34', '')}</td></tr>
      </tbody></table></div>
      <h3>参考欄</h3><div class="grid">
        <div class="field"><span>所得金額調整控除の適用の有無</span><span data-out="choseiLabel"></span></div>
        <div class="field"><span>配偶者の合計所得金額</span><span class="n">${out('spouse.income', '')}</span></div>
        <div class="field"><span>旧長期損害保険料支払額</span><span class="n">${out('quake.oldLongPaid', '')}</span></div>
        <div class="field"><span>⑫のうち小規模企業共済等掛金の金額</span><span class="n">${out('smallBizFromPayroll', '')}</span></div>
        <div class="field"><span>⑬のうち国民年金保険料等の金額</span><span class="n">${out('nationalPension', '')}</span></div></div></section>`;
  }

  function boki() {
    const e = emp();
    const line = (r, label) => { const p = getPath(e, r); return `<tr><td>${label}</td><td>${esc(p.payDate || '')}</td><td class="n">${yen(p.gross)}</td><td class="n">${yen(p.social)}</td>
      <td class="n">${p.gross !== '' ? yen(N.num(p.gross) - N.num(p.social)) : ''}</td><td class="n">${esc(p.depCount)}</td><td class="n">${yen(p.tax)}</td><td class="n">${yen(p.adj)}</td>
      <td class="n">${p.tax !== '' || p.adj !== '' ? yen(N.num(p.tax) + N.num(p.adj)) : ''}</td></tr>`; };
    const rows = e.payroll.salary.map((_, i) => line(`payroll.salary.${i}`, `${i + 1}月`)).join('') + e.payroll.bonus.map((_, i) => line(`payroll.bonus.${i}`, `賞与${i + 1}`)).join('');
    const yrows = CALC_ROWS.concat([['r27', '㉗', ''], ['r30', '㉚', '差引還付する税額'], ['r31', '㉛', '本年中に還付する金額'], ['r32', '㉜', '翌年において還付する金額'], ['r33', '㉝', '本年最後の給与から徴収する金額'], ['r34', '㉞', '翌年に繰り越して徴収する金額']])
      .map(([k, m, l]) => `<tr><td class="mark">${m}</td><td>${k === 'r27' ? out('statusLabel', '') : l}</td><td class="n">${out('lines.' + k, '')}</td></tr>`).join('');
    return `<section><h2>令和8年分 給与所得に対する源泉徴収簿</h2>
      <p class="lead">${esc(e.profile.name)}（${esc(e.profile.kana)}） ／ ${esc(e.profile.employer)}　— 集計シートと計算シートから自動作成（印刷用）</p>
      <div class="toolbar no-print"><button class="btn" data-action="print">印刷</button></div>
      <div class="flex"><div class="table-wrap"><table><thead><tr><th>区分</th><th>支給月日</th><th class="n">総支給金額</th><th class="n">社会保険料等</th><th class="n">差引金額</th>
        <th class="n">扶養数</th><th class="n">算出税額</th><th class="n">年調過不足</th><th class="n">差引徴収税額</th></tr></thead><tbody>${rows}</tbody></table></div>
      <div class="table-wrap"><table><thead><tr><th>欄</th><th>年末調整</th><th class="n">金額</th></tr></thead><tbody>${yrows}</tbody></table></div></div></section>`;
  }

  function kakutei() {
    return `<section><h2>確定申告チェック</h2>
      <p class="lead">年末調整で完結しないケースを判定します（国税庁 No.1900「給与所得者で確定申告が必要な人」、所得税の確定申告）。</p>
      <div class="grid" style="grid-template-columns:1fr">
        ${chk('kakutei.multipleEmployers', '2か所以上から給与を受けている')}
        ${chk('kakutei.medical', '医療費控除・セルフメディケーション税制を受けたい')}
        ${chk('kakutei.donation', '寄附金控除を受けたい（ワンストップ特例を使わないふるさと納税等）')}
        ${chk('kakutei.housingFirstYear', '住宅借入金等特別控除の初年度')}
        ${chk('kakutei.casualty', '災害・盗難等で雑損控除を受けたい')}</div>
      <h3>判定結果</h3><ul class="msgs" id="kakuteiList"></ul>
      <p class="note">給与以外の所得（「基礎・配偶者…」画面で入力）が20万円超、給与収入2,000万円超は自動判定します。
      参考：<a href="https://www.nta.go.jp/taxes/shiraberu/taxanswer/shotoku/1900.htm" target="_blank" rel="noopener">No.1900</a> ／
      <a href="https://www.nta.go.jp/taxes/shiraberu/shinkoku/kakutei.htm" target="_blank" rel="noopener">所得税の確定申告</a></p></section>`;
  }

  function data() {
    return `<section><h2>Excel出力</h2>
      <p class="lead">国税庁「年末調整計算シート（令和８年用）」のシート構成を踏襲したExcelを出力します。
      集計シート → 計算シート、各申告書 → 計算シートが<b>すべて関数でつながっており、全シート編集可能</b>（保護なし）です。控除額は「控除テーブル」シートで変更できます。</p>
      <div class="toolbar"><button class="btn primary" data-action="excel" ${emp() ? '' : 'disabled'}>この従業員のExcelを出力</button>
      <button class="btn" data-action="excel-all" ${state.employees.length ? '' : 'disabled'}>全員分を順に出力</button></div></section>
      <section><h2>データ管理</h2><p class="lead">データはこのブラウザ内に保存されています。定期的にバックアップ（JSON）を保存してください。</p>
      <div class="toolbar"><button class="btn" data-action="backup">バックアップ（JSON）を保存</button>
      <label class="btn">バックアップを読み込む<input type="file" id="restoreFile" accept="application/json" hidden></label>
      <button class="btn danger" data-action="wipe">全データを削除</button></div></section>`;
  }

  // ------------------------------------------------------------------ 追加の出力欄
  function extraOutputs() {
    if (!result) return;
    result.choseiAutoLabel = result.choseiAuto ? '要件に該当（850万円超なら適用）' : '要件に該当なし';
    result.choseiLabel = !result.choseiApplicable ? '無' : result.lines.r7 > 8500000 ? '有' : '有（給与収入850万円以下のため控除額は0円）';
    result.under23Label = result.hasUnder23Dependent ? 'あり（計算式Ⅱを適用）' : 'なし';
    $$('[data-out-val]').forEach((el) => { el.value = yen(getPath(result, el.dataset.outVal)); });
    const kl = $('#kakuteiList');
    if (kl) kl.innerHTML = result.kakutei.length
      ? result.kakutei.map((k) => `<li class="${k.need ? 'error' : 'warn'}">${k.need ? '【確定申告が必要】' : '【確定申告で控除】'}${esc(k.msg)}</li>`).join('')
      : '<li class="info">年末調整で完了します（確定申告は不要と判定）。</li>';
  }
  // ------------------------------------------------------------------ 操作
  function addEmployee(e) {
    state.employees.push(e); state.currentId = e.id; save();
  }
  async function exportExcel(e) {
    if (!window.ExcelJS) { alert('Excel出力ライブラリ（ExcelJS）を読み込めませんでした。ネットワーク接続を確認してください。'); return; }
    const r = N.calculate(e);
    const wb = W.build(window.ExcelJS, e, r);
    const buf = await wb.xlsx.writeBuffer();
    download(new Blob([buf], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' }), `年末調整計算シート_令和8年分_${e.profile.name || e.id}.xlsx`);
  }
  function download(blob, name) {
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob); a.download = name; document.body.appendChild(a); a.click();
    setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 1000);
  }
  function sampleEmployee() {
    const e = N.blankEmployee('見本 太郎');
    e.profile.kana = 'ミホン タロウ'; e.profile.employer = '株式会社サンプル';
    const g = [263129, 311123, 257125, 309071, 301413, 334686, 279125, 338823, 319518, 281114, 281114, 281114];
    const s = [18021, 19885, 18208, 19205, 19379, 22825, 20557, 42506, 21409, 21783, 21783, 21783];
    e.payroll.salary.forEach((r, i) => Object.assign(r, { payDate: `2026-${String(i + 1).padStart(2, '0')}-25`, gross: g[i], social: s[i], depCount: 2, tax: 3500 }));
    e.payroll.bonus[0] = { payDate: '2026-07-10', gross: 400000, social: 60000, smallBiz: '', depCount: 2, tax: 12000, adj: '' };
    e.spouse = { has: true, name: '見本 花子', birth: '1986-05-05', income: 800000, disability: 'none', cohabit: true, nonResident: false };
    e.fuyo.dependents = [
      { name: '見本 一郎', relation: '子', birth: '2006-06-06', income: 0, cohabit: true, disability: 'none' },
      { name: '見本 次子', relation: '子', birth: '2016-09-09', income: 0, cohabit: true, disability: 'none' },
    ];
    e.hoken.life = [{ company: 'サンプル生命', kind: 'general', era: 'new', amount: 96000 }, { company: 'サンプル生命', kind: 'care', era: 'new', amount: 36000 }];
    e.hoken.quake = [{ company: 'サンプル損保', kind: 'quake', amount: 18000 }];
    return e;
  }

  document.addEventListener('click', async (ev) => {
    const tabBtn = ev.target.closest('[data-tab]');
    if (tabBtn) { tab = tabBtn.dataset.tab; render(); $('#main').focus(); return; }
    const b = ev.target.closest('[data-action]');
    if (!b) return;
    const e = emp();
    const act = b.dataset.action;
    if (act === 'new-employee') { addEmployee(N.blankEmployee('')); tab = 'profile'; render(); }
    else if (act === 'sample') { addEmployee(sampleEmployee()); render(); }
    else if (act === 'open') { state.currentId = b.dataset.id; tab = 'agg'; save(); render(); }
    else if (act === 'dup') {
      const src = state.employees.find((x) => x.id === b.dataset.id);
      const c = JSON.parse(JSON.stringify(src)); c.id = N.blankEmployee().id; c.profile.name += '（コピー）'; addEmployee(c); render();
    } else if (act === 'del') {
      const src = state.employees.find((x) => x.id === b.dataset.id);
      if (confirm(`${src.profile.name || 'この従業員'} を削除しますか？（元に戻せません）`)) {
        state.employees = state.employees.filter((x) => x.id !== b.dataset.id);
        state.currentId = state.employees[0] ? state.employees[0].id : null; save(); render();
      }
    } else if (act === 'add-dep') { e.fuyo.dependents.push({ name: '', relation: '子', birth: '', income: '', cohabit: true, disability: 'none', nonResident: false, nrReason: '' }); save(); render(); }
    else if (act === 'add-row') {
      const blank = { 'hoken.life': { company: '', kind: 'general', era: 'new', amount: '' }, 'hoken.quake': { company: '', kind: 'quake', amount: '' },
        'hoken.social': { kind: '', payer: '', person: '', amount: '', nationalPension: false }, 'hoken.smallBiz': { kind: '個人型確定拠出年金', amount: '' } }[b.dataset.list];
      getPath(e, b.dataset.list).push(blank); save(); render();
    } else if (act === 'del-row') { getPath(e, b.dataset.list).splice(+b.dataset.i, 1); save(); render(); }
    else if (act === 'apply-parsed') { if (applyParsed(+b.dataset.i)) { parsed.splice(+b.dataset.i, 1); save(); render(); } }
    else if (act === 'apply-all') { const keep = parsed.filter((p, i) => !applyParsed(i)); parsed = keep; save(); render(); }
    else if (act === 'clear-parsed') { parsed = []; render(); }
    else if (act === 'parse-text') { const t = $('#pasteText').value; if (t.trim()) { parsed.push(toParsed('貼り付けテキスト', P.parseText(t))); render(); } }
    else if (act === 'fill-dep') { const c = result.withholdingCount; e.payroll.salary.forEach((r) => { if (r.gross !== '') r.depCount = c; }); save(); render(); }
    else if (act === 'write-adj') {
      const idx = [...e.payroll.salary.keys()].reverse().find((i) => e.payroll.salary[i].gross !== '') ?? 11;
      e.payroll.salary.forEach((r) => { r.adj = ''; }); e.payroll.salary[idx].adj = result.yearEndAdjustment; save(); render();
    } else if (act === 'clear-overrides') { e.overrides = {}; save(); render(); }
    else if (act === 'print') window.print();
    else if (act === 'excel') await exportExcel(e);
    else if (act === 'excel-all') { for (const x of state.employees) await exportExcel(x); }
    else if (act === 'backup') download(new Blob([JSON.stringify(state, null, 2)], { type: 'application/json' }), `年末調整_バックアップ_${new Date().toISOString().slice(0, 10)}.json`);
    else if (act === 'wipe') { if (confirm('このブラウザに保存した全従業員のデータを削除しますか？（元に戻せません）')) { state = { employees: [], currentId: null }; save(); render(); } }
    else if (act === 'export-list') {
      const head = ['氏名', '⑦給与等', '⑧徴収済税額', '㉑所得控除', '㉒課税給与所得', '㉖年調年税額', '区分', '㉗過不足額', '確定申告要確認'];
      const rows = state.employees.map((x) => { const r = N.calculate(x), L = r.lines; return [x.profile.name, L.r7, L.r8, L.r21, L.r22, L.r26, r.statusLabel, L.r27, r.kakuteiRequired ? '要確認' : '']; });
      const csv = [head, ...rows].map((r) => r.map((v) => `"${String(v ?? '').replace(/"/g, '""')}"`).join(',')).join('\r\n');
      download(new Blob(['﻿' + csv], { type: 'text/csv' }), '年末調整_一覧_令和8年分.csv');
    }
  });

  // 入力 → 状態に反映 → 再計算（再描画せずに出力欄だけ更新してフォーカスを保つ）
  document.addEventListener('input', (ev) => {
    const el = ev.target;
    if (el.dataset.parsed !== undefined) {
      const p = parsed[+el.dataset.parsed]; const k = el.dataset.k;
      p[k] = ['payDate', 'kind'].includes(k) ? el.value : el.value === '' ? null : N.num(el.value);
      return;
    }
    if (!el.dataset.bind || !emp()) return;
    const t = el.dataset.type;
    let v = el.value;
    if (t === 'num') v = v.trim() === '' ? '' : N.num(v);
    if (t === 'bool') v = el.checked;
    if (t === 'select' && el.dataset.bind === 'jutaku.rate') v = Number(v);
    setPath(emp(), el.dataset.bind, v);
    emp().updatedAt = new Date().toISOString();
    save();
    if (el.dataset.bind === 'profile.name') renderTabs();
    recompute();
  });
  document.addEventListener('change', (ev) => {
    const el = ev.target;
    if (el.id === 'empSelect') { state.currentId = el.value; save(); render(); return; }
    if (el.id === 'restoreFile' && el.files[0]) {
      el.files[0].text().then((txt) => {
        try { const s = JSON.parse(txt); if (!Array.isArray(s.employees)) throw new Error('形式が違います'); state = s; save(); render(); alert(`${s.employees.length}名分を読み込みました`); }
        catch (err) { alert('読み込めませんでした：' + err.message); }
      });
      return;
    }
    if (el.dataset.bind && (el.dataset.type === 'select' || el.dataset.type === 'bool') && ['fuyo', 'kiso'].includes(tab)) render();
  });
  document.addEventListener('focusout', (ev) => {
    const el = ev.target;
    if (el.dataset && el.dataset.type === 'num' && el.value !== '') el.value = fmtIn(N.num(el.value));
  });

  if (!state.currentId && state.employees[0]) state.currentId = state.employees[0].id;
  render();
})();
