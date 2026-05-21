from flask import Flask, render_template, request, redirect, session, abort
import psycopg2
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = "secret123"

# -------- Подключение к PostgreSQL --------
def get_db_connection():
    conn = psycopg2.connect(
        host="localhost",
        database="styleparic",   # имя твоей БД
        user="orlov_andrey_knowledge_base",       # пользователь
        password="123"        # пароль
    )
    return conn

# -------- Контекст для шаблонов --------
@app.context_processor
def inject_admin():
    return dict(is_admin=session.get("role") == 1)

# -------- Главная страница --------
@app.route("/")
def index():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT username,rating,comment,created_at
        FROM reviews
        ORDER BY created_at DESC
        LIMIT 4
    """)
    reviews = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template("index.html", reviews=reviews)

# -------- О нас --------
@app.route("/about")
def about():
    return render_template("about.html")

# -------- Услуги --------
@app.route("/services")
def services():
    return render_template("services.html")

# -------- Вход --------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute(
            "SELECT username, password, role FROM users WHERE username=%s",
            (username,)
        )
        user = cursor.fetchone()

        cursor.close()
        conn.close()

        if not user:
            return render_template("login.html", error="Такого аккаунта не существует")

        # Проверяем хэш пароля
        if not check_password_hash(user[1], password):
            return render_template("login.html", error="Неверный пароль")

        # Сохраняем данные в сессии
        session["username"] = user[0]
        session["role"] = user[2]

        return redirect("/")

    return render_template("login.html")

# -------- Регистрация --------
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        
        # 🔐 Проверка сложности пароля
        if len(password) < 6:
            return render_template("register.html", error="Пароль должен быть не менее 6 символов")
        
        if not any(c.isalpha() for c in password):
            return render_template("register.html", error="Пароль должен содержать хотя бы одну букву")
        
        if not any(c.isdigit() for c in password):
            return render_template("register.html", error="Пароль должен содержать хотя бы одну цифру")
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM users WHERE username=%s", (username,))
        existing_user = cursor.fetchone()
        
        if existing_user:
            cursor.close()
            conn.close()
            return render_template("register.html", error="Этот логин уже занят")
        
        # Хешируем пароль
        hashed_password = generate_password_hash(password)
        
        # Создаём пользователя
        cursor.execute(
            "INSERT INTO users (username, password, role) VALUES (%s,%s,%s)",
            (username, hashed_password, 0)
        )
        
        conn.commit()
        cursor.close()
        conn.close()
        
        session["username"] = username
        session["role"] = 0
        
        return redirect("/")
    
    return render_template("register.html")

# -------- Выход --------
@app.route("/logout")
def logout():
    session.pop("username", None)
    session.pop("role", None)
    return redirect("/")

# -------- Бронирование --------
@app.route("/booking", methods=["GET", "POST"])
def booking():
    if "username" not in session:
        return redirect("/login")

    busy_times = []
    selected_date = request.args.get("date")  # для первой загрузки страницы

    if request.method == "POST":
        name = request.form["name"]
        phone = request.form["phone"]
        service = request.form["service"]
        date = request.form["date"]
        time = request.form["time"]
        master = request.form["master"]  # получаем мастера

        conn = get_db_connection()
        cursor = conn.cursor()

        # Проверяем занятое время для этого мастера
        cursor.execute(
            "SELECT * FROM appointments WHERE date=%s AND time=%s AND master=%s",
            (date, time, master)
        )
        busy = cursor.fetchone()
        if busy:
            cursor.close()
            conn.close()
            return render_template(
                "booking.html",
                error="Это время уже занято",
                name=name,
                phone=phone,
                service=service,
                selected_date=date
            )

        # Вставляем запись с мастером
        cursor.execute("""
            INSERT INTO appointments (username, name, phone, service, date, time, master)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (session["username"], name, phone, service, date, time, master))

        conn.commit()
        cursor.close()
        conn.close()
        return redirect("/my_bookings")  # можно сразу на страницу "Мои записи"

    return render_template(
        "booking.html",
        busy_times=busy_times,
        selected_date=selected_date
    )

