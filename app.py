import os
from functools import wraps
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_socketio import SocketIO, emit, join_room
from werkzeug.security import generate_password_hash, check_password_hash

from config import Config
from db import get_db, close_db, init_db, table_exists
from utils.auth import login_required
from utils.upload import save_post_media, save_profile_media
from utils.ai_tools import generate_ai_text
from utils.helpers import current_user, is_following

app = Flask(__name__)
app.config.from_object(Config)
app.teardown_appcontext(close_db)

# Real-time support
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

os.makedirs(app.config["UPLOAD_FOLDER_POSTS"], exist_ok=True)
os.makedirs(app.config["UPLOAD_FOLDER_PROFILES"], exist_ok=True)
os.makedirs(os.path.join(app.root_path, "instance"), exist_ok=True)


def admin_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if not session.get("admin_logged_in"):
            flash("Admin login required.", "danger")
            return redirect(url_for("admin_login"))
        return view(*args, **kwargs)
    return wrapped_view


@app.context_processor
def inject_globals():
    user = current_user()
    if session.get("user_id") and user is None:
        session.pop("user_id", None)
    return {"current_user_data": user}


@app.before_request
def ensure_database_ready():
    try:
        if not table_exists("users"):
            init_db()
    except Exception as e:
        print("Database init error:", e)


def get_or_create_conversation(user_a, user_b):
    db = get_db()
    u1, u2 = sorted([int(user_a), int(user_b)])

    conversation = db.execute(
        """
        SELECT * FROM conversations
        WHERE user1_id = ? AND user2_id = ?
        """,
        (u1, u2),
    ).fetchone()

    if conversation:
        return conversation["id"]

    db.execute(
        """
        INSERT INTO conversations (user1_id, user2_id)
        VALUES (?, ?)
        """,
        (u1, u2),
    )
    db.commit()

    conversation = db.execute(
        """
        SELECT * FROM conversations
        WHERE user1_id = ? AND user2_id = ?
        """,
        (u1, u2),
    ).fetchone()

    return conversation["id"]


@app.route("/initdb")
def initdb_route():
    init_db()
    return "Database initialized successfully."


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/feed")
def feed():
    db = get_db()
    current_id = session.get("user_id")

    posts = db.execute(
        """
        SELECT 
            posts.*,
            users.username,
            users.profile_pic,
            (SELECT COUNT(*) FROM likes WHERE likes.post_id = posts.id) AS like_count,
            (SELECT COUNT(*) FROM comments WHERE comments.post_id = posts.id) AS comment_count
        FROM posts
        JOIN users ON posts.user_id = users.id
        ORDER BY posts.created_at DESC, posts.id DESC
        """
    ).fetchall()

    comments_map = {}
    for post in posts:
        comments_map[post["id"]] = db.execute(
            """
            SELECT comments.*, users.username
            FROM comments
            JOIN users ON comments.user_id = users.id
            WHERE comments.post_id = ?
            ORDER BY comments.created_at ASC, comments.id ASC
            """,
            (post["id"],),
        ).fetchall()

    if current_id:
        story_users = db.execute(
            """
            SELECT DISTINCT
                users.id,
                users.username,
                users.profile_pic,
                EXISTS(
                    SELECT 1
                    FROM stories s2
                    WHERE s2.user_id = users.id
                      AND datetime(s2.expires_at) > datetime('now')
                      AND NOT EXISTS (
                          SELECT 1
                          FROM story_views sv
                          WHERE sv.story_id = s2.id AND sv.viewer_id = ?
                      )
                ) AS has_unseen
            FROM stories
            JOIN users ON stories.user_id = users.id
            WHERE datetime(stories.expires_at) > datetime('now')
            ORDER BY stories.created_at DESC
            """,
            (current_id,),
        ).fetchall()
    else:
        story_users = db.execute(
            """
            SELECT DISTINCT
                users.id,
                users.username,
                users.profile_pic,
                0 AS has_unseen
            FROM stories
            JOIN users ON stories.user_id = users.id
            WHERE datetime(stories.expires_at) > datetime('now')
            ORDER BY stories.created_at DESC
            """
        ).fetchall()

    return render_template(
        "feed.html",
        posts=posts,
        comments_map=comments_map,
        story_users=story_users,
    )

