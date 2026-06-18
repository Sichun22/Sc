from flask import Flask, render_template, request, redirect
from flask_sqlalchemy import SQLAlchemy
from dotenv import load_dotenv
import os

from urllib.parse import urljoin
import requests

from bs4 import BeautifulSoup

from selenium import webdriver
from selenium.webdriver.common.by import By
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

with app.app_context():
    db.create_all()

    CACHE_FILE = "fju_cache.json"


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

    todo = Todo.query.get(id)

    if todo:

        new_content = request.form.get("content")

        if new_content:

            todo.content = new_content

            db.session.commit()

    return redirect("/todo")

@app.route("/news")
def news():

    url = "https://news.ycombinator.com/"

    response = requests.get(url)

    soup = BeautifulSoup(
        response.text,
        "html.parser"
    )

    titles = soup.select(".titleline a")


    news_list = []

    for title in titles:

        news_list.append({
            "title": title.text,
            "url": title["href"]
        })

    return render_template(
        "news.html",
        news_list=news_list
    )

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

    finally:
        driver.quit()

    return render_template(
        "quotes.html",
        quote_list=quote_list
    ) 

# 🔥 輔大數學系全站爬蟲
# =====================
def crawl_fju_math():

    base = "https://www.math.fju.edu.tw/zh-hant/"
    headers = {"User-Agent": "Mozilla/5.0"}

    visited = set()
    queue = deque([base])

    pages = []

    while queue:

        url = queue.popleft()

        if url in visited:
            continue

        visited.add(url)

        try:
            res = requests.get(url, headers=headers, timeout=10)
            soup = BeautifulSoup(res.text, "html.parser")

            text = soup.get_text("\n", strip=True)

            pages.append({
                "url": url,
                "text": text
            })

            # 找內部連結
            for a in soup.find_all("a", href=True):
                link = urljoin(url, a["href"])

                if "math.fju.edu.tw" in link and link not in visited:
                    queue.append(link)

        except:
            continue

        time.sleep(0.2)

    return pages

# =====================
# Cache
# =====================
def load_cache():
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return None


def save_cache(data):
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)


@app.route("/fju_math")
def fju_math():

    cache = load_cache()

    if not cache:
        cache = crawl_fju_math()
        save_cache(cache)

    result = []

    for page in cache:


        result.append({
            "text": page["url"],
            "href": page["url"]
        })

    return render_template(
        "fju_math.html",
        result=result
    )

@app.route("/api/course_search")
def course_search():

    keyword = request.args.get("keyword", "").strip()

    cache = load_cache()

    if not cache:
        cache = crawl_fju_math()
        save_cache(cache)

    results = []

    for page in cache:

        for line in page["text"].split("\n"):

            line = line.strip()

            if len(line) < 2:
                continue

            if keyword in line:

                results.append({
                    "course": line,
                    "source": page["url"]
                })

    return jsonify({"results": results[:50]})

# =====================
# smart search page
# =====================
@app.route("/smart_search")
def smart_search():
    return render_template("smart_search.html")


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 5000)),
        debug=True,
    )