"""
印尼每日新聞摘要 v4 (雜誌編輯風)
────────────────────────────
功能：
  1. 從 Google News RSS 抓印尼地區新聞（8 大類）
  2. 用 Gemini API 翻譯成中文 + 4-5 行摘要 + 對你的意義 + 重要性分級
  3. 抓即時匯率（TWD/USD/JPY → IDR）
  4. 累積最近 14 天，存進 data.json
  5. 推播每日精選到 Slack（選用）

環境變數（在 GitHub Secrets 設定）：
  GEMINI_API_KEY      - Gemini API 金鑰（不設就不翻譯）
  SLACK_WEBHOOK_URL   - Slack Incoming Webhook（不設就不推播）
  PAGE_URL            - GitHub Pages 網址，會放進 Slack 訊息（選用）
"""
import feedparser
import json
import os
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import quote
from pathlib import Path

# ============================================================
# 設定區
# ============================================================
CATEGORIES = {
    "經濟與匯率": {
        "icon": "💰",
        "key": "econ",
        "hue": 28,
        "query": "inflasi OR rupiah OR ekonomi OR BBM OR UMP",
        "desc": "通膨、匯率、最低薪資、燃料補貼 → 影響玩家購買力",
    },
    "宗教與節慶": {
        "icon": "🕌",
        "key": "religion",
        "hue": 168,
        "query": "Ramadan OR Lebaran OR \"Idul Fitri\" OR \"libur nasional\"",
        "desc": "齋戒月、開齋節、公眾假期 → 對 DAU 與儲值週期影響最大",
    },
    "法規政策": {
        "icon": "⚖️",
        "key": "policy",
        "hue": 220,
        "query": "KOMINFO OR \"judi online\" OR OJK OR \"aplikasi diblokir\"",
        "desc": "App 下架/封鎖、博弈相關言論、金融監管",
    },
    "行動支付": {
        "icon": "💳",
        "key": "pay",
        "hue": 142,
        "query": "GoPay OR DANA OR OVO OR ShopeePay OR \"dompet digital\"",
        "desc": "電子錢包動態 → 玩家儲值通路",
    },
    "電信網路": {
        "icon": "📶",
        "key": "telecom",
        "hue": 260,
        "query": "Telkomsel OR Indosat OR \"paket data\" OR \"kuota internet\"",
        "desc": "資費、網路品質 → 影響連線體驗與 Pulsa 儲值",
    },
    "遊戲產業": {
        "icon": "🎮",
        "key": "game",
        "hue": 320,
        "query": "\"game mobile\" Indonesia OR \"aplikasi game\"",
        "desc": "競品與市場動態",
    },
    "流行文化": {
        "icon": "🔥",
        "key": "culture",
        "hue": 12,
        "query": "viral Indonesia OR \"tren TikTok\"",
        "desc": "行銷素材靈感",
    },
    "重大事件": {
        "icon": "⚠️",
        "key": "major",
        "hue": 0,
        "query": "gempa OR banjir OR pemilu OR \"bencana alam\"",
        "desc": "天災、選舉、社會大事件 → 活動排程要避開",
    },
}

ITEMS_PER_CATEGORY = 8
HOURS_LOOKBACK = 36
KEEP_DAYS = 14
DATA_FILE = "data.json"
TPE = timezone(timedelta(hours=8))


# ============================================================
# 1. 抓 RSS
# ============================================================
def fetch_news(query):
    encoded = quote(query)
    url = (
        f"https://news.google.com/rss/search?"
        f"q={encoded}&hl=id&gl=ID&ceid=ID:id"
    )
    feed = feedparser.parse(url)
    cutoff = datetime.now(timezone.utc) - timedelta(hours=HOURS_LOOKBACK)
    items = []

    for entry in feed.entries:
        pub_time = None
        if hasattr(entry, "published_parsed") and entry.published_parsed:
            pub_time = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
            if pub_time < cutoff:
                continue

        title = entry.title
        source = ""
        if " - " in title:
            title, source = title.rsplit(" - ", 1)

        items.append({
            "title": title.strip(),
            "link": entry.link,
            "source": source.strip(),
            "time": pub_time.isoformat() if pub_time else None,
        })

        if len(items) >= ITEMS_PER_CATEGORY:
            break
    return items


