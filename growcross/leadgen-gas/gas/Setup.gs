/**
 * Setup.gs — メニュー・初期設定・トリガー登録
 */

function onOpen() {
  SpreadsheetApp.getUi().createMenu('営業自動化')
    .addItem('① 初期設定（シート作成）', 'initialize')
    .addSeparator()
    .addItem('② リスト作成（検索条件を実行）', 'runListBuild')
    .addItem('③ 企業調査＋AI判定（未調査を処理）', 'runEnrichBatch')
    .addItem('④ メール送信（送信待ちを処理）', 'runSendBatch')
    .addItem('⑤ フォーム営業の文面を作成', 'runFormPrepare')
    .addItem('⑥ フォーム営業を開始（サイドバー）', 'showFormSidebar')
    .addSeparator()
    .addItem('返信・バウンスを確認', 'runReplyAndBounceCheck')
    .addItem('日次レポートを作成', 'runDailyReport')
    .addItem('重複チェック（手動取込後）', 'runDedupe')
    .addSeparator()
    .addItem('自動実行トリガーを登録', 'setupTriggers')
    .addItem('自動実行トリガーを停止', 'removeTriggers')
    .addToUi();
}

function initialize() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const props = PropertiesService.getScriptProperties();
  props.setProperty('SPREADSHEET_ID', ss.getId());
  if (!props.getProperty('UNSUB_SECRET')) props.setProperty('UNSUB_SECRET', Utilities.getUuid() + Utilities.getUuid());

  ensureSheet_(SHEETS.CONFIG, ['キー', '値', '説明'], DEFAULT_CONFIG);
  ensureSheet_(SHEETS.QUERIES, HEADERS.QUERIES, DEFAULT_QUERIES);
  ensureSheet_(SHEETS.LEADS, HEADERS.LEADS, []);
  ensureSheet_(SHEETS.TEMPLATES, HEADERS.TEMPLATES, DEFAULT_TEMPLATES);
  ensureSheet_(SHEETS.FORM_QUEUE, HEADERS.FORM_QUEUE, []);
  ensureSheet_(SHEETS.LOG, HEADERS.LOG, []);
  ensureSheet_(SHEETS.SUPPRESS, HEADERS.SUPPRESS, []);
  ensureSheet_(SHEETS.KPI, HEADERS.KPI, []);

  // 入力規則（チェックボックス・プルダウン）
  const leads = sheet_(SHEETS.LEADS);
  const col = function (h) { return HEADERS.LEADS.indexOf(h) + 1; };
  leads.getRange(2, col('承認'), 2000, 1).insertCheckboxes();
  leads.getRange(2, col('ステータス'), 2000, 1).setDataValidation(
    SpreadsheetApp.newDataValidation().requireValueInList(Object.keys(STATUS).map(function (k) { return STATUS[k]; }), true).build());
  sheet_(SHEETS.QUERIES).getRange(2, 1, 200, 1).insertCheckboxes();
  const cfgSheet = sheet_(SHEETS.CONFIG);
  cfgSheet.setColumnWidth(1, 180).setColumnWidth(2, 360).setColumnWidth(3, 420);

  SpreadsheetApp.getUi().alert(
    '初期設定が完了しました。\n\n' +
    '次に行うこと：\n' +
    '1. 「設定」シートの送信元メール・事業者住所・テスト送信先を入力\n' +
    '2. スクリプトプロパティに ANTHROPIC_API_KEY と PLACES_API_KEY を登録\n' +
    '3. 「検索条件」シートに業種×エリアを入れ、実行にチェック\n' +
    '詳しくは SETUP.md をご覧ください。');
}

function ensureSheet_(name, headers, rows) {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  let sh = ss.getSheetByName(name);
  if (sh) return sh; // 既存シートは上書きしない
  sh = ss.insertSheet(name);
  sh.getRange(1, 1, 1, headers.length).setValues([headers]).setFontWeight('bold').setBackground('#e8eef7');
  sh.setFrozenRows(1);
  if (rows.length) sh.getRange(2, 1, rows.length, rows[0].length).setValues(rows);
  return sh;
}

/** 自動実行トリガー（既存のトリガーは一度すべて削除してから登録） */
function setupTriggers() {
  removeTriggers();
  ScriptApp.newTrigger('runListBuild').timeBased().everyDays(1).atHour(6).create();
  ScriptApp.newTrigger('runEnrichBatch').timeBased().everyHours(1).create();
  ScriptApp.newTrigger('runFormPrepare').timeBased().everyDays(1).atHour(7).create();
  ScriptApp.newTrigger('runSendBatch').timeBased().everyMinutes(30).create();
  ScriptApp.newTrigger('runReplyAndBounceCheck').timeBased().everyMinutes(30).create();
  ScriptApp.newTrigger('runDailyReport').timeBased().everyDays(1).atHour(18).create();
  SpreadsheetApp.getActiveSpreadsheet().toast('自動実行トリガーを登録しました', '営業自動化');
}

function removeTriggers() {
  ScriptApp.getProjectTriggers().forEach(function (t) { ScriptApp.deleteTrigger(t); });
}
