# 範式包與領域模組

**這是 `~/.claude/skills/domain-profile/` 的複本。** 那邊是編輯來源，這邊是部署來源。

```
packs/routing.md        路由自檢三問與選包規則（SKILL.md 的複本）
packs/paradigms/*.md    八個範式包：什麼算把一件事證明對了
packs/fields/*.md       五個領域模組：審稿人實際拿哪張清單來對
```

## 為什麼要複製一份

`domain-profile` 這個 skill 住在使用者的筆電上，Zeabur 上的 n8n 讀不到它。
W1 要判定領域框架、W3 的方法草圖要照範式決定三個組件的形態、S3 的方法軸要照範式
決定掃描什麼——這些都在雲端跑，都需要這些內容。

跟 `lib/search.py` 與 `lib/triage.py` 是同一個處理方式，理由也相同，見 README。

**副作用是好的**：CONTEXT.md 指出「系統橫跨三處，只有 repo 有版本控制」。
這些包原本不在版控裡，現在在了。

## 漂移的風險，以及怎麼看出來

**改了 skill 那邊，這裡不會自動跟上。** 兩份會分開走，而且不會有任何錯誤訊息。

同步方式：

```bash
S="$HOME/.claude/skills/domain-profile"
cp "$S/references"/*.md        packs/paradigms/
cp "$S/references/fields"/*.md packs/fields/
cp "$S/SKILL.md"               packs/routing.md
```

改動之後要 `POST /admin/sync-packs` 把新版灌進 `skill_prompt`，否則資料庫裡還是舊的。

## 為什麼還要進 `skill_prompt`

檔案在磁碟上就夠 n8n 取用了，再存一份進資料庫看起來多餘。不是的：

`skill_prompt` 是**當時實際生效的內容**的不可變紀錄，而 `project.domain_frame` 記
下用了哪個 key 的哪一版。半年後回頭看一份報告，要能知道當初是照哪一版的判準做的——
PRD 的硬規則寫著「報告要能單獨閱讀，不需要重跑系統就能知道當初為什麼選這個」。

磁碟上的檔案會隨部署改變，git 有歷史但對不回某一次跑動。這張表對得回去。
