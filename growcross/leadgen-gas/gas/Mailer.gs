/**
 * Mailer.gs — ステップメールの送信、返信・バウンスの検知
 * Gmail API（拡張サービス）で送信し、2通目以降は同じスレッドに返信として送ります。
 * 送信前に必ず checkSendable_ で配信停止・除外・お断り表記・上限・営業時間を確認します。
 */

const SENDABLE_STATUSES = [STATUS.SEND_READY, STATUS.SENDING];

function runSendBatch() {
  withLock_(function () {
    const cfg = getConfig_();
    if (!isBusinessTime_(cfg)) return;
    const testMode = cfg['テストモード'] === true;
    if (testMode && !cfg['テスト送信先']) throw new Error('テストモードです。「設定」シートのテスト送信先を入力してください');
    if (!cfg['WebアプリURL']) throw new Error('「設定」シートの WebアプリURL（配信停止ページ）が未入力です');

    let remaining = Math.min(Number(cfg['1日の送信上限']) - countSentToday_(), Number(cfg['1回の送信上限']));
    if (testMode) remaining = Math.min(remaining, 3);
    if (remaining <= 0) return;

    const templates = loadTemplates_();
    const suppress = loadSuppression_();
    const t = readTable_(SHEETS.LEADS);
    const started = Date.now();
    const now = now_();

    for (let i = 0; i < t.rows.length && remaining > 0; i++) {
      if (Date.now() - started > RUN_LIMIT_MS) break;
      const r = t.rows[i];
      if (r['アプローチ'] !== 'メール' || SENDABLE_STATUSES.indexOf(r['ステータス']) < 0) continue;
      if (cfg['送信前承認'] === true && r['承認'] !== true) continue;
      if (r['次回送信日'] && new Date(r['次回送信日']) > now) continue;

      const step = Number(r['ステップ']) || 0;
      const nextStep = step + 1;
      const tpl = templates[nextStep];
      if (!tpl) { if (!testMode) updateRow_(t, r, { 'ステータス': STATUS.DONE }); continue; }

      const guard = checkSendable_(r, suppress);
      if (!guard.ok) { updateRow_(t, r, { 'ステータス': guard.status, 'メモ': guard.reason }); continue; }

      // 2通目以降は、送る直前にも返信がないか確認する
      if (step > 0 && r['threadId'] && findReply_(r['threadId'], cfg)) {
        updateRow_(t, r, { 'ステータス': STATUS.REPLIED, '返信日': fmt_(now_()) });
        notify_('【返信あり】' + r['会社名'] + '（' + r['公開メール'] + '）');
        continue;
      }

      const to = testMode ? cfg['テスト送信先'] : r['公開メール'];
      const mail = renderEmail_(tpl, r, cfg, nextStep);
      try {
        const sent = sendMime_({
          to: to, subject: mail.subject, body: mail.body, unsubUrl: mail.unsubUrl,
          threadId: (!testMode && step > 0) ? r['threadId'] : null,
          inReplyTo: (!testMode && step > 0) ? r['初回MessageID'] : null,
        }, cfg);
        log_(testMode ? 'メール（テスト）' : 'メール', r, to, nextStep, mail.subject, '送信', sent.threadId, '');
        if (!testMode) {
          const nextTpl = templates[nextStep + 1];
          const patch = {
            'ステップ': nextStep, '最終送信日': fmt_(now_()),
            'ステータス': nextTpl ? STATUS.SENDING : STATUS.DONE,
            '次回送信日': nextTpl ? fmt_(addDays_(now_(), Number(nextTpl.days) || 4), 'yyyy/MM/dd') : '',
          };
          if (nextStep === 1) { patch['threadId'] = sent.threadId; patch['初回MessageID'] = sent.messageId; patch['初回件名'] = mail.subject; }
          updateRow_(t, r, patch);
        }
        remaining--;
      } catch (e) {
        log_('メール', r, to, nextStep, mail.subject, 'エラー', '', String(e.message).slice(0, 300));
        updateRow_(t, r, { 'ステータス': STATUS.ERROR, 'メモ': String(e.message).slice(0, 200) });
      }
      Utilities.sleep((Number(cfg['送信間隔秒']) || 20) * 1000 + Math.floor(Math.random() * 5000));
    }
  });
}

