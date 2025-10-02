@app.route('/menu')
@login_required
def menu():
    return render_template_string("""
        <h1>Menú principal</h1>
        <p>Autenticado correctamente.</p>
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