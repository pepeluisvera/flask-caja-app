from flask import Flask, render_template_string, request, redirect, url_for, flash
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
import os

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
# Modelo de usuario
# -------------------------
class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=True)  # <- nullable para setup inicial
    is_admin = db.Column(db.Boolean, default=False)
    is_active_flag = db.Column(db.Boolean, default=True)

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

# --- Bootstrap DB al importar el módulo (sirve con gunicorn/render) ---
with app.app_context():
    db.create_all()
    # Si no existe admin, creamos placeholder para que /setup_admin lo configure
    admin = User.query.filter_by(is_admin=True).order_by(User.id.asc()).first()
    if not admin:
        admin = User(email="admin@local", is_admin=True, is_active_flag=True, password_hash=None)
        db.session.add(admin)
        db.session.commit()

# -------------------------
# Helpers
# -------------------------
def require_admin():
    if not (current_user.is_authenticated and current_user.is_admin):
        flash("Se requiere usuario administrador.", "error")
        return False
    return True

def admin_needs_password_setup():
    admin = User.query.filter_by(is_admin=True).order_by(User.id.asc()).first()
    return (admin is None) or (not admin.password_hash)

# -------------------------
# Templates embebidos
# -------------------------
LOGIN_HTML = """
<!doctype html>
<html><head><meta charset="utf-8"><title>Login</title>
<style>
  body { font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif; max-width: 720px; margin: 40px auto; padding: 0 16px; }
  .card { border:1px solid #ddd; border-radius:12px; padding:16px; }
  input[type=email], input[type=password]{ width:100%; padding:10px; margin:8px 0 12px; border:1px solid #ccc; border-radius:8px; }
  button { padding:10px 14px; border:0; border-radius:10px; cursor:pointer; background:#2563eb; color:#fff; }
  .error { color:#b91c1c; }
  a { color:#2563eb; text-decoration:none; }
</style>
</head>
<body>
  <h1>Ingreso</h1>
  <div class="card">
    {% if error %}<p class="error">{{ error }}</p>{% endif %}
    <form method="post">
      <input type="email" name="email" placeholder="Correo">
      <input type="password" name="password" placeholder="Contraseña">
      <button type="submit">Ingresar</button>
    </form>
    {% if show_setup_link %}
      <p>¿Administrador sin configurar? <a href="{{ url_for('setup_admin') }}">Configurar admin</a></p>
    {% endif %}
  </div>
</body></html>
"""

# -------------------------
# Rutas principales / auth
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
    # Permitido solo si el admin aún no tiene contraseña
    admin = User.query.filter_by(is_admin=True).order_by(User.id.asc()).first()
    if admin and admin.password_hash:
        return redirect(url_for("login"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        if not email or not password:
            flash("Email y contraseña son obligatorios.", "error")
        else:
            if not admin:
                admin = User(email=email, is_admin=True, is_active_flag=True)
            admin.email = email
            admin.set_password(password)
            db.session.add(admin)
            db.session.commit()
            flash("Administrador configurado correctamente. Iniciá sesión.", "success")
            return redirect(url_for("login"))

    return render_template_string("""
        <h2>Configurar Administrador</h2>
        <form method="post">
            Email: <input type="email" name="email" required><br>
            Contraseña: <input type="password" name="password" required><br>
            <button type="submit">Crear/Actualizar Admin</button>
        </form>
        <p><a href="{{ url_for('login') }}">Volver al login</a></p>
    """)

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
            return redirect(url_for("menu"))
        else:
            error = "Credenciales inválidas o usuario inactivo."

    return render_template_string(LOGIN_HTML, error=error, show_setup_link=admin_needs_password_setup())

@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))

# -------------------------
# Menú principal
# -------------------------
@app.route("/menu")
@login_required
def menu():
    return render_template_string("""
        <h1>Menú principal</h1>
        <p style="color: green;">Autenticado correctamente.</p>
        <ul>
            <li><a href="{{ url_for('movimientos') }}">Movimientos de Caja</a></li>
            <li><a href="{{ url_for('resumen') }}">Resumen de Caja</a></li>
            {% if current_user.is_authenticated and current_user.is_admin %}
                <li><a href="{{ url_for('list_users') }}">Administración de usuarios</a></li>
            {% endif %}
        </ul>
        <p>Usuario: {{ current_user.email }} {% if current_user.is_admin %}(Admin){% endif %} | 
           <a href="{{ url_for('logout') }}">Salir</a></p>
    """)

