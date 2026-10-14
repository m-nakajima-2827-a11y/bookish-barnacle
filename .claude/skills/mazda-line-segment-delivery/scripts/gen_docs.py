"""result.json と references/branch-messages.md から、分岐別メッセージ案と配信計画書を作る。
使い方: python gen_docs.py <result.json> <branch-messages.md> <出力ディレクトリ>
"""
import sys, json, re, datetime as dt

R = json.load(open(sys.argv[1], encoding='utf-8'))
tpl = open(sys.argv[2], encoding='utf-8').read()
outdir = sys.argv[3]
BASE = dt.date.fromisoformat(R['base'])
W = '月火水木金土日'
def fmt(d, t): return f'{d.month}/{d.day}（{W[d.weekday()]}）{t}'
def nextday(wday):  # 基準日より後の最初の曜日（0=月…5=土）
    return BASE + dt.timedelta(days=((wday - BASE.weekday()) % 7) or 7)
SAT, WED = 5, 2
add = lambda d, n: d + dt.timedelta(days=n)
s = {}
s['至急'] = [nextday(SAT)]; s['至急'] += [add(s['至急'][0], 4), add(s['至急'][0], 7)]
s['A1'] = [nextday(WED)]; s['A1'] += [add(s['A1'][0], 14), add(s['A1'][0], 24)]
s['A2'] = [add(nextday(SAT), 7)]; s['A2'] += [add(s['A2'][0], 14), add(s['A2'][0], 26)]
s['A3'] = [add(nextday(SAT), 14)]; s['A3'] += [add(s['A3'][0], 11), add(s['A3'][0], 26)]
s['B'] = [add(s['A1'][0], 7)]; s['B'] += [add(s['B'][0], 15), add(s['B'][0], 24)]
s['C1'] = [add(nextday(SAT), 21)]; s['C1'] += [add(s['C1'][0], 28)]
s['C2'] = [add(nextday(SAT), 7)]; s['C2'] += [add(s['C2'][0], 25), add(s['C2'][0], 49)]
T = {'至急': ['10:00', '19:00', '10:00'], 'A1': ['19:00', '19:00', '10:00'], 'A2': ['10:00', '10:00', '12:00'], 'A3': ['10:00', '19:00', '12:00'],
     'B': ['19:00', '12:00', '10:00'], 'C1': ['10:00', '10:00'], 'C2': ['10:00', '19:00', '10:00']}
D = {k: [fmt(d, T[k][i]) for i, d in enumerate(v)] for k, v in s.items()}

P = R['prio']; ST = list(R['stores'].keys())
tot = lambda k: sum(P[k].values())
key = {k[:2].strip(): k for k in P}
urg = R['urgent_by']
net = {b: tot(key[b]) - urg.get(b, 0) for b in ['A1', 'A2', 'A3', 'B']}
def stores(d): return '・'.join(f'{k[:-1] if k.endswith("店") else k}{v}' for k, v in d.items())
def feat(b):
    f = R['feat'][b]
    mdl = '、'.join(f'{k} {v}件' for k, v in list(f['models'].items())[:4])
    ks = sorted(f['kaisu'].items(), key=lambda x: -x[1])[:2]
    return f'多い車種：{mdl}。次回車検：' + '、'.join(f'{k} {v}件' for k, v in ks)
bday_next = [(BASE.month % 12) + 1, ((BASE.month + 1) % 12) + 1]
x3 = '、'.join(f"{m}月 {R['bday'][f'{m}月']}件" for m in bday_next)

