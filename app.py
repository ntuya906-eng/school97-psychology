from __future__ import annotations

import os
import secrets
import sqlite3
from datetime import datetime
from functools import wraps
from pathlib import Path

from flask import Flask, flash, g, redirect, render_template, request, session, url_for

BASE_DIR = Path(__file__).resolve().parent
DATABASE = BASE_DIR / 'school97.db'
DEFAULT_ADMIN_USERNAME = 'admin'
DEFAULT_ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'School97@2026')

app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'school97_secure_secret_key')


def get_db() -> sqlite3.Connection:
    if 'db' not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(error=None):
    db = g.pop('db', None)
    if db is not None:
        db.close()


def init_db() -> None:
    db = sqlite3.connect(DATABASE)
    cursor = db.cursor()
    cursor.execute(
        '''
        CREATE TABLE IF NOT EXISTS registrations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_code TEXT UNIQUE NOT NULL,
            last_name TEXT NOT NULL,
            first_name TEXT NOT NULL,
            grade_class TEXT NOT NULL,
            phone TEXT NOT NULL,
            reason TEXT NOT NULL,
            appointment_date TEXT NOT NULL,
            appointment_time TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'Хүлээгдэж байна',
            admin_note TEXT DEFAULT '',
            created_at TEXT NOT NULL
        )
        '''
    )
    db.commit()
    db.close()


def generate_student_code() -> str:
    return f"PSY-{secrets.token_hex(3).upper()}"


def admin_required(view_func):
    @wraps(view_func)
    def wrapped_view(*args, **kwargs):
        if not session.get('admin_logged_in'):
            return redirect(url_for('admin_login'))
        return view_func(*args, **kwargs)
    return wrapped_view


@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        last_name = request.form.get('last_name', '').strip()
        first_name = request.form.get('first_name', '').strip()
        grade_class = request.form.get('grade_class', '').strip()
        phone = request.form.get('phone', '').strip()
        reason = request.form.get('reason', '').strip()
        appointment_date = request.form.get('appointment_date', '').strip()
        appointment_time = request.form.get('appointment_time', '').strip()

        if not all([last_name, first_name, grade_class, phone, reason, appointment_date, appointment_time]):
            flash('Бүх талбарыг бөглөнө үү.', 'error')
            return redirect(url_for('index'))

        if not phone.isdigit() or len(phone) != 8:
            flash('Утасны дугаар 8 оронтой тоо байна.', 'error')
            return redirect(url_for('index'))

        try:
            selected_datetime = datetime.strptime(f'{appointment_date} {appointment_time}', '%Y-%m-%d %H:%M')
            if selected_datetime < datetime.now():
                flash('Өнгөрсөн өдөр, цаг сонгох боломжгүй.', 'error')
                return redirect(url_for('index'))
        except ValueError:
            flash('Өдөр, цагийн формат буруу байна.', 'error')
            return redirect(url_for('index'))

        db = get_db()
        student_code = generate_student_code()
        while db.execute('SELECT 1 FROM registrations WHERE student_code = ?', (student_code,)).fetchone():
            student_code = generate_student_code()

        db.execute(
            '''
            INSERT INTO registrations
            (student_code, last_name, first_name, grade_class, phone, reason, appointment_date, appointment_time, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            (
                student_code,
                last_name,
                first_name,
                grade_class,
                phone,
                reason,
                appointment_date,
                appointment_time,
                datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            ),
        )
        db.commit()
        return render_template('success.html', student_code=student_code, phone=phone)

    return render_template('index.html')


@app.route('/check', methods=['GET', 'POST'])
def check_registration():
    registration = None
    if request.method == 'POST':
        student_code = request.form.get('student_code', '').strip().upper()
        phone = request.form.get('phone', '').strip()
        db = get_db()
        registration = db.execute(
            'SELECT * FROM registrations WHERE student_code = ? AND phone = ?',
            (student_code, phone),
        ).fetchone()
        if not registration:
            flash('Код эсвэл утасны дугаар буруу байна.', 'error')
    return render_template('check.html', registration=registration)


@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        if username == DEFAULT_ADMIN_USERNAME and password == DEFAULT_ADMIN_PASSWORD:
            session['admin_logged_in'] = True
            flash('Админ хэсэгт амжилттай нэвтэрлээ.', 'success')
            return redirect(url_for('admin_dashboard'))
        flash('Нэвтрэх нэр эсвэл нууц үг буруу байна.', 'error')
    return render_template('admin_login.html')


@app.route('/admin/logout')
def admin_logout():
    session.clear()
    flash('Админ хэсгээс гарлаа.', 'success')
    return redirect(url_for('admin_login'))


@app.route('/admin', methods=['GET', 'POST'])
@admin_required
def admin_dashboard():
    db = get_db()

    if request.method == 'POST':
        record_id = request.form.get('record_id', '').strip()
        appointment_date = request.form.get('appointment_date', '').strip()
        appointment_time = request.form.get('appointment_time', '').strip()
        status = request.form.get('status', '').strip()
        admin_note = request.form.get('admin_note', '').strip()

        if not all([record_id, appointment_date, appointment_time, status]):
            flash('Шаардлагатай мэдээллээ бүрэн бөглөнө үү.', 'error')
            return redirect(url_for('admin_dashboard'))

        db.execute(
            '''
            UPDATE registrations
            SET appointment_date = ?, appointment_time = ?, status = ?, admin_note = ?
            WHERE id = ?
            ''',
            (appointment_date, appointment_time, status, admin_note, record_id),
        )
        db.commit()
        flash('Бүртгэлийн мэдээлэл шинэчлэгдлээ.', 'success')
        return redirect(url_for('admin_dashboard'))

    registrations = db.execute(
        'SELECT * FROM registrations ORDER BY appointment_date ASC, appointment_time ASC, created_at DESC'
    ).fetchall()
    return render_template('admin_dashboard.html', registrations=registrations)


if __name__ == '__main__':
    init_db()
    app.run(debug=True)
