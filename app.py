from flask import Flask, render_template_string, request, redirect, url_for, flash
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from datetime import datetime, date
import os, re

# =========================
# Opciones configurables
# =========================
BREED_OPTIONS = [
    "Aberdeen Angus", "Hereford", "Braford", "Brangus", "Holando", "Criollo", "Otra"
]

SEED_CATEGORIES = [
    "Vaca",
    "Vaca Invernada",
    "Toro",
    "Nov. 1 año",
    "Vaq. 1 año",
    "Ternero M",
    "Ternera H",
    "Vaq. 2+",
    "Vaq. 3",
]

DEFAULT_DAILY_GAIN = 0.6  # kg/día

# -------------------------
# Configuración de la app
# -------------------------
app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "cambia_esto_en_produccion")
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL", "sqlite:///app.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = "login"

# -------------------------
# Modelos
# -------------------------
class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=True)  # nullable para setup inicial
    is_admin = db.Column(db.Boolean, default=False, nullable=False)
    is_active_flag = db.Column(db.Boolean, default=True, nullable=False)

    def set_password(self, password: str):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        if not self.password_hash:
            return False
        return check_password_hash(self.password_hash, password)

    def get_id(self):
        return str(self.id)

    @property
    def is_active(self):
        return self.is_active_flag

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

class Category(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(30), unique=True, nullable=False)   # máx 30, único
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    daily_gain_kg = db.Column(db.Float, default=DEFAULT_DAILY_GAIN, nullable=False)  # kg/día

