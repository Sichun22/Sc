from flask import Flask, render_template, request, redirect, jsonify
from flask_sqlalchemy import SQLAlchemy
from dotenv import load_dotenv
import os
import re
from pathlib import Path
from urllib.parse import urljoin
import requests

from bs4 import BeautifulSoup

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
project_root = Path(__file__).resolve().parent
load_dotenv(project_root / ".env")
import json
import time
from collections import deque

project_root = Path(__file__).resolve().parent
load_dotenv(project_root / ".env")

app = Flask(__name__)

app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-secret-key")
configured_database_uri = os.getenv("DATABASE_URL") or os.getenv("SQLALCHEMY_DATABASE_URI")
if configured_database_uri:
    app.config["SQLALCHEMY_DATABASE_URI"] = configured_database_uri
else:
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///todo.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

class Todo(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    content = db.Column(
        db.String(200),
        nullable=False
    )
CACHE_FILE = "fju_all_data.json"


def initialize_database():
    try:
        with app.app_context():
            db.create_all()
            if Todo.query.count() == 0:
                seed_todo = Todo(content="歡迎使用輔大數學系 Flask 網站")
                db.session.add(seed_todo)
                db.session.commit()
        print(f"資料庫初始化成功：{app.config['SQLALCHEMY_DATABASE_URI']}")
        return True
    except Exception as exc:
        print(f"資料庫初始化失敗，改用 SQLite 備用: {exc}")
        app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///todo.db"
        if hasattr(db, "engine"):
            db.engine.dispose()
        with app.app_context():
            db.create_all()
            if Todo.query.count() == 0:
                seed_todo = Todo(content="歡迎使用輔大數學系 Flask 網站")
                db.session.add(seed_todo)
                db.session.commit()
        return False


initialize_database()

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
# 功能二：【智能課程查詢】
# 修正版重點：
# 1. 不再只抓單一 td/span，改用整頁文字順序解析「課名 → 老師 → 時間 → 教室」
# 2. 查詢結果只顯示課程名稱、任課老師、上課時間與教室
# 3. 支援同義關鍵字，例如「AI」可查到「人工智慧概論」
# =====================
COURSE_URLS = [
    {
        "group": "資數組課表",
        "url": "https://www.math.fju.edu.tw/zh-hant/courses/%E8%B3%87%E6%95%B8%E7%B5%84%E8%AA%B2%E8%A1%A8",
    },
    {
        "group": "應數組課表",
        "url": "https://www.math.fju.edu.tw/zh-hant/courses/%E6%87%89%E6%95%B8%E7%B5%84%E8%AA%B2%E8%A1%A8",
    },
    {
        "group": "學士班課程",
        "url": "https://www.math.fju.edu.tw/zh-hant/courses/bachelor-program-courses",
    },
]

COURSE_ALIASES = {
    "ai": ["人工智慧", "人工智慧概論"],
    "AI": ["人工智慧", "人工智慧概論"],
    "程式": ["程式設計", "Ｃ語言", "C語言", "動態網頁設計", "行動裝置程式設計"],
    "微積分": ["微積分", "高等微積分"],
    "線代": ["線性代數"],
}

TIME_PATTERN = re.compile(r"\d{1,2}:\d{2}\s*-\s*\d{1,2}:\d{2}")
ROOM_PATTERN = re.compile(r"^(?:MA|LH|LE|SE|SF|SL|ES|LM|FG|TC|BS|MD|DG|HE|LB|JS|YP|SEB)[A-Z0-9-]*\d*$|排球場|操場|體育館")
COURSE_ID_PATTERN = re.compile(r'[A-Z][A-Z0-9-]{5,15}') 
CREDIT_PATTERN = re.compile(r'(\d)-(\d)')

IGNORE_LINES = {"星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日", "必修", "必選", "選修", "* * *", "English", "首頁", "最新消息", "課程資訊"}
COURSE_LINE_HINTS = ["課", "班", "程", "設", "概", "論", "微", "線", "數", "學"]
COURSE_NAME_HINTS = ["課程", "概論", "設計", "程式", "微積分", "線性", "人工智慧", "應用", "數學"]

def normalize_keyword(keyword):
    keyword = (keyword or "").strip()
    words = [keyword]
    words.extend(COURSE_ALIASES.get(keyword, []))
    return list(dict.fromkeys([w for w in words if w]))

def clean_course_lines(soup):
    for noisy in soup(["nav", "footer", "header", "aside", "script", "style"]):
        noisy.decompose()

    lines = []
    for line in soup.get_text("\n").split("\n"):
        line = " ".join(line.strip().split())
        if not line:
            continue
        if line in IGNORE_LINES:
            continue
        if len(line) > 80:
            continue
        lines.append(line)
    return lines

def looks_like_noise(line):
    noise_words = ["輔仁大學數學系", "系所公告", "課程公告", "師資介紹", "辦法表格", "學生園地", "相關連結", "課程地圖", "學士班課程", "碩士班課程", "資數一", "資數二", "資數三", "資數四", "應數一", "應數二", "應數三", "應數四", "114 學年度", "113 學年度"]
    if any(word in line for word in noise_words): return True
    if len(line) <= 1: return True
    if any(k in line for k in ["微積分", "線代", "代數", "程式", "C語言", "Ｃ語言"]): return False
    if not any(ch in line for ch in COURSE_LINE_HINTS) or not any(hint in line for hint in COURSE_NAME_HINTS): return True
    return False

def find_next_time_and_room(lines, start_index, max_scan=6):
    teacher, course_time, room = "", "", ""
    for j in range(start_index + 1, min(len(lines), start_index + max_scan + 1)):
        line = lines[j].strip()
        if not course_time and TIME_PATTERN.search(line):
            course_time = TIME_PATTERN.search(line).group(0)
            continue
        if not room and ROOM_PATTERN.search(line):
            room = line
            continue
        if not teacher and 2 <= len(line) <= 4 and not any(ch in line for ch in ["⏳", "級", "班", "組", "週"]):
            if line not in ["星期", "必修", "選修", "學分"]:
                teacher = line
                continue
    return teacher, course_time, room


# 放寬課號匹配：支援任何包含大寫英文字母跟數字的課號，或者根本沒有課號也沒關係
COURSE_ID_PATTERN = re.compile(r'[A-Z][A-Z0-9-]{5,15}') 
CREDIT_PATTERN = re.compile(r'(\d)-(\d)')  # 匹配學分格式 (如 4-0, 0-3)

def auto_extract_course_details(line):
    course_name, teacher, credits = line.strip(), "未定/系辦公告", 3
    credit_match = CREDIT_PATTERN.search(line)
    if credit_match:
        credits = max(int(credit_match.group(1)), int(credit_match.group(2))) or 3
        raw_course_name = line[:credit_match.start()].strip()
        id_match = COURSE_ID_PATTERN.search(raw_course_name)
        course_name = raw_course_name[len(id_match.group(0)):].strip() if id_match and raw_course_name.startswith(id_match.group(0)) else raw_course_name
        name_match = re.search(r'[\u4e00-\u9fa5]{2,4}', line[credit_match.end():].strip())
        if name_match and name_match.group(0) not in ["應數", "資數", "資應", "碩一", "學年", "選修", "必修", "學分"]:
            teacher = name_match.group(0)
    return course_name, teacher, credits

def extract_course_events_from_soup(soup):
    events = []
    for container in soup.select("div.event_container"):
        header = container.select_one("span.event_header") or container.select_one(".event_header")
        if not header: continue
        course_name = (header.get("title") or header.get_text(" ", strip=True)).strip()
        if not course_name: continue
        before_text = container.select_one("div.before_hour_text").get_text(" ", strip=True) if container.select_one("div.before_hour_text") else ""
        after_text = container.select_one("div.after_hour_text").get_text(" ", strip=True) if container.select_one("div.after_hour_text") else ""
        course_time = container.select_one("div.hours_container span.hours").get_text(" ", strip=True) if container.select_one("div.hours_container span.hours") else ""
        if not course_time and TIME_PATTERN.search(container.get_text(" ", strip=True)):
            course_time = TIME_PATTERN.search(container.get_text(" ", strip=True)).group(0)
        teacher, room = "未定/系辦公告", "教室未顯示"
        for text in [before_text, after_text]:
            if not text: continue
            if ROOM_PATTERN.search(text) or "樓" in text or "場" in text: room = text
            elif len(text) >= 2 and len(text) <= 4 and not any(k in text for k in ["資數", "應數", "學士", "碩士", "必修", "選修"]): teacher = text
        events.append({"course_name": course_name, "teacher": teacher, "time": course_time or "未排定時間", "room": room, "credits": 4 if "微積分" in course_name or "代數" in course_name else 3, "type": "必修" if any(k in course_name for k in ["必", "微積分", "代數", "程式"]) else "選修"})
    return events


def live_course_crawler(keyword):
    search_words = normalize_keyword(keyword)
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    course_results, seen_ids = [], set()
    for target in COURSE_URLS:
        current_url, group_name = target["url"], target["group"]
        try:
            res = requests.get(current_url, headers=headers, timeout=10)
            res.raise_for_status()
            soup = BeautifulSoup(res.text, "html.parser")
            timetable_events = extract_course_events_from_soup(soup)
            if timetable_events:
                for event in timetable_events:
                    if not any(word.lower() in f"{event['course_name']} {event['teacher']} {event['time']} {event['room']}".lower() for word in search_words): continue
                    course_id = f"{group_name}:{event['course_name']}:{event['teacher']}:{event['time']}"
                    if course_id in seen_ids: continue
                    seen_ids.add(course_id)
                    course_results.append({"course_id": course_id, "course_name": event["course_name"], "teacher": event["teacher"], "time": event["time"], "room": event["room"], "group": group_name, "type": event["type"], "credits": event["credits"], "source": current_url})
            lines = clean_course_lines(soup)
            for i, line in enumerate(lines):
                if not line or looks_like_noise(line.strip()) or not (CREDIT_PATTERN.search(line) or any(hint.lower() in line.lower() for hint in COURSE_NAME_HINTS)) or TIME_PATTERN.search(line): continue
                clean_course_name, teacher, credits = auto_extract_course_details(line)
                _, course_time, room = find_next_time_and_room(lines, i)
                if not course_time: course_time = TIME_PATTERN.search(line).group(0) if TIME_PATTERN.search(line) else "未排定時間"
                if not any(w.lower() in f"{line} {teacher} {clean_course_name}".lower() for w in search_words): continue
                id_match = COURSE_ID_PATTERN.search(line)
                course_id = id_match.group(0) if id_match else f"CUSTOM_{hash(clean_course_name + group_name)}"
                if course_id in seen_ids: continue
                seen_ids.add(course_id)
                course_results.append({"course_id": course_id, "course_name": clean_course_name, "teacher": teacher, "time": course_time.strip(), "room": room or "教室未顯示", "group": group_name, "type": "必修" if any(k in line or k in clean_course_name for k in ["必", "微積分", "核心"]) else "選修", "credits": credits, "source": current_url})
        except Exception as e: print(f"課程爬取失敗。目標網址：{current_url} | 錯誤原因：{e}")
    course_results.sort(key=lambda x: (x["group"], x["course_name"]))
    return course_results

@app.route("/api/course_search")
def api_course_search():
    keyword = request.args.get("keyword", "").strip()
    if not keyword:
        return jsonify({
            "status": "error",
            "message": "請輸入課程關鍵字或教授姓名",
            "results": [],
            "count": 0
        }), 400
        
    # 執行全自動雙軌爬蟲，微積分與老師姓名在此滿血復活
    results = live_course_crawler(keyword)
    
    return jsonify({
        "status": "success",
        "message": "查詢成功",
        "keyword": keyword,
        "count": len(results),
        "results": results
    }), 200


@app.route("/smart_search")
def smart_search():
    return render_template("smart_search.html")

if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 5000)),
        debug=False,
    )