/** 送信してよいかの最終確認 */
function checkSendable_(r, suppress) {
  const email = String(r['公開メール'] || '').toLowerCase();
  const domain = email.split('@')[1] || '';
  if (!email) return { ok: false, status: STATUS.MANUAL, reason: '公開メールなし' };
  if (!r['メール掲載URL']) return { ok: false, status: STATUS.MANUAL, reason: '掲載元URLが記録されていないため送信しません' };
  if (r['営業お断り'] === true) return { ok: false, status: STATUS.EXCLUDED, reason: '営業お断りの表記あり' };
  if (suppress.emails.has(email)) return { ok: false, status: STATUS.UNSUB, reason: '配信停止・除外リストに該当' };
  if (suppress.domains.has(domain) || suppress.domains.has(r['ドメイン'])) return { ok: false, status: STATUS.EXCLUDED, reason: '除外ドメインに該当' };
  if (['A', 'B'].indexOf(r['AI適合度']) < 0) return { ok: false, status: STATUS.EXCLUDED, reason: '適合度がA/B以外' };
  return { ok: true };
}

function loadTemplates_() {
  const t = readTable_(SHEETS.TEMPLATES);
  const map = {};
  t.rows.forEach(function (r) {
    if (r['ステップ'] === '' || !r['本文']) return;
    map[Number(r['ステップ'])] = { days: r['前回からの日数'], subject: r['件名'], body: r['本文'] };
  });
  return map;
}

/** 差し込みと、特定電子メール法の表示事項（送信者・住所・配信停止）を本文末尾に必ず付ける */
function renderEmail_(tpl, r, cfg, step) {
  const vars = {
    '会社名': r['会社名'], 'パーソナライズ文': r['パーソナライズ文'], '課題仮説': r['課題仮説'] || '営業活動の仕組み化',
    '業種': r['AI業種'] || r['検索業種'], '送信者名': cfg['送信者名'], '署名': cfg['署名'],
  };
  const fill = function (s) { return String(s).replace(/\{\{(.+?)\}\}/g, function (_, k) { return vars[k.trim()] !== undefined ? vars[k.trim()] : ''; }); };
  const unsubUrl = cfg['WebアプリURL'] + '?id=' + encodeURIComponent(r['ID']) + '&t=' + unsubToken_(r['ID'], r['公開メール']);
  const subject = tpl.subject ? fill(tpl.subject) : ('Re: ' + (r['初回件名'] || fill(loadTemplates_()[1].subject)));
  const footer = [
    '',
    '――――――――――――――――',
    '本メールは、貴社Webサイトに掲載されているアドレス宛にお送りしています。',
    '今後のご案内が不要な場合は、こちらから配信を停止できます：',
    unsubUrl,
    '（本メールに「配信停止」とご返信いただいても停止いたします）',
    '送信者：' + cfg['事業者名'],
    '住所：' + cfg['事業者住所'],
    'お問い合わせ：' + cfg['問い合わせ先'],
  ].join('\n');
  return { subject: subject, body: fill(tpl.body) + '\n' + footer, unsubUrl: unsubUrl, step: step };
}

/** Gmail API で送信し、{id, threadId, messageId} を返す */
function sendMime_(o, cfg) {
  const b64 = function (s) { return Utilities.base64Encode(s, Utilities.Charset.UTF_8); };
  const encWord = function (s) { return '=?UTF-8?B?' + b64(s) + '?='; };
  const from = cfg['送信元メール'] || Session.getActiveUser().getEmail();
  const headers = [
    'From: ' + encWord(cfg['送信者名']) + ' <' + from + '>',
    'To: ' + o.to,
    'Subject: ' + encWord(o.subject),
    'MIME-Version: 1.0',
    'Content-Type: text/plain; charset=UTF-8',
    'Content-Transfer-Encoding: base64',
  ];
  if (o.inReplyTo) headers.push('In-Reply-To: ' + o.inReplyTo, 'References: ' + o.inReplyTo);
  if (o.unsubUrl) {
    headers.push('List-Unsubscribe: <' + o.unsubUrl + '>, <mailto:' + from + '?subject=unsubscribe>');
    headers.push('List-Unsubscribe-Post: List-Unsubscribe=One-Click');
  }
  const body = b64(o.body).replace(/(.{76})/g, '$1\r\n');
  const raw = Utilities.base64EncodeWebSafe(headers.join('\r\n') + '\r\n\r\n' + body);
  const resource = { raw: raw };
  if (o.threadId) resource.threadId = o.threadId;
  const sent = Gmail.Users.Messages.send(resource, 'me');
  const meta = Gmail.Users.Messages.get('me', sent.id, { format: 'metadata', metadataHeaders: ['Message-ID'] });
  const mid = (meta.payload.headers || []).filter(function (h) { return h.name.toLowerCase() === 'message-id'; })[0];
  return { id: sent.id, threadId: sent.threadId, messageId: mid ? mid.value : '' };
}

