from flask import Flask, render_template_string, request, redirect, url_for, flash
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
import os

# ----------------------------------------------------------------------------
# Config
# ----------------------------------------------------------------------------
app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "cambia_esto_en_produccion")
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL", "sqlite:///app.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = "login"

# ----------------------------------------------------------------------------
# Modelo de usuario
# ----------------------------------------------------------------------------
class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=True)
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

# ----------------------------------------------------------------------------
# Bootstrap inicial (Flask 3 compatible)
# ----------------------------------------------------------------------------
with app.app_context():
    db.create_all()
    if User.query.count() == 0:
        admin = User(email="admin@local", is_admin=True, is_active_flag=True, password_hash=None)
        db.session.add(admin)
        db.session.commit()

# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------
def require_admin():
    if not (current_user.is_authenticated and current_user.is_admin):
        flash("Se requiere usuario administrador.", "error")
        return False
    return True

def admin_needs_password_setup():
    admin = User.query.filter_by(is_admin=True).order_by(User.id.asc()).first()
    return admin is not None and (admin.password_hash is None or admin.password_hash == "")

# ----------------------------------------------------------------------------
# Rutas principales
# ----------------------------------------------------------------------------
@app.route("/")
def index():
    if admin_needs_password_setup():
        return redirect(url_for("setup_admin"))
    if current_user.is_authenticated:
        return redirect(url_for("menu"))
    return redirect(url_for("login"))

@app.route("/login", methods=["GET", "POST"])
def login():
    if admin_needs_password_setup():
        return redirect(url_for("setup_admin"))
    error = None
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = User.query.filter_by(email=email).first()
        if user and user.is_active_flag and user.check_password(password):
            login_user(user)
            flash("Autenticado correctamente.", "ok")
            return redirect(url_for("menu"))
        else:
            error = "Credenciales inválidas o usuario inactivo."
    return render_template_string(LOGIN_HTML, error=error, show_setup_link=admin_needs_password_setup())

@app.route("/setup_admin", methods=["GET", "POST"])
def setup_admin():
    admin = User.query.filter_by(is_admin=True).order_by(User.id.asc()).first()
    if not admin or (admin.password_hash not in (None, "")):
        return redirect(url_for("index"))
    error = None
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        p1 = request.form.get("password", "")
        p2 = request.form.get("password2", "")
        if not email or not p1:
            error = "Completá email y contraseña."
        elif p1 != p2:
            error = "Las contraseñas no coinciden."
        else:
            admin.email = email
            admin.set_password(p1)
            db.session.commit()
            flash("Administrador configurado. Iniciá sesión.", "ok")
            return redirect(url_for("login"))
    return render_template_string(SETUP_ADMIN_HTML, error=error, default_email=admin.email)

@app.route("/menu")
@login_required
def menu():
    return render_template_string(MENU_HTML, email=current_user.email, is_admin=current_user.is_admin)

@app.route("/movimientos")
@login_required
def movimientos():
    return "<h2>Movimientos de Caja</h2><p>Aquí irá el módulo de movimientos.</p>"

@app.route("/resumen")
@login_required
def resumen():
    return "<h2>Resumen de Caja</h2><p>Aquí irá el módulo de resumen de caja.</p>"

@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))

# ----------------------------------------------------------------------------
# ABM Usuarios (RESTABLECIDO)
# ----------------------------------------------------------------------------
@app.route("/users")
@login_required
def users():
    if not require_admin():
        return redirect(url_for("menu"))
    q = request.args.get("q", "").strip().lower()
    users = User.query.order_by(User.id.asc()).all()
    if q:
        users = [u for u in users if q in (u.email or "").lower()]
    return render_template_string(USERS_LIST_HTML, users=users, q=q, email=current_user.email)

@app.route("/users/create", methods=["GET", "POST"])
@login_required
def users_create():
    if not require_admin():
        return redirect(url_for("menu"))
    error = None
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        is_admin = request.form.get("is_admin") == "on"
        if not email or not password:
            error = "Email y contraseña son obligatorios."
        elif User.query.filter_by(email=email).first():
            error = "Ese email ya existe."
        else:
            u = User(email=email, is_admin=is_admin, is_active_flag=True)
            u.set_password(password)
            db.session.add(u)
            db.session.commit()
            flash("Usuario creado.", "ok")
            return redirect(url_for("users"))
    return render_template_string(USERS_CREATE_HTML, error=error)

