# research-api

n8n 透過 Zeabur 私有網路呼叫的計算層。包裝文獻檢索與點子分流腳本成 HTTP 端點。

## 端點

| 方法 | 路徑 | 用途 |
|---|---|---|
| GET | `/healthz` | 健康檢查（不需金鑰） |
| POST | `/compute/search/query` | 多來源文獻檢索與合併去重 |
| POST | `/compute/search/vocab` | MeSH／OpenAlex 詞彙展開 |
| POST | `/compute/search/chain` | 引用鏈遍歷 |
| POST | `/compute/triage/dedup` | 近重複候選配對 |
| POST | `/compute/triage/pairs` | 錦標賽賽程（含批次隔離） |
| POST | `/compute/triage/elo` | ELO 計算與錨點校準 |

除 `/healthz` 外都需要 `X-API-Key` 標頭。

## 環境變數

| 變數 | 必要 | 說明 |
|---|---|---|
| `API_KEY` | 是 | n8n 呼叫時要帶的金鑰 |
| `PORT` | 否 | Zeabur 自動注入 |
| `ACADEMIC_MAILTO` | 否 | OpenAlex／Crossref polite pool |
| `NCBI_API_KEY` | 否 | PubMed 速率 3→10 req/s |

## 本機測試

```bash
pip install -r requirements.txt
API_KEY=testkey123 python -m uvicorn main:app --port 8111
curl http://127.0.0.1:8111/healthz
```

## 注意

`lib/search.py` 與 `lib/triage.py` 是 Claude Code skill 腳本的複本。
改動 skill 那邊之後，要重新複製過來。

`profile.py` 刻意不在此處——資料剖析只在本機執行，原始研究資料永不上雲。