function countSentToday_() {
  const today = todayStr_();
  return readTable_(SHEETS.LOG).rows.filter(function (r) {
    return String(r['種別']).indexOf('メール') === 0 && r['結果'] === '送信' && fmt_(new Date(r['日時']), 'yyyy/MM/dd') === today;
  }).length;
}

/** スレッド内に相手からのメッセージがあれば、そのメッセージを返す */
function findReply_(threadId, cfg) {
  const me = String(cfg['送信元メール'] || Session.getActiveUser().getEmail()).toLowerCase();
  const thread = GmailApp.getThreadById(threadId);
  if (!thread) return null;
  const msgs = thread.getMessages();
  for (let i = 1; i < msgs.length; i++) {
    const from = msgs[i].getFrom().toLowerCase();
    if (from.indexOf(me) >= 0 || /mailer-daemon|postmaster/.test(from)) continue;
    return msgs[i];
  }
  return null;
}

/** 返信・配信停止依頼・バウンスを確認する（30分ごと） */
function runReplyAndBounceCheck() {
  withLock_(function () {
    const cfg = getConfig_();
    const t = readTable_(SHEETS.LEADS);
    const started = Date.now();

    // 1) 返信の検知（返信があればシーケンスを止めて担当者に通知）
    t.rows.forEach(function (r) {
      if (Date.now() - started > RUN_LIMIT_MS) return;
      if ([STATUS.SENDING, STATUS.DONE].indexOf(r['ステータス']) < 0 || !r['threadId']) return;
      const reply = findReply_(r['threadId'], cfg);
      if (!reply) return;
      const text = reply.getPlainBody().slice(0, 300);
      if (/配信停止|停止して|不要です|unsubscribe|送らないで/i.test(text)) {
        addSuppression_(String(r['公開メール']).toLowerCase(), '配信停止（返信）', r['会社名']);
        updateRow_(t, r, { 'ステータス': STATUS.UNSUB, '返信日': fmt_(now_()) });
        log_('配信停止', r, r['公開メール'], '', '', '返信で停止', r['threadId'], '');
      } else {
        updateRow_(t, r, { 'ステータス': STATUS.REPLIED, '返信日': fmt_(now_()) });
        log_('返信', r, r['公開メール'], '', reply.getSubject(), '返信あり', r['threadId'], text.slice(0, 120));
        notify_('【返信あり】' + r['会社名'] + '\n' + text.slice(0, 120) + '\nhttps://mail.google.com/mail/u/0/#inbox/' + r['threadId']);
      }
    });

    // 2) バウンス（宛先不明）の検知
    const threads = GmailApp.search('from:(mailer-daemon OR postmaster) newer_than:3d', 0, 50);
    if (!threads.length) return;
    const bodies = threads.map(function (th) { return th.getMessages().map(function (m) { return m.getPlainBody(); }).join('\n'); }).join('\n').toLowerCase();
    t.rows.forEach(function (r) {
      const email = String(r['公開メール'] || '').toLowerCase();
      if (!email || r['ステータス'] === STATUS.BOUNCE || [STATUS.SENDING, STATUS.DONE].indexOf(r['ステータス']) < 0) return;
      if (bodies.indexOf(email) >= 0) {
        updateRow_(t, r, { 'ステータス': STATUS.BOUNCE });
        addSuppression_(email, 'バウンス', r['会社名']);
        log_('バウンス', r, email, '', '', 'バウンス', r['threadId'], '');
      }
    });
  });
}
