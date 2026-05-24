from flask import Flask, request, jsonify, render_template, redirect, session, flash
import sqlite3, hashlib, os, uuid
from datetime import datetime
from functools import wraps

app = Flask(__name__)
app.secret_key = "adolescentes_app_clave_2024"

DB = "ipuc.db"
FOTOS_DIR = os.path.join("static", "fotos")

# ══════════════════════════════════════════════
# BASE DE DATOS
# ══════════════════════════════════════════════

def get_db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def init_db():
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS usuarios (
            id       TEXT PRIMARY KEY,
            nombre   TEXT NOT NULL,
            email    TEXT NOT NULL UNIQUE,
            password TEXT NOT NULL,
            rol      TEXT NOT NULL DEFAULT 'adolescente',
            ciudad   TEXT,
            activo   INTEGER DEFAULT 1,
            fecha    TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS modulos (
            id          TEXT PRIMARY KEY,
            titulo      TEXT NOT NULL,
            descripcion TEXT,
            activo      INTEGER DEFAULT 1,
            creado_por  TEXT,
            fecha       TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS preguntas (
            id          TEXT PRIMARY KEY,
            modulo_id   TEXT NOT NULL REFERENCES modulos(id),
            texto       TEXT NOT NULL,
            opcion_a    TEXT NOT NULL,
            opcion_b    TEXT NOT NULL,
            opcion_c    TEXT NOT NULL,
            opcion_d    TEXT NOT NULL,
            correcta    TEXT NOT NULL,
            explicacion TEXT
        );

        CREATE TABLE IF NOT EXISTS respuestas (
            id         TEXT PRIMARY KEY,
            usuario_id TEXT NOT NULL REFERENCES usuarios(id),
            modulo_id  TEXT NOT NULL REFERENCES modulos(id),
            puntaje    INTEGER NOT NULL,
            total      INTEGER NOT NULL,
            puntos     INTEGER NOT NULL DEFAULT 0,
            detalle    TEXT,
            fecha      TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS historial_intentos (
            id         TEXT PRIMARY KEY,
            usuario_id TEXT NOT NULL REFERENCES usuarios(id),
            modulo_id  TEXT NOT NULL REFERENCES modulos(id),
            puntaje    INTEGER NOT NULL,
            fecha      TEXT DEFAULT (datetime('now'))
        );
    """)
    conn.commit()

    try:
        conn.execute("ALTER TABLE respuestas ADD COLUMN puntos INTEGER NOT NULL DEFAULT 0")
        conn.commit()
    except:
        pass

    try:
        conn.execute("ALTER TABLE usuarios ADD COLUMN foto TEXT")
        conn.commit()
    except:
        pass

    try:
        conn.executescript("""
            INSERT INTO historial_intentos (id, usuario_id, modulo_id, puntaje, fecha)
            SELECT id, usuario_id, modulo_id, puntaje, fecha FROM respuestas
            WHERE id NOT IN (SELECT id FROM historial_intentos)
        """)
        conn.commit()
    except:
        pass

    os.makedirs(FOTOS_DIR, exist_ok=True)

    admin = conn.execute("SELECT id FROM usuarios WHERE rol = 'admin' LIMIT 1").fetchone()
    if not admin:
        conn.execute(
            "INSERT INTO usuarios (id, nombre, email, password, rol, ciudad) VALUES (?,?,?,?,?,?)",
            (str(uuid.uuid4()), "Administrador", "admin@ipuc.com",
             hash_pw("admin1234"), "admin", "Colombia")
        )
        conn.commit()
        print("Usuario Admin creado → email: admin@ipuc.com  |  contraseña: admin1234")

    if not conn.execute("SELECT 1 FROM modulos LIMIT 1").fetchone():
        _seed(conn)

    conn.close()


def _seed(conn):
    m1 = str(uuid.uuid4())
    m2 = str(uuid.uuid4())
    m3 = str(uuid.uuid4())

    conn.executemany("INSERT INTO modulos (id, titulo, descripcion) VALUES (?,?,?)", [
        (m1, "Doctrina Apostólica",  "Fundamentos de la fe pentecostal unida"),
        (m2, "Conocimiento Bíblico", "Historia, libros y personajes de la Biblia"),
        (m3, "Vida Cristiana",       "Cómo vivir en santidad siendo joven hoy"),
    ])

    preguntas = [
        (m1, "¿Cuál es el plan de salvación según Hechos 2:38?",
         "Solo confesar a Jesús con la boca",
         "Arrepentimiento, bautismo en el nombre de Jesús y recibir el Espíritu Santo",
         "Bautismo de niño y Primera Comunión",
         "Ir a la iglesia todos los domingos", "B",
         "Pedro predicó el día de Pentecostés: arrepentirse, bautizarse y recibir el Espíritu Santo."),
        (m1, "¿En qué nombre debe hacerse el bautismo según la IPUC?",
         "Padre, Hijo y Espíritu Santo", "El nombre no importa",
         "En el nombre de Jesucristo", "En el nombre de la iglesia", "C",
         "En Hechos 2:38: 'Bautícese cada uno en el nombre de Jesucristo'."),
        (m1, "¿Qué señal evidencia el bautismo del Espíritu Santo?",
         "Sentir calor en las manos", "Hablar en otras lenguas",
         "Llorar durante la adoración", "Ver visiones", "B",
         "En Hechos 2:4 comenzaron a hablar en otras lenguas."),
        (m2, "¿Cuántos libros tiene la Biblia?",
         "60", "66", "72", "73", "B",
         "66 libros: 39 del Antiguo y 27 del Nuevo Testamento."),
        (m2, "¿Quién fue el primer rey de Israel?",
         "David", "Salomón", "Saúl", "Moisés", "C",
         "Saúl fue ungido por Samuel (1 Samuel 10)."),
        (m2, "¿Cuántos evangelios hay en el Nuevo Testamento?",
         "3", "4", "5", "6", "B",
         "Mateo, Marcos, Lucas y Juan."),
        (m3, "Según 1 Corintios 15:33, ¿qué hacen las malas compañías?",
         "Nada si tu fe es fuerte", "Solo afectan a nuevos creyentes",
         "Corrompen las buenas costumbres", "Nos hacen más fuertes", "C",
         "'Las malas conversaciones corrompen las buenas costumbres.'"),
        (m3, "¿A qué nos llama Jesús en Mateo 5:14?",
         "Sal de la tierra", "Luz del mundo",
         "Guerreros de Dios", "Siervos del Señor", "B",
         "'Vosotros sois la luz del mundo.'"),
    ]
    for p in preguntas:
        conn.execute("""
            INSERT INTO preguntas
            (id, modulo_id, texto, opcion_a, opcion_b, opcion_c, opcion_d, correcta, explicacion)
            VALUES (?,?,?,?,?,?,?,?,?)
        """, (str(uuid.uuid4()),) + p)
    conn.commit()
    print("Datos de ejemplo insertados.")


# ══════════════════════════════════════════════
# HELPERS Y DECORADORES
# ══════════════════════════════════════════════

def hash_pw(pw):
    return hashlib.sha256(pw.encode()).hexdigest()

def calcular_puntos(puntaje):
    if puntaje >= 80:
        return 3
    elif puntaje >= 60:
        return 2
    else:
        return 1

def login_requerido(f):
    @wraps(f)
    def dec(*args, **kwargs):
        if "usuario" not in session:
            return redirect("/login")
        conn = get_db()
        u = conn.execute(
            "SELECT activo, rol, foto FROM usuarios WHERE id = ?",
            (session["usuario"]["id"],)
        ).fetchone()
        conn.close()
        if not u or not u["activo"]:
            session.clear()
            flash("Tu cuenta ha sido desactivada.", "error")
            return redirect("/login")
        session["usuario"]["rol"] = u["rol"]
        session["usuario"]["foto"] = u["foto"]
        return f(*args, **kwargs)
    return dec

def solo_admin(f):
    @wraps(f)
    def dec(*args, **kwargs):
        if session.get("usuario", {}).get("rol") != "admin":
            flash("Solo el administrador puede acceder aquí.", "error")
            return redirect("/")
        return f(*args, **kwargs)
    return dec

def solo_maestro(f):
    @wraps(f)
    def dec(*args, **kwargs):
        rol = session.get("usuario", {}).get("rol")
        if rol not in ("maestro", "admin"):
            flash("Solo maestros o administradores pueden acceder.", "error")
            return redirect("/")
        return f(*args, **kwargs)
    return dec

def redirigir_por_rol(rol):
    if rol == "admin":
        return redirect("/admin")
    elif rol == "maestro":
        return redirect("/maestro")
    else:
        return redirect("/")


# ══════════════════════════════════════════════
# AUTH
# ══════════════════════════════════════════════

@app.route("/registro", methods=["GET", "POST"])
def registro():
    if request.method == "POST":
        nombre   = request.form.get("nombre", "").strip()
        email    = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        rol      = request.form.get("rol", "adolescente")
        ciudad   = request.form.get("ciudad", "").strip()

        if rol == "admin":
            flash("No puedes registrarte como administrador.", "error")
            return render_template("registro.html")

        if not nombre or not email or not password:
            flash("Completa todos los campos obligatorios.", "error")
            return render_template("registro.html")
        if len(password) < 6:
            flash("La contraseña debe tener al menos 6 caracteres.", "error")
            return render_template("registro.html")

        conn = get_db()
        if conn.execute("SELECT id FROM usuarios WHERE email = ?", (email,)).fetchone():
            conn.close()
            flash("Ya existe una cuenta con ese correo.", "error")
            return render_template("registro.html")

        conn.execute(
            "INSERT INTO usuarios (id, nombre, email, password, rol, ciudad) VALUES (?,?,?,?,?,?)",
            (str(uuid.uuid4()), nombre, email, hash_pw(password), rol, ciudad)
        )
        conn.commit()
        conn.close()
        flash("Cuenta creada. Ahora inicia sesión.", "success")
        return redirect("/login")

    return render_template("registro.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email    = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        conn = get_db()
        u = conn.execute(
            "SELECT * FROM usuarios WHERE email = ? AND password = ?",
            (email, hash_pw(password))
        ).fetchone()
        conn.close()

        if u:
            if not u["activo"]:
                flash("Tu cuenta está desactivada. Contacta al administrador.", "error")
                return render_template("login.html")
            session["usuario"] = dict(u)
            return redirigir_por_rol(u["rol"])

        flash("Correo o contraseña incorrectos.", "error")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")


# ══════════════════════════════════════════════
# FOTO DE PERFIL
# ══════════════════════════════════════════════

@app.route("/perfil/foto", methods=["POST"])
@login_requerido
def subir_foto():
    if "foto" not in request.files:
        return jsonify({"ok": False, "error": "No se recibió imagen"})

    archivo = request.files["foto"]
    if not archivo.filename:
        return jsonify({"ok": False, "error": "Archivo vacío"})

    ext = archivo.filename.rsplit(".", 1)[-1].lower()
    if ext not in ("jpg", "jpeg", "png", "webp", "gif", "jfif", "heic", "avif"):
        return jsonify({"ok": False, "error": "Formato no permitido"})

    nombre_archivo = f"{session['usuario']['id']}.{ext}"
    ruta = os.path.join(FOTOS_DIR, nombre_archivo)
    archivo.save(ruta)

    conn = get_db()
    conn.execute("UPDATE usuarios SET foto = ? WHERE id = ?",
                 (nombre_archivo, session["usuario"]["id"]))
    conn.commit()
    conn.close()

    session["usuario"]["foto"] = nombre_archivo
    return jsonify({"ok": True, "foto": nombre_archivo})


# ══════════════════════════════════════════════
# VISTA ADOLESCENTE
# ══════════════════════════════════════════════

@app.route("/")
@login_requerido
def index():
    if session["usuario"]["rol"] != "adolescente":
        return redirigir_por_rol(session["usuario"]["rol"])

    conn = get_db()
    modulos = conn.execute("SELECT * FROM modulos WHERE activo = 1 ORDER BY fecha").fetchall()
    progreso = {}
    for m in modulos:
        r = conn.execute(
            "SELECT COUNT(*) as n, MAX(puntaje) as mejor FROM respuestas "
            "WHERE usuario_id = ? AND modulo_id = ?",
            (session["usuario"]["id"], m["id"])
        ).fetchone()
        progreso[m["id"]] = {"intentos": r["n"], "mejor": r["mejor"] or 0}
    conn.close()
    return render_template("index.html", usuario=session["usuario"],
                           modulos=modulos, progreso=progreso)


@app.route("/modulo/<modulo_id>")
@login_requerido
def ver_modulo(modulo_id):
    conn = get_db()
    modulo    = conn.execute("SELECT * FROM modulos WHERE id = ?", (modulo_id,)).fetchone()
    preguntas = conn.execute(
        "SELECT * FROM preguntas WHERE modulo_id = ? ORDER BY RANDOM() LIMIT 5",
        (modulo_id,)
    ).fetchall()
    conn.close()
    if not modulo:
        return redirect("/")
    return render_template("modulo.html", usuario=session["usuario"],
                           modulo=modulo, preguntas=preguntas)


@app.route("/mis-resultados")
@login_requerido
def mis_resultados():
    conn = get_db()

    historial = conn.execute("""
        SELECT r.puntaje, r.total, r.puntos, r.fecha, m.titulo as modulo_titulo
        FROM respuestas r JOIN modulos m ON r.modulo_id = m.id
        WHERE r.usuario_id = ? ORDER BY r.fecha DESC
    """, (session["usuario"]["id"],)).fetchall()

    tabla = [dict(r) for r in conn.execute("""
        SELECT u.nombre, u.ciudad, u.foto, SUM(r.puntos) as total_puntos,
               COUNT(r.id) as modulos_hechos
        FROM respuestas r
        JOIN usuarios u ON r.usuario_id = u.id
        WHERE u.rol = 'adolescente'
        GROUP BY u.id
        ORDER BY total_puntos DESC
    """).fetchall()]

    mis_puntos = conn.execute(
        "SELECT SUM(puntos) as total FROM respuestas WHERE usuario_id = ?",
        (session["usuario"]["id"],)
    ).fetchone()

    conn.close()
    return render_template("mis_resultados.html", usuario=session["usuario"],
                           historial=historial, tabla=tabla,
                           mis_puntos=mis_puntos["total"] or 0)


# ══════════════════════════════════════════════
# VISTA MAESTRO
# ══════════════════════════════════════════════

@app.route("/maestro")
@login_requerido
@solo_maestro
def maestro():
    conn = get_db()
    modulos = conn.execute("SELECT * FROM modulos WHERE activo = 1 ORDER BY fecha DESC").fetchall()
    n_adol  = conn.execute("SELECT COUNT(*) FROM usuarios WHERE rol = 'adolescente'").fetchone()[0]
    n_eval  = conn.execute("SELECT COUNT(*) FROM respuestas").fetchone()[0]
    ranking = [dict(r) for r in conn.execute("""
        SELECT u.nombre, u.ciudad, u.foto, COALESCE(SUM(r.puntos), 0) as total_puntos,
               COUNT(r.id) as modulos_hechos
        FROM usuarios u
        LEFT JOIN respuestas r ON u.id = r.usuario_id
        WHERE u.rol = 'adolescente'
        GROUP BY u.id
        ORDER BY total_puntos DESC
    """).fetchall()]
    conn.close()
    return render_template("maestro.html", usuario=session["usuario"],
                           modulos=modulos, n_adolescentes=n_adol, n_eval=n_eval, ranking=ranking)


# ══════════════════════════════════════════════
# VISTA ADMIN
# ══════════════════════════════════════════════

@app.route("/admin")
@login_requerido
@solo_admin
def admin():
    conn = get_db()
    usuarios = conn.execute("SELECT * FROM usuarios ORDER BY fecha DESC").fetchall()
    modulos  = conn.execute("SELECT * FROM modulos ORDER BY fecha DESC").fetchall()
    n_eval   = conn.execute("SELECT COUNT(*) FROM respuestas").fetchone()[0]
    ranking  = [dict(r) for r in conn.execute("""
        SELECT u.nombre, u.ciudad, u.foto, COALESCE(SUM(r.puntos), 0) as total_puntos,
               COUNT(r.id) as modulos_hechos
        FROM usuarios u
        LEFT JOIN respuestas r ON u.id = r.usuario_id
        WHERE u.rol = 'adolescente'
        GROUP BY u.id
        ORDER BY total_puntos DESC
    """).fetchall()]
    conn.close()
    return render_template("admin.html", usuario=session["usuario"],
                           usuarios=usuarios, modulos=modulos,
                           n_eval=n_eval, ranking=ranking)


@app.route("/admin/toggle-usuario/<uid>", methods=["POST"])
@login_requerido
@solo_admin
def toggle_usuario(uid):
    conn = get_db()
    u = conn.execute("SELECT activo, rol FROM usuarios WHERE id = ?", (uid,)).fetchone()
    if u and u["rol"] != "admin":
        nuevo = 0 if u["activo"] else 1
        conn.execute("UPDATE usuarios SET activo = ? WHERE id = ?", (nuevo, uid))
        conn.commit()
        if nuevo == 0:
            flash("Usuario desactivado. Su sesión se cerrará en los próximos 5 segundos.", "success")
        else:
            flash("Usuario activado correctamente.", "success")
    conn.close()
    return redirect("/admin")


@app.route("/admin/cambiar-rol/<uid>", methods=["POST"])
@login_requerido
@solo_admin
def cambiar_rol(uid):
    nuevo_rol = request.form.get("rol")
    if nuevo_rol not in ("adolescente", "maestro"):
        flash("Rol no válido.", "error")
        return redirect("/admin")
    conn = get_db()
    u = conn.execute("SELECT rol FROM usuarios WHERE id = ?", (uid,)).fetchone()
    if u and u["rol"] != "admin":
        conn.execute("UPDATE usuarios SET rol = ? WHERE id = ?", (nuevo_rol, uid))
        conn.commit()
        flash("Rol actualizado. El panel cambiará en la próxima acción del usuario.", "success")
    conn.close()
    return redirect("/admin")


@app.route("/admin/cambiar-password/<uid>", methods=["POST"])
@login_requerido
@solo_admin
def cambiar_password(uid):
    body = request.json or {}
    nueva = body.get("password", "")
    if len(nueva) < 6:
        return jsonify({"ok": False, "error": "Mínimo 6 caracteres"})
    conn = get_db()
    u = conn.execute("SELECT rol FROM usuarios WHERE id = ?", (uid,)).fetchone()
    if u and u["rol"] != "admin":
        conn.execute("UPDATE usuarios SET password = ? WHERE id = ?", (hash_pw(nueva), uid))
        conn.commit()
        conn.close()
        return jsonify({"ok": True})
    conn.close()
    return jsonify({"ok": False, "error": "No permitido"})


@app.route("/admin/toggle-modulo/<mid>", methods=["POST"])
@login_requerido
@solo_admin
def admin_toggle_modulo(mid):
    conn = get_db()
    m = conn.execute("SELECT activo FROM modulos WHERE id = ?", (mid,)).fetchone()
    if m:
        nuevo = 0 if m["activo"] else 1
        conn.execute("UPDATE modulos SET activo = ? WHERE id = ?", (nuevo, mid))
        conn.commit()
        flash("Módulo actualizado.", "success")
    conn.close()
    return redirect("/admin")


@app.route("/admin/crear-modulo", methods=["POST"])
@login_requerido
@solo_admin
def admin_crear_modulo():
    titulo      = request.form.get("titulo", "").strip()
    descripcion = request.form.get("descripcion", "").strip()
    if not titulo:
        flash("El título es obligatorio.", "error")
        return redirect("/admin")
    conn = get_db()
    conn.execute(
        "INSERT INTO modulos (id, titulo, descripcion, creado_por) VALUES (?,?,?,?)",
        (str(uuid.uuid4()), titulo, descripcion, session["usuario"]["id"])
    )
    conn.commit()
    conn.close()
    flash("Módulo creado correctamente.", "success")
    return redirect("/admin")


# ══════════════════════════════════════════════
# API
# ══════════════════════════════════════════════

@app.route("/api/check-session")
def check_session():
    if "usuario" not in session:
        return jsonify({"activo": False})
    conn = get_db()
    u = conn.execute(
        "SELECT activo, rol, foto FROM usuarios WHERE id = ?",
        (session["usuario"]["id"],)
    ).fetchone()
    conn.close()
    if not u or not u["activo"]:
        session.clear()
        return jsonify({"activo": False})
    session["usuario"]["rol"]  = u["rol"]
    session["usuario"]["foto"] = u["foto"]
    return jsonify({"activo": True, "rol": u["rol"]})


@app.route("/api/modulos", methods=["GET"])
@login_requerido
def api_get_modulos():
    conn = get_db()
    data = [dict(m) for m in conn.execute("SELECT * FROM modulos WHERE activo = 1").fetchall()]
    conn.close()
    return jsonify(data)


@app.route("/api/modulos", methods=["POST"])
@login_requerido
@solo_maestro
def api_crear_modulo():
    body = request.json or {}
    if not body.get("titulo"):
        return jsonify({"ok": False, "error": "El título es obligatorio"}), 400

    conn = get_db()
    mid  = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO modulos (id, titulo, descripcion, creado_por) VALUES (?,?,?,?)",
        (mid, body["titulo"], body.get("descripcion", ""), session["usuario"]["id"])
    )
    for p in body.get("preguntas", []):
        conn.execute("""
            INSERT INTO preguntas
            (id, modulo_id, texto, opcion_a, opcion_b, opcion_c, opcion_d, correcta, explicacion)
            VALUES (?,?,?,?,?,?,?,?,?)
        """, (str(uuid.uuid4()), mid,
              p["texto"], p["opcion_a"], p["opcion_b"], p["opcion_c"], p["opcion_d"],
              p["correcta"].upper(), p.get("explicacion", "")))
    conn.commit()
    conn.close()
    return jsonify({"ok": True, "id": mid})


@app.route("/api/modulos/<modulo_id>", methods=["DELETE"])
@login_requerido
@solo_maestro
def api_eliminar_modulo(modulo_id):
    conn = get_db()
    conn.execute("UPDATE modulos SET activo = 0 WHERE id = ?", (modulo_id,))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


@app.route("/api/preguntas/<modulo_id>")
@login_requerido
def api_preguntas(modulo_id):
    conn = get_db()
    rows = conn.execute(
        "SELECT id, texto, opcion_a, opcion_b, opcion_c, opcion_d "
        "FROM preguntas WHERE modulo_id = ? ORDER BY RANDOM() LIMIT 5",
        (modulo_id,)
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route("/api/respuestas", methods=["POST"])
@login_requerido
def api_respuestas():
    body = request.json or {}
    if not body.get("modulo_id") or not body.get("respuestas"):
        return jsonify({"ok": False, "error": "Datos incompletos"}), 400

    conn      = get_db()
    resp_usr  = body["respuestas"]
    correctas = 0
    detalle   = []

    for pid, letra in resp_usr.items():
        p = conn.execute(
            "SELECT texto, correcta, explicacion FROM preguntas WHERE id = ?", (pid,)
        ).fetchone()
        if not p:
            continue
        ok = letra.upper() == p["correcta"].upper()
        if ok:
            correctas += 1
        detalle.append({
            "pregunta":     p["texto"],
            "tu_respuesta": letra.upper(),
            "correcta":     p["correcta"],
            "ok":           ok,
            "explicacion":  p["explicacion"] or ""
        })

    total   = len(resp_usr)
    puntaje = round((correctas / total) * 100) if total else 0
    puntos  = calcular_puntos(puntaje)

    conn.execute(
        "INSERT INTO historial_intentos (id, usuario_id, modulo_id, puntaje) VALUES (?,?,?,?)",
        (str(uuid.uuid4()), session["usuario"]["id"], body["modulo_id"], puntaje)
    )

    existente = conn.execute(
        "SELECT id, puntos FROM respuestas WHERE usuario_id = ? AND modulo_id = ?",
        (session["usuario"]["id"], body["modulo_id"])
    ).fetchone()

    if existente:
        conn.execute(
            "UPDATE respuestas SET puntaje = ?, total = ?, puntos = ?, detalle = ?, fecha = datetime('now') WHERE id = ?",
            (puntaje, total, puntos, str(detalle), existente["id"])
        )
    else:
        conn.execute(
            "INSERT INTO respuestas (id, usuario_id, modulo_id, puntaje, total, puntos, detalle) VALUES (?,?,?,?,?,?,?)",
            (str(uuid.uuid4()), session["usuario"]["id"],
             body["modulo_id"], puntaje, total, puntos, str(detalle))
        )

    conn.commit()
    conn.close()

    return jsonify({"ok": True, "puntaje": puntaje, "puntos": puntos,
                    "correctas": correctas, "total": total, "detalle": detalle})


@app.route("/api/resultados")
@login_requerido
@solo_maestro
def api_resultados():
    conn = get_db()
    rows = conn.execute("""
        SELECT r.puntaje, r.total, r.puntos, r.fecha,
               u.nombre AS estudiante, u.email, u.id AS usuario_id,
               m.titulo AS modulo, m.id AS modulo_id
        FROM respuestas r
        JOIN usuarios u ON r.usuario_id = u.id
        JOIN modulos m  ON r.modulo_id  = m.id
        ORDER BY r.fecha DESC
    """).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route("/api/intentos/<usuario_id>/<modulo_id>")
@login_requerido
@solo_maestro
def api_intentos(usuario_id, modulo_id):
    conn = get_db()
    rows = conn.execute("""
        SELECT puntaje, fecha
        FROM historial_intentos
        WHERE usuario_id = ? AND modulo_id = ?
        ORDER BY fecha DESC
    """, (usuario_id, modulo_id)).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


# ══════════════════════════════════════════════
if __name__ == "__main__":
    init_db()
    app.run(debug=True, host='0.0.0.0')