/**
 * Utils.gs — シート操作・設定読込・共通処理
 */

const TZ = 'Asia/Tokyo';
const RUN_LIMIT_MS = 4.5 * 60 * 1000; // GASの実行上限（6分）より手前で止める

function ss_() {
  const id = PropertiesService.getScriptProperties().getProperty('SPREADSHEET_ID');
  return id ? SpreadsheetApp.openById(id) : SpreadsheetApp.getActiveSpreadsheet();
}

function sheet_(name) {
  const sh = ss_().getSheetByName(name);
  if (!sh) throw new Error('シート「' + name + '」がありません。メニュー「営業自動化 > 初期設定」を実行してください。');
  return sh;
}

/** シートを {sh, headers, rows[]} で読み込む。rows の各要素は {_row: 行番号, 見出し: 値} */
function readTable_(name) {
  const sh = sheet_(name);
  const values = sh.getDataRange().getValues();
  const headers = values.shift() || [];
  const rows = values.map(function (v, i) {
    const o = { _row: i + 2 };
    headers.forEach(function (h, j) { o[h] = v[j]; });
    return o;
  });
  return { sh: sh, headers: headers, rows: rows };
}

/** 1行をまとめて更新する */
function updateRow_(table, row, patch) {
  Object.keys(patch).forEach(function (k) {
    if (table.headers.indexOf(k) < 0) throw new Error('列「' + k + '」がシート「' + table.sh.getName() + '」にありません');
    row[k] = patch[k];
  });
  const values = table.headers.map(function (h) { return row[h] === undefined ? '' : row[h]; });
  table.sh.getRange(row._row, 1, 1, values.length).setValues([values]);
}

/** オブジェクトの配列を末尾に追記する */
function appendRows_(name, objs) {
  if (!objs.length) return;
  const sh = sheet_(name);
  const headers = sh.getRange(1, 1, 1, sh.getLastColumn()).getValues()[0];
  const values = objs.map(function (o) { return headers.map(function (h) { return o[h] === undefined ? '' : o[h]; }); });
  sh.getRange(sh.getLastRow() + 1, 1, values.length, headers.length).setValues(values);
}

let CONFIG_CACHE_ = null;
function getConfig_() {
  if (CONFIG_CACHE_) return CONFIG_CACHE_;
  const values = sheet_(SHEETS.CONFIG).getDataRange().getValues().slice(1);
  const cfg = {};
  values.forEach(function (r) { if (r[0] !== '') cfg[String(r[0]).trim()] = r[1]; });
  CONFIG_CACHE_ = cfg;
  return cfg;
}

function getSecret_(key) {
  const v = PropertiesService.getScriptProperties().getProperty(key);
  if (!v) throw new Error('スクリプトプロパティ「' + key + '」が未設定です（プロジェクトの設定 > スクリプト プロパティ）');
  return v;
}

function now_() { return new Date(); }
function fmt_(d, pattern) { return Utilities.formatDate(d, TZ, pattern || 'yyyy/MM/dd HH:mm'); }
function todayStr_() { return fmt_(now_(), 'yyyy/MM/dd'); }
function newId_(prefix) { return prefix + Utilities.getUuid().replace(/-/g, '').slice(0, 10); }

function addDays_(d, n) {
  const x = new Date(d.getTime());
  x.setDate(x.getDate() + n);
  x.setHours(9, 0, 0, 0);
  return x;
}

function domainOf_(url) {
  if (!url) return '';
  const m = String(url).match(/^https?:\/\/([^\/:?#]+)/i);
  return m ? m[1].toLowerCase().replace(/^www\./, '') : '';
}

function originOf_(url) {
  const m = String(url).match(/^(https?:\/\/[^\/?#]+)/i);
  return m ? m[1] : '';
}

/** 相対URLを絶対URLに変換する */
function resolveUrl_(base, href) {
  if (/^https?:\/\//i.test(href)) return href;
  if (/^\/\//.test(href)) return 'https:' + href;
  const origin = originOf_(base);
  if (href.charAt(0) === '/') return origin + href;
  const dir = base.replace(/[?#].*$/, '').replace(/\/[^\/]*$/, '/');
  return dir + href;
}

/** 営業時間・営業日の判定 */
function isBusinessTime_(cfg) {
  const d = now_();
  const day = Number(fmt_(d, 'u')); // 1=月 … 7=日
  if (day >= 6) return false;
  const hour = Number(fmt_(d, 'H'));
  if (hour < Number(cfg['送信開始時'] || 9) || hour >= Number(cfg['送信終了時'] || 18)) return false;
  if (cfg['祝日は送信しない'] === true) {
    const cal = CalendarApp.getCalendarById('ja.japanese#holiday@group.v.calendar.google.com');
    if (cal && cal.getEventsForDay(d).length > 0) return false;
  }
  return true;
}

/** 同時実行を防ぐ */
function withLock_(fn) {
  const lock = LockService.getScriptLock();
  if (!lock.tryLock(10 * 1000)) { console.log('別の処理が実行中のためスキップしました'); return; }
  try { return fn(); } finally { lock.releaseLock(); }
}

/** 配信停止・除外リストを読み込む */
function loadSuppression_() {
  const t = readTable_(SHEETS.SUPPRESS);
  const emails = new Set();
  const domains = new Set();
  t.rows.forEach(function (r) {
    const v = String(r['対象（メール or ドメイン）'] || '').trim().toLowerCase();
    if (!v) return;
    if (v.indexOf('@') >= 0) emails.add(v); else domains.add(v.replace(/^www\./, ''));
  });
  return { emails: emails, domains: domains };
}

function addSuppression_(target, reason, memo) {
  appendRows_(SHEETS.SUPPRESS, [{ '対象（メール or ドメイン）': target, '理由': reason, '登録日': fmt_(now_()), 'メモ': memo || '' }]);
}

function log_(type, lead, to, step, subject, result, threadId, detail) {
  appendRows_(SHEETS.LOG, [{
    '日時': fmt_(now_()), '種別': type, 'リードID': lead ? lead['ID'] : '', '会社名': lead ? lead['会社名'] : '',
    '宛先': to || '', 'ステップ': step || '', '件名': subject || '', '結果': result, 'threadId': threadId || '', '詳細': detail || '',
  }]);
}

/** Google Chat の Incoming Webhook に通知（スクリプトプロパティ CHAT_WEBHOOK_URL が無ければ何もしない） */
function notify_(text) {
  const url = PropertiesService.getScriptProperties().getProperty('CHAT_WEBHOOK_URL');
  if (!url) { console.log('[通知] ' + text); return; }
  UrlFetchApp.fetch(url, {
    method: 'post', contentType: 'application/json; charset=UTF-8',
    payload: JSON.stringify({ text: text }), muteHttpExceptions: true,
  });
}

/** 配信停止リンクの改ざん防止トークン */
function unsubToken_(leadId, email) {
  const secret = getSecret_('UNSUB_SECRET');
  const sig = Utilities.computeHmacSha256Signature(leadId + '|' + String(email).toLowerCase(), secret);
  return Utilities.base64EncodeWebSafe(sig).replace(/=+$/, '').slice(0, 24);
}
