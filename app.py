from flask import Flask, render_template
import os

app = Flask(__name__)

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/html_tags")
def html_tags():
    return render_template("html_tags.html")

if __name__ == "__main__":
    app.run(host="0.0.0.0", 
            port=int(os.environ.get("PORT",5000)),
            debug=True
    )