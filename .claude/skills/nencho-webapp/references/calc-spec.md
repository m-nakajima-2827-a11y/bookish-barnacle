# 計算仕様（engine.js）

`Nencho.calculate(employee)` が1人分の年末調整を計算し、計算シート①〜㉞・Ⓐ〜Ⓘ・警告・確定申告判定を返します。

## 1. 入力データ（employee）

| パス | 内容 | 元Excel |
|---|---|---|
| `profile.*` | 氏名・フリガナ・生年月日・住所・支払者 | 計算シート E3/E4 |
| `payroll.salary[0..11]` | `payDate, gross, social(小規模共済の天引き含む), smallBiz(うち小規模), depCount, tax(算出税額), adj(過不足)` | 集計シート 3〜14行 |
| `payroll.bonus[0..3]` | 同上 | 集計シート 16〜19行 |
| `fuyo.self` | `disability: none/general/special`, `widow: none/widow/single_parent`, `student: bool` | Ⓔ〜Ⓘ |
| `fuyo.dependents[]` | `name, relation, lineal(直系尊属・省略時は続柄から判定), birth, income(合計所得見積), cohabit, nonResident, nrReason, disability` | Ⓐ〜Ⓖ・⑱ |
| `kiso.otherIncome` | 給与所得以外の所得の合計額 | 基礎控除申告書 |
| `spouse` | `has, name, birth, income, disability, cohabit, nonResident` | ⑰・V22 |
| `chosei.mode` | `auto / yes / no` | T18 |
| `hoken.life[]` | `kind: general/care/pension, era: new/old, amount` | ⑮ |
| `hoken.quake[]` | `kind: quake/oldlong, amount` | ⑯・V24 |
| `hoken.social[]` | `kind, payer, person, amount, nationalPension` | ⑬・V28 |
| `hoken.smallBiz[]` | `kind, amount` | ⑭ |
| `jutaku` | `balance, rate, limit, direct` | ㉔ |
| `settle` | `r28, r29, r31, r33`（空欄＝自動） | ㉘㉙㉛㉝ |
| `kakutei` | `multipleEmployers, medical, donation, housingFirstYear, casualty` | 確定申告チェック |
| `overrides` | `{ r1: 金額, … }` 計算シートの手入力（上書き） | 計算シートを直接修正するのと同じ |

## 2. 計算順序

1. **集計**：① = Σ給料 gross、③ = Σ給料 tax、④⑥ = 賞与、⑦ = ①＋④、⑧ = ③＋⑥、⑫ = Σsocial（給料＋賞与）
2. **扶養親族の自動区分**（`classifyDependent`）：年末年齢＝`年 − 生年 + (1月1日生なら1)`
   - 合計所得 ≤ 62万 → 扶養親族：16歳未満＝年少（控除なし）／非居住者30〜69歳で要件なし＝控除対象外／19〜22歳＝特定扶養／70歳以上＝直系尊属かつ同居なら同居老親等、それ以外は老人／その他＝一般
   - 62万超 123万以下かつ19〜22歳 → 特定親族（特定親族特別控除の表）
   - 障害者控除は扶養親族（年少を含む）と同一生計配偶者（所得62万以下）・本人が対象。特別障害者で同居なら同居特別障害者
3. **所得金額調整控除の判定**：本人が特別障害者／同一生計配偶者が特別障害者／扶養親族が特別障害者又は23歳未満 → 自動「有」（`chosei.mode` で上書き可）
4. ⑨ = `salaryIncomeAfterDeduction(⑦)`（元Excel M17と同じ式）、⑩ = 有かつ⑦>850万なら `min(ceil((min(⑦,1000万)−850万)×10%),15万)`、⑪ = ⑨−⑩
5. **本人の合計所得** = ⑪＋給与以外の所得 → ⑳基礎控除・区分Ⅰ（A/B/C）
6. ⑬⑭ = 申告分の合計、⑮ = 生命保険料控除（23歳未満の扶養親族がいれば計算式Ⅱ）、⑯ = 地震保険料控除
7. ⑰ = 配偶者（特別）控除（区分Ⅰ×配偶者所得・70歳以上）、⑱ = 特定親族特別控除の合計、⑲ = Ⓐ〜Ⓘの金額合計
8. ㉑ = ⑫〜⑳の合計、㉒ = ⑪<㉑なら0、それ以外は(⑪−㉑)の1,000円未満切捨て、㉓ = 速算表
9. ㉔ = 直接入力 又は min(残高×控除率, 限度額) を100円未満切捨て・最高60万、㉕ = max(㉓−㉔,0)、㉖ = floor100(㉕×1.021)
10. ㉗ = |㉖−⑧|、⑧>㉖なら差引超過額（還付）、⑧<㉖なら差引不足額（徴収）
11. 精算：超過 → ㉚ = ㉗−㉘−㉙、㉛（既定＝㉚）、㉜ = ㉚−㉛／不足 → ㉝（既定＝㉗）、㉞ = ㉗−㉝
12. `yearEndAdjustment` = 超過なら −㉗、不足なら +㉗（集計シートJ列＝年末調整による過不足税額に記入する値）

各欄は `overrides.rN` が入っていればその値を採用し、以降の計算もその値で続けます（元Excelで欄を手入力した場合と同じ）。

## 3. 出力（result）

- `lines.r1〜r34`：計算シートの各欄
- `fuyo.box`（Ⓐ〜Ⓘの人数・該当）／`fuyo.amounts`（金額）／`fuyo.dependents`（各人の判定・メモ）
- `spouse`（区分Ⅰ・区分Ⅱ・種類・金額）、`life`、`quake`、`totalIncome`、`choseiApplicable`、`hasUnder23Dependent`
- `withholdingCount`：源泉徴収税額表の「扶養親族等の数」（参考値。源泉控除対象配偶者・源泉控除対象親族・本人の障害者等・障害者の加算）
- `warnings[]`：`error`（元Excelのエラーメッセージ相当）／`warn`（要件逸脱の可能性）／`info`（入力漏れ・手続の案内）
- `kakutei[]`・`kakuteiRequired`：確定申告の要否
- `outOfScope`：給与等の総額2,000万円超

## 4. 検証済みの内容
- 給与所得控除後の金額（境界値17点）、基礎控除、配偶者控除、特定親族、年齢・区分、生命保険（計算式Ⅰ〜Ⅲ・切上げ）、地震、速算表：`scripts/test_engine.js`
- Excel出力の関数をLibreOfficeで再計算し、計算シート①〜㉞がエンジンと一致（4シナリオ）：`scripts/verify_workbook.js`
- 画面操作（PDF取込→集計→扶養判定→保険→上書き→Excel出力、スマホ幅）：`scripts/e2e_test.js`