class Animal(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    # Identificación
    tag_current = db.Column(db.String(64), unique=True, nullable=False, index=True)  # Caravana actual
    tag_previous = db.Column(db.String(64), nullable=True)  # Caravana anterior

    # Datos productivos
    weight = db.Column(db.Float, nullable=True)             # Peso del último pesaje (kg)
    weigh_date = db.Column(db.Date, nullable=True)          # Fecha del último pesaje
    est_weight_today = db.Column(db.Float, nullable=True)   # Valor estimado del peso al día de hoy (kg)

    # Metadatos/otros con límites
    comment = db.Column(db.String(30), nullable=True)       # máx 30
    origin = db.Column(db.String(30), nullable=True)        # máx 30
    category = db.Column(db.String(30), nullable=True)      # guarda el texto de categoría
    read_date = db.Column(db.Date, nullable=True)
    last_seen = db.Column(db.Date, nullable=True)
    birth_date = db.Column(db.Date, nullable=True)
    sex = db.Column(db.String(1), nullable=True)            # 'M'/'H'
    breed = db.Column(db.String(30), nullable=True)         # desde dropdown fijo
    diagnosis = db.Column(db.String(10), nullable=True)     # máx 10
    lot = db.Column(db.String(20), nullable=True)           # máx 20

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def compute_estimated_weight(self, daily_gain_kg: float = DEFAULT_DAILY_GAIN) -> float | None:
        if not self.weight or not self.weigh_date:
            return None
        today = date.today()
        days = (today - self.weigh_date).days
        return round(self.weight + max(0, days) * daily_gain_kg, 1)

# --- Bootstrap DB + seeds + “migración” ligera ---
with app.app_context():
    db.create_all()

    # MIGRACIÓN: agregar columna daily_gain_kg si falta (SQLite)
    try:
        db.session.execute(text("SELECT daily_gain_kg FROM category LIMIT 1"))
    except OperationalError:
        db.session.execute(text(
            f"ALTER TABLE category ADD COLUMN daily_gain_kg FLOAT NOT NULL DEFAULT {DEFAULT_DAILY_GAIN}"
        ))
        db.session.commit()

    # Seed admin si falta
    admin = User.query.filter_by(is_admin=True).order_by(User.id.asc()).first()
    if not admin:
        admin = User(email="admin@local", is_admin=True, is_active_flag=True, password_hash=None)
        db.session.add(admin)
        db.session.commit()

    # Seed categorías si está vacío
    if Category.query.count() == 0:
        for n in SEED_CATEGORIES:
            db.session.add(Category(name=n, is_active=True, daily_gain_kg=DEFAULT_DAILY_GAIN))
        db.session.commit()

# -------------------------
# Estilos y shell
# -------------------------
BASE_CSS = """
<style>
  :root{
    --bg:#f7f8fb; --card:#ffffff; --text:#0f172a; --muted:#64748b; --primary:#2563eb;
    --primary-600:#1d4ed8; --danger:#b91c1c; --ok:#065f46; --border:#e5e7eb;
  }
  @media (prefers-color-scheme: dark){
    :root{ --bg:#0b1220; --card:#0f172a; --text:#e5e7eb; --muted:#94a3b8; --primary:#60a5fa; --primary-600:#3b82f6; --danger:#ef4444; --ok:#34d399; --border:#1f2937; }
  }
  *{ box-sizing:border-box; }
  body{ margin:0; font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif; background:var(--bg); color:var(--text); }
  a{ color:var(--primary); text-decoration:none; }
  a:hover{ text-decoration:underline; }
  header.appbar{
    position:sticky; top:0; background:rgba(255,255,255,.6); backdrop-filter: blur(8px);
    border-bottom:1px solid var(--border); padding:12px 0; margin-bottom:24px;
  }
  @media (prefers-color-scheme: dark){ header.appbar{ background:rgba(15,23,42,.6); } }
  .container{ max-width:1040px; margin:0 auto; padding:0 16px; }
  .brand{ display:flex; align-items:center; gap:12px; font-weight:700; }
  .brand .logo{ width:28px; height:28px; border-radius:8px; background:linear-gradient(135deg, var(--primary), var(--primary-600)); }
  .session{ color:var(--muted); font-size:14px; }
  .grid{ display:grid; gap:16px; }
  .card{
    background:var(--card); border:1px solid var(--border); border-radius:14px; padding:18px;
    box-shadow: 0 6px 20px rgba(2,6,23,.06);
  }
  h1{ font-size:28px; margin:6px 0 4px; }
  h2{ font-size:22px; margin:0 0 8px; }
  p.lead{ color:var(--muted); margin:0 0 16px; }
  .row{ display:flex; gap:12px; flex-wrap:wrap; }
  input, select, textarea{
    width:100%; padding:12px 12px; border-radius:12px; border:1px solid var(--border); background:transparent; color:var(--text);
  }
  textarea{ min-height:96px; }
  button, .btn{ display:inline-block; padding:10px 14px; border:0; border-radius:12px; cursor:pointer; font-weight:600; }
  .btn-primary{ background:var(--primary); color:white; } .btn-primary:hover{ background:var(--primary-600); }
  .btn-muted{ background:#e5e7eb; color:#111827; } @media (prefers-color-scheme: dark){ .btn-muted{ background:#1f2937; color:#e5e7eb; } }
  .btn-ghost{ background:transparent; color:var(--primary); }
  .btn-danger{ background:var(--danger); color:white; }
  .links a{ margin-right:12px; }
  .flash{ padding:10px 12px; border-radius:12px; margin-bottom:8px; font-size:14px; }
  .flash.ok{ background:rgba(16,185,129,.15); color:var(--ok); }
  .flash.error{ background:rgba(239,68,68,.15); color:var(--danger); }
  table{ width:100%; border-collapse:collapse; }
  th, td{ padding:10px; border-bottom:1px solid var(--border); text-align:left; vertical-align: top; }
  th{ color:var(--muted); font-weight:600; white-space:nowrap; }
  tr:hover td{ background:rgba(2,6,23,.03); }
  .nowrap{ white-space:nowrap; }
  footer{ color:var(--muted); font-size:12px; padding:24px 0; text-align:center; }
</style>
"""

# IMPORTANTE: NO usar .format(...) aquí. Dejamos {{ title }} para Jinja.
SHELL_HTML_HEAD = """<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{{ title }}</title>""" + BASE_CSS + """</head>
<body>
<header class="appbar">
  <div class="container" style="display:flex; align-items:center; justify-content:space-between; gap:16px;">
    <div class="brand"><div class="logo"></div> <span>Flask Caja</span></div>
    <div class="session">
      {% if current_user.is_authenticated %}
        {{ current_user.email }}{% if current_user.is_admin %} · Admin{% endif %} · <a href="{{ url_for('logout') }}">Salir</a>
      {% else %}
        <a href="{{ url_for('login') }}">Ingresar</a>
      {% endif %}
    </div>
  </div>
</header>
<main class="container">
"""

SHELL_HTML_FOOT = """
</main>
<footer>
  Hecho con Flask · {{ 'Admin' if current_user.is_authenticated and current_user.is_admin else 'Usuario' if current_user.is_authenticated else 'Invitado' }}
</footer>
</body></html>
"""

FLASHES_HTML = """
{% with msgs = get_flashed_messages(with_categories=true) %}
  {% if msgs %}
    <div class="grid">
      {% for cat, msg in msgs %}
        <div class="flash {{ 'ok' if cat=='success' or cat=='ok' else 'error' if cat=='error' else '' }}">{{ msg }}</div>
      {% endfor %}
    </div>
  {% endif %}
{% endwith %}
"""

# -------------------------
# Validaciones / parsing
# -------------------------
TAG_RE = re.compile(r"^[0-9 ]+$")                      # dígitos y espacios
WEIGHT_RE = re.compile(r"^\d{1,4}([.,]\d)?$")          # 1-4 dígitos + opcional ,/.[1]
DATE_FMT = "%d/%m/%y"                                  # DD/MM/AA

def fmt_date(d: date | None) -> str:
    return d.strftime(DATE_FMT) if d else ""

def parse_date_ddmmyy(s: str) -> date | None:
    s = (s or "").strip()
    if not s: return None
    try:
        return datetime.strptime(s, DATE_FMT).date()
    except ValueError:
        return None

def parse_weight_1d(s: str) -> float | None:
    raw = (s or "").strip()
    if not raw: return None
    if not WEIGHT_RE.match(raw): return None
    raw = raw.replace(",", ".")
    try:
        return round(float(raw), 1)
    except ValueError:
        return None

def clean_tag(tag: str) -> str | None:
    raw = (tag or "").strip()
    if not raw: return None
    if not TAG_RE.match(raw): return None
    return re.sub(r"\s+", " ", raw)

def limit_len(s: str | None, maxlen: int) -> str | None:
    s = (s or "").strip()
    if not s: return None
    return s[:maxlen]

def require_admin():
    if not (current_user.is_authenticated and current_user.is_admin):
        flash("Se requiere usuario administrador.", "error")
        return False
    return True

def admin_needs_password_setup():
    admin = User.query.filter_by(is_admin=True).order_by(User.id.asc()).first()
    return (admin is None) or (not admin.password_hash)

def active_category_names():
    return [c.name for c in Category.query.filter_by(is_active=True).order_by(Category.name.asc()).all()]

def all_category_names():
    return [c.name for c in Category.query.order_by(Category.name.asc()).all()]

def get_gain(cat_name: str | None) -> float:
    if not cat_name:
        return DEFAULT_DAILY_GAIN
    c = Category.query.filter_by(name=cat_name).first()
    return c.daily_gain_kg if c and c.daily_gain_kg is not None else DEFAULT_DAILY_GAIN

# -------------------------
# Autenticación y menú
# -------------------------
@app.route("/")
def index():
    if admin_needs_password_setup():
        return redirect(url_for("setup_admin"))
    if current_user.is_authenticated:
        return redirect(url_for("menu"))
    return redirect(url_for("login"))

@app.route("/setup_admin", methods=["GET", "POST"])
def setup_admin():
    # Buscar el admin "placeholder" (o el primero que haya)
    admin = User.query.filter_by(is_admin=True).order_by(User.id.asc()).first()

    # Si ya existe un admin con password, no permitir reconfigurar
    if admin and admin.password_hash:
        return redirect(url_for("login"))

    error = None

    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""

        if not email or not password:
            error = "Email y contraseña son obligatorios."
        else:
            existing = User.query.filter_by(email=email).first()

            if admin is None:
                # No hay admin aún
                if existing:
                    # Promover usuario existente a admin
                    existing.is_admin = True
                    if not existing.password_hash:
                        existing.set_password(password)
                    try:
                        db.session.commit()
                        flash("Administrador configurado usando un usuario existente.", "success")
                        return redirect(url_for("login"))
                    except Exception as e:
                        db.session.rollback()
                        error = "No se pudo promover el usuario existente. " + str(e)
                else:
                    # Crear admin nuevo
                    new_admin = User(email=email, is_admin=True, is_active_flag=True)
                    new_admin.set_password(password)
                    try:
                        db.session.add(new_admin)
                        db.session.commit()
                        flash("Administrador creado correctamente.", "success")
                        return redirect(url_for("login"))
                    except Exception as e:
                        db.session.rollback()
                        if "UNIQUE constraint failed: user.email" in str(e):
                            error = "Ese email ya está registrado."
                        else:
                            error = "No se pudo crear el administrador. " + str(e)
            else:
                # Hay un admin placeholder (sin password) → reusarlo
                if existing and existing.id != admin.id:
                    # El email pertenece a otro usuario → promoverlo y borrar placeholder
                    existing.is_admin = True
                    if not existing.password_hash:
                        existing.set_password(password)
                    try:
                        if not admin.password_hash:
                            db.session.delete(admin)
                        db.session.commit()
                        flash("Administrador configurado promoviendo usuario existente.", "success")
                        return redirect(url_for("login"))
                    except Exception as e:
                        db.session.rollback()
                        error = "No se pudo promover el usuario existente. " + str(e)
                else:
                    # Email libre o es el mismo registro del placeholder
                    try:
                        admin.email = email
                        admin.set_password(password)
                        db.session.commit()
                        flash("Administrador configurado correctamente.", "success")
                        return redirect(url_for("login"))
                    except Exception as e:
                        db.session.rollback()
                        if "UNIQUE constraint failed: user.email" in str(e):
                            error = "Ese email ya está registrado."
                        else:
                            error = "No se pudo guardar el administrador. " + str(e)

    content = SHELL_HTML_HEAD + """
    """ + FLASHES_HTML + """
    <div class="grid"><div class="card">
      <h1>Primer uso</h1>
      <p class="lead">Definí el <strong>email</strong> y la <strong>contraseña</strong> del administrador.</p>
      {% if error %}<div class="flash error">{{ error }}</div>{% endif %}
      <form method="post" class="grid">
        <input type="email" name="email" placeholder="Email admin" autocomplete="username" required>
        <input type="password" name="password" placeholder="Contraseña" autocomplete="new-password" required>
        <div class="row">
          <button type="submit" class="btn btn-primary">Guardar</button>
          <a class="btn btn-ghost" href="{{ url_for('login') }}">Ir a Login</a>
        </div>
      </form>
    </div></div>
    """ + SHELL_HTML_FOOT
    return render_template_string(content, error=error, title="Configurar Administrador")
@app.route("/login", methods=["GET", "POST"])
def login():
    if admin_needs_password_setup():
        return redirect(url_for("setup_admin"))
    error = None
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = User.query.filter_by(email=email).first()
        if user and user.is_active_flag and user.password_hash and user.check_password(password):
            login_user(user)
            flash("Bienvenido 👋", "success")
            return redirect(url_for("menu"))
        else:
            error = "Credenciales inválidas o usuario inactivo."
    content = SHELL_HTML_HEAD + """
    """ + FLASHES_HTML + """
    <div class="grid"><div class="card">
      <h1>Ingresar</h1>
      <p class="lead">Accedé con tu email y contraseña.</p>
      {% if error %}<div class="flash error">{{ error }}</div>{% endif %}
      <form method="post" class="grid">
        <input type="email" name="email" placeholder="Correo" autocomplete="username" required>
        <input type="password" name="password" placeholder="Contraseña" autocomplete="current-password" required>
        <div class="row">
          <button type="submit" class="btn btn-primary">Ingresar</button>
          {% if show_setup_link %}<a class="btn btn-ghost" href="{{ url_for('setup_admin') }}">Configurar admin</a>{% endif %}
        </div>
      </form>
    </div></div>
    """ + SHELL_HTML_FOOT
    return render_template_string(content, error=error, show_setup_link=admin_needs_password_setup(), title="Ingresar")

@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash("Sesión cerrada.", "ok")
    return redirect(url_for("login"))

@app.route("/menu")
@login_required
def menu():
    content = SHELL_HTML_HEAD + """
    """ + FLASHES_HTML + """
    <div class="grid"><div class="card">
      <h1>Menú principal</h1>
      <p class="lead">Elegí una opción para comenzar.</p>
      <div class="row" style="gap:10px;">
        <a class="btn btn-primary" href="{{ url_for('movimientos') }}">Movimientos de Caja</a>
        <a class="btn btn-muted" href="{{ url_for('resumen') }}">Resumen de Caja</a>
        <a class="btn btn-ghost" href="{{ url_for('animals') }}">Animales</a>
        {% if current_user.is_admin %}
          <a class="btn btn-ghost" href="{{ url_for('categories') }}">Administrar categorías</a>
          <a class="btn btn-ghost" href="{{ url_for('list_users') }}">Usuarios</a>
        {% endif %}
      </div>
    </div></div>
    """ + SHELL_HTML_FOOT
    return render_template_string(content, title="Menú principal")

# -------------------------
# Categorías (solo admin)
# -------------------------
@app.route("/categories", methods=["GET", "POST"])
@login_required
def categories():
    if not require_admin(): return redirect(url_for("menu"))

    error = None
    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        gain_raw = (request.form.get("daily_gain_kg") or str(DEFAULT_DAILY_GAIN)).strip().replace(",", ".")
        if not name:
            error = "El nombre es obligatorio."
        elif len(name) > 30:
            error = "El nombre no puede superar 30 caracteres."
        elif Category.query.filter_by(name=name).first():
            error = "Ya existe una categoría con ese nombre."
        else:
            try:
                gain = float(gain_raw)
                if gain < 0 or gain > 3:
                    raise ValueError()
            except ValueError:
                error = "Ganancia diaria inválida (0.0 – 3.0)."
        if not error:
            db.session.add(Category(name=name, is_active=True, daily_gain_kg=gain))
            db.session.commit()
            flash("Categoría creada.", "success")
            return redirect(url_for("categories"))

    cats = Category.query.order_by(Category.is_active.desc(), Category.name.asc()).all()
    content = SHELL_HTML_HEAD + """
    """ + FLASHES_HTML + """
    <div class="grid"><div class="card">
      <h1>Categorías</h1>
      <p class="lead">Activá/desactivá, creá nuevas o renombrá. Las inactivas no aparecen en combos, pero preservan datos históricos.</p>
      {% if error %}<div class="flash error">{{ error }}</div>{% endif %}

      <form method="post" class="row" style="margin-bottom:12px;">
        <input type="text" name="name" placeholder="Nueva categoría (máx 30)" maxlength="30" required>
        <input type="number" step="0.1" min="0" max="3" name="daily_gain_kg" placeholder="Ganancia kg/día" value="0.6" required>
        <button class="btn btn-primary" type="submit">Crear</button>
        <a class="btn btn-ghost" href="{{ url_for('menu') }}">Volver</a>
      </form>

      <table>
        <thead><tr><th>Nombre</th><th>Estado</th><th>Ganancia (kg/d)</th><th class="nowrap">Acciones</th></tr></thead>
        <tbody>
          {% for c in cats %}
          <tr>
            <td>{{ c.name }}</td>
            <td>{{ "Activa" if c.is_active else "Inactiva" }}</td>
            <td>{{ "%.1f"|format(c.daily_gain_kg or 0.0) }}</td>
            <td class="nowrap">
              <a href="{{ url_for('category_edit', cat_id=c.id) }}">Editar</a> ·
              <a href="{{ url_for('category_toggle', cat_id=c.id) }}">{{ "Desactivar" if c.is_active else "Activar" }}</a>
            </td>
          </tr>
          {% endfor %}
        </tbody>
      </table>
    </div></div>
    """ + SHELL_HTML_FOOT
    return render_template_string(content, error=error, cats=cats, title="Categorías")

@app.route("/categories/<int:cat_id>/toggle")
@login_required
def category_toggle(cat_id):
    if not require_admin(): return redirect(url_for("categories"))
    c = Category.query.get_or_404(cat_id)
    c.is_active = not c.is_active
    db.session.commit()
    flash(("Activada" if c.is_active else "Desactivada") + " correctamente.", "success")
    return redirect(url_for("categories"))

@app.route("/categories/<int:cat_id>/edit", methods=["GET", "POST"])
@login_required
def category_edit(cat_id):
    if not require_admin(): return redirect(url_for("categories"))
    c = Category.query.get_or_404(cat_id)
    error = None
    if request.method == "POST":
        new_name = (request.form.get("name") or "").strip()
        gain_raw = (request.form.get("daily_gain_kg") or "").strip().replace(",", ".")
        if not new_name:
            error = "El nombre es obligatorio."
        elif len(new_name) > 30:
            error = "Máximo 30 caracteres."
        elif Category.query.filter(Category.name == new_name, Category.id != c.id).first():
            error = "Ya existe otra categoría con ese nombre."
        else:
            try:
                gain = float(gain_raw)
                if gain < 0 or gain > 3:
                    raise ValueError()
            except ValueError:
                error = "Ganancia diaria inválida (0.0 – 3.0)."
        if not error:
            c.name = new_name
            c.daily_gain_kg = gain
            db.session.commit()
            flash("Categoría actualizada.", "success")
            return redirect(url_for("categories"))

    content = SHELL_HTML_HEAD + """
    """ + FLASHES_HTML + """
    <div class="grid"><div class="card">
      <h1>Editar categoría</h1>
      {% if error %}<div class="flash error">{{ error }}</div>{% endif %}
      <form method="post" class="row">
        <input type="text" name="name" value="{{ c.name }}" maxlength="30" required>
        <input type="number" step="0.1" min="0" max="3" name="daily_gain_kg" value="{{ '%.1f' % (c.daily_gain_kg or 0.0) }}" required>
        <button class="btn btn-primary" type="submit">Guardar</button>
        <a class="btn btn-ghost" href="{{ url_for('categories') }}">Volver</a>
      </form>
    </div></div>
    """ + SHELL_HTML_FOOT
    return render_template_string(content, c=c, error=error, title="Editar categoría")

# -------------------------
# ANIMALES (ABM)
# -------------------------
def _validate_and_collect_animal_form(for_edit=False, current_category=None):
    tag_current = clean_tag(request.form.get("tag_current"))
    tag_previous = clean_tag(request.form.get("tag_previous")) if request.form.get("tag_previous") else None
    if not tag_current:
        return None, "La caravana (actual) es obligatoria y solo admite dígitos y espacios."

    weight = parse_weight_1d(request.form.get("weight"))
    est_weight_today = parse_weight_1d(request.form.get("est_weight_today"))

    weigh_date = parse_date_ddmmyy(request.form.get("weigh_date"))
    read_date = parse_date_ddmmyy(request.form.get("read_date"))
    last_seen = parse_date_ddmmyy(request.form.get("last_seen"))
    birth_date = parse_date_ddmmyy(request.form.get("birth_date"))
    if request.form.get("weigh_date") and not weigh_date: return None, "Fecha de pesaje inválida (DD/MM/AA)."
    if request.form.get("read_date") and not read_date: return None, "Fecha de lectura inválida (DD/MM/AA)."
    if request.form.get("last_seen") and not last_seen: return None, "Última vez inválida (DD/MM/AA)."
    if request.form.get("birth_date") and not birth_date: return None, "Fecha de nacimiento inválida (DD/MM/AA)."

    comment = limit_len(request.form.get("comment"), 30)
    origin = limit_len(request.form.get("origin"), 30)
    diagnosis = limit_len(request.form.get("diagnosis"), 10)
    lot = limit_len(request.form.get("lot"), 20)

    sex = (request.form.get("sex") or "").strip().upper() or None
    sex = sex if sex in ("M", "H") else None

    # Validación de categoría (activa). En edición, permitir mantener una inactiva existente.
    cat = (request.form.get("category") or "").strip()
    actives = set(active_category_names())
    allcats = set(all_category_names())
    if cat:
        if cat not in actives:
            if for_edit and current_category and cat == current_category and cat in allcats:
                pass
            else:
                return None, "Categoría inválida."
    else:
        cat = None

    breed = (request.form.get("breed") or "").strip()
    if breed and breed not in BREED_OPTIONS:
        return None, "Raza inválida."
    breed = breed or None

    return {
        "tag_current": tag_current,
        "tag_previous": tag_previous,
        "weight": weight,
        "weigh_date": weigh_date,
        "est_weight_today": est_weight_today,
        "comment": comment,
        "origin": origin,
        "category": cat,
        "read_date": read_date,
        "last_seen": last_seen,
        "birth_date": birth_date,
        "sex": sex,
        "breed": breed,
        "diagnosis": diagnosis,
        "lot": lot,
    }, None

@app.route("/animals")
@login_required
def animals():
    q = (request.args.get("q") or "").strip().lower()
    lot = (request.args.get("lot") or "").strip().lower()
    breed = (request.args.get("breed") or "").strip().lower()
    origin = (request.args.get("origin") or "").strip().lower()
    category = (request.args.get("category") or "").strip().lower()

    query = Animal.query
    if q:
        like = f"%{q}%"
        query = query.filter(
            db.or_(Animal.tag_current.ilike(like),
                   Animal.tag_previous.ilike(like),
                   Animal.diagnosis.ilike(like),
                   Animal.comment.ilike(like))
        )
    if lot:
        query = query.filter(Animal.lot.ilike(f"%{lot}%"))
    if breed:
        query = query.filter(Animal.breed.ilike(f"%{breed}%"))
    if origin:
        query = query.filter(Animal.origin.ilike(f"%{origin}%"))
    if category:
        query = query.filter(Animal.category.ilike(f"%{category}%"))

    animals = query.order_by(Animal.id.desc()).all()

    content = SHELL_HTML_HEAD + """
    """ + FLASHES_HTML + """
    <div class="grid"><div class="card">
      <div class="row" style="justify-content:space-between; align-items:center;">
        <div><h1>Animales</h1><p class="lead">Base de datos de bovinos.</p></div>
        <a class="btn btn-primary" href="{{ url_for('animals_new') }}">➕ Nuevo animal</a>
      </div>

      <form method="get" class="row" style="margin-top:8px;">
        <input type="search" name="q" placeholder="Buscar por caravana / comentario / diagnóstico" value="{{ request.args.get('q','') }}">
        <input type="text" name="lot" placeholder="Lote" value="{{ request.args.get('lot','') }}">
        <input type="text" name="breed" placeholder="Raza" value="{{ request.args.get('breed','') }}">
        <input type="text" name="origin" placeholder="Origen" value="{{ request.args.get('origin','') }}">
        <input type="text" name="category" placeholder="Categoría" value="{{ request.args.get('category','') }}">
        <button class="btn btn-muted" type="submit">Filtrar</button>
        <a class="btn btn-ghost" href="{{ url_for('animals') }}">Limpiar</a>
      </form>

      <div class="grid" style="overflow:auto;">
        <table>
          <thead>
            <tr>
              <th>ID</th><th>Caravana</th><th>Peso (kg)</th><th>Fecha pesaje</th><th>Estimado hoy</th>
              <th>Sexo</th><th>Raza</th><th>Lote</th><th>Origen</th><th>Categoría</th>
              <th class="nowrap">Últ. vez</th><th class="nowrap">F. lectura</th><th>Diagnóstico</th><th>Comentario</th>
              <th class="nowrap">Acciones</th>
            </tr>
          </thead>
          <tbody>
            {% for a in animals %}
            <tr>
              <td>{{ a.id }}</td>
              <td>
                <div><strong>{{ a.tag_current }}</strong></div>
                {% if a.tag_previous %}<div class="muted">Ant.: {{ a.tag_previous }}</div>{% endif %}
              </td>
              <td>{{ a.weight if a.weight is not none else '' }}</td>
              <td>{{ fmt_date(a.weigh_date) }}</td>
              <td>{{ a.est_weight_today if a.est_weight_today is not none else (a.compute_estimated_weight(get_gain(a.category)) or '') }}</td>
              <td>{{ 'M' if a.sex=='M' else 'H' if a.sex=='H' else '' }}</td>
              <td>{{ a.breed or '' }}</td>
              <td>{{ a.lot or '' }}</td>
              <td>{{ a.origin or '' }}</td>
              <td>{{ a.category or '' }}</td>
              <td>{{ fmt_date(a.last_seen) }}</td>
              <td>{{ fmt_date(a.read_date) }}</td>
              <td>{{ a.diagnosis or '' }}</td>
              <td>{{ a.comment or '' }}</td>
              <td class="nowrap">
                <a href="{{ url_for('animals_edit', animal_id=a.id) }}">Editar</a>
                {% if current_user.is_admin %}· <a href="{{ url_for('animals_delete', animal_id=a.id) }}" onclick="return confirm('¿Eliminar animal?');" class="danger">Eliminar</a>{% endif %}
              </td>
            </tr>
            {% endfor %}
          </tbody>
        </table>
        <div class="links"><a href="{{ url_for('menu') }}">Volver al menú</a></div>
      </div>
    </div></div>
    """ + SHELL_HTML_FOOT
    return render_template_string(content, animals=animals, fmt_date=fmt_date, get_gain=get_gain, title="Animales")

@app.route("/animals/new", methods=["GET", "POST"])
@login_required
def animals_new():
    error = None
    if request.method == "POST":
        data, error = _validate_and_collect_animal_form()
        if not error and Animal.query.filter_by(tag_current=data["tag_current"]).first():
            error = "Ya existe un animal con esa caravana."
        if not error:
            a = Animal(**data)
            if a.est_weight_today is None:
                calc = a.compute_estimated_weight(get_gain(a.category))
                if calc is not None:
                    a.est_weight_today = calc
            db.session.add(a)
            db.session.commit()
            flash("Animal creado.", "success")
            return redirect(url_for("animals"))

    def category_options():
        ops = ['<option value="">Categoría</option>']
        for n in active_category_names():
            ops.append(f'<option value="{n}">{n}</option>')
        return "".join(ops)

    def breed_options():
        ops = ['<option value="">Raza</option>']
        for n in BREED_OPTIONS:
            ops.append(f'<option value="{n}">{n}</option>')
        return "".join(ops)

    content = SHELL_HTML_HEAD + """
    """ + FLASHES_HTML + """
    <div class="grid"><div class="card">
      <h1>Nuevo animal</h1>
      {% if error %}<div class="flash error">{{ error }}</div>{% endif %}
      <form method="post" class="grid">
        <div class="row">
          <input type="text" name="tag_current" placeholder="Caravana (actual) — solo dígitos y espacios" required>
          <input type="text" name="tag_previous" placeholder="Caravana anterior (opcional)">
        </div>

        <div class="row">
          <input type="text" name="weight" placeholder="Peso (kg) ej: 750.3" maxlength="6">
          <input type="text" name="weigh_date" placeholder="Fecha de pesaje (DD/MM/AA)" maxlength="8">
          <input type="text" name="est_weight_today" placeholder="Peso estimado hoy (kg)" maxlength="6">
        </div>

        <div class="row">
          <select name="sex">
            <option value="">Sexo</option>
            <option value="M">Macho (M)</option>
            <option value="H">Hembra (H)</option>
          </select>
          <select name="breed">
            """ + breed_options() + """
          </select>
          <input type="text" name="lot" placeholder="Lote (máx 20)" maxlength="20">
        </div>

        <div class="row">
          <input type="text" name="origin" placeholder="Origen (máx 30)" maxlength="30">
          <select name="category">
            """ + category_options() + """
          </select>
        </div>

        <div class="row">
          <input type="text" name="read_date" placeholder="Fecha de lectura (DD/MM/AA)" maxlength="8">
          <input type="text" name="last_seen" placeholder="Última vez (DD/MM/AA)" maxlength="8">
          <input type="text" name="birth_date" placeholder="Fecha de nacimiento (DD/MM/AA)" maxlength="8">
        </div>

        <input type="text" name="diagnosis" placeholder="Diagnóstico (máx 10)" maxlength="10">
        <input type="text" name="comment" placeholder="Comentario (máx 30)" maxlength="30">

        <div class="row">
          <button class="btn btn-primary" type="submit">Guardar</button>
          <a class="btn btn-ghost" href="{{ url_for('animals') }}">Cancelar</a>
        </div>
      </form>
    </div></div>
    """ + SHELL_HTML_FOOT
    return render_template_string(content, error=error, title="Nuevo animal")

@app.route("/animals/<int:animal_id>/edit", methods=["GET", "POST"])
@login_required
def animals_edit(animal_id):
    a = Animal.query.get_or_404(animal_id)
    error = None

    if request.method == "POST":
        data, error = _validate_and_collect_animal_form(for_edit=True, current_category=a.category)
        if not error:
            other = Animal.query.filter(Animal.tag_current == data["tag_current"], Animal.id != a.id).first()
            if other:
                error = "Ya existe otro animal con esa caravana."
        if not error:
            for k, v in data.items():
                setattr(a, k, v)
            if a.est_weight_today is None:
                calc = a.compute_estimated_weight(get_gain(a.category))
                a.est_weight_today = calc if calc is not None else a.est_weight_today
            db.session.commit()
            flash("Animal actualizado.", "success")
            return redirect(url_for("animals"))

    def category_options_with_current(current):
        ops = ['<option value="">(sin seleccionar)</option>']
        actives = active_category_names()
        showed_current = False
        for n in actives:
            sel = ' selected' if (current or '') == n else ''
            if sel: showed_current = True
            ops.append(f'<option value="{n}"{sel}>{n}</option>')
        if current and not showed_current:
            ops.append(f'<option value="{current}" selected>{current} (inactiva)</option>')
        return "".join(ops)

    def breed_options_with_current(current):
        ops = ['<option value="">(sin seleccionar)</option>']
        for n in BREED_OPTIONS:
            sel = ' selected' if (current or '') == n else ''
            ops.append(f'<option value="{n}"{sel}>{n}</option>')
        return "".join(ops)

    content = SHELL_HTML_HEAD + """
    """ + FLASHES_HTML + """
    <div class="grid"><div class="card">
      <h1>Editar animal</h1>
      {% if error %}<div class="flash error">{{ error }}</div>{% endif %}
      <form method="post" class="grid">
        <div class="row">
          <input type="text" name="tag_current" placeholder="Caravana (actual)" value="{{ a.tag_current }}" required>
          <input type="text" name="tag_previous" placeholder="Caravana anterior" value="{{ a.tag_previous or '' }}">
        </div>

        <div class="row">
          <input type="text" name="weight" placeholder="Peso (kg)" value="{{ a.weight if a.weight is not none else '' }}" maxlength="6">
          <input type="text" name="weigh_date" placeholder="Fecha de pesaje (DD/MM/AA)" value="{{ fmt_date(a.weigh_date) }}" maxlength="8">
          <input type="text" name="est_weight_today" placeholder="Peso estimado hoy (kg)" value="{{ a.est_weight_today if a.est_weight_today is not none else (a.compute_estimated_weight(get_gain(a.category)) or '') }}" maxlength="6">
        </div>

        <div class="row">
          <select name="sex">
            <option value="">Sexo</option>
            <option value="M" {% if a.sex=='M' %}selected{% endif %}>Macho (M)</option>
            <option value="H" {% if a.sex=='H' %}selected{% endif %}>Hembra (H)</option>
          </select>
          <select name="breed">
            """ + breed_options_with_current("{{ a.breed or '' }}") + """
          </select>
          <input type="text" name="lot" placeholder="Lote" value="{{ a.lot or '' }}" maxlength="20">
        </div>

        <div class="row">
          <input type="text" name="origin" placeholder="Origen" value="{{ a.origin or '' }}" maxlength="30">
          <select name="category">
            """ + category_options_with_current("{{ a.category or '' }}") + """
          </select>
        </div>

        <div class="row">
          <input type="text" name="read_date" placeholder="Fecha de lectura (DD/MM/AA)" value="{{ fmt_date(a.read_date) }}" maxlength="8">
          <input type="text" name="last_seen" placeholder="Última vez (DD/MM/AA)" value="{{ fmt_date(a.last_seen) }}" maxlength="8">
          <input type="text" name="birth_date" placeholder="Fecha de nacimiento (DD/MM/AA)" value="{{ fmt_date(a.birth_date) }}" maxlength="8">
        </div>

        <input type="text" name="diagnosis" placeholder="Diagnóstico (máx 10)" value="{{ a.diagnosis or '' }}" maxlength="10">
        <input type="text" name="comment" placeholder="Comentario (máx 30)" value="{{ a.comment or '' }}" maxlength="30">

        <div class="row">
          <button class="btn btn-primary" type="submit">Guardar</button>
          <a class="btn btn-ghost" href="{{ url_for('animals') }}">Volver</a>
        </div>
      </form>
    </div></div>
    """ + SHELL_HTML_FOOT
    return render_template_string(content, a=a, error=error, fmt_date=fmt_date, get_gain=get_gain, title="Editar animal")

@app.route("/animals/<int:animal_id>/delete")
@login_required
def animals_delete(animal_id):
    if not require_admin():
        return redirect(url_for("animals"))
    a = Animal.query.get_or_404(animal_id)
    db.session.delete(a)
    db.session.commit()
    flash("Animal eliminado.", "success")
    return redirect(url_for("animals"))

# -------------------------
# Usuarios (solo admin)
# -------------------------
@app.route("/users")
@login_required
def list_users():
    if not require_admin(): return redirect(url_for("menu"))
    users = User.query.order_by(User.id.asc()).all()
    content = SHELL_HTML_HEAD + """
    """ + FLASHES_HTML + """
    <div class="grid"><div class="card">
      <h1>Usuarios</h1>
      <p><a class="btn btn-primary" href="{{ url_for('new_user') }}">➕ Crear usuario</a> · <a class="btn btn-ghost" href="{{ url_for('menu') }}">Volver</a></p>
      <table>
        <thead><tr><th>ID</th><th>Email</th><th>Admin</th><th>Activo</th><th>Acciones</th></tr></thead>
        <tbody>
          {% for u in users %}
          <tr>
            <td>{{ u.id }}</td><td>{{ u.email }}</td>
            <td>{{ "Sí" if u.is_admin else "No" }}</td><td>{{ "Sí" if u.is_active_flag else "No" }}</td>
            <td><a href="{{ url_for('edit_user', user_id=u.id) }}">Editar</a></td>
          </tr>
          {% endfor %}
        </tbody>
      </table>
    </div></div>
    """ + SHELL_HTML_FOOT
    return render_template_string(content, users=users, title="Usuarios")

@app.route("/users/new", methods=["GET", "POST"])
@login_required
def new_user():
    if not require_admin(): return redirect(url_for("menu"))
    error = None
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""
        is_admin = "is_admin" in request.form
        if not email or not password:
            error = "Email y contraseña son obligatorios."
        elif User.query.filter_by(email=email).first():
            error = "Ese email ya existe."
        else:
            u = User(email=email, is_admin=is_admin, is_active_flag=True)
            u.set_password(password)
            db.session.add(u); db.session.commit()
            flash("Usuario creado.", "success")
            return redirect(url_for("list_users"))
    content = SHELL_HTML_HEAD + """
    """ + FLASHES_HTML + """
    <div class="grid"><div class="card">
      <h1>Nuevo usuario</h1>
      {% if error %}<div class="flash error">{{ error }}</div>{% endif %}
      <form method="post" class="grid">
        <input type="email" name="email" placeholder="Email" required>
        <div class="row">
          <input type="password" name="password" placeholder="Contraseña" required>
          <label><input type="checkbox" name="is_admin"> Es administrador</label>
        </div>
        <div class="row">
          <button class="btn btn-primary" type="submit">Crear</button>
          <a class="btn btn-ghost" href="{{ url_for('list_users') }}">Volver</a>
        </div>
      </form>
    </div></div>
    """ + SHELL_HTML_FOOT
    return render_template_string(content, error=error, title="Nuevo usuario")

@app.route("/users/<int:user_id>/edit", methods=["GET", "POST"])
@login_required
def edit_user(user_id):
    if not require_admin(): return redirect(url_for("menu"))
    u = User.query.get_or_404(user_id)
    error = None
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        is_admin = "is_admin" in request.form
        is_active = "is_active" in request.form
        pw = request.form.get("password") or ""
        if not email:
            error = "Email es obligatorio."
        else:
            other = User.query.filter(User.email == email, User.id != u.id).first()
            if other:
                error = "Ese email ya está en uso por otro usuario."
        if not error:
            u.email = email; u.is_admin = is_admin; u.is_active_flag = is_active
            if pw: u.set_password(pw)
            db.session.commit()
            flash("Usuario actualizado.", "success")
            return redirect(url_for("list_users"))
    content = SHELL_HTML_HEAD + """
    """ + FLASHES_HTML + """
    <div class="grid"><div class="card">
      <h1>Editar usuario</h1>
      {% if error %}<div class="flash error">{{ error }}</div>{% endif %}
      <form method="post" class="grid">
        <input type="email" name="email" placeholder="Email" value="{{ u.email }}">
        <div class="row">
          <label><input type="checkbox" name="is_admin" {% if u.is_admin %}checked{% endif %}> Es administrador</label>
          <label><input type="checkbox" name="is_active" {% if u.is_active_flag %}checked{% endif %}> Activo</label>
        </div>
        <input type="password" name="password" placeholder="Nueva contraseña (opcional)">
        <div class="row">
          <button class="btn btn-primary" type="submit">Guardar</button>
          <a class="btn btn-ghost" href="{{ url_for('list_users') }}">Volver</a>
        </div>
      </form>
    </div></div>
    """ + SHELL_HTML_FOOT
    return render_template_string(content, u=u, error=error, title="Editar usuario")

# -------------------------
# Caja (placeholders)
# -------------------------
@app.route("/movimientos")
@login_required
def movimientos():
    content = SHELL_HTML_HEAD + """
    """ + FLASHES_HTML + """
    <div class="grid"><div class="card">
      <h1>Movimientos de Caja</h1>
      <p class="lead">Aquí irá el módulo de movimientos.</p>
      <a class="btn btn-ghost" href="{{ url_for('menu') }}">Volver al menú</a>
    </div></div>
    """ + SHELL_HTML_FOOT
    return render_template_string(content, title="Movimientos de Caja")

@app.route("/resumen")
@login_required
def resumen():
    content = SHELL_HTML_HEAD + """
    """ + FLASHES_HTML + """
    <div class="grid"><div class="card">
      <h1>Resumen de Caja</h1>
      <p class="lead">Aquí irá el módulo de resumen.</p>
      <a class="btn btn-ghost" href="{{ url_for('menu') }}">Volver al menú</a>
    </div></div>
    """ + SHELL_HTML_FOOT
    return render_template_string(content, title="Resumen de Caja")

# -------------------------
# Main (solo local)
# -------------------------
if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)