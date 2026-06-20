from flask import Flask, render_template, request, redirect
from flask_sqlalchemy import SQLAlchemy
from dotenv import load_dotenv
import os
import re 
from urllib.parse import urljoin
import requests

from bs4 import BeautifulSoup

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from flask import Flask, render_template, request, redirect, jsonify
load_dotenv()
import json
import time
from collections import deque

load_dotenv()

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

    try:
        driver.get("https://quotes.toscrape.com/js/")

        quote_elements = driver.find_elements(
            By.CLASS_NAME,
            "quote"
        )

        quote_list = []

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
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    
    course_results = []

    for url in target_urls:
        try:
            res = requests.get(url, headers=headers, timeout=8)
            res.raise_for_status()
            # 💡 保留換行符號做精準切分標記
            html_content = res.text.replace("<br>", "【SPLIT】").replace("<br/>", "【SPLIT】").replace("</br>", "【SPLIT】")
            soup = BeautifulSoup(html_content, "html.parser")

            rows = soup.find_all("tr")
            for row in rows:
                cols = row.find_all(["td", "th"])
                if len(cols) < 2:
                    continue
                
                row_cells = [c.get_text(" ", strip=True) for c in cols]
                
                # 從這一排中抓取純粹的上課時間（排除含有中文字的欄位）
                base_time = ""
                for cell in row_cells:
                    time_match = re.search(r'\d{1,2}\s*:\s*\d{2}\s*[-~~]\s*\d{1,2}\s*:\s*\d{2}', cell)
                    if time_match and not re.search(r'[\u4e00-\u9fa5]', cell):
                        base_time = time_match.group(0).strip()
                        break

                for cell in cols:
                    raw_text = cell.get_text("【SPLIT】", strip=True)
                    potential_lines = [p.strip() for p in raw_text.split("【SPLIT】") if p.strip()]
                    
                    # 💡 鄰近智慧綁定核心：遍歷同一格內被切碎的各行文字
                    for idx, line_text in enumerate(potential_lines):
                        if keyword in line_text.lower():
                            # 排除掉單純只有時間的短行
                            if len(line_text) < 3 or re.search(r'^\d{1,2}\s*:\s*\d{2}', line_text):
                                continue
                            
                            # 🔍 往下一行找老師名字（通常為 2~4 個中文字）
                            teacher_name = "系所指派教師"
                            detected_time = ""
                            
                            if idx + 1 < len(potential_lines):
                                next_line = potential_lines[idx+1]
                                if re.match(r'^[\u4e00-\u9fa5]{2,4}$', next_line):
                                    teacher_name = next_line
                                elif re.search(r'\d{1,2}\s*:\s*\d{2}', next_line):
                                    detected_time = next_line

                            # 🔍 如果下一行被老師拿走了，再往後一行找教室與時間段
                            if idx + 2 < len(potential_lines) and not detected_time:
                                third_line = potential_lines[idx+2]
                                if re.search(r'\d{1,2}\s*:\s*\d{2}', third_line) or any(k in third_line for k in ["MA", "LE", "LH"]):
                                    detected_time = third_line

                            # 決定這堂課最終展示的時間與地點
                            final_time = detected_time if detected_time else base_time
                            
                            # 智慧計算學分
                            credits = "3.0 學分"
                            if "微積分" in line_text or "高微" in line_text:
                                credits = "4.0 學分"
                            else:
                                for p in row_cells:
                                    if "學分" in p or (p.replace('.', '', 1).isdigit() and float(p) < 6):
                                        credits = p if "學分" in p else f"{p} 學分"
                                        break
                            
                            course_type = "核心必修" if any(k in line_text.lower() or k in "".join(row_cells).lower() for k in ["必修", "必", "核心", "微積分", "代數"]) else "專業選修"

                            # 精準黏合成最完美的資訊展示串，餵飽前端預期的 raw_info
                            info_parts = [line_text, f"授課教授: {teacher_name}"]
                            if final_time:
                                info_parts.append(f"時間地點: {final_time}")
                            
                            raw_info_text = " | ".join(info_parts)

                            if any(item["raw_info"] == f"課程詳情：{raw_info_text}" for item in course_results):
                                continue

                            course_results.append({
                                "type": course_type,
                                "credits": credits,
                                "raw_info": f"課程詳情：{raw_info_text}",
                                "source": url
                            })

            # 策略二：防漏機制區塊搜尋
            elements = soup.find_all(["a", "li", "p", "div"])
            for elem in elements:
                try:
                    text = elem.get_text("【SPLIT】", strip=True)
                    parts = [p.strip() for p in text.split("【SPLIT】") if p.strip()]
                    for part in parts:
                        if keyword in part.lower() and 5 < len(part) < 120:
                            if any(bad in part for bad in [":::", "首頁", "版權所有", "電話", "傳真"]):
                                continue
                            if "國文" in part and keyword != "國文":
                                continue

                            credits = "3.0 學分"
                            if "微積分" in part:
                                credits = "4.0 學分"
                            
                            course_type = "核心必修" if any(k in part.lower() for k in ["必修", "微積分", "代數"]) else "專業選修"
                            
                            if any(item["raw_info"] == f"現場即時尋獲課堂：{part}" for item in course_results):
                                continue

                            course_results.append({
                                "type": course_type,
                                "credits": credits,
                                "raw_info": f"現場即時尋獲課堂：{part}",
                                "source": url
                            })
                except Exception:
                    pass

        except Exception as e:
            print(f"現場即時爬取網址出錯 ({url}): {e}")

    return course_results
    
@app.route("/api/course_search")
def course_search():
    keyword = request.args.get("keyword", "").strip().lower()
    if not keyword:
        return jsonify({"results": []})

    print(f"📡 爬蟲引擎啟動！正在即時為您現場爬取輔大數學系課程表網頁：'{keyword}'")

    results = live_course_crawler(keyword)
    
    print(f"✨ 現場爬取完畢，共撈出 {len(results)} 筆真實網頁數據。")
    return jsonify({"results": results})

@app.route("/smart_search")
def smart_search():
    return render_template("smart_search.html")

if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 5000)),
        debug=True,
    )