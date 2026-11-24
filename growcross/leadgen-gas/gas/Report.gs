/**
 * Report.gs — 日次KPIの集計と通知（毎日18時）
 */

function runDailyReport() {
  const today = todayStr_();
  const leads = readTable_(SHEETS.LEADS).rows;
  const logs = readTable_(SHEETS.LOG).rows;
  const isToday = function (v) { return v && fmt_(new Date(v), 'yyyy/MM/dd') === today; };
  const countLog = function (pred) { return logs.filter(pred).length; };

  const mailSentTotal = countLog(function (r) { return r['種別'] === 'メール' && r['結果'] === '送信'; });
  const formSentTotal = countLog(function (r) { return r['種別'] === 'フォーム' && r['結果'] === '送信済'; });
  const repliedTotal = leads.filter(function (r) { return [STATUS.REPLIED, STATUS.MEETING].indexOf(r['ステータス']) >= 0; }).length;
  const contacted = leads.filter(function (r) { return Number(r['ステップ']) > 0 || r['ステータス'] === STATUS.FORM_SENT || r['ステータス'] === STATUS.REPLIED || r['ステータス'] === STATUS.MEETING; }).length;

  const row = {
    '日付': today,
    'リスト追加': leads.filter(function (r) { return isToday(r['取得日']); }).length,
    '調査完了': leads.filter(function (r) { return r['AI適合度'] && r['ステータス'] !== STATUS.NEW; }).length,
    '送信対象（A/B）': leads.filter(function (r) { return r['AI適合度'] === 'A' || r['AI適合度'] === 'B'; }).length,
    'メール送信': countLog(function (r) { return r['種別'] === 'メール' && r['結果'] === '送信' && isToday(r['日時']); }),
    'フォーム送信': countLog(function (r) { return r['種別'] === 'フォーム' && r['結果'] === '送信済' && isToday(r['日時']); }),
    '返信': leads.filter(function (r) { return isToday(r['返信日']); }).length,
    '商談化': leads.filter(function (r) { return r['ステータス'] === STATUS.MEETING; }).length,
    '配信停止': countLog(function (r) { return r['種別'] === '配信停止' && isToday(r['日時']); }),
    'バウンス': countLog(function (r) { return r['種別'] === 'バウンス' && isToday(r['日時']); }),
    '累計送信': mailSentTotal + formSentTotal,
    '累計返信': repliedTotal,
    '累計返信率': contacted ? Math.round(repliedTotal / contacted * 1000) / 10 + '%' : '-',
  };
  appendRows_(SHEETS.KPI, [row]);

  const waiting = leads.filter(function (r) { return r['ステータス'] === STATUS.SEND_READY && r['承認'] !== true; }).length;
  notify_([
    '【営業自動化 日次レポート ' + today + '】',
    'メール送信 ' + row['メール送信'] + '件／フォーム送信 ' + row['フォーム送信'] + '件／返信 ' + row['返信'] + '件',
    '配信停止 ' + row['配信停止'] + '件／バウンス ' + row['バウンス'] + '件',
    '累計返信率 ' + row['累計返信率'] + '（累計接触 ' + contacted + '社）',
    waiting ? '承認待ち ' + waiting + '件があります（リストシートの「承認」にチェック）' : '',
  ].filter(String).join('\n'));
}