# ---------- 分岐別メッセージ案 ----------
head = f"""# LINE OnetoOne 分岐別メッセージ案（{'・'.join(ST)}）

- 元データ：`{R['src']}`（基準日 {BASE:%Y年%m月%d日}）
- 作成方法：skill `mazda-line-segment-delivery` の分岐ルールと `references/branch-messages.md` のひな形
- 分析結果：`LINE_お友だち分析_{BASE:%Y%m%d}.xlsx`（07_優先度×店舗・08_担当者別・09_加入状況×車検時期・20_配信リスト）
- 表記：件数は**【事実】**、施策・反応の見込みは**【仮説】**

## 0. 分岐の全体像

### 0-1 分岐ツリー【事実】
```
お友だち（{R['n']:,}件）
 ├─ 車検まで2か月以内（車検予約が未確認）……… 【至急】{R['urgent']}件 ※主分岐より先に配信
 ├─ 車検まで6か月以内
 │    ├─ スカイプラン加入 …………………………… 【A1】{tot(key['A1'])}件
 │    ├─ 販売終了車種 ………………………………… 【A2】{tot(key['A2'])}件
 │    ├─ 次回車検で7年以上 ………………………… 【A3】{tot(key['A3'])}件
 │    └─ 上記以外 ……………………………………… 【B】 {tot(key['B'])}件
 ├─ 車検まで7〜12か月 ……………………………… 【C1】{tot(key['C1'])}件
 └─ 車検まで13か月以上 …………………………… 【C2】{tot(key['C2']):,}件

補助の分岐（主分岐と重ねて使う）
 ├─ パックdeメンテ未加入（車検6か月以内）…… 【X1】{R['x1']}件
 ├─ 任意保険（店舗扱い）未加入（車検6か月以内）【X2】{R['x2']}件
 └─ 誕生月（{x3}）…… 【X3】
```

### 0-2 配信のルール
| ルール | 内容 |
|---|---|
| 優先順位 | 至急 → A1 → A2 → A3 → B → X1・X2 → C1 → C2。同じ週に複数の分岐に入る方には、優先順位の高い1通だけ送る |
| 頻度の上限 | 1人あたり月4通まで。C2は月1〜2通まで |
| 配信しない時間 | 22時〜翌8時 |
| 複数台保有（{R['multi']}人） | 電話番号で重複を除き、優先順位の高い車両の分岐で1通だけ送る |
| 3案の使い方 | 案1→案2→案3の順に送る。反応（リンククリック・予約・返信）があった方には次の案を送らず、担当者が個別に連絡する |
| 計測 | URLにUTMを付ける（例：`utm_source=line&utm_medium=onetoone&utm_campaign=a1_01`） |

### 0-3 配信スケジュール
| 分岐 | 対象【事実】 | 案1 | 案2 | 案3 |
|---|---|---|---|---|
| 至急 | {R['urgent']}件（{stores(R['urgent_store'])}） | {D['至急'][0]} | {D['至急'][1]} | {D['至急'][2]}＋電話 |
| A1 | {net['A1']}件（{tot(key['A1'])}件から至急の{urg.get('A1', 0)}件を除く） | {D['A1'][0]} | {D['A1'][1]} | {D['A1'][2]} |
| A2 | {net['A2']}件（{tot(key['A2'])}件から至急の{urg.get('A2', 0)}件を除く） | {D['A2'][0]} | {D['A2'][1]} | {D['A2'][2]} |
| A3 | {net['A3']}件（{tot(key['A3'])}件から至急の{urg.get('A3', 0)}件を除く） | {D['A3'][0]} | {D['A3'][1]} | {D['A3'][2]} |
| B | {net['B']}件（{tot(key['B'])}件から至急の{urg.get('B', 0)}件を除く） | {D['B'][0]} | {D['B'][1]} | {D['B'][2]} |
| C1 | {tot(key['C1'])}件 | {D['C1'][0]} | {D['C1'][1]} | 車検の6か月前（ステップ配信の1回目へ移行） |
| C2 | {tot(key['C2']):,}件 | {D['C2'][0]} | {D['C2'][1]} | {D['C2'][2]} |
| X1 | {R['x1']}件 | 車検予約の完了直後 | 入庫の7日前 | 入庫の3日後 |
| X2 | {R['x2']}件 | 車検満了の1か月前 | 入庫の7日前 | 入庫の3日後 |
| X3 | 誕生月の方 | 3案から1案を選んで、誕生月の1日 10:00 に送る | | |

---

"""
body = tpl[tpl.index('## 1. 【至急】'):]
secs = re.split(r'(?m)^(?=## \d+\. )', body)
REL = {
 '至急': ['分析した週の土曜 10:00', '案1の4日後 19:00', '案1の1週間後 10:00'],
 'A1': ['分析の翌週 水曜 19:00', '案1の2週間後 19:00', '案2の10日後 土曜 10:00'],
 'A2': ['分析の翌週 土曜 10:00', '案1の2週間後 土曜 10:00', '案2の12日後 12:00'],
 'A3': ['分析の2週間後 土曜 10:00', '案1の11日後 19:00', '案2の15日後 木曜 12:00'],
 'B': ['分析の2週間後 水曜 19:00', '案1の15日後 木曜 12:00', '案2の9日後 土曜 10:00'],
 'C1': ['分析の3週間後 土曜 10:00', '案1の4週間後 土曜 10:00'],
 'C2': ['季節の配信日。10〜11月なら冬タイヤ', '案1の3〜4週間後 19:00', '案2の3〜4週間後 土曜 10:00'],
}
FACT = {
 '至急': f"**対象【事実】**：{R['urgent']}件（{stores(R['urgent_store'])}）。内訳：" + '、'.join(f'{k} {v}件' for k, v in urg.items()),
 'A1': f"**対象【事実】**：{net['A1']}件（全体{tot(key['A1'])}件、{stores(P[key['A1']])}）。{feat('A1')}",
 'A2': f"**対象【事実】**：{net['A2']}件（全体{tot(key['A2'])}件、{stores(P[key['A2']])}）。{feat('A2')}",
 'A3': f"**対象【事実】**：{net['A3']}件（全体{tot(key['A3'])}件、{stores(P[key['A3']])}）。{feat('A3')}",
 'B': f"**対象【事実】**：{net['B']}件（全体{tot(key['B'])}件、{stores(P[key['B']])}）。{feat('B')}",
 'C1': f"**対象【事実】**：{tot(key['C1'])}件（{stores(P[key['C1']])}）。{feat('C1')}",
 'C2': f"**対象【事実】**：{tot(key['C2']):,}件（{stores(P[key['C2']])}）。{feat('C2')}",
 'X1': f"**対象【事実】**：{R['x1']}件",
 'X2': f"**対象【事実】**：{R['x2']}件（{stores(R['x2_store'])}）",
 'X3': f"**対象【事実】**：{x3}",
}
out = []
for sec in secs:
    mm = re.match(r'## \d+\. 【(.+?)】', sec)
    if not mm: out.append(sec); continue
    b = mm.group(1)
    if b in REL:
        for rel, d in zip(REL[b], D[b]):
            sec = sec.replace(f'（{rel}', f'（{d}', 1)
    sec = re.sub(r'(\*\*目的\*\*：.*\n)', r'\1' + FACT[b].replace('\\', '\\\\') + '\n', sec, count=1) if '**目的**' in sec else sec.replace('\n\n', '\n\n' + FACT[b] + '\n', 1)
    out.append(sec)
