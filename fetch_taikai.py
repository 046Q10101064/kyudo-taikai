import os           #### Pythonプログラム ####
import json
import datetime
import requests
from bs4 import BeautifulSoup
from google import genai
from google.genai import types

# ==========================================
# 1. 巡回したい弓道連盟のURLリスト（ここに追加できます）
# ==========================================
TARGET_URLS = [
    "https://kyudo.jp",  # 全日本弓道連盟 行事予定
    # 今後、都道府県連盟の大会予定URLを以下のように追加していけます
    # "https://tokyo-kyudo.or.jp...",
]

def fetch_page_text(url):
    """Webページからテキストとリンク情報を抽出する"""
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        res = requests.get(url, headers=headers, timeout=15)
        res.encoding = res.apparent_encoding
        soup = BeautifulSoup(res.text, "html.parser")
        
        # 不要なスクリプトやスタイルを除去
        for tag in soup(["script", "style", "header", "footer", "nav"]):
            tag.decompose()
            
        # リンク先（PDFや要項ページ）のURLもテキストに補記してAIが参照先を分かるようにする
        for a in soup.find_all("a", href=True):
            href = requests.compat.urljoin(url, a["href"])
            a.append(f" [URL: {href}] ")
            
        text = soup.get_text(separator="\n", strip=True)
        return text[:15000]  # 文字数が多すぎる場合は先頭15,000文字に制限
    except Exception as e:
        print(f"取得エラー ({url}): {e}")
        return ""

def extract_events_with_gemini(client, page_text, source_url):
    """Gemini APIを使ってテキストから大会情報を7項目に整理する"""
    prompt = f"""
あなたは弓道大会の情報を整理するアシスタントです。
以下のWebページテキストから、これから開催される「弓道大会・競技会・審査」の情報を抽出し、JSON形式で出力してください。

【出力ルール】
- 必ず以下のキーを持つオブジェクトの配列（JSON）のみを出力してください。
- 情報が読み取れない項目は「要項を確認」としてください。
- 参照先URL（url）は、その大会の個別ページや要項PDFのURLがあればそれを、無ければ元のページURL（{source_url}）を入れてください。

【JSONの項目定義】
- date: 開催日（YYYY-MM-DD形式。例: 2026-12-06。複数日の場合は初日）
- date_display: 表示用の年月日（例: 2026年12月6日(日)）
- name: 大会名
- location: 大会場所（会場名や都道府県）
- qualification: 参加資格（例: 四段以上、連盟会員など）
- deadline: 申込期限（例: 2026年11月25日(水)）
- apply_to: 申込先（例: 各都道府県連盟、大会事務局など）
- url: 参照先URL

【抽出対象のテキスト】
{page_text}
"""
    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
            ),
        )
        return json.loads(response.text)
    except Exception as e:
        print(f"AI解析エラー ({source_url}): {e}")
        return []

def main():
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY が設定されていません。")

    client = genai.Client(api_key=api_key)
    all_events = []

    for url in TARGET_URLS:
        print(f"巡回中: {url}")
        text = fetch_page_text(url)
        if text:
            events = extract_events_with_gemini(client, text, url)
            if isinstance(events, list):
                all_events.extend(events)

    # 日本時間（JST）で現在時刻を取得
    jst = datetime.timezone(datetime.timedelta(hours=9))
    now_str = datetime.datetime.now(jst).strftime("%Y-%m-%d %H:%M")

    output_data = {
        "updated_at": now_str,
        "events": all_events
    }

    # Step 1の index.html が読み込む data.json として保存
    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)

    print(f"完了: {len(all_events)} 件の大会情報を data.json に保存しました。")

if __name__ == "__main__":
    main()