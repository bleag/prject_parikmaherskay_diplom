from flask import Flask, render_template, request, redirect, session, abort
import psycopg2
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
import re
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


def time_to_minutes(time_str):
    if not time_str:
        return 0
    h, m = map(int, time_str.split(':'))
    return h * 60 + m

def minutes_to_time(minutes):
    h = minutes // 60
    m = minutes % 60
    return f"{h:02d}:{m:02d}"

def get_service_duration(service):
    durations = {
        "Мужская стрижка": 30,
        "Женская стрижка": 60,
        "Окрашивание": 120,
        "Маникюр": 120
    }
    return durations.get(service, 30)

def validate_phone(phone):
    """Простая проверка: 11 цифр (например 89131234567)"""
    if not phone:
        return False
    # Убираем всё, кроме цифр
    cleaned = re.sub(r'\D', '', phone)
    # Проверяем, что ровно 11 цифр
    return len(cleaned) == 11


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

    if request.method == "POST":
        name = request.form["name"]
        phone = request.form["phone"]
        service = request.form["service"]
        date = request.form["date"]
        time = request.form["time"]
        master = request.form["master"]
        
        # ===== ПРОВЕРКА ТЕЛЕФОНА =====
        cleaned_phone = re.sub(r'\D', '', phone)
        if len(cleaned_phone) != 11:
            return render_template(
                "booking.html",
                error="❌ Введите корректный номер телефона (11 цифр, например: 89131234567)",
                name=name,
                phone=phone,
                service=service,
                selected_date=date
            )
        phone = cleaned_phone
        # ===== КОНЕЦ ПРОВЕРКИ ТЕЛЕФОНА =====
        
        # ===== ПРОВЕРКА: сколько записей пользователь сделал СЕГОДНЯ =====
        conn = get_db_connection()
        cursor = conn.cursor()
        
        from datetime import datetime
        today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        
        cursor.execute("""
            SELECT COUNT(*) FROM appointments 
            WHERE username=%s AND created_at >= %s
        """, (session["username"], today_start))
        today_bookings = cursor.fetchone()[0]
        
        print(f"DEBUG: Пользователь {session['username']} сделал {today_bookings} записей сегодня")
        
        if today_bookings >= 5:
            cursor.close()
            conn.close()
            return render_template(
                "booking.html",
                error=f"⚠️ ЗАЩИТА ОТ СПАМА: Вы уже сделали {today_bookings} записей сегодня. Максимум 5 записей в день!",
                name=name,
                phone=phone,
                service=service,
                selected_date=date
            )
        # ===== КОНЕЦ ПРОВЕРКИ =====
        
        duration = get_service_duration(service)
        new_start = time_to_minutes(time)
        new_end = new_start + duration
        
        # ===== ПРОВЕРКА: не выходит ли услуга за рабочее время =====
        WORK_END_MINUTES = time_to_minutes("20:00")
        
        if new_end > WORK_END_MINUTES:
            cursor.close()
            conn.close()
            return render_template(
                "booking.html",
                error=f"Услуга '{service}' длится {duration} минут и не может быть начата в {time}, так как закончится после 20:00. Пожалуйста, выберите более раннее время.",
                name=name,
                phone=phone,
                service=service,
                selected_date=date
            )
        # ===== КОНЕЦ ПРОВЕРКИ =====
        
        try:
            # Получаем все записи этого мастера на эту дату
            cursor.execute("""
                SELECT time, service FROM appointments 
                WHERE date=%s AND master=%s AND status != 'Завершена'
            """, (date, master))
            existing = cursor.fetchall()
            
            # Проверяем пересечение интервалов
            is_busy = False
            for ex in existing:
                ex_time = ex[0].strftime("%H:%M") if hasattr(ex[0], 'strftime') else ex[0]
                ex_service = ex[1]
                ex_start = time_to_minutes(ex_time)
                ex_end = ex_start + get_service_duration(ex_service)
                
                if new_start < ex_end and new_end > ex_start:
                    is_busy = True
                    break
            
            if is_busy:
                cursor.close()
                conn.close()
                return render_template(
                    "booking.html",
                    error="Это время уже занято у выбранного мастера",
                    name=name,
                    phone=phone,
                    service=service,
                    selected_date=date
                )
            
            # Сохраняем запись с created_at
            cursor.execute("""
                INSERT INTO appointments (username, name, phone, service, date, time, master, status, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (session["username"], name, phone, service, date, time, master, "Ожидает", datetime.now()))
            
            conn.commit()
            
        except Exception as e:
            print(f"Ошибка при бронировании: {e}")
            return render_template(
                "booking.html",
                error="Произошла ошибка при записи. Попробуйте позже.",
                name=name,
                phone=phone,
                service=service,
                selected_date=date
            )
        finally:
            cursor.close()
            conn.close()
        
        return redirect("/my_bookings")
    
    return render_template("booking.html", selected_date=request.args.get("date"))

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

    conn = get_db_connection()
    cursor = conn.cursor()

    if request.method == "POST":
        name = request.form["name"]
        phone = request.form["phone"]
        service = request.form["service"]
        date = request.form["date"]
        time = request.form["time"]
        master = request.form["master"]
        
        # ===== ПРОСТАЯ ПРОВЕРКА ТЕЛЕФОНА =====
        # Убираем всё, кроме цифр
        cleaned_phone = re.sub(r'\D', '', phone)
        if len(cleaned_phone) != 11:
            cursor.close()
            conn.close()
            return render_template(
                "admin_create.html",
                error="❌ Введите корректный номер телефона (11 цифр, например: 89131234567)",
                name=name,
                phone=phone,
                service=service,
                selected_date=date
            )
        # Сохраняем очищенный номер в БД
        phone = cleaned_phone
        # ===== КОНЕЦ ПРОВЕРКИ =====

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
    if not date:
        return jsonify({"busy": [], "masters": [], "detailedBusy": {}})
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Получаем мастеров, которые работают в этот день
    cursor.execute("""
        SELECT master_name 
        FROM schedule
        WHERE date=%s AND (note='Работает' OR note IS NULL)
    """, (date,))
    masters = [row[0] for row in cursor.fetchall()]
    
    if not masters:
        masters = ["Ирина", "Марина", "Ольга"]
    
    # Получаем записи на эту дату
    cursor.execute("""
        SELECT master, time, service
        FROM appointments
        WHERE date=%s AND status != 'Завершена'
    """, (date,))
    bookings = cursor.fetchall()
    cursor.close()
    conn.close()
    
    WORK_END_MINUTES = time_to_minutes("20:00")  # 20:00
    
    # Формируем занятые интервалы для каждого мастера
    detailed_busy = {master: [] for master in masters}
    
    for booking in bookings:
        master = booking[0]
        time_str = booking[1].strftime("%H:%M") if hasattr(booking[1], 'strftime') else booking[1]
        service = booking[2]
        
        if master in detailed_busy:
            start_min = time_to_minutes(time_str)
            duration = get_service_duration(service)
            end_min = start_min + duration
            
            detailed_busy[master].append({
                "start": minutes_to_time(start_min),
                "end": minutes_to_time(end_min)
            })
    
    return jsonify({
        "busy": [],
        "masters": masters,
        "detailedBusy": detailed_busy,
        "workEnd": "20:00"  # отправляем клиенту рабочий конец дня
    })


@app.route("/admin/stats")
@admin_required
def admin_stats():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Общее количество записей
    cursor.execute("SELECT COUNT(*) FROM appointments")
    total_bookings = cursor.fetchone()[0]
    
    # Записей на сегодня
    today = datetime.now().strftime("%Y-%m-%d")
    cursor.execute("SELECT COUNT(*) FROM appointments WHERE date=%s", (today,))
    today_bookings = cursor.fetchone()[0]
    
    # Самая популярная услуга
    cursor.execute("""
        SELECT service, COUNT(*) as cnt 
        FROM appointments 
        GROUP BY service 
        ORDER BY cnt DESC 
        LIMIT 1
    """)
    top_service = cursor.fetchone()
    top_service_name = top_service[0] if top_service else "Нет данных"
    
    # Количество уникальных клиентов
    cursor.execute("SELECT COUNT(DISTINCT username) FROM appointments")
    total_clients = cursor.fetchone()[0]
    
    cursor.close()
    conn.close()
    
    return render_template("admin_stats.html", 
                          total_bookings=total_bookings,
                          today_bookings=today_bookings,
                          top_service=top_service_name,
                          total_clients=total_clients)


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