from flask import Flask, render_template, request, redirect, jsonify
from flask_sqlalchemy import SQLAlchemy
from dotenv import load_dotenv
import os
import re
from urllib.parse import urljoin
import requests

from bs4 import BeautifulSoup

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
load_dotenv()
import json
import time
from collections import deque

app = Flask(__name__)

app.config["SECRET_KEY"] = os.getenv("SECRET_KEY")
app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

class Todo(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    content = db.Column(
        db.String(200),
        nullable=False
    )
CACHE_FILE = "fju_all_data.json"
with app.app_context():
    db.create_all()

def load_all_cache():
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return None

def save_all_cache(data):  # ✨ 修正點：移除多餘的 all，確保定義正確
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
   
@app.route("/")
def home():
    return render_template("home.html")

@app.route("/html_tags")
def html_tags():
    return render_template("html_tags.html")

@app.route("/todo")
def todo():

    todos = Todo.query.all()

    return render_template(
        "todo.html",
        todos=todos
    )

@app.route("/add", methods=["POST"])
def add_todo():

    content = request.form.get("content")

    if content:

        new_todo = Todo(content=content)

        db.session.add(new_todo)

        db.session.commit()

    return redirect("/todo")

@app.route("/update/<int:id>", methods=["POST"])
def update_todo(id):

    todo = db.session.get(Todo, id)

    if todo:

        new_content = request.form.get("content")

        if new_content:

            todo.content = new_content

            db.session.commit()

    return redirect("/todo")

@app.route("/news")
def news():

    url = "https://news.ycombinator.com/"
    try:
        response = requests.get(url, timeout=10)
        soup = BeautifulSoup(response.text, "html.parser")
        title_spans = soup.select(".titleline")
        news_list = []
        for span in title_spans:
            a_tag = span.find("a")
            if a_tag:
                link = a_tag["href"]
                if link.startswith("item?"):
                    link = urljoin(url, link)
                news_list.append({"title": a_tag.text, "url": link})
        return render_template("news.html", news_list=news_list)
    except Exception as e:
        return f"新聞抓取失敗: {e}", 500
    
@app.route("/quotes")
def quotes():
    options = Options()
    options.binary_location = "/usr/bin/chromium"
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")

    driver = webdriver.Chrome(options=options)
    quote_list = []

    try:
        driver.get("https://quotes.toscrape.com/js/")

        quote_elements = driver.find_elements(
            By.CLASS_NAME,
            "quote"
        )

        for quote in quote_elements:

            text = quote.find_element(
                By.CLASS_NAME,
                "text"
            ).text

            author = quote.find_element(
                By.CLASS_NAME,
                "author"
            ).text

            quote_list.append({
                "text": text,
                "author": author
            })

    except Exception as e:
        print(f"Selenium 錯誤: {e}")

    finally:
        driver.quit()

    return render_template(
        "quotes.html",
        quote_list=quote_list
    ) 

def crawl_fju_all_system():
    start_url = "https://www.math.fju.edu.tw/"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    visited = set()
    queue = deque([start_url])
    collected_pages = []
    
    MAX_PAGES = 35

    while queue and len(visited) < MAX_PAGES:
        url = queue.popleft()

        # 💡 強制網址正規化：拔掉尾部斜線與參數
        url = url.strip().rstrip("/")
        url = url.split("?")[0] # 抹平所有網頁參數防止被繞過

        if url in visited:
            continue
        visited.add(url)

        try:
            if any(url.lower().endswith(ext) for ext in [".pdf", ".docx", ".jpg", ".png", ".xlsx", ".rar", ".zip"]):
                continue

            res = requests.get(url, headers=headers, timeout=5)
            if "text/html" not in res.headers.get("Content-Type", ""):
                continue

            res.raise_for_status()
            soup = BeautifulSoup(res.text, "html.parser")
            
            # 獲取標題與全網頁乾淨純文字
            title = soup.title.string.strip() if soup.title else "無標題網頁"
            
            # 💡 改進點 1：如果標題已經抓過了，說明是同一個頁面的不同變體網址，直接跳過
            if any(page["title"] == title for page in collected_pages):
                continue

            # 💡 雙重防禦鐵律 2：如果是純粹的英文版首頁重複切換，也扔掉
            if "Home" in title and "Department of Mathematics" in title and url != start_url:
                continue

            # 去除指令碼與樣式標籤避免雜訊
            for script in soup(["script", "style"]):
                script.decompose()
                
            clean_text = soup.get_text()
            # 💡 改進點 2：段落去重。利用 dict 保持順序並剃除手機/電腦版選單的重複文字
            raw_paragraphs = [p.strip() for p in clean_text.split("\n") if p.strip()]
            unique_paragraphs = list(dict.fromkeys(raw_paragraphs))
            
            # 擷取前15行不重複的乾淨段落作為摘要展示
            summary = " | ".join(unique_paragraphs[:15])

            collected_pages.append({
                "title": title,
                "url": url,
                "summary": summary[:150] + "..." if len(summary) > 150 else summary
            })

            # 自動向下延伸抓取系網內部連結
            for a in soup.find_all("a", href=True):
                link = urljoin(url, a["href"]).split("#")[0]
                if link.endswith("/"):
                    link = link[:-1]

                if "math.fju.edu.tw" in link and link not in visited:
                    queue.append(link)
        except Exception as e:
            pass
            
    return collected_pages

@app.route("/fju_math")
def fju_math():
    # 💡 修正關鍵點：強制刪除舊的快取文件，不讓舊資料鬼打牆
    if os.path.exists(CACHE_FILE):
        try:
            os.remove(CACHE_FILE)
            print("🧹 已成功銷毀舊有快取，即時重爬去重機制啟動！")
        except Exception:
            pass

    # 執行最新的無重複爬蟲
    data = crawl_fju_all_system()
    save_all_cache(data)
    return render_template("fju_math.html", result=data)


@app.route("/refresh_cache")
def refresh_cache():
    # 強制清空重爬系網所有資料
    data = crawl_fju_all_system()
    save_all_cache(data)
    return jsonify({"status": "success", "message": f"全站資料快取成功更新，共分析 {len(data)} 個系網網頁！"})

# =====================
# 功能二：【智能課程現場全自動查詢】（精準抓取：課程、老師、學分）
# =====================
def live_course_crawler(keyword):
    # 直接鎖定輔大數學系的核心開課資訊、課表、選課與公告網址出發
    target_urls = [
        "https://www.math.fju.edu.tw/zh-hant/courses/%E8%B3%87%E6%95%B8%E7%B5%84%E8%AA%B2%E8%A1%A8",
        "https://www.math.fju.edu.tw/zh-hant/courses/%E6%87%89%E6%95%B8%E7%B5%84%E8%AA%B2%E8%A1%A8",
        "https://www.math.fju.edu.tw/zh-hant/courses/bachelor-program-courses"
    ]
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    course_results = []
    
    for current_url in target_urls:
        try:
            res = requests.get(current_url, headers=headers, timeout=8)
            res.raise_for_status()
            
            soup = BeautifulSoup(res.text, "html.parser")

            # 銷毀噪音
            for noisy in soup(["nav", "footer", "header", "aside", "script", "style"]):
                noisy.decompose()
            
            # 💡 核心安全修正 1：只抓最小單位的 td 與 span，且字數限制在 60 字以內，徹底封鎖整坨大課表！
            elements = soup.find_all(["td", "span"])
            
            for elem in elements:
                text_content = elem.get_text().strip()
                
                # 擋掉整張課表的超長文字
                if len(text_content) > 60 or not text_content:
                    continue
                
                # 只有包含關鍵字才採集
                if keyword in text_content:
                    
                    # 抹平換行
                    clean_line = " ".join(text_content.split())
                    
                    # 擋掉無關的表頭字眼
                    if "星期" in clean_line or "組課表" in clean_line or "必修" in clean_line:
                        continue
                        
                    # 防止重複
                    if any(r["raw_info"] == clean_line for r in course_results):
                        continue
                    
                    # 💡 核心安全修正 2：利用最基礎的 if-in 語法進行性質與學分分類，完全不呼叫 re
                    core_required = ["微積分", "線性代數", "高等微積分", "代數", "幾何", "拓樸", "國文", "外國語文", "人生哲學", "導師時間", "程式設計", "Ｃ語言"]
                    
                    c_type = "選修"
                    for req in core_required:
                        if req in clean_line:
                            c_type = "必修"
                            break
                        
                    c_credits = "3 學分" # 預設選修與大部分專業課為 3 學分
                    
                    # 依據時段特徵自動歸類
                    if "10:10" in clean_line or "13:40" in clean_line or "15:40" in clean_line or "08:10" in clean_line:
                        c_credits = "2 學分"
                    
                    # 微積分特殊校正
                    if "微積分" in clean_line:
                        c_credits = "4 學分"
                    
                    course_results.append({
                        "type": c_type,
                        "credits": c_credits,
                        "raw_info": clean_line,
                        "source": current_url
                    })
                    
        except Exception as e:
            print(f"即時爬取發生錯誤: {e}")
            
    return course_results

# 💡 補齊前端 API 對接路由
@app.route("/api/course_search")
def api_course_search():
    keyword = request.args.get("keyword", "").strip()

    if not keyword:
        return jsonify({
            "status": "error",
            "message": "請輸入課程關鍵字",
            "results": []
        })

    results = live_course_crawler(keyword)

    return jsonify({
        "status": "success",
        "keyword": keyword,
        "count": len(results),
        "results": results
    })

@app.route("/smart_search")
def smart_search():
    return render_template("smart_search.html")

if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 5000)),
        debug=True,
    )