@app.route("/users/<int:user_id>/edit", methods=["GET", "POST"])
@login_required
def users_edit(user_id):
    if not require_admin():
        return redirect(url_for("menu"))
    u = User.query.get_or_404(user_id)
    error = None
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        is_admin = request.form.get("is_admin") == "on"
        is_active = request.form.get("is_active") == "on"
        if not email:
            error = "Email es obligatorio."
        else:
            other = User.query.filter(User.email == email, User.id != u.id).first()
            if other:
                error = "Ese email ya está en uso por otro usuario."
            else:
                u.email = email
                u.is_admin = is_admin
                u.is_active_flag = is_active
                db.session.commit()
                flash("Usuario actualizado.", "ok")
                return redirect(url_for("users"))
    return render_template_string(USERS_EDIT_HTML, u=u, error=error)

@app.route("/users/<int:user_id>/reset_password", methods=["POST"])
@login_required
def users_reset_password(user_id):
    if not require_admin():
        return redirect(url_for("menu"))
    u = User.query.get_or_404(user_id)
    new_pass = request.form.get("new_password", "")
    if not new_pass:
        flash("Nueva contraseña requerida.", "error")
    else:
        u.set_password(new_pass)
        db.session.commit()
        flash("Contraseña restablecida.", "ok")
    return redirect(url_for("users_edit", user_id=user_id))

@app.route("/users/<int:user_id>/delete", methods=["POST"])
@login_required
def users_delete(user_id):
    if not require_admin():
        return redirect(url_for("menu"))
    u = User.query.get_or_404(user_id)
    if u.id == current_user.id:
        flash("No podés eliminarte a vos mismo.", "error")
        return redirect(url_for("users"))
    db.session.delete(u)
    db.session.commit()
    flash("Usuario eliminado.", "ok")
    return redirect(url_for("users"))

# ----------------------------------------------------------------------------
# Templates
# ----------------------------------------------------------------------------
BASE_CSS = """
<style>
  body { font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif; max-width: 880px; margin: 32px auto; padding: 0 16px; }
  header { display:flex; justify-content: space-between; align-items:center; margin-bottom: 16px; }
  .card { border:1px solid #ddd; border-radius:12px; padding:16px; margin: 12px 0; }
  input[type=text], input[type=email], input[type=password], input[type=search] { width:100%; padding:10px; margin:6px 0 12px; border:1px solid #ccc; border-radius:8px; }
  button { padding:10px 14px; border:0; border-radius:10px; cursor:pointer; }
  .primary { background:#2563eb; color:white; }
  .muted { background:#f3f4f6; }
  .danger { background:#b91c1c; color:white; }
  .success { color:#065f46; }
  .error { color:#b91c1c; }
  table { width:100%; border-collapse: collapse; }
  th, td { border-bottom:1px solid #eee; text-align:left; padding:8px; }
  .row { display:flex; gap:12px; }
  .row > * { flex:1; }
  .right { text-align:right; }
  a { color:#2563eb; text-decoration:none; }
</style>
"""

FLASHES_HTML = """
{% with msgs = get_flashed_messages(with_categories=true) %}
  {% if msgs %}
    <div class="card">
      {% for cat, msg in msgs %}
        <p class="{{ 'success' if cat=='ok' else 'error' if cat=='error' else '' }}">{{ msg }}</p>
      {% endfor %}
    </div>
  {% endif %}
{% endwith %}
"""

LOGIN_HTML = """<!doctype html>
<html><head><meta charset="utf-8"><title>Login</title>""" + BASE_CSS + """</head>
<body>
  <header><h1>Ingreso</h1></header>
  """ + FLASHES_HTML + """
  <div class="card">
    {% if error %}<p class="error">{{ error }}</p>{% endif %}
    <form method="post">
      <input type="email" name="email" placeholder="Correo">
      <input type="password" name="password" placeholder="Contraseña">
      <button type="submit" class="primary">Ingresar</button>
    </form>
    {% if show_setup_link %}
      <p>¿Administrador sin configurar? <a href="{{ url_for('setup_admin') }}">Configurar admin</a></p>
    {% endif %}
  </div>
</body></html>
"""

SETUP_ADMIN_HTML = """<!doctype html>
<html><head><meta charset="utf-8"><title>Configurar administrador</title>""" + BASE_CSS + """</head>
<body>
  <header><h1>Primer uso: configurar Administrador</h1></header>
  """ + FLASHES_HTML + """
  <div class="card">
    <p>Definí el <strong>email</strong> y la <strong>contraseña inicial</strong> del Administrador.</p>
    {% if error %}<p class="error">{{ error }}</p>{% endif %}
    <form method="post">
      <input type="email" name="email" placeholder="Email admin" value="{{ default_email }}">
      <div class="row">
        <input type="password" name="password" placeholder="Contraseña">
        <input type="password" name="password2" placeholder="Repetir contraseña">
      </div>
      <button type="submit" class="primary">Guardar</button>
    </form>
  </div>
</body></html>
"""

