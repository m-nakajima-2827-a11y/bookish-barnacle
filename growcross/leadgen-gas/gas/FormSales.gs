/**
 * FormSales.gs — フォーム営業（半自動）
 * AIが企業ごとの文面を作り、担当者がサイドバーを見ながらフォームに入力・送信します。
 * フォームへの自動投稿（ボット送信）は行いません。CAPTCHAの回避や、相手サイトの規約違反につながるためです。
 */

function runFormPrepare() {
  withLock_(function () {
    const cfg = getConfig_();
    const t = readTable_(SHEETS.LEADS);
    const queued = new Set(readTable_(SHEETS.FORM_QUEUE).rows.map(function (q) { return q['リードID']; }));
    const suppress = loadSuppression_();
    const started = Date.now();
    const rows = [];
    let n = 0;
    for (let i = 0; i < t.rows.length; i++) {
      const r = t.rows[i];
      if (r['ステータス'] !== STATUS.FORM_WAIT || queued.has(r['ID'])) continue;
      if (n >= 15 || Date.now() - started > RUN_LIMIT_MS) break;
      if (r['営業お断り'] === true || suppress.domains.has(r['ドメイン'])) {
        updateRow_(t, r, { 'ステータス': STATUS.EXCLUDED, 'メモ': '営業お断り・除外に該当' });
        continue;
      }
      n++;
      try {
        const msg = writeFormMessage_(r, cfg);
        const contact = [cfg['送信者名'], cfg['フォーム入力_メール'], cfg['フォーム入力_電話']].filter(String).join(' / ');
        const body = String(msg.body).replace(/\{\{連絡先\}\}/g, contact);
        rows.push({
          'キューID': newId_('F'), 'リードID': r['ID'], '会社名': r['会社名'], '問い合わせURL': r['問い合わせURL'],
          'CAPTCHA': r['CAPTCHA'], '件名': msg.subject, '本文': body, '文字数': body.length,
          'ステータス': '準備済', '作成日': fmt_(now_()),
        });
        updateRow_(t, r, { 'ステータス': STATUS.FORM_READY });
      } catch (e) {
        updateRow_(t, r, { 'ステータス': STATUS.ERROR, 'メモ': String(e.message).slice(0, 200) });
      }
    }
    appendRows_(SHEETS.FORM_QUEUE, rows);
    if (rows.length) notify_('【フォーム営業】' + rows.length + '件の文面を準備しました。サイドバーから送信してください');
  });
}

function showFormSidebar() {
  const html = HtmlService.createHtmlOutputFromFile('FormSidebar').setTitle('フォーム営業');
  SpreadsheetApp.getUi().showSidebar(html);
}

/** サイドバー：次に対応する1件を返す */
function getNextFormItem() {
  const cfg = getConfig_();
  const q = readTable_(SHEETS.FORM_QUEUE);
  const item = q.rows.filter(function (r) { return r['ステータス'] === '準備済'; })[0];
  const left = q.rows.filter(function (r) { return r['ステータス'] === '準備済'; }).length;
  if (!item) return { done: true };
  return {
    done: false, left: left, queueId: item['キューID'], company: item['会社名'], url: item['問い合わせURL'],
    captcha: item['CAPTCHA'] === true, subject: item['件名'], body: item['本文'],
    me: {
      company: cfg['フォーム入力_会社名'], name: cfg['フォーム入力_氏名'],
      email: cfg['フォーム入力_メール'], tel: cfg['フォーム入力_電話'],
    },
  };
}

/**
 * サイドバー：結果を記録する
 * @param {string} queueId
 * @param {string} result '送信済' | 'スキップ' | 'お断り表記あり'
 * @param {string} body 担当者が修正した本文
 */
function markFormItem(queueId, result, body) {
  const q = readTable_(SHEETS.FORM_QUEUE);
  const item = q.rows.filter(function (r) { return r['キューID'] === queueId; })[0];
  if (!item) throw new Error('キューが見つかりません');
  const user = Session.getActiveUser().getEmail();
  updateRow_(q, item, { 'ステータス': result, '本文': body || item['本文'], '対応者': user, '対応日時': fmt_(now_()) });

  const t = readTable_(SHEETS.LEADS);
  const lead = t.rows.filter(function (r) { return r['ID'] === item['リードID']; })[0];
  if (lead) {
    const status = result === '送信済' ? STATUS.FORM_SENT : STATUS.EXCLUDED;
    updateRow_(t, lead, { 'ステータス': status, '最終送信日': result === '送信済' ? fmt_(now_()) : lead['最終送信日'], '担当': user });
    if (result === 'お断り表記あり') addSuppression_(lead['ドメイン'], '営業お断り（フォーム）', lead['会社名']);
  }
  log_('フォーム', lead || { 'ID': item['リードID'], '会社名': item['会社名'] }, item['問い合わせURL'], 1, item['件名'], result, '', '');
  return getNextFormItem();
}