# -------- Мои бронирования --------
@app.route("/my_bookings")
def my_bookings():
    if "username" not in session:
        return redirect("/login")

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id,service,date,time,status,master
        FROM appointments
        WHERE username=%s AND status != 'Завершена'
        ORDER BY date,time
    """,(session["username"],))
    bookings = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template("my_bookings.html", bookings=bookings)

@app.route("/delete_booking/<int:id>")
def delete_booking(id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM appointments WHERE id=%s", (id,))
    conn.commit()
    cursor.close()
    conn.close()
    return redirect("/my_bookings")

# -------- Декоратор для админки --------
from functools import wraps
def admin_required(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if session.get("role") != 1:
            abort(403)
        return func(*args, **kwargs)
    return wrapper

# -------- Админка --------
@app.route("/admin")
@admin_required
def admin():
    search = request.args.get("search")
    date = request.args.get("date")

    conn = get_db_connection()
    cursor = conn.cursor()
    query = "SELECT id,name,phone,service,date,time,status, master FROM appointments WHERE status!='Завершена'"
    params = []
    if search:
        query += " AND (name ILIKE %s OR phone ILIKE %s)"
        params.extend([f"%{search}%", f"%{search}%"])
    if date:
        query += " AND date=%s"
        params.append(date)
    query += " ORDER BY date,time"
    cursor.execute(query, params)
    bookings = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template("admin.html", bookings=bookings)

@app.route("/confirm/<int:id>")
@admin_required
def confirm_booking(id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE appointments SET status='Подтверждена' WHERE id=%s", (id,))
    conn.commit()
    cursor.close()
    conn.close()
    return redirect("/admin")

@app.route("/complete/<int:id>")
@admin_required
def complete_booking(id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE appointments SET status='Завершена' WHERE id=%s", (id,))
    conn.commit()
    cursor.close()
    conn.close()
    return redirect("/admin")

@app.route("/admin_create", methods=["GET","POST"])
@admin_required
def admin_create():
    if "username" not in session:
        return redirect("/login")

    # Можно добавить проверку на роль администратора, если есть поле role в users
    conn = get_db_connection()
    cursor = conn.cursor()

    if request.method == "POST":
        name = request.form["name"]
        phone = request.form["phone"]
        service = request.form["service"]
        date = request.form["date"]
        time = request.form["time"]
        master = request.form["master"]

        cursor.execute("SELECT * FROM appointments WHERE date=%s AND time=%s AND master=%s",
               (date, time, master))
        busy = cursor.fetchone()
        if busy:
            cursor.close()
            conn.close()
            return render_template("admin_create.html", error="Это время уже занято",
                                   name=name, phone=phone, service=service, selected_date=date)

        cursor.execute("""
            INSERT INTO appointments (name, phone, service, date, time, status, master)
            VALUES (%s,%s,%s,%s,%s,%s,%s)
        """, (name, phone, service, date, time, "Подтверждена", master))
        conn.commit()
        cursor.close()
        conn.close()
        return redirect("/admin")

    cursor.close()
    conn.close()
    return render_template("admin_create.html")
# -------- Отзывы --------
@app.route("/review", methods=["GET","POST"])
def review():
    if request.method == "POST":
        name = request.form["username"]
        rating = request.form["rating"]
        comment = request.form["comment"]

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO reviews (username,rating,comment) VALUES (%s,%s,%s)", (name,rating,comment))
        conn.commit()
        cursor.close()
        conn.close()
        return redirect("/")
    return render_template("review.html")

@app.route("/reviews")
def reviews():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, username,rating,comment,created_at FROM reviews ORDER BY created_at DESC")
    reviews = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template("reviews.html", reviews=reviews)

@app.route("/delete_review/<int:id>")
@admin_required
def delete_review(id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM reviews WHERE id=%s", (id,))
    conn.commit()
    cursor.close()
    conn.close()
    return redirect("/reviews")

@app.route("/get_busy_times")
def get_busy_times():
    date = request.args.get("date")
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT time FROM appointments WHERE date=%s", (date,))
    rows = cursor.fetchall()
    busy = [row[0].strftime("%H:%M") for row in rows]
    cursor.close()
    conn.close()
    return {"busy": busy}  # Flask автоматически вернёт JSON

@app.route("/get_busy_times_admin")
@admin_required
def get_busy_times_admin():
    date = request.args.get("date")
    conn = get_db_connection()
    cursor = conn.cursor()

    # Времена, которые уже заняты
    cursor.execute("SELECT time FROM appointments WHERE date=%s", (date,))
    busy = [row[0].strftime("%H:%M") for row in cursor.fetchall()]

    # Мастера, которые работают в этот день
    cursor.execute("SELECT master_name FROM schedule WHERE date=%s AND note='Работает'", (date,))
    masters = [row[0] for row in cursor.fetchall()]

    cursor.close()
    conn.close()
    return {"busy": busy, "masters": masters}

from datetime import datetime, timedelta

@app.route("/schedule")
def schedule():
    # проверяем авторизацию
    if "username" not in session:
        return redirect("/login")

    conn = get_db_connection()
    cursor = conn.cursor()

    # список мастеров
    masters = ["Ирина", "Марина", "Ольга"]

    # формируем даты для текущего месяца + 1 месяц
    today = datetime.today().date()
    dates = [today + timedelta(days=i) for i in range(30)]  # всегда 30 дней вперед

    # создаем записи в schedule, если их нет
    for date in dates:
        for master in masters:
            cursor.execute(
                "SELECT * FROM schedule WHERE date=%s AND master_name=%s",
                (date, master)
            )
            if not cursor.fetchone():
                cursor.execute(
                    "INSERT INTO schedule (date, master_name) VALUES (%s, %s)",
                    (date, master)
                )
    conn.commit()

    # получаем данные для отображения
    cursor.execute("SELECT date, master_name, note FROM schedule WHERE date BETWEEN %s AND %s",
                   (today, today + timedelta(days=29)))
    rows = cursor.fetchall()
    cursor.close()
    conn.close()

    # формируем словарь {date: {master: note}}
    schedule_data = {}
    for d in dates:
        schedule_data[d] = {master: "" for master in masters}

    for row in rows:
        schedule_data[row[0]][row[1]] = row[2]

    return render_template("schedule.html", dates=dates, masters=masters, schedule_data=schedule_data)

from flask import request, jsonify

@app.route("/update_schedule", methods=["POST"])
@admin_required
def update_schedule():
    if "username" not in session or session.get("role") != 1:
        return jsonify({"error": "Нет прав"}), 403

    data = request.get_json()
    date = data.get("date")
    master = data.get("master")
    note = data.get("note")

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE schedule SET note=%s WHERE date=%s AND master_name=%s",
                   (note, date, master))
    conn.commit()
    cursor.close()
    conn.close()

    return jsonify({"success": True})

from flask import jsonify, request

@app.route("/get_available")
def get_available():
    date = request.args.get("date")
    conn = get_db_connection()
    cursor = conn.cursor()

    # Времена, которые уже заняты
    cursor.execute("SELECT time FROM appointments WHERE date=%s", (date,))
    busy_times = [row[0].strftime("%H:%M") for row in cursor.fetchall()]

    # Мастера, которые работают в этот день
    cursor.execute("""
        SELECT master_name 
        FROM schedule
        WHERE date=%s AND note='Работает'
    """, (date,))
    masters = [row[0] for row in cursor.fetchall()]

    cursor.close()
    conn.close()

    return jsonify({"busy": busy_times, "masters": masters})


@app.route("/admin_notifications")
@admin_required
def admin_notifications():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM appointments WHERE status='Ожидает'")
    count = cursor.fetchone()[0]
    cursor.close()
    conn.close()
    return {"count": count}  # возвращаем JSON
# -------- Запуск сервера --------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)