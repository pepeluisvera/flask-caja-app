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
    password_hash = db.Column(db.String(255), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    is_active_flag = db.Column(db.Boolean, default=True)

    def set_password(self, password: str):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    def get_id(self):
        return str(self.id)

    @property
    def is_active(self):
        return self.is_active_flag

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# -------------------------
# Helper: requerir admin
# -------------------------
def require_admin():
    if not (current_user.is_authenticated and current_user.is_admin):
        flash("Se requiere usuario administrador.", "error")
        return False
    return True

# -------------------------
# Rutas de autenticación
# -------------------------
@app.route("/setup_admin", methods=["GET", "POST"])
def setup_admin():
    if User.query.filter_by(is_admin=True).first():
        return redirect(url_for("login"))

    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]
        user = User(email=email, is_admin=True)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        flash("Administrador creado correctamente.", "success")
        return redirect(url_for("login"))

    return render_template_string("""
        <h2>Configurar Administrador</h2>
        <form method="post">
            Email: <input type="email" name="email" required><br>
            Contraseña: <input type="password" name="password" required><br>
            <button type="submit">Crear Admin</button>
        </form>
    """)

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]
        user = User.query.filter_by(email=email).first()
        if user and user.check_password(password):
            login_user(user)
            return redirect(url_for("menu"))
        flash("Credenciales inválidas", "error")

    return render_template_string("""
        <h2>Iniciar sesión</h2>
        <form method="post">
            Email: <input type="email" name="email" required><br>
            Contraseña: <input type="password" name="password" required><br>
            <button type="submit">Ingresar</button>
        </form>
    """)

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
    if not require_admin(): return redirect(url_for("menu"))
    users = User.query.all()
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
    if not require_admin(): return redirect(url_for("menu"))
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]
        is_admin = "is_admin" in request.form
        user = User(email=email, is_admin=is_admin)
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
    if not require_admin(): return redirect(url_for("menu"))
    user = User.query.get_or_404(user_id)
    if request.method == "POST":
        user.email = request.form["email"]
        user.is_admin = "is_admin" in request.form
        if request.form.get("password"):
            user.set_password(request.form["password"])
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
    if not require_admin(): return redirect(url_for("menu"))
    user = User.query.get_or_404(user_id)
    user.is_active_flag = not user.is_active_flag
    db.session.commit()
    return redirect(url_for("list_users"))

@app.route("/users/<int:user_id>/delete")
@login_required
def delete_user(user_id):
    if not require_admin(): return redirect(url_for("menu"))
    user = User.query.get_or_404(user_id)
    if user.id == current_user.id:
        flash("No puedes eliminarte a ti mismo.", "error")
    else:
        db.session.delete(user)
        db.session.commit()
        flash("Usuario eliminado.", "success")
    return redirect(url_for("list_users"))

# -------------------------
# Ejemplos de vistas de caja
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
# Main
# -------------------------
if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(debug=True, host="0.0.0.0", port=5000)