# 為什麼有 5.8% 的對局沒判出來（2026-08-29）

滿場地跑動（執行 144，450 場）有 26 場沒有判決。這份紀錄是從**已存在的執行資料**
裡找出原因並修掉，沒有重跑。

## 不是截斷

第一個要排除的假設。`Judge The Batch` 的 `simplify` 已經關掉，所以原始回應帶著
`stop_reason`：

```
150 次呼叫，stop_reason 全部是 end_turn
```

**一次截斷都沒有。** `maxTokens: 4000` 沒有被碰到。所以問題不在輸出預算。

## 原因一：欄位名跟答案值撞在一起

輸入用 `A` / `B` 當競爭者的鍵：

```json
{"match": 58, "A": "<甲的敘述>", "A_counts": {...}, "B": "<乙的敘述>", "B_counts": {...}}
```

而答案要求 `{"match":1,"winner":"A","reason":"..."}`。**同一個字母既是鍵也是值。**

模型於是把標籤寫成了欄位名：

```json
{"match":58,"A":"A","reason":"..."}       ← 鍵是 "A"，不是 "winner"
{"match":59,"B":"B","reason":"..."}
{"match":238,"A":"tie","reason":"..."}
```

有一筆更能說明混淆的程度——理由被放進 `"A"`，而 `winner` 同時也填對了：

```json
{"match":240,"A":"Both address plausible mechanistic...","winner":"A"}
```

## 原因二：模型會自我更正，而解析器只讀第一個物件

```
{"verdicts":[{"match":349,"A":"tie","reason":"placeholder"}, ...]}

Wait, I need to redo this properly.

{"verdicts":[{"match":349,"A":"A","reason":"Contribution: A establishes a foundational..."}]}
```

第二份才是模型真正的答案。搶救碼「讀第一個平衡物件」每次都拿到被作廢的那一份。

這條跟原因一無關，是獨立的第二個缺陷。

## 修法與實測效果

在**執行 144 的 150 份真實回應**上離線驗證，沒有重跑：

```
原本判出   424 / 450   （漏 26，5.8%）
修正後     441 / 450   （漏  9，2.0%）
```

救回 6 個批次（run 19、79、116、123、129、141）。

兩個改動：

1. **欄位改名去掉衝突**：`A` / `B` → `option_a` / `option_b`，答案值改成小寫
   `"a"` / `"b"` / `"tie"`。提示詞另外明講「答案只放在 `winner`，不要寫成
   `"option_a": "option_a"`」，並要求 **`winner` 寫在 `reason` 之前**——
   失敗的批次都是理由先寫、決定沒跟上。
2. **解析器取所有平衡物件裡「可用答案最多」的那個，平手取最後一個**，
   讓模型的更正勝過它自己作廢的版本。同時**接受舊的 `A`/`B` 鍵形狀**：
   只對格式正確的輸出有效的修正不算修正。

改名這一項**無法離線驗證**，因為那需要重新呼叫模型。解析器那一項已驗。

## 剩下的 2.0%，刻意不修

三個批次（9 場）模型**整個沒寫 winner 欄位**，但理由裡用白話講了勝負：

```
"...so A wins on conclusiveness."
"...whereas B's ... would settle a genuinely open interaction question either way, so B contributes more."
"B poses a coherent, testable epidemiological question ... while A's ... is incoherent"
```

**不去解析這段白話。** 第三個例子要真的讀懂才判得出來，而解析錯就是把勝負**判反**。

判反比判不出來糟得多：判不出來會被計分跳過，判反會拿捏造的證據去動 Elo 分數，
而且事後在排名裡看不出來。這跟「判不了的 `novelty_check.verdict` 存 NULL」
是同一條原則。

要真正收掉這 2%，做法是**把沒判出來的批次重判一次**（150 批裡約 3 批，成本增加約 2%），
不是再加一句提示詞——提示詞已經用大寫寫過「EVERY verdict must contain a winner field」，
還是漏了。
