/**
 * WebApp.gs — 配信停止ページ
 * デプロイ：「デプロイ > 新しいデプロイ > ウェブアプリ」（実行ユーザー：自分／アクセス：全員）。
 * 発行されたURLを「設定」シートの WebアプリURL に貼り付けます。
 *
 * メールのセキュリティ製品がリンクを自動で開くことがあるため、
 * GET ではすぐに停止せず、確認ボタンを押したときに停止します。
 * List-Unsubscribe-Post（ワンクリック解除）の POST は doPost で受け付けます。
 */

function doGet(e) {
  const id = (e.parameter.id || '').trim();
  const t = (e.parameter.t || '').trim();
  const lead = findLeadById_(id);
  const valid = lead && t === unsubToken_(id, lead['公開メール']);
  const tpl = HtmlService.createTemplate(
    '<!DOCTYPE html><html><head><meta name="viewport" content="width=device-width,initial-scale=1">' +
    '<style>body{font-family:sans-serif;max-width:560px;margin:40px auto;padding:0 16px;line-height:1.8}button{padding:10px 18px;font-size:15px}</style></head><body>' +
    '<? if (valid) { ?><h2>配信停止の確認</h2><p><?= company ?> 様宛のご案内メールを停止します。</p>' +
    '<button id="b" onclick="this.disabled=true;google.script.run.withSuccessHandler(function(m){document.body.innerHTML=\'<h2>\'+m+\'</h2>\'}).confirmUnsubscribe(\'<?= id ?>\',\'<?= t ?>\')">配信を停止する</button>' +
    '<? } else { ?><h2>リンクが無効です</h2><p>お手数ですが、メールにご返信いただくか、お問い合わせ先までご連絡ください。</p><? } ?>' +
    '</body></html>');
  tpl.valid = !!valid;
  tpl.company = lead ? lead['会社名'] : '';
  tpl.id = id;
  tpl.t = t;
  return tpl.evaluate().setTitle('配信停止').addMetaTag('viewport', 'width=device-width, initial-scale=1');
}

/** ワンクリック解除（RFC 8058）。リダイレクトを伴うため、受信側の環境によっては動作しない場合があります */
function doPost(e) {
  const id = (e.parameter.id || '').trim();
  const t = (e.parameter.t || '').trim();
  const msg = confirmUnsubscribe(id, t);
  return ContentService.createTextOutput(msg);
}

function confirmUnsubscribe(id, t) {
  const table = readTable_(SHEETS.LEADS);
  const lead = table.rows.filter(function (r) { return r['ID'] === id; })[0];
  if (!lead || t !== unsubToken_(id, lead['公開メール'])) return 'リンクが無効です';
  if (lead['ステータス'] !== STATUS.UNSUB) {
    updateRow_(table, lead, { 'ステータス': STATUS.UNSUB });
    addSuppression_(String(lead['公開メール']).toLowerCase(), '配信停止（リンク）', lead['会社名']);
    log_('配信停止', lead, lead['公開メール'], '', '', 'リンクで停止', lead['threadId'], '');
  }
  return '配信を停止しました。ご連絡ありがとうございました。';
}

function findLeadById_(id) {
  if (!id) return null;
  return readTable_(SHEETS.LEADS).rows.filter(function (r) { return r['ID'] === id; })[0] || null;
}
