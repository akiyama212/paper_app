# app.py
# 簡易 論文管理アプリ（Flask + SQLite）
from flask import Flask, render_template, request, redirect, url_for
import sqlite3
from pathlib import Path
from datetime import datetime
import os
from werkzeug.utils import secure_filename

# アップロード設定
UPLOAD_FOLDER = Path("uploads")
UPLOAD_FOLDER.mkdir(exist_ok=True)  # フォルダがなければ作る

ALLOWED_EXTENSIONS = {"pdf", "doc", "docx", "ppt", "pptx"}


def generate_ai_summary(text: str) -> str:
    """
    AI要約を生成する関数。
    今はダミー実装（テキストを短く切って返すだけ）。
    あとで OpenAI API などに置き換えてOK。
    """
    text = (text or "").strip()
    if not text:
        return "要約元のテキストがありません。"

    # ざっくり400文字くらいにトリミング
    max_len = 400
    trimmed = text.replace("\r\n", "\n").replace("\n\n", "\n")
    if len(trimmed) > max_len:
        trimmed = trimmed[:max_len] + "..."

    return "【自動要約（簡易版）】\n" + trimmed


def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def save_uploaded_file(file_storage):
    """アップロードされたファイルを保存し、Webからアクセスするパスを返す"""
    if file_storage and file_storage.filename:
        filename = secure_filename(file_storage.filename)
        save_path = UPLOAD_FOLDER / filename
        # 同名ファイル対策（かんたん版：連番をつける）
        counter = 1
        while save_path.exists():
            stem = Path(filename).stem
            suffix = Path(filename).suffix
            new_name = f"{stem}_{counter}{suffix}"
            save_path = UPLOAD_FOLDER / new_name
            counter += 1
        file_storage.save(save_path)
        # Web からアクセスするパス（/uploads/...）
        return f"/uploads/{save_path.name}"
    return None


app = Flask(__name__)

DB_PATH = Path("papers.db")


