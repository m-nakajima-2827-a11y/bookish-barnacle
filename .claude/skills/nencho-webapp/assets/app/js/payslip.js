/*
 * 給与明細PDF 読取りパーサー
 *
 * PDF.js で取り出したテキスト片（座標付き）または平文テキストから、
 * 集計シートに必要な項目（支給日・総支給金額・社会保険料等・所得税・扶養人数）を抽出する。
 * 給与ソフトごとに表記が違うため、ラベル辞書 LABELS を拡張して対応する。
 * スキャン画像のPDF（文字情報なし）は読めないため、OCRするか手入力する。
 */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else root.Payslip = factory();
})(typeof self !== 'undefined' ? self : this, function () {
  'use strict';

  // 先に書いたものほど優先。完全一致 > 前方一致 > 部分一致 の順に評価する。
  const LABELS = {
    gross: ['総支給額', '総支給金額', '支給合計', '支給額合計', '支給合計額', '総支給', '支給総額', '賞与支給額', '支給額計'],
    socialTotal: ['社会保険料合計', '社会保険料計', '社会保険計', '社保合計', '社会保険料等合計', '社会保険料'],
    health: ['健康保険料', '健康保険', '健保'],
    care: ['介護保険料', '介護保険'],
    pension: ['厚生年金保険料', '厚生年金保険', '厚生年金', '厚年'],
    employment: ['雇用保険料', '雇用保険'],
    childSupport: ['子ども・子育て支援金', '子ども子育て支援金', '子育て支援金', '支援金'],
    fund: ['厚生年金基金', '健保組合', '企業年金'],
    smallBiz: ['確定拠出年金', 'マッチング拠出', 'iDeCo', 'イデコ', '小規模企業共済'],
    tax: ['源泉所得税', '所得税'],
    residentTax: ['住民税', '市町村民税', '市県民税'],
    deductionTotal: ['控除合計', '控除額合計', '控除計'],
    net: ['差引支給額', '差引支給', '手取額', '振込支給額', '振込額'],
    depCount: ['扶養人数', '扶養親族等の数', '扶養親族数', '税扶養'],
  };
  const EXCLUDE = {
    tax: ['住民税', '課税', '非課税', '所得税調整'],
    gross: ['課税'],
    socialTotal: [],
    health: ['介護'],
  };

  const z2h = (s) => String(s || '')
    .replace(/[０-９Ａ-Ｚａ-ｚ]/g, (c) => String.fromCharCode(c.charCodeAt(0) - 0xfee0))
    .replace(/[，]/g, ',').replace(/[．]/g, '.').replace(/[　]/g, ' ').replace(/[−ー－‐]/g, '-')
    .replace(/￥|¥/g, '');
  const norm = (s) => z2h(s).replace(/\s+/g, '');

  const NUM_RE = /^-?\(?-?\d{1,3}(,\d{3})+\)?(円)?$|^-?\d+(円)?$/;
  function parseNum(s) {
    const t = z2h(s).replace(/\s/g, '');
    if (!NUM_RE.test(t)) return null;
    const neg = t.startsWith('-') || t.startsWith('(');
    const n = Number(t.replace(/[^0-9]/g, ''));
    return neg ? -n : n;
  }

  /** 和暦・西暦の日付を ISO 形式に */
  function parseDate(text) {
    const t = z2h(text);
    let m = t.match(/(令和|R)\s*(\d{1,2}|元)\s*[年.\/-]\s*(\d{1,2})\s*[月.\/-]\s*(\d{1,2})\s*日?/);
    if (m) return iso(2018 + (m[2] === '元' ? 1 : +m[2]), +m[3], +m[4]);
    m = t.match(/(20\d{2})\s*[年.\/-]\s*(\d{1,2})\s*[月.\/-]\s*(\d{1,2})/);
    if (m) return iso(+m[1], +m[2], +m[3]);
    return null;
  }
  function parsePeriod(text) {
    const t = z2h(text);
    let m = t.match(/(令和|R)\s*(\d{1,2}|元)\s*年\s*(\d{1,2})\s*月\s*分/);
    if (m) return { year: 2018 + (m[2] === '元' ? 1 : +m[2]), month: +m[3] };
    m = t.match(/(20\d{2})\s*年\s*(\d{1,2})\s*月\s*分/);
    if (m) return { year: +m[1], month: +m[2] };
    m = t.match(/(\d{1,2})\s*月\s*分/);
    if (m) return { year: null, month: +m[1] };
    return null;
  }
  const iso = (y, m, d) => `${y}-${String(m).padStart(2, '0')}-${String(d).padStart(2, '0')}`;

  function labelScore(text, key) {
    const t = norm(text);
    if (!t || (EXCLUDE[key] || []).some((x) => t.includes(x))) return 0;
    let best = 0;
    LABELS[key].forEach((lab, i) => {
      const w = LABELS[key].length - i; // 辞書の前方ほど高い
      if (t === lab) best = Math.max(best, 300 + w);
      else if (t.startsWith(lab) && t.length <= lab.length + 3) best = Math.max(best, 200 + w);
      else if (t.includes(lab) && t.length <= lab.length + 6) best = Math.max(best, 100 + w);
    });
    return best;
  }

  /**
   * 座標付きテキスト片から抽出する。
   * @param {Array<{str:string,x:number,y:number,w:number,h:number,page?:number}>} items  y は上から下へ増える座標
   */
  function parseItems(items) {
    const cells = items.map((it) => ({ ...it, str: String(it.str || '').trim() })).filter((it) => it.str);
    const nums = cells.map((c) => ({ c, v: parseNum(c.str) })).filter((n) => n.v !== null);
    const fullText = linesFromItems(cells).join('\n');
    const result = { fields: {}, sources: {} };

    Object.keys(LABELS).forEach((key) => {
      let best = null;
      cells.forEach((c) => {
        const s = labelScore(c.str, key);
        if (!s) return;
        // ラベル片の中に数値が含まれる場合（例「所得税 12,345」）
        const inline = z2h(c.str).match(/(-?\d{1,3}(?:,\d{3})+|-?\d+)\s*円?\s*$/);
        const v = inline && norm(c.str).replace(inline[0].replace(/\s/g, ''), '') ? parseNum(inline[1]) : null;
        let cand = v !== null ? { v, dist: 0 } : findValue(c, nums);
        if (cand && (!best || s > best.s || (s === best.s && cand.dist < best.dist))) best = { s, v: cand.v, dist: cand.dist, label: c.str };
      });
      if (best) { result.fields[key] = best.v; result.sources[key] = best.label; }
    });
    return finalize(result, fullText);
  }

  function findValue(label, nums) {
    const lh = label.h || 10;
    let best = null;
    nums.forEach(({ c, v }) => {
      if (c === label || (c.page || 0) !== (label.page || 0)) return;
      const dy = c.y - label.y;
      const dxRight = c.x - (label.x + (label.w || 0));
      const sameLine = Math.abs(dy) <= lh * 0.6;
      const lcx = label.x + (label.w || 0) / 2, ccx = c.x + (c.w || 0) / 2;
      const colOverlap = Math.abs(lcx - ccx) <= Math.max(label.w || 0, c.w || 0, 30) * 0.75;
      let dist = null;
      if (sameLine && dxRight >= -2 && dxRight < 260) dist = dxRight;               // 同じ行の右側
      else if (dy > lh * 0.4 && dy < lh * 4 && colOverlap) dist = 1000 + dy;         // 直下（表形式）
      if (dist !== null && (!best || dist < best.dist)) best = { v, dist };
    });
    return best;
  }

  function linesFromItems(cells) {
    const sorted = [...cells].sort((a, b) => (a.page || 0) - (b.page || 0) || a.y - b.y || a.x - b.x);
    const lines = [];
    let cur = [], lastY = null, lastP = null;
    sorted.forEach((c) => {
      if (lastY !== null && (Math.abs(c.y - lastY) > (c.h || 10) * 0.5 || c.page !== lastP)) { lines.push(cur); cur = []; }
      cur.push(c); lastY = c.y; lastP = c.page;
    });
    if (cur.length) lines.push(cur);
    return lines.map((l) => l.sort((a, b) => a.x - b.x).map((c) => c.str).join('  '));
  }

  /** 平文テキスト（pdftotext -layout 等）から抽出する */
  function parseText(text) {
    // 空行を除き、空白・タブ・縦線で区切ったトークン列にする（pdftotext -layout の出力にも対応）
    const lines = String(text).split(/\r?\n/)
      .map((l) => z2h(l).split(/[\s|]+/).map((s) => s.trim()).filter(Boolean))
      .filter((toks) => toks.length);
    const isNum = (t) => parseNum(t) !== null;
    const result = { fields: {}, sources: {} };
    Object.keys(LABELS).forEach((key) => {
      let best = null;
      lines.forEach((tokens, li) => {
        tokens.forEach((tok, ti) => {
          const s = labelScore(tok, key);
          if (!s) return;
          let v = null;
          // ① 同じ行でラベルの直後が数値（例「所得税 5,620」）
          if (tokens[ti + 1] !== undefined && isNum(tokens[ti + 1])) v = parseNum(tokens[ti + 1]);
          // ② 表形式：ラベル行のラベル数と次の行の数値数が同じなら、同じ順番の数値
          if (v === null) {
            const labelsInRow = tokens.filter((t) => !isNum(t));
            const below = lines[li + 1] || [];
            const nums = below.filter(isNum);
            const pos = labelsInRow.indexOf(tok);
            if (labelsInRow.length === tokens.length && nums.length === labelsInRow.length && pos >= 0) v = parseNum(nums[pos]);
          }
          if (v !== null && (!best || s > best.s)) best = { s, v, label: tok };
        });
      });
      if (best) { result.fields[key] = best.v; result.sources[key] = best.label; }
    });
    return finalize(result, text);
  }

  function finalize(result, fullText) {
    const f = result.fields;
    const parts = ['health', 'care', 'pension', 'employment', 'childSupport', 'fund'];
    const partsSum = parts.reduce((a, k) => a + (f[k] || 0), 0);
    const social = f.socialTotal !== undefined ? f.socialTotal : partsSum || undefined;
    const t = z2h(fullText);
    const isBonus = /賞与|ボーナス|期末手当|勤勉手当/.test(t);
    let payDate = null;
    const dm = t.match(/(支給日|支払日|支給年月日|振込日)[^\d令R]{0,6}((令和|R)?\s*[\d元]{1,4}\s*[年.\/-]\s*\d{1,2}\s*[月.\/-]\s*\d{1,2}\s*日?)/);
    if (dm) payDate = parseDate(dm[2]);
    if (!payDate) payDate = parseDate(t);
    const period = parsePeriod(t);
    const warnings = [];
    if (f.gross === undefined) warnings.push('総支給金額が見つかりません');
    if (social === undefined) warnings.push('社会保険料が見つかりません');
    if (f.tax === undefined) warnings.push('所得税が見つかりません');
    if (f.socialTotal !== undefined && partsSum && Math.abs(partsSum - f.socialTotal) > 1)
      warnings.push(`社会保険料の内訳合計(${partsSum.toLocaleString()})と合計欄(${f.socialTotal.toLocaleString()})が一致しません`);
    if (f.net !== undefined && f.gross !== undefined && f.deductionTotal !== undefined && f.gross - f.deductionTotal !== f.net)
      warnings.push('総支給額 − 控除合計 が差引支給額と一致しません（読取り位置を確認してください）');
    const month = period ? period.month : payDate ? +payDate.slice(5, 7) : null;
    return {
      kind: isBonus ? 'bonus' : 'salary', payDate, period, month,
      gross: f.gross ?? null, social: social ?? null, smallBiz: f.smallBiz ?? null,
      tax: f.tax ?? null, depCount: f.depCount ?? null, residentTax: f.residentTax ?? null, net: f.net ?? null,
      socialParts: Object.fromEntries(parts.filter((k) => f[k] !== undefined).map((k) => [k, f[k]])),
      sources: result.sources, warnings,
    };
  }

  return { LABELS, parseItems, parseText, parseDate, parsePeriod, parseNum };
});
