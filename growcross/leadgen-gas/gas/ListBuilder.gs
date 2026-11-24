/**
 * ListBuilder.gs — 営業リストの作成
 * 「検索条件」シートの業種キーワード×エリアで Google Places API（Text Search, New）を検索し、
 * 「リスト」シートに企業を追加します。place_id とドメインで重複を除きます。
 *
 * 注意：Google Maps Platform の利用規約には、取得データの保存（キャッシュ）に関する制限があります。
 *       運用前に最新の規約を確認してください（設計書「9. リスクと対策」参照）。
 */

const PLACES_ENDPOINT = 'https://places.googleapis.com/v1/places:searchText';
const PLACES_FIELDS = 'places.id,places.displayName,places.formattedAddress,places.nationalPhoneNumber,places.websiteUri,places.businessStatus,nextPageToken';

function runListBuild() {
  withLock_(function () {
    const cfg = getConfig_();
    const q = readTable_(SHEETS.QUERIES);
    const leads = readTable_(SHEETS.LEADS);
    const suppress = loadSuppression_();
    const excluded = String(cfg['除外ドメイン'] || '').split(',').map(function (s) { return s.trim().toLowerCase(); }).filter(String);
    const seenPlace = new Set(leads.rows.map(function (r) { return r['place_id']; }).filter(String));
    const seenDomain = new Set(leads.rows.map(function (r) { return r['ドメイン']; }).filter(String));
    const started = Date.now();
    let total = 0;

    q.rows.forEach(function (row) {
      if (Date.now() - started > RUN_LIMIT_MS) return;
      if (row['実行'] !== true || row['ステータス'] === '実行済') return;
      const text = (String(row['業種キーワード']) + ' ' + String(row['エリア'])).trim();
      const max = Math.min(Number(row['最大件数']) || 20, 60); // Text Search は1検索あたり最大60件
      const places = [];
      let token = null;
      try {
        do {
          const res = searchPlaces_(text, token);
          (res.places || []).forEach(function (p) { places.push(p); });
          token = res.nextPageToken;
          if (token) Utilities.sleep(2000);
        } while (token && places.length < max);
      } catch (e) {
        updateRow_(q, row, { 'ステータス': 'エラー', 'メモ': String(e.message).slice(0, 200) });
        return;
      }

      const added = [];
      places.slice(0, max).forEach(function (p) {
        if (p.businessStatus && p.businessStatus !== 'OPERATIONAL') return;
        const domain = domainOf_(p.websiteUri);
        if (!domain && cfg['Webサイトなしは除外'] === true) return;
        if (domain && excluded.some(function (d) { return domain === d || domain.endsWith('.' + d); })) return;
        if (seenPlace.has(p.id) || (domain && seenDomain.has(domain))) return;
        if (domain && suppress.domains.has(domain)) return;
        seenPlace.add(p.id);
        if (domain) seenDomain.add(domain);
        added.push({
          'ID': newId_('L'), '取得日': todayStr_(), '取得元': 'Places API', 'place_id': p.id,
          '会社名': p.displayName ? p.displayName.text : '', '検索業種': row['業種キーワード'], 'エリア': row['エリア'],
          '住所': p.formattedAddress || '', '電話番号': p.nationalPhoneNumber || '',
          'WebサイトURL': p.websiteUri || '', 'ドメイン': domain,
          '承認': false, 'ステータス': domain ? STATUS.NEW : STATUS.MANUAL, 'ステップ': 0,
        });
      });
      appendRows_(SHEETS.LEADS, added);
      updateRow_(q, row, { 'ステータス': '実行済', '実行日': fmt_(now_()), '取得件数': added.length });
      total += added.length;
    });
    if (total) notify_('【営業リスト】' + total + '社を追加しました');
  });
}

function searchPlaces_(textQuery, pageToken) {
  const body = { textQuery: textQuery, languageCode: 'ja', regionCode: 'JP', pageSize: 20 };
  if (pageToken) body.pageToken = pageToken;
  const res = UrlFetchApp.fetch(PLACES_ENDPOINT, {
    method: 'post', contentType: 'application/json',
    headers: { 'X-Goog-Api-Key': getSecret_('PLACES_API_KEY'), 'X-Goog-FieldMask': PLACES_FIELDS },
    payload: JSON.stringify(body), muteHttpExceptions: true,
  });
  if (res.getResponseCode() !== 200) throw new Error('Places API ' + res.getResponseCode() + ': ' + res.getContentText().slice(0, 300));
  return JSON.parse(res.getContentText());
}

/**
 * 手動取込（展示会名刺・既存リスト・購入リストなど）をリストシートに貼り付けた後に実行。
 * ドメイン重複・除外リストに該当する行を「対象外」にし、空のIDとステータスを補完します。
 */
function runDedupe() {
  withLock_(function () {
    const t = readTable_(SHEETS.LEADS);
    const suppress = loadSuppression_();
    const seen = new Set();
    let dup = 0;
    t.rows.forEach(function (r) {
      const patch = {};
      if (!r['ID']) patch['ID'] = newId_('L');
      if (!r['ドメイン'] && r['WebサイトURL']) patch['ドメイン'] = domainOf_(r['WebサイトURL']);
      if (!r['ステータス']) patch['ステータス'] = STATUS.NEW;
      if (!r['取得日']) patch['取得日'] = todayStr_();
      if (!r['取得元']) patch['取得元'] = '手動取込';
      const domain = patch['ドメイン'] || r['ドメイン'];
      if (domain) {
        if (seen.has(domain) || suppress.domains.has(domain)) {
          if ([STATUS.NEW, STATUS.SEND_READY, STATUS.FORM_WAIT].indexOf(r['ステータス']) >= 0 || !r['ステータス']) {
            patch['ステータス'] = STATUS.EXCLUDED;
            patch['メモ'] = seen.has(domain) ? '重複' : '除外リスト該当';
            dup++;
          }
        }
        seen.add(domain);
      }
      if (Object.keys(patch).length) updateRow_(t, r, patch);
    });
    SpreadsheetApp.getActiveSpreadsheet().toast('重複・除外 ' + dup + '件を「対象外」にしました', '営業自動化');
  });
}