def init_db():
    """最初に呼び出してDBとテーブルを作成＆不足カラムを追加"""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # ベースとなるテーブル
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS papers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            authors TEXT,
            year INTEGER,
            journal TEXT,
            summary_short TEXT,
            summary_detail TEXT,
            pdf_path TEXT,
            word_path TEXT,
            ppt_path TEXT,
            created_at TEXT
        )
        """
    )

    # 既存テーブルのカラムを確認
    cur.execute("PRAGMA table_info(papers)")
    cols = [row[1] for row in cur.fetchall()]

    # AI要約カラム
    if "summary_ai" not in cols:
        cur.execute("ALTER TABLE papers ADD COLUMN summary_ai TEXT")

    # 分野（カテゴリ）
    if "category" not in cols:
        cur.execute("ALTER TABLE papers ADD COLUMN category TEXT")

    # キーワード（カンマ区切りで保存）
    if "keywords" not in cols:
        cur.execute("ALTER TABLE papers ADD COLUMN keywords TEXT")

    conn.commit()
    conn.close()


def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


@app.route("/")
def index():
    return redirect(url_for("list_papers"))


@app.route("/papers")
def list_papers():
    """論文一覧ページ＋検索＋カテゴリ絞り込み"""
    q = request.args.get("q", "").strip()
    category = request.args.get("category", "").strip()

    conn = get_db_connection()
    cur = conn.cursor()

    if q or category:
        query = "SELECT * FROM papers WHERE 1=1"
        params = []

        if q:
            like = f"%{q}%"
            query += """
                AND (
                    title LIKE ?
                    OR authors LIKE ?
                    OR summary_short LIKE ?
                    OR summary_detail LIKE ?
                    OR keywords LIKE ?
                )
            """
            params.extend([like, like, like, like, like])

        if category:
            query += " AND category = ?"
            params.append(category)

        query += " ORDER BY created_at DESC"
        cur.execute(query, params)
    else:
        cur.execute("SELECT * FROM papers ORDER BY created_at DESC")

    papers = cur.fetchall()
    conn.close()
    return render_template("list_papers.html", papers=papers, q=q, selected_category=category)

@app.route("/papers/new", methods=["GET", "POST"])
def new_paper():
    if request.method == "POST":
        title = request.form.get("title")
        authors = request.form.get("authors")
        year = request.form.get("year") or None
        journal = request.form.get("journal")
        summary_short = request.form.get("summary_short")
        summary_detail = request.form.get("summary_detail")

        # ▼ ここから: 分野とキーワード
        category = request.form.get("category") or ""  # 飛行, 匂い, ナビゲーション, その他, 未選択
        kw1 = (request.form.get("keyword1") or "").strip()
        kw2 = (request.form.get("keyword2") or "").strip()
        kw3 = (request.form.get("keyword3") or "").strip()
        keyword_list = [k for k in [kw1, kw2, kw3] if k]
        keywords = ", ".join(keyword_list) if keyword_list else None
        # ▲ ここまで

        # ファイル取得
        pdf_file = request.files.get("pdf_file")
        word_file = request.files.get("word_file")
        ppt_file = request.files.get("ppt_file")

        # 保存してWebパスを取得
        pdf_path = save_uploaded_file(pdf_file) if pdf_file and allowed_file(pdf_file.filename) else None
        word_path = save_uploaded_file(word_file) if word_file and allowed_file(word_file.filename) else None
        ppt_path = save_uploaded_file(ppt_file) if ppt_file and allowed_file(ppt_file.filename) else None

        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO papers
            (title, authors, year, journal,
             summary_short, summary_detail,
             pdf_path, word_path, ppt_path,
             category, keywords,
             created_at, summary_ai)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                title,
                authors,
                int(year) if year else None,
                journal,
                summary_short,
                summary_detail,
                pdf_path,
                word_path,
                ppt_path,
                category,
                keywords,
                datetime.now().isoformat(timespec="seconds"),
                None,  # summary_ai はまだなし
            ),
        )
        conn.commit()
        conn.close()

        return redirect(url_for("list_papers"))

    # GET
    return render_template("new_paper.html")


@app.route("/papers/<int:paper_id>")
def paper_detail(paper_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM papers WHERE id = ?", (paper_id,))
    paper = cur.fetchone()
    conn.close()

    if paper is None:
        return redirect(url_for("list_papers"))

    return render_template("paper_detail.html", paper=paper)

@app.route("/papers/<int:paper_id>/generate_ai", methods=["POST"])
def generate_ai_summary_route(paper_id):
    """指定した論文のAI要約を生成して保存"""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT title, summary_detail, summary_short FROM papers WHERE id = ?",
        (paper_id,),
    )
    row = cur.fetchone()

    if row is None:
        conn.close()
        return redirect(url_for("list_papers"))

    # 要約の元になるテキストを決める
    source_text = row["summary_detail"] or row["summary_short"] or row["title"]

    if not source_text:
        conn.close()
        # 要約元がない場合もとりあえず詳細画面に戻す
        return redirect(url_for("paper_detail", paper_id=paper_id))

    ai_summary = generate_ai_summary(source_text)

    cur.execute(
        "UPDATE papers SET summary_ai = ? WHERE id = ?",
        (ai_summary, paper_id),
    )
    conn.commit()
    conn.close()

    return redirect(url_for("paper_detail", paper_id=paper_id))


@app.route("/papers/<int:paper_id>/edit", methods=["GET", "POST"])
def edit_paper(paper_id):
    conn = get_db_connection()
    cur = conn.cursor()

    if request.method == "POST":
        title = request.form.get("title")
        authors = request.form.get("authors")
        year = request.form.get("year") or None
        journal = request.form.get("journal")
        summary_short = request.form.get("summary_short")
        summary_detail = request.form.get("summary_detail")

        # 分野＆キーワード
        category = request.form.get("category") or ""
        kw1 = (request.form.get("keyword1") or "").strip()
        kw2 = (request.form.get("keyword2") or "").strip()
        kw3 = (request.form.get("keyword3") or "").strip()
        keyword_list = [k for k in [kw1, kw2, kw3] if k]
        keywords = ", ".join(keyword_list) if keyword_list else None

        # 既存のファイルパスを取得（新しいファイルがなければそのまま）
        cur.execute("SELECT pdf_path, word_path, ppt_path FROM papers WHERE id = ?", (paper_id,))
        old = cur.fetchone()
        pdf_path = old["pdf_path"]
        word_path = old["word_path"]
        ppt_path = old["ppt_path"]

        # 新しいファイルがあれば上書き
        pdf_file = request.files.get("pdf_file")
        word_file = request.files.get("word_file")
        ppt_file = request.files.get("ppt_file")

        if pdf_file and allowed_file(pdf_file.filename):
            pdf_path = save_uploaded_file(pdf_file)
        if word_file and allowed_file(word_file.filename):
            word_path = save_uploaded_file(word_file)
        if ppt_file and allowed_file(ppt_file.filename):
            ppt_path = save_uploaded_file(ppt_file)

        cur.execute(
            """
            UPDATE papers
            SET title = ?, authors = ?, year = ?, journal = ?,
                summary_short = ?, summary_detail = ?,
                pdf_path = ?, word_path = ?, ppt_path = ?,
                category = ?, keywords = ?
            WHERE id = ?
            """,
            (
                title,
                authors,
                int(year) if year else None,
                journal,
                summary_short,
                summary_detail,
                pdf_path,
                word_path,
                ppt_path,
                category,
                keywords,
                paper_id,
            ),
        )
        conn.commit()
        conn.close()
        return redirect(url_for("paper_detail", paper_id=paper_id))

    # GET のときはフォームに初期値を入れる
    cur.execute("SELECT * FROM papers WHERE id = ?", (paper_id,))
    paper = cur.fetchone()
    conn.close()

    if paper is None:
        return redirect(url_for("list_papers"))

    # キーワードを3つにばらしてテンプレートに渡す
    kw_text = paper["keywords"] or ""
    kw_list = [k.strip() for k in kw_text.split(",") if k.strip()]
    kw1 = kw_list[0] if len(kw_list) > 0 else ""
    kw2 = kw_list[1] if len(kw_list) > 1 else ""
    kw3 = kw_list[2] if len(kw_list) > 2 else ""

    return render_template("edit_paper.html", paper=paper, kw1=kw1, kw2=kw2, kw3=kw3)

@app.route("/papers/<int:paper_id>/delete", methods=["POST"])
def delete_paper(paper_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM papers WHERE id = ?", (paper_id,))
    conn.commit()
    conn.close()
    return redirect(url_for("list_papers"))


from flask import send_from_directory

@app.route("/uploads/<path:filename>")
def uploaded_file(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)


if __name__ == "__main__":
    init_db()
    import os
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