@app.route("/create_story", methods=["GET", "POST"])
@login_required
def create_story():
    if request.method == "POST":
        caption = request.form.get("caption", "").strip()
        media = request.files.get("media")

        media_file, media_type = save_post_media(media)

        if not media_file:
            flash("Please upload an image or video for the story.", "danger")
            return redirect(url_for("create_story"))

        expires_at = (datetime.now() + timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S")

        db = get_db()
        db.execute(
            """
            INSERT INTO stories (user_id, media_file, media_type, caption, expires_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (session["user_id"], media_file, media_type, caption, expires_at),
        )
        db.commit()

        flash("Story uploaded successfully.", "success")
        return redirect(url_for("feed"))

    return render_template("create_story.html")

@app.route("/stories/<int:user_id>")
@app.route("/stories/<int:user_id>")
def view_stories(user_id):
    db = get_db()

    user = db.execute(
        "SELECT * FROM users WHERE id = ?",
        (user_id,),
    ).fetchone()

    if not user:
        flash("User not found.", "danger")
        return redirect(url_for("feed"))

    stories = db.execute(
        """
        SELECT *
        FROM stories
        WHERE user_id = ?
          AND datetime(expires_at) > datetime('now')
        ORDER BY created_at ASC
        """,
        (user_id,),
    ).fetchall()

    if not stories:
        flash("No active stories available.", "warning")
        return redirect(url_for("feed"))

    return render_template("view_stories.html", user=user, stories=stories)

@app.route("/story/<int:story_id>/delete", methods=["POST"])
@login_required
def delete_story(story_id):
    db = get_db()

    story = db.execute(
        "SELECT * FROM stories WHERE id = ?",
        (story_id,),
    ).fetchone()

    if not story:
        flash("Story not found.", "danger")
        return redirect(url_for("feed"))

    if story["user_id"] != session["user_id"]:
        flash("Unauthorized action.", "danger")
        return redirect(url_for("feed"))

    db.execute("DELETE FROM stories WHERE id = ?", (story_id,))
    db.commit()

    flash("Story deleted successfully.", "success")
    return redirect(url_for("feed"))

@app.route("/story/<int:story_id>/views")
@login_required
def story_views_page(story_id):
    db = get_db()

    story = db.execute(
        "SELECT * FROM stories WHERE id = ?",
        (story_id,),
    ).fetchone()

    if not story:
        flash("Story not found.", "danger")
        return redirect(url_for("feed"))

    if story["user_id"] != session["user_id"]:
        flash("Unauthorized action.", "danger")
        return redirect(url_for("feed"))

    viewers = db.execute(
        """
        SELECT users.username, users.profile_pic, story_views.viewed_at
        FROM story_views
        JOIN users ON story_views.viewer_id = users.id
        WHERE story_views.story_id = ?
        ORDER BY story_views.viewed_at DESC
        """,
        (story_id,),
    ).fetchall()

    return render_template("story_views.html", viewers=viewers, story=story)


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")

        if not username or not email or not password:
            flash("All fields are required.", "danger")
            return redirect(url_for("register"))

        db = get_db()
        existing = db.execute(
            "SELECT id FROM users WHERE username = ? OR email = ?",
            (username, email),
        ).fetchone()

        if existing:
            flash("Username or email already exists.", "danger")
            return redirect(url_for("register"))

        password_hash = generate_password_hash(password)
        db.execute(
            "INSERT INTO users (username, email, password_hash) VALUES (?, ?, ?)",
            (username, email, password_hash),
        )
        db.commit()

        flash("Registration successful. Please login.", "success")
        return redirect(url_for("login"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")

        db = get_db()
        user = db.execute(
            "SELECT * FROM users WHERE email = ?",
            (email,),
        ).fetchone()

        if user and check_password_hash(user["password_hash"], password):
            session["user_id"] = user["id"]
            flash("Login successful.", "success")
            return redirect(url_for("feed"))

        flash("Invalid email or password.", "danger")
        return redirect(url_for("login"))

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.pop("user_id", None)
    flash("Logged out successfully.", "info")
    return redirect(url_for("index"))


@app.route("/create_post", methods=["GET", "POST"])
@login_required
def create_post():
    if request.method == "POST":
        content = request.form.get("content", "").strip()
        media = request.files.get("media")
        media_file, media_type = save_post_media(media)

        if not content and not media_file:
            flash("Post cannot be empty.", "danger")
            return redirect(url_for("create_post"))

        db = get_db()
        db.execute(
            """
            INSERT INTO posts (user_id, content, media_file, media_type)
            VALUES (?, ?, ?, ?)
            """,
            (session["user_id"], content, media_file, media_type),
        )
        db.commit()

        flash("Post created successfully.", "success")
        return redirect(url_for("feed"))

    return render_template("create_post.html")



@app.route("/post/<int:post_id>/edit", methods=["GET", "POST"])
@login_required
def edit_post(post_id):
    db = get_db()
    post = db.execute(
        "SELECT * FROM posts WHERE id = ?",
        (post_id,),
    ).fetchone()

    if not post or post["user_id"] != session["user_id"]:
        flash("Unauthorized action.", "danger")
        return redirect(url_for("feed"))

    if request.method == "POST":
        content = request.form.get("content", "").strip()
        db.execute(
            "UPDATE posts SET content = ? WHERE id = ?",
            (content, post_id),
        )
        db.commit()
        flash("Post updated successfully.", "success")
        return redirect(url_for("feed"))

    return render_template("edit_post.html", post=post)


@app.route("/post/<int:post_id>/delete", methods=["POST"])
@login_required
def delete_post(post_id):
    db = get_db()
    post = db.execute(
        "SELECT * FROM posts WHERE id = ?",
        (post_id,),
    ).fetchone()

    if not post or post["user_id"] != session["user_id"]:
        flash("Unauthorized action.", "danger")
        return redirect(url_for("feed"))

    db.execute("DELETE FROM posts WHERE id = ?", (post_id,))
    db.commit()
    flash("Post deleted.", "info")
    return redirect(url_for("feed"))


@app.route("/post/<int:post_id>/like", methods=["POST"])
@login_required
def like_post(post_id):
    db = get_db()
    existing = db.execute(
        """
        SELECT id FROM likes WHERE post_id = ? AND user_id = ?
        """,
        (post_id, session["user_id"]),
    ).fetchone()

    if existing:
        db.execute(
            "DELETE FROM likes WHERE post_id = ? AND user_id = ?",
            (post_id, session["user_id"]),
        )
    else:
        db.execute(
            "INSERT INTO likes (post_id, user_id) VALUES (?, ?)",
            (post_id, session["user_id"]),
        )

    db.commit()
    return redirect(url_for("feed"))


@app.route("/post/<int:post_id>/comment", methods=["POST"])
@login_required
def comment_post(post_id):
    comment_text = request.form.get("comment_text", "").strip()

    if not comment_text:
        flash("Comment cannot be empty.", "danger")
        return redirect(url_for("feed"))

    db = get_db()
    db.execute(
        """
        INSERT INTO comments (post_id, user_id, comment_text)
        VALUES (?, ?, ?)
        """,
        (post_id, session["user_id"], comment_text),
    )
    db.commit()

    flash("Comment added.", "success")
    return redirect(url_for("feed"))


@app.route("/profile/<int:user_id>")
def profile(user_id):
    db = get_db()
    user = db.execute(
        "SELECT * FROM users WHERE id = ?",
        (user_id,),
    ).fetchone()

    if not user:
        flash("User not found.", "danger")
        return redirect(url_for("feed"))

    posts = db.execute(
        """
        SELECT
            posts.*,
            (SELECT COUNT(*) FROM likes WHERE likes.post_id = posts.id) AS like_count,
            (SELECT COUNT(*) FROM comments WHERE comments.post_id = posts.id) AS comment_count
        FROM posts
        WHERE user_id = ?
        ORDER BY created_at DESC, id DESC
        """,
        (user_id,),
    ).fetchall()

    followers = db.execute(
        "SELECT COUNT(*) AS count FROM follows WHERE following_id = ?",
        (user_id,),
    ).fetchone()["count"]

    following = db.execute(
        "SELECT COUNT(*) AS count FROM follows WHERE follower_id = ?",
        (user_id,),
    ).fetchone()["count"]

    can_follow = False
    already_following = False
    if "user_id" in session and session["user_id"] != user_id:
        can_follow = True
        already_following = is_following(session["user_id"], user_id)

    return render_template(
        "profile.html",
        user=user,
        posts=posts,
        followers=followers,
        following=following,
        can_follow=can_follow,
        already_following=already_following,
    )


@app.route("/edit_profile", methods=["GET", "POST"])
@login_required
def edit_profile():
    db = get_db()
    user = db.execute(
        "SELECT * FROM users WHERE id = ?",
        (session["user_id"],),
    ).fetchone()

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        bio = request.form.get("bio", "").strip()
        profile_pic = request.files.get("profile_pic")

        if not username:
            flash("Username is required.", "danger")
            return redirect(url_for("edit_profile"))

        new_profile_pic = user["profile_pic"]
        saved_pic = save_profile_media(profile_pic)
        if saved_pic:
            new_profile_pic = saved_pic

        db.execute(
            """
            UPDATE users
            SET username = ?, bio = ?, profile_pic = ?
            WHERE id = ?
            """,
            (username, bio, new_profile_pic, session["user_id"]),
        )
        db.commit()

        flash("Profile updated successfully.", "success")
        return redirect(url_for("profile", user_id=session["user_id"]))

    return render_template("edit_profile.html", user=user)


@app.route("/follow/<int:user_id>", methods=["POST"])
@login_required
def follow_user(user_id):
    if session["user_id"] == user_id:
        flash("You cannot follow yourself.", "warning")
        return redirect(url_for("profile", user_id=user_id))

    db = get_db()
    existing = db.execute(
        """
        SELECT id FROM follows WHERE follower_id = ? AND following_id = ?
        """,
        (session["user_id"], user_id),
    ).fetchone()

    if existing:
        db.execute(
            "DELETE FROM follows WHERE follower_id = ? AND following_id = ?",
            (session["user_id"], user_id),
        )
    else:
        db.execute(
            "INSERT INTO follows (follower_id, following_id) VALUES (?, ?)",
            (session["user_id"], user_id),
        )

    db.commit()
    return redirect(url_for("profile", user_id=user_id))


@app.route("/users")
def users():
    db = get_db()
    users_data = db.execute(
        """
        SELECT users.*,
               (SELECT COUNT(*) FROM posts WHERE posts.user_id = users.id) AS post_count
        FROM users
        ORDER BY users.created_at DESC
        """
    ).fetchall()
    return render_template("users.html", users=users_data)


@app.route("/search")
def search():
    q = request.args.get("q", "").strip()
    db = get_db()

    users_result = []
    posts_result = []

    if q:
        users_result = db.execute(
            """
            SELECT * FROM users
            WHERE username LIKE ? OR email LIKE ? OR bio LIKE ?
            ORDER BY username
            """,
            (f"%{q}%", f"%{q}%", f"%{q}%"),
        ).fetchall()

        posts_result = db.execute(
            """
            SELECT posts.*, users.username
            FROM posts
            JOIN users ON posts.user_id = users.id
            WHERE posts.content LIKE ?
            ORDER BY posts.created_at DESC, posts.id DESC
            """,
            (f"%{q}%",),
        ).fetchall()

    return render_template(
        "search.html",
        q=q,
        users_result=users_result,
        posts_result=posts_result,
    )


@app.route("/ai_tools", methods=["GET", "POST"])
@login_required
def ai_tools():
    output = ""
    selected_tool = "caption"
    input_text = ""

    if request.method == "POST":
        selected_tool = request.form.get("tool", "caption")
        input_text = request.form.get("input_text", "").strip()

        if input_text:
            output = generate_ai_text(selected_tool, input_text)
            db = get_db()
            db.execute(
                """
                INSERT INTO ai_history (user_id, tool, input_text, output_text)
                VALUES (?, ?, ?, ?)
                """,
                (session["user_id"], selected_tool, input_text, output),
            )
            db.commit()
        else:
            flash("Please enter input text.", "danger")

    return render_template(
        "ai_tools.html",
        output=output,
        selected_tool=selected_tool,
        input_text=input_text,
    )


# ---------------- CHAT PAGES ----------------

@app.route("/messages")
@login_required
def chat_list():
    db = get_db()
    current_id = session["user_id"]

    conversations = db.execute(
        """
        SELECT
            c.id AS conversation_id,
            u.id AS other_user_id,
            u.username AS other_username,
            u.profile_pic AS other_profile_pic,
            (
                SELECT m.message_text
                FROM messages m
                WHERE m.conversation_id = c.id
                ORDER BY m.created_at DESC, m.id DESC
                LIMIT 1
            ) AS last_message,
            (
                SELECT m.created_at
                FROM messages m
                WHERE m.conversation_id = c.id
                ORDER BY m.created_at DESC, m.id DESC
                LIMIT 1
            ) AS last_message_time
        FROM conversations c
        JOIN users u
            ON u.id = CASE
                WHEN c.user1_id = ? THEN c.user2_id
                ELSE c.user1_id
            END
        WHERE c.user1_id = ? OR c.user2_id = ?
        ORDER BY last_message_time DESC, c.id DESC
        """,
        (current_id, current_id, current_id),
    ).fetchall()

    all_users = db.execute(
        """
        SELECT id, username, profile_pic
        FROM users
        WHERE id != ?
        ORDER BY username ASC
        """,
        (current_id,),
    ).fetchall()

    return render_template(
        "chat_list.html",
        conversations=conversations,
        all_users=all_users,
    )


@app.route("/chat/start/<int:user_id>")
@login_required
def start_chat(user_id):
    if user_id == session["user_id"]:
        flash("You cannot chat with yourself.", "warning")
        return redirect(url_for("chat_list"))

    db = get_db()
    user = db.execute(
        "SELECT id FROM users WHERE id = ?",
        (user_id,),
    ).fetchone()
    if not user:
        flash("User not found.", "danger")
        return redirect(url_for("chat_list"))

    conversation_id = get_or_create_conversation(session["user_id"], user_id)
    return redirect(url_for("chat_room", conversation_id=conversation_id))


@app.route("/chat/<int:conversation_id>")
@login_required
def chat_room(conversation_id):
    db = get_db()
    current_id = session["user_id"]

    conversation = db.execute(
        "SELECT * FROM conversations WHERE id = ?",
        (conversation_id,),
    ).fetchone()

    if not conversation:
        flash("Conversation not found.", "danger")
        return redirect(url_for("chat_list"))

    if current_id not in [conversation["user1_id"], conversation["user2_id"]]:
        flash("Unauthorized access.", "danger")
        return redirect(url_for("chat_list"))

    other_user_id = (
        conversation["user2_id"]
        if conversation["user1_id"] == current_id
        else conversation["user1_id"]
    )

    other_user = db.execute(
        """
        SELECT id, username, profile_pic
        FROM users
        WHERE id = ?
        """,
        (other_user_id,),
    ).fetchone()

    messages = db.execute(
        """
        SELECT messages.*, users.username
        FROM messages
        JOIN users ON messages.sender_id = users.id
        WHERE messages.conversation_id = ?
        ORDER BY messages.created_at ASC, messages.id ASC
        """,
        (conversation_id,),
    ).fetchall()

    db.execute(
        """
        UPDATE messages
        SET is_read = 1
        WHERE conversation_id = ? AND sender_id != ?
        """,
        (conversation_id, current_id),
    )
    db.commit()

    conversations = db.execute(
        """
        SELECT
            c.id AS conversation_id,
            u.id AS other_user_id,
            u.username AS other_username,
            u.profile_pic AS other_profile_pic,
            (
                SELECT m.message_text
                FROM messages m
                WHERE m.conversation_id = c.id
                ORDER BY m.created_at DESC, m.id DESC
                LIMIT 1
            ) AS last_message
        FROM conversations c
        JOIN users u
            ON u.id = CASE
                WHEN c.user1_id = ? THEN c.user2_id
                ELSE c.user1_id
            END
        WHERE c.user1_id = ? OR c.user2_id = ?
        ORDER BY c.id DESC
        """,
        (current_id, current_id, current_id),
    ).fetchall()

    return render_template(
    "chat.html",
    conversation_id=conversation_id,
    current_user_id=current_id,
    other_user=other_user,
    messages=messages,
    conversations=conversations
)


# Optional fallback non-realtime route
@app.route("/chat/<int:conversation_id>/send", methods=["POST"])
@login_required
def send_message_fallback(conversation_id):
    db = get_db()
    current_id = session["user_id"]
    message_text = request.form.get("message_text", "").strip()

    if not message_text:
        flash("Message cannot be empty.", "danger")
        return redirect(url_for("chat_room", conversation_id=conversation_id))

    conversation = db.execute(
        "SELECT * FROM conversations WHERE id = ?",
        (conversation_id,),
    ).fetchone()

    if not conversation:
        flash("Conversation not found.", "danger")
        return redirect(url_for("chat_list"))

    if current_id not in [conversation["user1_id"], conversation["user2_id"]]:
        flash("Unauthorized action.", "danger")
        return redirect(url_for("chat_list"))

    db.execute(
        """
        INSERT INTO messages (conversation_id, sender_id, message_text)
        VALUES (?, ?, ?)
        """,
        (conversation_id, current_id, message_text),
    )
    db.commit()

    return redirect(url_for("chat_room", conversation_id=conversation_id))


# ---------------- REAL-TIME SOCKET EVENTS ----------------

@socketio.on("join_chat")
def handle_join_chat(data):
    conversation_id = data.get("conversation_id")
    if not conversation_id:
        return

    room = f"conversation_{conversation_id}"
    join_room(room)


@socketio.on("send_chat_message")
def handle_send_chat_message(data):
    """
    Expected payload:
    {
        "conversation_id": 1,
        "sender_id": 2,
        "message_text": "hello"
    }
    """
    conversation_id = data.get("conversation_id")
    sender_id = data.get("sender_id")
    message_text = (data.get("message_text") or "").strip()

    if not conversation_id or not sender_id or not message_text:
        return

    db = get_db()

    # Validate conversation
    conversation = db.execute(
        """
        SELECT * FROM conversations
        WHERE id = ?
        """,
        (conversation_id,),
    ).fetchone()

    if not conversation:
        return

    if int(sender_id) not in [conversation["user1_id"], conversation["user2_id"]]:
        return

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    db.execute(
        """
        INSERT INTO messages (conversation_id, sender_id, message_text, created_at)
        VALUES (?, ?, ?, ?)
        """,
        (conversation_id, sender_id, message_text, now_str),
    )
    db.commit()

    sender = db.execute(
        "SELECT username FROM users WHERE id = ?",
        (sender_id,),
    ).fetchone()

    room = f"conversation_{conversation_id}"

    emit(
        "receive_chat_message",
        {
            "conversation_id": int(conversation_id),
            "sender_id": int(sender_id),
            "sender_name": sender["username"] if sender else "Unknown",
            "message_text": message_text,
            "created_at": now_str,
        },
        to=room,
    )


# ---------------- ADMIN ----------------

@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "").strip()

        admin_email = os.getenv("ADMIN_EMAIL", "admin@famshare.com")
        admin_password = os.getenv("ADMIN_PASSWORD", "admin123")

        if email == admin_email and password == admin_password:
            session["admin_logged_in"] = True
            flash("Admin login successful.", "success")
            return redirect(url_for("admin_dashboard"))

        flash("Invalid admin credentials.", "danger")
        return redirect(url_for("admin_login"))

    return render_template("admin_login.html")


@app.route("/admin/logout")
def admin_logout():
    session.pop("admin_logged_in", None)
    flash("Admin logged out.", "info")
    return redirect(url_for("admin_login"))


@app.route("/admin/dashboard")
@admin_required
def admin_dashboard():
    db = get_db()

    user_count = db.execute("SELECT COUNT(*) AS count FROM users").fetchone()["count"]
    post_count = db.execute("SELECT COUNT(*) AS count FROM posts").fetchone()["count"]
    comment_count = db.execute("SELECT COUNT(*) AS count FROM comments").fetchone()["count"]
    like_count = db.execute("SELECT COUNT(*) AS count FROM likes").fetchone()["count"]
    conversation_count = db.execute("SELECT COUNT(*) AS count FROM conversations").fetchone()["count"]
    message_count = db.execute("SELECT COUNT(*) AS count FROM messages").fetchone()["count"]

    recent_users = db.execute(
        "SELECT * FROM users ORDER BY created_at DESC LIMIT 5"
    ).fetchall()

    recent_posts = db.execute(
        """
        SELECT posts.*, users.username
        FROM posts
        JOIN users ON posts.user_id = users.id
        ORDER BY posts.created_at DESC, posts.id DESC
        LIMIT 5
        """
    ).fetchall()

    return render_template(
        "admin_dashboard.html",
        user_count=user_count,
        post_count=post_count,
        comment_count=comment_count,
        like_count=like_count,
        conversation_count=conversation_count,
        message_count=message_count,
        recent_users=recent_users,
        recent_posts=recent_posts,
    )


@app.route("/admin/users")
@admin_required
def admin_users():
    db = get_db()
    users = db.execute(
        """
        SELECT users.*,
               (SELECT COUNT(*) FROM posts WHERE posts.user_id = users.id) AS post_count
        FROM users
        ORDER BY users.id ASC
        """
    ).fetchall()
    return render_template("admin_users.html", users=users)


@app.route("/admin/posts")
@admin_required
def admin_posts():
    db = get_db()
    posts = db.execute(
        """
        SELECT posts.*, users.username
        FROM posts
        JOIN users ON posts.user_id = users.id
        ORDER BY posts.id DESC
        """
    ).fetchall()
    return render_template("admin_posts.html", posts=posts)


@app.route("/admin/chats")
@admin_required
def admin_chats():
    db = get_db()
    chats = db.execute(
        """
        SELECT
            c.id,
            u1.username AS user1_name,
            u2.username AS user2_name,
            (
                SELECT COUNT(*)
                FROM messages m
                WHERE m.conversation_id = c.id
            ) AS message_count,
            c.created_at
        FROM conversations c
        JOIN users u1 ON c.user1_id = u1.id
        JOIN users u2 ON c.user2_id = u2.id
        ORDER BY c.id DESC
        """
    ).fetchall()
    return render_template("admin_chats.html", chats=chats)


@app.route("/admin/chat/<int:conversation_id>")
@admin_required
def admin_chat_view(conversation_id):
    db = get_db()

    conversation = db.execute(
        """
        SELECT
            c.*,
            u1.username AS user1_name,
            u2.username AS user2_name
        FROM conversations c
        JOIN users u1 ON c.user1_id = u1.id
        JOIN users u2 ON c.user2_id = u2.id
        WHERE c.id = ?
        """,
        (conversation_id,),
    ).fetchone()

    if not conversation:
        flash("Conversation not found.", "danger")
        return redirect(url_for("admin_chats"))

    messages = db.execute(
        """
        SELECT m.*, u.username AS sender_name
        FROM messages m
        JOIN users u ON m.sender_id = u.id
        WHERE m.conversation_id = ?
        ORDER BY m.created_at ASC, m.id ASC
        """,
        (conversation_id,),
    ).fetchall()

    return render_template(
        "admin_chat_view.html",
        conversation=conversation,
        messages=messages,
    )


@app.route("/admin/user/<int:user_id>/delete", methods=["POST"])
@admin_required
def admin_delete_user(user_id):
    db = get_db()
    db.execute("DELETE FROM users WHERE id = ?", (user_id,))
    db.commit()
    flash("User deleted successfully.", "success")
    return redirect(url_for("admin_users"))


@app.route("/admin/post/<int:post_id>/delete", methods=["POST"])
@admin_required
def admin_delete_post(post_id):
    db = get_db()
    db.execute("DELETE FROM posts WHERE id = ?", (post_id,))
    db.commit()
    flash("Post deleted successfully.", "success")
    return redirect(url_for("admin_posts"))


if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=5000, debug=True)