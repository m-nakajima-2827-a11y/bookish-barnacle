/**
 * Enrich.gs — 企業サイトの調査とAI判定
 * トップページ・問い合わせページ・会社概要ページ（最大3ページ）を取得し、
 * 公開メール・フォーム有無・CAPTCHA・「営業お断り」表記を確認したうえで、AIが適合度を判定します。
 * robots.txt で全体の巡回が禁止されているサイトは取得しません。
 */

const CONTACT_RE = /contact|inquiry|toiawase|otoiawase|form|お問い?合わ?せ|問合せ|ご相談|資料請求/i;
const ABOUT_RE = /company|about|corporate|profile|outline|会社概要|会社案内|企業情報|事業内容/i;
const REFUSAL_RE = /(営業|セールス|勧誘|売り込み)[^。\n]{0,30}(お断り|ご遠慮|禁止|お控え|受け付けて(い|お)りません|対応(いた)?しかね|返信(いた)?しません)/;
const AD_MAIL_REFUSAL_RE = /(広告|宣伝)[^。\n]{0,10}(メール)[^。\n]{0,20}(お断り|拒否|ご遠慮|禁止)/;
const EMAIL_RE = /[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}/g;
const EMAIL_IGNORE_RE = /\.(png|jpe?g|gif|svg|webp)$|example\.|sentry|wixpress|@2x|domain\.com|xxx/i;

function runEnrichBatch() {
  withLock_(function () {
    const cfg = getConfig_();
    const t = readTable_(SHEETS.LEADS);
    const started = Date.now();
    const limit = Number(cfg['調査件数_1回']) || 10;
    let n = 0;
    for (let i = 0; i < t.rows.length; i++) {
      const r = t.rows[i];
      if (r['ステータス'] !== STATUS.NEW) continue;
      if (n >= limit || Date.now() - started > RUN_LIMIT_MS) break;
      n++;
      try {
        updateRow_(t, r, enrichLead_(r, cfg));
      } catch (e) {
        updateRow_(t, r, { 'ステータス': STATUS.ERROR, 'メモ': String(e.message).slice(0, 200) });
      }
    }
    if (n) console.log('調査: ' + n + '件');
  });
}

function enrichLead_(r, cfg) {
  const url = r['WebサイトURL'];
  if (!url) return { 'ステータス': STATUS.MANUAL, 'メモ': 'Webサイトなし' };
  const domain = r['ドメイン'] || domainOf_(url);

  if (isRobotsDisallowed_(originOf_(url))) {
    return { 'robots制限': true, 'ステータス': STATUS.MANUAL, 'メモ': 'robots.txtで巡回不可のため手動確認' };
  }

  const top = fetchPage_(url);
  if (!top) return { 'ステータス': STATUS.ERROR, 'メモ': 'サイトを取得できませんでした' };

  const links = extractLinks_(top.html, top.url).filter(function (l) { return domainOf_(l.href) === domain; });
  const contactLink = links.filter(function (l) { return CONTACT_RE.test(l.href + ' ' + l.text); })[0];
  const aboutLink = links.filter(function (l) { return ABOUT_RE.test(l.href + ' ' + l.text); })[0];
  let contact = null, about = null;
  if (contactLink) { Utilities.sleep(1000); contact = fetchPage_(contactLink.href); }
  if (aboutLink && (!contactLink || aboutLink.href !== contactLink.href)) { Utilities.sleep(1000); about = fetchPage_(aboutLink.href); }

  const pages = [top, contact, about].filter(Boolean);
  const texts = pages.map(function (p) { return htmlToText_(p.html); });
  const allText = texts.join('\n');

  const email = pickEmail_(pages, domain);
  const refusal = REFUSAL_RE.test(allText) || AD_MAIL_REFUSAL_RE.test(allText);
  const formHtml = contact ? contact.html : '';
  const hasForm = !!contact && (/<form[\s>]/i.test(formHtml) || /<iframe[^>]+(form|hubspot|formrun|docs\.google\.com\/forms)/i.test(formHtml));
  const captcha = !!contact && /recaptcha|hcaptcha|turnstile|captcha/i.test(formHtml);

  const patch = {
    '問い合わせURL': contactLink ? contactLink.href : '',
    'フォーム有無': hasForm,
    'CAPTCHA': captcha,
    '公開メール': email ? email.address : '',
    'メール掲載URL': email ? email.url : '',
    '営業お断り': refusal,
    'robots制限': false,
  };

  if (refusal) {
    // 「営業お断り」「広告メールお断り」の表記がある企業には、メールもフォームも送らない
    return Object.assign(patch, { 'アプローチ': '対象外', 'ステータス': STATUS.EXCLUDED, 'メモ': '営業・広告メールお断りの表記あり' });
  }

  const ai = analyzeCompany_(r, texts, cfg);
  Object.assign(patch, {
    'AI業種': ai.industry, 'AI事業概要': ai.business_summary, 'AI適合度': ai.fit,
    'AI判定理由': ai.fit_reason, '課題仮説': ai.pain_hypothesis, 'パーソナライズ文': ai.personalized_opening,
  });

  if (ai.fit === 'C' || ai.fit === '対象外') {
    return Object.assign(patch, { 'アプローチ': '対象外', 'ステータス': STATUS.EXCLUDED });
  }
  if (email) {
    return Object.assign(patch, { 'アプローチ': 'メール', 'ステータス': STATUS.SEND_READY, 'ステップ': 0, '次回送信日': todayStr_() });
  }
  if (contactLink) {
    return Object.assign(patch, { 'アプローチ': 'フォーム', 'ステータス': STATUS.FORM_WAIT });
  }
  return Object.assign(patch, { 'アプローチ': '電話・手動', 'ステータス': STATUS.MANUAL, 'メモ': '公開メール・問い合わせページが見つからない' });
}