MENU_HTML = """<!doctype html>
<html><head><meta charset="utf-8"><title>Menú principal</title>""" + BASE_CSS + """</head>
<body>
  <header>
    <h1>Menú principal</h1>
    <div>
      <span>Usuario: {{ email }} {% if is_admin %}(Admin){% endif %}</span> | 
      <a href="{{ url_for('logout') }}">Salir</a>
    </div>
  </header>
  """ + FLASHES_HTML + """
  <div class="card">
    <ul>
      <li><a href="{{ url_for('movimientos') }}">Movimientos de Caja</a></li>
      <li><a href="{{ url_for('resumen') }}">Resumen de Caja</a></li>
      {% if is_admin %}
        <li><a href="{{ url_for('users') }}">Administración de usuarios</a></li>
      {% endif %}
    </ul>
  </div>
</body></html>
"""

USERS_LIST_HTML = """<!doctype html>
<html><head><meta charset="utf-8"><title>Usuarios</title>""" + BASE_CSS + """</head>
<body>
  <header>
    <h1>Administración de usuarios</h1>
    <div>
      <span>Admin: {{ email }}</span> | <a href="{{ url_for('logout') }}">Salir</a>
    </div>
  </header>
  """ + FLASHES_HTML + """
  <div class="card">
    <form method="get">
      <input type="search" name="q" placeholder="Buscar por email" value="{{ q }}">
    </form>
    <p>
      <a class="primary" href="{{ url_for('users_create') }}">➕ Crear usuario</a> |
      <a href="{{ url_for('menu') }}">Volver al menú</a>
    </p>
    <table>
      <thead><tr><th>ID</th><th>Email</th><th>Admin</th><th>Activo</th><th class="right">Acciones</th></tr></thead>
      <tbody>
        {% for u in users %}
        <tr>
          <td>{{ u.id }}</td>
          <td>{{ u.email }}</td>
          <td>{{ "Sí" if u.is_admin else "No" }}</td>
          <td>{{ "Sí" if u.is_active_flag else "No" }}</td>
          <td class="right">
            <a href="{{ url_for('users_edit', user_id=u.id) }}">Editar</a>
          </td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
  </div>
</body></html>
"""

USERS_CREATE_HTML = """<!doctype html>
<html><head><meta charset="utf-8"><title>Crear usuario</title>""" + BASE_CSS + """</head>
<body>
  <header><h1>Crear usuario</h1></header>
  """ + FLASHES_HTML + """
  <div class="card">
    {% if error %}<p class="error">{{ error }}</p>{% endif %}
    <form method="post">
      <input type="email" name="email" placeholder="Email">
      <div class="row">
        <input type="password" name="password" placeholder="Contraseña">
        <label style="display:flex;align-items:center;gap:8px;">
          <input type="checkbox" name="is_admin"> Es administrador
        </label>
      </div>
      <button type="submit" class="primary">Crear</button>
      <a class="muted" href="{{ url_for('users') }}">Cancelar</a>
    </form>
  </div>
</body></html>
"""

USERS_EDIT_HTML = """<!doctype html>
<html><head><meta charset="utf-8"><title>Editar usuario</title>""" + BASE_CSS + """</head>
<body>
  <header><h1>Editar usuario</h1></header>
  """ + FLASHES_HTML + """
  <div class="card">
    {% if error %}<p class="error">{{ error }}</p>{% endif %}
    <form method="post">
      <input type="email" name="email" placeholder="Email" value="{{ u.email }}">
      <div class="row">
        <label><input type="checkbox" name="is_admin" {% if u.is_admin %}checked{% endif %}> Es administrador</label>
        <label><input type="checkbox" name="is_active" {% if u.is_active_flag %}checked{% endif %}> Activo</label>
      </div>
      <div class="row">
        <button type="submit" class="primary">Guardar</button>
        <a class="muted" href="{{ url_for('users') }}">Volver</a>
      </div>
    </form>
  </div>

  <div class="card">
    <h3>Restablecer contraseña</h3>
    <form method="post" action="{{ url_for('users_reset_password', user_id=u.id) }}">
      <input type="password" name="new_password" placeholder="Nueva contraseña">
      <button type="submit">Restablecer</button>
    </form>
  </div>

  <div class="card">
    <h3>Eliminar usuario</h3>
    <form method="post" action="{{ url_for('users_delete', user_id=u.id) }}" onsubmit="return confirm('¿Seguro que quieres eliminar este usuario?');">
      <button type="submit" class="danger">Eliminar</button>
    </form>
  </div>
</body></html>
"""

if __name__ == "__main__":
    app.run(debug=True)