# -------------------------
# ABM de Usuarios (solo admin)
# -------------------------
@app.route("/users")
@login_required
def list_users():
    if not require_admin(): 
        return redirect(url_for("menu"))
    users = User.query.order_by(User.id.asc()).all()
    return render_template_string("""
        <h2>Usuarios</h2>
        <a href="{{ url_for('new_user') }}">Nuevo usuario</a>
        <ul>
            {% for u in users %}
                <li>{{ u.email }}
                    {% if u.is_admin %}(Admin){% endif %}
                    - <a href="{{ url_for('edit_user', user_id=u.id) }}">Editar</a>
                    - <a href="{{ url_for('toggle_user', user_id=u.id) }}">
                        {% if u.is_active %}Desactivar{% else %}Activar{% endif %}
                      </a>
                    - <a href="{{ url_for('delete_user', user_id=u.id) }}">Eliminar</a>
                </li>
            {% endfor %}
        </ul>
        <a href="{{ url_for('menu') }}">Volver</a>
    """, users=users)

@app.route("/users/new", methods=["GET", "POST"])
@login_required
def new_user():
    if not require_admin(): 
        return redirect(url_for("menu"))
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        is_admin = "is_admin" in request.form
        if not email or not password:
            flash("Email y contraseña son obligatorios.", "error")
        elif User.query.filter_by(email=email).first():
            flash("Ese email ya existe.", "error")
        else:
            user = User(email=email, is_admin=is_admin, is_active_flag=True)
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            flash("Usuario creado.", "success")
            return redirect(url_for("list_users"))
    return render_template_string("""
        <h2>Nuevo usuario</h2>
        <form method="post">
            Email: <input type="email" name="email" required><br>
            Contraseña: <input type="password" name="password" required><br>
            Admin: <input type="checkbox" name="is_admin"><br>
            <button type="submit">Guardar</button>
        </form>
        <a href="{{ url_for('list_users') }}">Volver</a>
    """)

@app.route("/users/<int:user_id>/edit", methods=["GET", "POST"])
@login_required
def edit_user(user_id):
    if not require_admin(): 
        return redirect(url_for("menu"))
    user = User.query.get_or_404(user_id)
    if request.method == "POST":
        new_email = request.form.get("email", "").strip().lower()
        user.is_admin = "is_admin" in request.form
        if new_email:
            other = User.query.filter(User.email == new_email, User.id != user.id).first()
            if other:
                flash("Ese email ya está en uso.", "error")
                return redirect(url_for("edit_user", user_id=user.id))
            user.email = new_email
        if request.form.get("password"):
            user.set_password(request.form.get("password"))
        db.session.commit()
        flash("Usuario actualizado.", "success")
        return redirect(url_for("list_users"))
    return render_template_string("""
        <h2>Editar usuario</h2>
        <form method="post">
            Email: <input type="email" name="email" value="{{ user.email }}"><br>
            Contraseña: <input type="password" name="password" placeholder="Dejar en blanco si no cambia"><br>
            Admin: <input type="checkbox" name="is_admin" {% if user.is_admin %}checked{% endif %}><br>
            <button type="submit">Actualizar</button>
        </form>
        <a href="{{ url_for('list_users') }}">Volver</a>
    """, user=user)

@app.route("/users/<int:user_id>/toggle")
@login_required
def toggle_user(user_id):
    if not require_admin(): 
        return redirect(url_for("menu"))
    user = User.query.get_or_404(user_id)
    user.is_active_flag = not user.is_active_flag
    db.session.commit()
    return redirect(url_for("list_users"))

@app.route("/users/<int:user_id>/delete")
@login_required
def delete_user(user_id):
    if not require_admin(): 
        return redirect(url_for("menu"))
    user = User.query.get_or_404(user_id)
    if user.id == current_user.id:
        flash("No puedes eliminarte a ti mismo.", "error")
    else:
        db.session.delete(user)
        db.session.commit()
        flash("Usuario eliminado.", "success")
    return redirect(url_for("list_users"))

# -------------------------
# Vistas de caja (placeholders)
# -------------------------
@app.route("/movimientos")
@login_required
def movimientos():
    return "<h2>Movimientos de Caja</h2>"

@app.route("/resumen")
@login_required
def resumen():
    return "<h2>Resumen de Caja</h2>"

# -------------------------
# Main (solo para correr local)
# -------------------------
if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)