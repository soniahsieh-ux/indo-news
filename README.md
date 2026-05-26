# 🇮🇩 印尼每日新聞 v4（雜誌編輯風）

每天自動從 Google News 抓取印尼地區新聞，用 Gemini 翻譯成中文、寫 4-5 行摘要、加上「對你的意義」分析、自動分級高/中/低重要性，保留最近 14 天歷史。**雜誌編輯風版面**，零成本運行。

## ✨ v4 改版重點

- 📰 **雜誌頭版視覺** —— 大字 serif 報頭、上方匯率列、報紙質感版面
- 📅 **14 天日期條** —— 頁面頂端固定，今日紅點標示，週末紅字
- 🗂 **上方類別 Tab** —— 不用再下捲找類別，一鍵切換
- ⭐ **「今日必看」頭版區** —— Lead Story + 編號 02-04 精選清單
- 📑 **單類別 Focus 模式** —— 點任一類別 → 該類別全展開
- 🔍 **全文搜尋** —— 點 🔍 搜尋當日所有新聞
- 📝 **長摘要** —— 每則新聞 4-5 行完整摘要（不點原文也能看懂主要內容）
- 🎯 **三級重要性** —— ● 高重要性 / ● 中等 / ● 一般（自動判定）
- 💱 **即時匯率** —— TWD/USD/JPY → IDR，含與前日漲跌幅
- 📱 **手機友善** —— 雜誌版面自動塌成單欄

## 📁 檔案結構

```
indo-news/
├─ scraper.py            ← 主程式（要改關鍵字、prompt 看這個）
├─ index.html            ← 雜誌風前端（CSS+JS 都在裡面）
├─ requirements.txt
├─ README.md
├─ data.json             ← 14 天歷史（自動產生與更新）
└─ .github/workflows/
   └─ daily.yml          ← 自動排程
```

## 🚀 升級步驟（v3 → v4）

如果已經部署 v3，只要做這幾件事：

1. **覆蓋這 4 個檔案**到既有的 repo：
   - `scraper.py`、`index.html`、`requirements.txt`、`README.md`
2. **保留現有的 `data.json`**——舊資料會被前端自動相容處理（沒有 priority 欄位的舊新聞會顯示為「高」或「一般」）
3. **不用動任何 Secrets / Variables / 排程**——GEMINI_API_KEY、SLACK_WEBHOOK_URL、PAGE_URL 全部維持
4. 去 `Actions` 手動 `Run workflow` 跑一次新版

升完後第一天，**今天的新聞**會是新版的（含長摘要、priority、匯率），但**過去 13 天**還是舊版資料；14 天後全部新格式。

## ⚙️ 自訂方式

### 改新聞類別 / 關鍵字
`scraper.py` 最上面 `CATEGORIES` 字典。每類有：
- `icon`: emoji（已不直接顯示在新版視覺，保留以備將來用）
- `key`: 英文代號（CSS class 用）
- `hue`: 0-360 色相值（圖片區漸層色）
- `query`: Google News 搜尋字串
- `desc`: 中文說明

### 改重要性分級邏輯
`scraper.py` 找 `translate_batch` 函式裡的 prompt，第 4 條 priority 那段。預設：
- high: 每天 3-5 則
- medium: 每天 5-10 則
- low: 其餘多數

### 改「對你的意義」的觀點背景
`scraper.py` 同樣在 prompt 裡，「讀者背景」段落。改成你想要的角度（例如改成行銷視角、決策者視角等）。

### 改執行時間
`.github/workflows/daily.yml`：
```yaml
- cron: '0 23 * * *'   # UTC 23:00 = 台北 07:00
```

## 💰 成本

- GitHub Actions（Public repo）：免費
- GitHub Pages：免費
- Gemini API（免費版）：免費，每天 250 次請求，腳本只用 1 次
- 匯率 API（open.er-api.com）：免費，無 key
- 字型（Google Fonts）：免費 CDN

**完全免費**。

## ❓ FAQ

**Q：第一次跑完版面看起來怪怪的？**
A：可能是字型還在載入，等 5 秒後重整。Noto Serif TC / Noto Sans TC 第一次從 Google Fonts CDN 下載要時間。

**Q：匯率沒有出現？**
A：可能 open.er-api.com 暫時無法存取。前端會自動隱藏匯率列。

**Q：「今日必看」挑得太多 / 太少？**
A：去 scraper.py 改 prompt 裡 priority 的判定原則（建議每天 high 維持 3-5 則）。

**Q：怎麼從 v4 切回 v3？**
A：保留你 v3 的 index.html 備份，覆蓋回去就好。data.json 是相容的，不會有問題。

## 📝 致謝

- 資料：Google News
- 翻譯與分析：Google Gemini（2.5 Flash）
- 匯率：open.er-api.com
- 字型：Google Fonts（Noto Serif TC、Noto Sans TC）
- 設計：雜誌編輯風 B 方案