/** ページを取得し、文字コードを判定して {url, html} を返す */
function fetchPage_(url) {
  try {
    const res = UrlFetchApp.fetch(url, {
      muteHttpExceptions: true, followRedirects: true, validateHttpsCertificates: true,
      headers: { 'User-Agent': 'Mozilla/5.0 (compatible; LeadResearchBot/1.0)' },
    });
    if (res.getResponseCode() >= 400) return null;
    const ctype = String(res.getHeaders()['Content-Type'] || res.getHeaders()['content-type'] || '');
    if (ctype && !/html/i.test(ctype)) return null;
    let charset = (ctype.match(/charset=([\w-]+)/i) || [])[1];
    if (!charset) {
      const head = res.getBlob().getDataAsString('ISO-8859-1').slice(0, 3000);
      charset = (head.match(/<meta[^>]+charset=["']?([\w-]+)/i) || [])[1] || 'UTF-8';
    }
    if (/shift_jis|sjis|x-sjis/i.test(charset)) charset = 'Shift_JIS';
    if (/euc-jp/i.test(charset)) charset = 'EUC-JP';
    return { url: url, html: res.getContentText(charset) };
  } catch (e) {
    console.log('取得失敗 ' + url + ': ' + e.message);
    return null;
  }
}

/** robots.txt の「User-agent: *」に「Disallow: /」がある場合は true */
function isRobotsDisallowed_(origin) {
  try {
    const res = UrlFetchApp.fetch(origin + '/robots.txt', { muteHttpExceptions: true, followRedirects: true });
    if (res.getResponseCode() !== 200) return false;
    const lines = res.getContentText().split(/\r?\n/);
    let inStar = false;
    for (let i = 0; i < lines.length; i++) {
      const line = lines[i].replace(/#.*$/, '').trim();
      if (/^user-agent:/i.test(line)) inStar = /^user-agent:\s*\*\s*$/i.test(line);
      else if (inStar && /^disallow:\s*\/\s*$/i.test(line)) return true;
    }
    return false;
  } catch (e) {
    return false;
  }
}

function extractLinks_(html, baseUrl) {
  const out = [];
  const re = /<a\s[^>]*href=["']([^"'#]+)["'][^>]*>([\s\S]*?)<\/a>/gi;
  let m;
  while ((m = re.exec(html)) !== null) {
    const href = m[1].trim();
    if (/^(mailto|tel|javascript):/i.test(href)) continue;
    out.push({ href: resolveUrl_(baseUrl, href), text: htmlToText_(m[2]).slice(0, 50) });
  }
  return out;
}

function htmlToText_(html) {
  return String(html)
    .replace(/<(script|style|noscript|svg)[\s\S]*?<\/\1>/gi, ' ')
    .replace(/<br\s*\/?>|<\/(p|div|li|h\d|tr)>/gi, '\n')
    .replace(/<[^>]+>/g, ' ')
    .replace(/&nbsp;/g, ' ').replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&quot;/g, '"').replace(/&#39;/g, "'")
    .replace(/[ \t　]+/g, ' ')
    .replace(/\n\s*\n+/g, '\n')
    .trim();
}

/** サイトに掲載されたメールアドレスを1件選ぶ（自社ドメインのものを優先） */
function pickEmail_(pages, domain) {
  const found = [];
  pages.forEach(function (p) {
    const text = p.html.replace(/&#64;|&#x40;/gi, '@');
    (text.match(EMAIL_RE) || []).forEach(function (addr) {
      addr = addr.toLowerCase();
      if (EMAIL_IGNORE_RE.test(addr)) return;
      if (!found.some(function (f) { return f.address === addr; })) found.push({ address: addr, url: p.url });
    });
  });
  if (!found.length) return null;
  const same = found.filter(function (f) { return domain && f.address.split('@')[1].replace(/^www\./, '').endsWith(domain); });
  const pool = same.length ? same : found;
  // 個人名らしいアドレスより、代表・問い合わせ用アドレスを優先
  const generic = pool.filter(function (f) { return /^(info|contact|inquiry|sales|support|office|mail|toiawase|soudan)/.test(f.address); });
  return (generic[0] || pool[0]);
}