kpi = """
---

## 11. 効果測定（KPI）
| 分岐 | 主なKPI | 確認のタイミング |
|---|---|---|
| 至急・B | 車検予約率（予約数÷対象件数） | 毎週 |
| A1・A2・A3 | 資料請求・試乗・査定の予約数、3か月以内の成約数 | 毎週・月次 |
| C1・C2 | アンケート回答率、ブロック率 | 配信ごと |
| X1・X2 | パックdeメンテ・保険の加入件数 | 月次 |
| 全体 | 案ごとのリンククリック率（UTMで計測） | 配信ごと |

初回の配信結果を基準値として、反応の低い案は文面を見直します。目標値は初回の結果を見てから決めます。
"""
msg = head + ''.join(out).rstrip() + '\n' + kpi
open(f'{outdir}/LINE_分岐別メッセージ案_{BASE:%Y%m%d}.md', 'w', encoding='utf-8').write(msg)

# ---------- 配信計画書 ----------
t2 = R['t2']; t3 = {r['車格']: r for r in R['t3']}
cal = R['cal']; months = list(cal.keys())
peak = max(cal, key=cal.get)
st = R['steps']; mon = sorted(set().union(*[set(v) for v in st.values()]))[:6]
def row_cal(store): return ' | '.join(str(R['cal_store'][m][store]) for m in months[:-1])
imp_lines = '\n'.join(f"| {k} | " + '<br>'.join(f'{chr(0x2460 + i)} {t}' for i, t in enumerate(v)) + ' |' for k, v in R['imp'].items())
plan = f"""# LINE OnetoOne セグメント配信計画（{'・'.join(ST)}）

- 元データ：`{R['src']}`（基準日 {BASE:%Y年%m月%d日}）
- 付属資料：`LINE_お友だち分析_{BASE:%Y%m%d}.xlsx`（集計13シート＋配信リスト）、`LINE_分岐別メッセージ案_{BASE:%Y%m%d}.md`
- 作成方法：skill `mazda-line-segment-delivery` の手順1〜5
- 表記：**【事実】**＝集計値、**【仮説】**＝推定、**【目安】**＝一般的な目安

## 0. データの前提
| 項目 | 内容 |
|---|---|
| 件数 | {R['n']:,}件（1件＝お友だち×車両1台）。電話番号で名寄せすると{R['persons']:,}人、2台以上お持ちの方{R['multi']}人 |
| 店舗 | {'／'.join(f'{k} {v:,}件' for k, v in R['stores'].items())} |
| ない項目 | 年齢（生年）・年収・最終来店日。年齢は「次回車検の回数」、年収は「暫定価格帯セグメント（仮説）」で代用 |
| 車種の分類 | すべての車種がskillの分類表で判定できました（未分類 {len(R['unclassified'])}件） |

## 1. 分析サマリー【事実】
| 指標 | 値 |
|---|---|
| 車検6か月以内 | {R['s6']}件（{R['s6'] / R['n']:.1%}） |
| 車検12か月以内 | {R['s12']:,}件 |
| 平均経過年数 | {R['avg_age']:.1f}年 |
| 加入率 | 任意保険 {R['ins_rate']:.1%}／パックdeメンテ {R['pack_rate']:.1%}／スカイプラン {R['sky_rate']:.1%} |
| 車検の山 | {peak[:4]}年{int(peak[5:])}月 {cal[peak]}件 |

**車種 上位10【事実】**
| 車種 | 件数 | 平均経過年数 | 車検6か月以内 | 車種区分 | 提案車種 |
|---|---|---|---|---|---|
""" + '\n'.join(f"| {r['車種']} | {r['件数']} | {r['平均経過年数']}年 | {r['車検6か月以内']} | {r['車種区分']} | {r['提案車種']} |" for r in t2) + f"""

**車検到来カレンダー【事実】**
| 満了月 | {' | '.join(m[2:].replace('-', '/') for m in months[:-1])} |
|---|{'---|' * (len(months) - 1)}
""" + '\n'.join(f'| {s_} | {row_cal(s_)} |' for s_ in ST) + f"""

## 2. 分岐と件数【事実】
| 分岐 | {' | '.join(ST)} | 合計 |
|---|{'---|' * len(ST)}---|
""" + '\n'.join(f"| {k} | {' | '.join(str(P[k][s_]) for s_ in ST)} | {tot(k)} |" for k in P) + f"""
| （再掲）至急：車検2か月以内 | {' | '.join(str(R['urgent_store'].get(s_, 0)) for s_ in ST)} | {R['urgent']} |
| X1 パックdeメンテ未加入（6か月以内） | {' | '.join(str(R['x1_store'].get(s_, 0)) for s_ in ST)} | {R['x1']} |
| X2 任意保険未加入（6か月以内） | {' | '.join(str(R['x2_store'].get(s_, 0)) for s_ in ST)} | {R['x2']} |

**担当者別 優先度A件数（上位）**【事実】：""" + '、'.join(f'{k} {v}件' for k, v in list(R['aA_staff'].items())[:6]) + f"""

## 3. 配信スケジュール
分岐ごとの配信日と本文は `LINE_分岐別メッセージ案_{BASE:%Y%m%d}.md` の 0-3 と各章を参照してください。

**ステップ配信（車検の6・4・3・2か月前）の月別件数【事実】**
| 配信月 | 1回目 | 2回目 | 3回目 | 4回目 | 合計 |
|---|---|---|---|---|---|
""" + '\n'.join(f"| {m} | " + ' | '.join(str(st[n].get(m, 0)) for n in ['1回目', '2回目', '3回目', '4回目']) + f" | {sum(st[n].get(m, 0) for n in ['1回目', '2回目', '3回目', '4回目'])} |" for m in mon) + f"""

## 4. 各シートの改善点（Excelの4行目と同じ内容）
| シート | 改善点 |
|---|---|
{imp_lines}

## 5. KPI
| 指標 | 対象 |
|---|---|
| 車検予約率 | 至急 {R['urgent']}件・B {tot(key['B'])}件 |
| 試乗・査定・資料請求の予約数 | 優先度A {tot(key['A1']) + tot(key['A2']) + tot(key['A3'])}件 |
| 車検入庫率 | 車検6か月以内の{R['s6']}件のうち自店で車検を受けた割合 |
| 代替成約数 | 優先度Aのうち3か月以内の成約数 |
| アンケート回答率・ブロック率 | C1・C2 |

## 6. 次のアクション
| 優先 | 内容 | 担当（案） | 期限（案） |
|---|---|---|---|
| 1 | 至急{R['urgent']}件に車検予約の案内を配信し、担当者から電話 | 各担当者 | {D['至急'][0].split('）')[0]}） |
| 2 | スカイプラン加入フラグの意味（現在の契約か）と、A1対象者の満了時期を確認 | 店長・事務 | {fmt(add(s['A1'][0], -1), '').strip()} |
| 3 | 担当者「サービス」・未設定の方に営業担当を割り当て | 店長 | {fmt(add(s['A1'][0], -1), '').strip()} |
| 4 | 予算アンケートを配信し、暫定価格帯セグメントを置き換え | LINE運用担当 | {D['C2'][1].split('）')[0]}） |
| 5 | {peak[:4]}年{int(peak[5:])}月の車検の山に向けて、試乗枠・入庫枠を確保 | サービス・営業 | {int(peak[5:]) - 3 if int(peak[5:]) > 3 else int(peak[5:]) + 9}月末 |
| 6 | データ品質の修正（13_データ品質） | LINE運用担当 | 次回のデータ出力まで |
"""
open(f'{outdir}/LINE_セグメント配信計画_{BASE:%Y%m%d}.md', 'w', encoding='utf-8').write(plan)
print('docs OK', D)