# ============================================================
# 2. 翻譯 + 分析（Gemini API）
# ============================================================
def translate_batch(items):
    """整批翻譯。失敗回傳空 dict，HTML 會 fallback 顯示原文。"""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("  ⚠️  未設定 GEMINI_API_KEY → 跳過翻譯")
        return {}
    try:
        from google import genai
        from google.genai import types
    except ImportError:
        print("  ⚠️  未安裝 google-genai 套件 → 跳過翻譯")
        return {}

    client = genai.Client(api_key=api_key)

    items_text = "\n".join(
        f'{i + 1}. [{it["source"]}] {it["title"]}'
        for i, it in enumerate(items)
    )

    prompt = f"""你是印尼市場手遊 PM 的私人新聞助手。

讀者背景：在台灣公司做印尼市場手機遊戲產品（牌類撲克/賭場機台類），關注：
- 玩家儲值習慣與通路（GoPay/DANA/OVO/ShopeePay/Pulsa 電信儲值）
- 印尼齋戒月、開齋節、宰牲節等節慶對 DAU 與儲值週期的影響
- 博弈相關法規風向（特別是 KOMINFO 對 App 的封鎖、OJK 對金流的監管）
- 高價值玩家（單日儲值 3000+ TWD 等級的「超級戶」）的維繫
- 通膨/匯率/購買力變化對玩家儲值意願的衝擊
- 在地競品、行銷素材靈感（TikTok 趨勢、本土文化）

請為以下每則印尼新聞輸出：
1. title_zh: 翻譯成繁體中文（台灣用語）
2. summary_zh: 重點摘要，**120-180 字（約 4-5 行）**。要涵蓋關鍵的人事時地物與數字，讓讀者不點原文也能掌握主要內容。寫成完整段落，不用條列。
3. impact_zh: 1-2 句「對你的意義」——必須具體連結到上述背景，指出結構性訊號、策略意涵或具體行動點。**避免「這對產業有影響」這類沒資訊量的廢話**。若該則新聞對讀者業務影響很弱，impact_zh 直接填「相關性低，僅供背景參考」。
4. priority: "high" | "medium" | "low"，依下列原則分級：
   - "high": 對業務有結構性、直接的影響（**每天最多 3-5 則**）
   - "medium": 值得知道、有間接影響（每天約 5-10 則）
   - "low": 相關性低、僅供背景參考（其餘多數）

只回傳 JSON 陣列，不要任何說明文字或 markdown 圍欄：
[{{"id": 1, "title_zh": "...", "summary_zh": "...", "impact_zh": "...", "priority": "high"}}, ...]

新聞清單：
{items_text}"""

    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
            ),
        )
        text = (response.text or "").strip()
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
        translations = json.loads(text)
        result = {t["id"]: t for t in translations}
        print(f"  ✓ 翻譯成功 {len(result)} 則")
        return result
    except Exception as e:
        print(f"  ⚠️  翻譯失敗（會顯示原文）: {e}")
        return {}


# ============================================================
# 3. 匯率（free API，失敗則略過）
# ============================================================
def fetch_rates():
    """抓即時匯率。失敗回傳空 dict，前端會隱藏匯率列。
    使用 open.er-api.com（免費、無 API key、每日更新）。"""
    try:
        import requests
    except ImportError:
        return {}
    try:
        # base=USD，可以從中換算 TWD/IDR、JPY/IDR
        r = requests.get("https://open.er-api.com/v6/latest/USD", timeout=8)
        if not r.ok:
            print(f"  ⚠️  匯率 API 失敗 {r.status_code}")
            return {}
        data = r.json()
        rates = data.get("rates", {})
        idr = rates.get("IDR")
        twd = rates.get("TWD")
        jpy = rates.get("JPY")
        if not (idr and twd and jpy):
            print("  ⚠️  匯率資料不完整")
            return {}
        result = {
            "USD_IDR": round(idr, 2),
            "TWD_IDR": round(idr / twd, 2),
            "JPY_IDR": round(idr / jpy, 2),
            "fetched_at": datetime.now(TPE).isoformat(),
        }
        print(f"  ✓ 匯率：USD/IDR={result['USD_IDR']:,} TWD/IDR={result['TWD_IDR']} JPY/IDR={result['JPY_IDR']}")
        return result
    except Exception as e:
        print(f"  ⚠️  匯率錯誤: {e}")
        return {}


def compute_rate_changes(today_rates, prev_rates):
    """計算與前一日的變化百分比"""
    if not today_rates or not prev_rates:
        return today_rates
    for k in ["USD_IDR", "TWD_IDR", "JPY_IDR"]:
        if k in today_rates and k in prev_rates and prev_rates[k]:
            change = (today_rates[k] - prev_rates[k]) / prev_rates[k] * 100
            today_rates[k + "_change"] = round(change, 2)
    return today_rates


# ============================================================
# 4. 資料存取
# ============================================================
def load_data():
    p = Path(DATA_FILE)
    if not p.exists():
        return {"categories_meta": {}, "dates": [], "data": {}}
    return json.loads(p.read_text(encoding="utf-8"))


def save_data(data):
    Path(DATA_FILE).write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def prune_old(data, keep_days):
    dates_sorted = sorted(data["dates"], reverse=True)
    keep = dates_sorted[:keep_days]
    data["dates"] = sorted(keep)
    data["data"] = {d: data["data"][d] for d in keep if d in data["data"]}
    return data


