import os
import sqlite3
import hashlib
import re
from datetime import datetime
from flask import Flask, render_template_string, request, redirect, url_for, send_from_directory
from werkzeug.utils import secure_filename

app = Flask(__name__)

# [ネット公開用の修正] サーバー上の正しい場所にデータベースと画像フォルダを作る設定
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_NAME = os.path.join(BASE_DIR, "2ch_database.db")
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# 画像フォルダがサーバー上になければ自動で作成する仕組み
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1).lower() in ALLOWED_EXTENSIONS

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS threads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS replies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            thread_id INTEGER,
            name TEXT NOT NULL,
            trip TEXT,
            message TEXT NOT NULL,
            image_file TEXT,
            created_at TEXT,
            user_id TEXT,
            FOREIGN KEY (thread_id) REFERENCES threads (id)
        )
    """)
    conn.commit()
    conn.close()

def generate_id(ip_address):
    today_str = datetime.now().strftime("%Y-%m-%d")
    secret_string = f"{ip_address}_{today_str}"
    return hashlib.md5(secret_string.encode('utf-8')).hexdigest()[:8].upper()

def generate_trip(name_input):
    if "#" in name_input:
        name_part, key_part = name_input.split("#", 1)
        if not key_part:
            return name_input, ""
        trip_hash = hashlib.sha256(key_part.encode('utf-8')).hexdigest()
        trip_string = f" ◆{trip_hash[:10]}"
        return name_part, trip_string
    return name_input, ""

def convert_anchors(text):
    escaped = text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('\n', '<br>')
    result = re.sub(r'&gt;&gt;(\d+)', r'<a href="#res-\1">&gt;&gt;\1</a>', escaped)
    return result

CSS_STYLE = """
<style>
    html { scroll-behavior: smooth; }
    body { 
        font-family: "Monapo", "Mona", "MS PGothic", "Hiragino Kaku Gothic ProN", sans-serif; 
        background-color: #EFEFEF; 
        color: #000000; 
        padding: 20px; 
        font-size: 16px;
    }
    h1 { font-size: 26px; color: #990000; margin-bottom: 20px; }
    h2 { font-size: 22px; color: #FF0000; font-weight: normal; margin-top: 10px; margin-bottom: 20px; }
    .box { background: #EFEFEF; padding: 15px; border: 1px dashed #999; margin-bottom: 20px; max-width: 600px; }
    .item { margin-bottom: 25px; line-height: 1.5; max-width: 900px; padding-top: 10px; }
    .item:target { background-color: #FFFFAA; border-left: 3px solid #FF0000; padding-left: 5px; }
    .res-header { color: #555; font-size: 15px; }
    .num { color: #228B22; font-weight: bold; font-size: 16px; }
    .name { color: #0000FF; font-weight: bold; }
    .trip { color: #228B22; font-weight: bold; }
    .date-id { color: #555; }
    .message-text { margin-top: 5px; margin-bottom: 0; margin-left: 20px; color: #000; word-break: break-all; }
    .message-text a { color: #FF0000; text-decoration: underline; }
    .attached-image { display: block; margin-top: 10px; margin-left: 20px; max-width: 250px; max-height: 250px; border: 1px solid #ccc; }
    a { color: #0000EE; text-decoration: none; }
    a:hover { text-decoration: underline; color: #FF0000; }
    ul { list-style-type: none; padding-left: 10px; }
    li { margin-bottom: 8px; font-size: 16px; }
    input[type="text"], textarea { border: 1px solid #777; padding: 4px; font-family: inherit; }
    input[type="file"] { font-family: inherit; margin-top: 5px; }
    input[type="submit"] { background-color: #DDD; border: 1px solid #777; padding: 3px 10px; cursor: pointer; }
    input[type="submit"]:hover { background-color: #CCC; }
</style>
"""

HTML_TOP = CSS_STYLE + """
<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><title>2ch風掲示板 - スレッド一覧</title></head>
<body>
    <h1>Python 2ch風掲示板</h1>
    
    <div class="box">
        <h3 style="margin-top:0; color:#990000;">スレッド一覧</h3>
        <ul>
            {% for thread in threads %}
            <li>{{ loop.index }}: <a href="/thread/{{ thread }}">{{ thread }}</a></li>
            {% endfor %}
        </ul>
    </div>

    <div class="box">
        <h3 style="margin-top:0; color:#990000;">新スレ作成</h3>
        <form method="POST" action="/create_thread">
            <label>タイトル: <input type="text" name="title" size="40" required></label>
            <input type="submit" value="新規スレッド作成">
        </form>
    </div>
</body>
</html>
"""

HTML_THREAD = CSS_STYLE + """
<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><title>{{ thread_title }}</title></head>
<body>
    <p><a href="/">■掲示板トップに戻る</a></p>
    <h2>【{{ thread_title }}】</h2>

    <div class="res-list">
        {% for reply in replies %}
        <div class="item" id="res-{{ loop.index }}">
            <div class="res-header">
                <span class="num">{{ loop.index }}</span> ：
                <span class="name">{{ reply }}</span>
                {% if reply %}<span class="trip">{{ reply }}</span>{% endif %} ：
                <span class="date-id">{{ reply }} ID:{{ reply }}</span>
            </div>
            <p class="message-text">{{ reply | safe }}</p>
            {% if reply %}
            <a href="/uploads/{{ reply }}" target="_blank">
                <img class="attached-image" src="/uploads/{{ reply }}">
            </a>
            {% endif %}
        </div>
        {% endfor %}
    </div>

    <div class="box">
        <h3 style="margin-top:0; color:#990000;">レスを書き込む</h3>
        <form method="POST" action="/thread/{{ thread_id }}/post" enctype="multipart/form-data">
            <label>名前: <input type="text" name="username" value="名無しさん" size="25"></label><br><br>
            <label>本文:<br><textarea name="message" rows="5" cols="60" placeholder=">>1 への返信は、本文に >>1 と書いてね" required></textarea></label><br><br>
            <label>画像 (任意): <input type="file" name="image_file" accept="image/*"></label><br><br>
            <input type="submit" value="書き込む">
        </form>
    </div>
</body>
</html>
"""

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/')
def index():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT id, title FROM threads ORDER BY id DESC")
    threads = cursor.fetchall()
    conn.close()
    return render_template_string(HTML_TOP, threads=threads)

@app.route('/create_thread', methods=['POST'])
def create_thread():
    title = request.form.get('title', '').strip()
    if title:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("INSERT INTO threads (title) VALUES (?)", (title,))
        conn.commit()
        conn.close()
    return redirect(url_for('index'))

@app.route('/thread/<int:thread_id>')
def view_thread(thread_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT title FROM threads WHERE id = ?", (thread_id,))
    thread = cursor.fetchone()
    if not thread:
        return "スレッドが見つかりません", 404
    
    cursor.execute("SELECT id, thread_id, name, trip, message, created_at, user_id, image_file FROM replies WHERE thread_id = ? ORDER BY id ASC", (thread_id,))
    raw_replies = cursor.fetchall()
    conn.close()
    
    replies = []
    for r in raw_replies:
        r_list = list(r)
        r_list = convert_anchors(r_list)
        replies.append(r_list)
    
    return render_template_string(HTML_THREAD, thread_id=thread_id, thread_title=thread, replies=replies)

@app.route('/thread/<int:thread_id>/post', methods=['POST'])
def post_reply(thread_id):
    raw_name = request.form.get('username', '名無しさん').strip()
    if not raw_name:
        raw_name = "名無しさん"
    message = request.form.get('message', '').strip()
    
    saved_filename = None
    if 'image_file' in request.files:
        file = request.files['image_file']
        if file and file.filename != '' and allowed_file(file.filename):
            ext = file.filename.rsplit('.', 1).lower()
            timestamp = datetime.now().strftime("%Y%m%d%H%M%S%f")
            filename = secure_filename(f"{timestamp}.{ext}")
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            saved_filename = filename

    if message or saved_filename:
        name, trip = generate_trip(raw_name)
        now_str = datetime.now().strftime("%Y/%m/%d %H:%M:%S")
        ip_addr = request.remote_addr
        user_id = generate_id(ip_addr)
        
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO replies (thread_id, name, trip, message, image_file, created_at, user_id) VALUES (?, ?, ?, ?, ?, ?, ?)", 
            (thread_id, name, trip, message, saved_filename, now_str, user_id)
        )
        conn.commit()
        conn.close()
        
    return redirect(url_for('view_thread', thread_id=thread_id))

if __name__ == '__main__':
    init_db()
    # [ネット公開用の修正] 公開サーバーが自動で割り振るポート番号（PORT）を読み取って起動する設定
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
