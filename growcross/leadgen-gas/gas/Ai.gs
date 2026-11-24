/**
 * Ai.gs — Claude API の呼び出し（UrlFetchApp で Messages API を直接呼びます）
 * APIキーはスクリプトプロパティ ANTHROPIC_API_KEY に保存してください。
 */

const ANTHROPIC_ENDPOINT = 'https://api.anthropic.com/v1/messages';
const ANTHROPIC_VERSION = '2026-10-21';

/**
 * JSON Schema に沿った回答を返す（構造化出力）。
 * @param {string} system システムプロンプト
 * @param {string} userText 入力
 * @param {Object} schema JSON Schema（すべての object に additionalProperties:false が必要）
 * @return {Object} パース済みの回答
 */
function callClaudeJson_(system, userText, schema) {
  const cfg = getConfig_();
  const payload = {
    model: cfg['AIモデル'] || 'claude-opus-5-5',
    max_tokens: 8000,
    system: system,
    messages: [{ role: 'user', content: userText }],
    output_config: {
      effort: cfg['AI推論レベル'] || 'low',
      format: { type: 'json_schema', schema: schema },
    },
  };
  const headers = { 'x-api-key': getSecret_('ANTHROPIC_API_KEY'), 'anthropic-version': ANTHROPIC_VERSION };
  if (cfg['AIフォールバック'] === true) {
    // AIが回答を控えた（refusal）場合に、サーバー側で別モデルへ自動的に切り替えて再実行する
    headers['anthropic-beta'] = 'server-side-fallback-2026-07-01';
    payload.fallbacks = 'default';
  }

  let lastError = '';
  for (let attempt = 0; attempt < 4; attempt++) {
    const res = UrlFetchApp.fetch(ANTHROPIC_ENDPOINT, {
      method: 'post', contentType: 'application/json', headers: headers,
      payload: JSON.stringify(payload), muteHttpExceptions: true,
    });
    const code = res.getResponseCode();
    if (code === 200) {
      const body = JSON.parse(res.getContentText());
      if (body.stop_reason === 'refusal') throw new Error('AIが回答を控えました（refusal）');
      if (body.stop_reason === 'max_tokens') throw new Error('AIの出力が上限で途切れました');
      const textBlock = (body.content || []).filter(function (b) { return b.type === 'text'; })[0];
      if (!textBlock) throw new Error('AIの回答が空でした');
      return JSON.parse(textBlock.text);
    }
    lastError = code + ': ' + res.getContentText().slice(0, 300);
    // 429（レート制限）・5xx・529（過負荷）は待って再試行。それ以外（400・401など）は即エラー
    if (code === 429 || code >= 500) { Utilities.sleep(Math.pow(2, attempt) * 3000); continue; }
    break;
  }
  throw new Error('Claude API エラー ' + lastError);
}

/** 企業調査結果から、業種・事業概要・適合度・課題仮説・パーソナライズ文を作る */
function analyzeCompany_(lead, pageTexts, cfg) {
  const system = [
    'あなたはBtoB営業の調査担当者です。企業サイトの本文から、営業アプローチの判断材料を作成します。',
    '事実はサイト本文に書かれている内容だけを使い、書かれていないことは推測で断定しないでください。',
    '課題仮説は「〜ではないか」という仮説として書きます。実績・数値・社名を創作しないでください。',
    '',
    '# 自社（送り手）のサービス',
    String(cfg['自社サービス概要'] || ''),
    '',
    '# ターゲット条件',
    String(cfg['ターゲット条件'] || ''),
    '',
    '# 適合度の基準',
    'A: ターゲット条件に合い、法人営業・紹介元営業・反響営業など営業活動の存在がサイトから読み取れる',
    'B: ターゲット条件に概ね合うが、営業活動の様子や規模が読み取れない',
    'C: 業種または規模がターゲットから外れる可能性が高い',
    '対象外: 個人事業の店舗のみ、行政・学校・医療機関、上場大企業、競合（営業コンサル・広告代理店）など',
  ].join('\n');

  const user = [
    '会社名: ' + lead['会社名'],
    '検索業種: ' + lead['検索業種'],
    '住所: ' + lead['住所'],
    'URL: ' + lead['WebサイトURL'],
    '',
    '# サイト本文（抜粋）',
    pageTexts.join('\n----\n').slice(0, 12000),
  ].join('\n');

  const schema = {
    type: 'object',
    additionalProperties: false,
    required: ['industry', 'business_summary', 'fit', 'fit_reason', 'pain_hypothesis', 'personalized_opening'],
    properties: {
      industry: { type: 'string', description: '業種（例：金属加工業、有料老人ホーム運営）' },
      business_summary: { type: 'string', description: '事業内容の要約（80字以内）' },
      fit: { type: 'string', enum: ['A', 'B', 'C', '対象外'] },
      fit_reason: { type: 'string', description: '判定理由（80字以内）' },
      pain_hypothesis: { type: 'string', description: '営業面の課題仮説。メール本文に「〜といった点」の形で差し込める名詞句（40字以内）' },
      personalized_opening: { type: 'string', description: 'メール冒頭の一文。サイトに書かれた具体的な事業内容・取り組みに触れる（80字以内、です・ます調、過度な賛辞は避ける）' },
    },
  };
  return callClaudeJson_(system, user, schema);
}

/** 問い合わせフォーム用の文面を作る */
function writeFormMessage_(lead, cfg) {
  const limit = Number(cfg['フォーム本文上限文字数']) || 500;
  const system = [
    'あなたはBtoB営業の担当者です。企業の問い合わせフォームに送る、簡潔で丁寧な営業文面を作成します。',
    '条件：',
    '- 本文は' + limit + '文字以内。です・ます調。',
    '- 冒頭で「営業のご連絡」であることを明記し、相手の時間をとらせない構成にする。',
    '- 相手の事業内容に1点だけ具体的に触れる。過度な賛辞・誇張・断定はしない。',
    '- 実績・数値・社名は、下記の自社情報に書かれているもの以外は書かない。',
    '- 最後に、不要な場合は返信不要である旨と、送信者名・連絡先（{{連絡先}} と書く）を入れる。',
    '',
    '# 自社（送り手）のサービス',
    String(cfg['自社サービス概要'] || ''),
  ].join('\n');
  const user = [
    '会社名: ' + lead['会社名'],
    '業種: ' + (lead['AI業種'] || lead['検索業種']),
    '事業概要: ' + lead['AI事業概要'],
    '課題仮説: ' + lead['課題仮説'],
    '冒頭の一文の候補: ' + lead['パーソナライズ文'],
  ].join('\n');
  const schema = {
    type: 'object', additionalProperties: false, required: ['subject', 'body'],
    properties: {
      subject: { type: 'string', description: 'フォームの件名欄（30字以内）' },
      body: { type: 'string', description: 'フォームの本文' },
    },
  };
  return callClaudeJson_(system, user, schema);
}