# ============================================================
# 5. Slack 推播（同 v3）
# ============================================================
def send_slack(today_data, page_url):
    webhook = os.getenv("SLACK_WEBHOOK_URL")
    if not webhook:
        print("  ⚠️  未設定 SLACK_WEBHOOK_URL → 跳過推播")
        return
    try:
        import requests
    except ImportError:
        return

    today_str = datetime.now(TPE).strftime("%Y/%m/%d")
    total = sum(len(v) for v in today_data["categories"].values())
    header_text = f"🇮🇩 印尼每日新聞摘要 · {today_str}"
    if page_url:
        context_text = f"共 {total} 則 | <{page_url}|📊 看完整報告>"
    else:
        context_text = f"共 {total} 則"

    blocks = [
        {"type": "header", "text": {"type": "plain_text", "text": header_text}},
        {"type": "context", "elements": [{"type": "mrkdwn", "text": context_text}]},
        {"type": "divider"},
    ]

    for cat, items in today_data["categories"].items():
        if not items:
            continue
        # 只取 priority=high 的當推播，最多 2 則
        high_items = [it for it in items if it.get("priority") == "high" or it.get("important")]
        top = (high_items[:2] if high_items else items[:1])
        icon = CATEGORIES.get(cat, {}).get("icon", "•")
        lines = []
        for it in top:
            title = it.get("title_zh") or it["title"]
            if len(title) > 80:
                title = title[:77] + "..."
            lines.append(f"• <{it['link']}|{title}>")
        if lines:
            blocks.append({
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*{icon} {cat}*\n" + "\n".join(lines)},
            })

    try:
        r = requests.post(webhook, json={"blocks": blocks}, timeout=10)
        if r.ok:
            print("  ✓ Slack 推播成功")
        else:
            print(f"  ⚠️  Slack 失敗 {r.status_code}")
    except Exception as e:
        print(f"  ⚠️  Slack 錯誤: {e}")


# ============================================================
# 主流程
# ============================================================
def main():
    print("=" * 50)
    print(f"印尼每日新聞 · {datetime.now(TPE).strftime('%Y-%m-%d %H:%M')}")
    print("=" * 50)

    today_str = datetime.now(TPE).strftime("%Y-%m-%d")

    # Step 1: 抓新聞
    print("\n📰 抓取 RSS：")
    today_data = {"generated_at": datetime.now(TPE).isoformat(), "categories": {}}
    all_items_flat = []
    for cat, cat_data in CATEGORIES.items():
        print(f"  {cat} ... ", end="", flush=True)
        try:
            news = fetch_news(cat_data["query"])
            today_data["categories"][cat] = news
            all_items_flat.extend(news)
            print(f"{len(news)} 則")
        except Exception as e:
            print(f"⚠️  錯誤: {e}")
            today_data["categories"][cat] = []

    # Step 2: 翻譯 + 分析
    if all_items_flat:
        print(f"\n🌏 翻譯與分析 {len(all_items_flat)} 則新聞...")
        translations = translate_batch(all_items_flat)
        if translations:
            idx = 0
            for cat in today_data["categories"]:
                for it in today_data["categories"][cat]:
                    idx += 1
                    t = translations.get(idx)
                    if t:
                        it["title_zh"] = t.get("title_zh", "")
                        it["summary_zh"] = t.get("summary_zh", "")
                        it["impact_zh"] = t.get("impact_zh", "")
                        # priority + 向下相容的 important
                        priority = t.get("priority", "low")
                        if priority not in ("high", "medium", "low"):
                            priority = "low"
                        it["priority"] = priority
                        it["important"] = (priority == "high")  # 向下相容

    # Step 3: 抓匯率（與前一日比較）
    print("\n💱 抓取匯率：")
    today_rates = fetch_rates()
    data = load_data()
    if today_rates and data["dates"]:
        # 取最近一天有匯率的資料作為前一日基準
        for d in sorted(data["dates"], reverse=True):
            prev = data["data"].get(d, {}).get("rates")
            if prev:
                today_rates = compute_rate_changes(today_rates, prev)
                break
    today_data["rates"] = today_rates

    # Step 4: 寫入 data.json
    print("\n💾 更新 data.json...")
    data["categories_meta"] = {
        cat: {"icon": d["icon"], "key": d["key"], "hue": d["hue"], "desc": d["desc"]}
        for cat, d in CATEGORIES.items()
    }
    if today_str not in data["dates"]:
        data["dates"].append(today_str)
    data["data"][today_str] = today_data
    data = prune_old(data, KEEP_DAYS)
    save_data(data)

    total = sum(len(v) for v in today_data["categories"].values())
    high = sum(1 for cat in today_data["categories"].values() for it in cat if it.get("priority") == "high")
    print(f"  ✓ {today_str} 共 {total} 則（高重要性 {high} 則，保留 {len(data['dates'])} 天）")

    # Step 5: Slack 推播
    page_url = os.getenv("PAGE_URL", "").strip()
    print("\n📢 Slack 推播：")
    send_slack(today_data, page_url)

    print("\n" + "=" * 50)
    print("✅ 完成")
    print("=" * 50)


if __name__ == "__main__":
    main()
