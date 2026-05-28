from flask import Flask, request, jsonify, render_template, redirect, session, flash
import hashlib, os, uuid
from functools import wraps
from supabase import create_client, Client
from dotenv import load_dotenv

# Cargar variables del archivo .env
load_dotenv()

app = Flask(__name__)
app.secret_key = "adolescentes_app_clave_2024"

# ══════════════════════════════════════════════
# SUPABASE
# ══════════════════════════════════════════════
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


# ══════════════════════════════════════════════
# HELPERS
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
        u = supabase.table("usuarios").select("activo, rol, foto").eq("id", session["usuario"]["id"]).single().execute()
        if not u.data or not u.data["activo"]:
            session.clear()
            flash("Tu cuenta ha sido desactivada.", "error")
            return redirect("/login")
        session["usuario"]["rol"]  = u.data["rol"]
        session["usuario"]["foto"] = u.data.get("foto")
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

        existe = supabase.table("usuarios").select("id").eq("email", email).execute()
        if existe.data:
            flash("Ya existe una cuenta con ese correo.", "error")
            return render_template("registro.html")

        supabase.table("usuarios").insert({
            "id": str(uuid.uuid4()),
            "nombre": nombre,
            "email": email,
            "password": hash_pw(password),
            "rol": rol,
            "ciudad": ciudad,
            "activo": 1
        }).execute()

        flash("Cuenta creada. Ahora inicia sesión.", "success")
        return redirect("/login")

    return render_template("registro.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email    = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        res = supabase.table("usuarios").select("*").eq("email", email).eq("password", hash_pw(password)).execute()

        if res.data:
            u = res.data[0]
            if not u["activo"]:
                flash("Tu cuenta está desactivada. Contacta al administrador.", "error")
                return render_template("login.html")
            session["usuario"] = u
            return redirigir_por_rol(u["rol"])

        flash("Correo o contraseña incorrectos.", "error")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")


# ══════════════════════════════════════════════
# VISTA ADOLESCENTE
# ══════════════════════════════════════════════

@app.route("/")
@login_requerido
def index():
    if session["usuario"]["rol"] != "adolescente":
        return redirigir_por_rol(session["usuario"]["rol"])

    modulos = supabase.table("modulos").select("*").eq("activo", 1).order("fecha").execute().data
    progreso = {}
    for m in modulos:
        r = supabase.table("respuestas").select("puntaje").eq("usuario_id", session["usuario"]["id"]).eq("modulo_id", m["id"]).execute().data
        intentos = len(r)
        mejor = max([x["puntaje"] for x in r], default=0)
        progreso[m["id"]] = {"intentos": intentos, "mejor": mejor}

    return render_template("index.html", usuario=session["usuario"], modulos=modulos, progreso=progreso)


@app.route("/modulo/<modulo_id>")
@login_requerido
def ver_modulo(modulo_id):
    modulo = supabase.table("modulos").select("*").eq("id", modulo_id).single().execute().data
    if not modulo:
        return redirect("/")
    preguntas_all = supabase.table("preguntas").select("*").eq("modulo_id", modulo_id).execute().data
    import random
    preguntas = random.sample(preguntas_all, min(5, len(preguntas_all)))
    return render_template("modulo.html", usuario=session["usuario"], modulo=modulo, preguntas=preguntas)


@app.route("/mis-resultados")
@login_requerido
def mis_resultados():
    historial_raw = supabase.table("respuestas").select("*, modulos(titulo)").eq("usuario_id", session["usuario"]["id"]).order("fecha", desc=True).execute().data
    historial = []
    for r in historial_raw:
        historial.append({
            "puntaje": r["puntaje"],
            "total": r["total"],
            "puntos": r["puntos"],
            "fecha": r["fecha"],
            "modulo_titulo": r["modulos"]["titulo"] if r.get("modulos") else ""
        })

    # Ranking
    todas_respuestas = supabase.table("respuestas").select("usuario_id, puntos").execute().data
    usuarios_adol = supabase.table("usuarios").select("id, nombre, ciudad, foto").eq("rol", "adolescente").execute().data

    tabla = []
    for u in usuarios_adol:
        puntos_u = [r["puntos"] for r in todas_respuestas if r["usuario_id"] == u["id"]]
        tabla.append({
            "nombre": u["nombre"],
            "ciudad": u.get("ciudad"),
            "foto": u.get("foto"),
            "total_puntos": sum(puntos_u),
            "modulos_hechos": len(puntos_u)
        })
    tabla.sort(key=lambda x: x["total_puntos"], reverse=True)

    mis_puntos_raw = supabase.table("respuestas").select("puntos").eq("usuario_id", session["usuario"]["id"]).execute().data
    mis_puntos = sum([r["puntos"] for r in mis_puntos_raw])

    return render_template("mis_resultados.html", usuario=session["usuario"],
                           historial=historial, tabla=tabla, mis_puntos=mis_puntos)


# ══════════════════════════════════════════════
# FORO
# ══════════════════════════════════════════════

@app.route("/foro")
@login_requerido
def foro():
    posts_raw = supabase.table("foro_posts").select("*, usuarios(nombre, rol, foto)").order("fecha", desc=True).execute().data
    posts = []
    for p in posts_raw:
        respuestas_count = supabase.table("foro_respuestas").select("id").eq("post_id", p["id"]).execute().data
        posts.append({
            "id": p["id"],
            "titulo": p["titulo"],
            "contenido": p["contenido"],
            "fecha": p["fecha"],
            "autor": p["usuarios"]["nombre"] if p.get("usuarios") else "",
            "autor_rol": p["usuarios"]["rol"] if p.get("usuarios") else "",
            "autor_foto": p["usuarios"]["foto"] if p.get("usuarios") else None,
            "n_respuestas": len(respuestas_count)
        })
    return render_template("foro.html", usuario=session["usuario"], posts=posts)


@app.route("/foro/<post_id>")
@login_requerido
def foro_post(post_id):
    p = supabase.table("foro_posts").select("*, usuarios(nombre, rol, foto)").eq("id", post_id).single().execute().data
    if not p:
        return redirect("/foro")
    post = {
        "id": p["id"],
        "titulo": p["titulo"],
        "contenido": p["contenido"],
        "fecha": p["fecha"],
        "usuario_id": p["usuario_id"],
        "autor": p["usuarios"]["nombre"] if p.get("usuarios") else "",
        "autor_rol": p["usuarios"]["rol"] if p.get("usuarios") else "",
        "autor_foto": p["usuarios"]["foto"] if p.get("usuarios") else None,
    }
    resp_raw = supabase.table("foro_respuestas").select("*, usuarios(nombre, rol, foto)").eq("post_id", post_id).order("fecha").execute().data
    respuestas = []
    for r in resp_raw:
        respuestas.append({
            "id": r["id"],
            "contenido": r["contenido"],
            "fecha": r["fecha"],
            "usuario_id": r["usuario_id"],
            "autor": r["usuarios"]["nombre"] if r.get("usuarios") else "",
            "autor_rol": r["usuarios"]["rol"] if r.get("usuarios") else "",
            "autor_foto": r["usuarios"]["foto"] if r.get("usuarios") else None,
        })
    return render_template("foro_post.html", usuario=session["usuario"], post=post, respuestas=respuestas)


@app.route("/foro/nuevo", methods=["POST"])
@login_requerido
def foro_nuevo_post():
    titulo    = request.form.get("titulo", "").strip()
    contenido = request.form.get("contenido", "").strip()
    if not titulo or not contenido:
        flash("El título y el contenido son obligatorios.", "error")
        return redirect("/foro")
    pid = str(uuid.uuid4())
    supabase.table("foro_posts").insert({
        "id": pid,
        "usuario_id": session["usuario"]["id"],
        "titulo": titulo,
        "contenido": contenido
    }).execute()
    return redirect(f"/foro/{pid}")


@app.route("/foro/<post_id>/responder", methods=["POST"])
@login_requerido
def foro_responder(post_id):
    contenido = request.form.get("contenido", "").strip()
    if not contenido:
        flash("La respuesta no puede estar vacía.", "error")
        return redirect(f"/foro/{post_id}")
    supabase.table("foro_respuestas").insert({
        "id": str(uuid.uuid4()),
        "post_id": post_id,
        "usuario_id": session["usuario"]["id"],
        "contenido": contenido
    }).execute()
    return redirect(f"/foro/{post_id}")


@app.route("/foro/eliminar/<post_id>", methods=["POST"])
@login_requerido
def foro_eliminar_post(post_id):
    p = supabase.table("foro_posts").select("usuario_id").eq("id", post_id).single().execute().data
    rol = session["usuario"]["rol"]
    if p and (p["usuario_id"] == session["usuario"]["id"] or rol in ("admin", "maestro")):
        supabase.table("foro_respuestas").delete().eq("post_id", post_id).execute()
        supabase.table("foro_posts").delete().eq("id", post_id).execute()
    return redirect("/foro")


@app.route("/foro/eliminar-respuesta/<resp_id>", methods=["POST"])
@login_requerido
def foro_eliminar_respuesta(resp_id):
    r = supabase.table("foro_respuestas").select("usuario_id, post_id").eq("id", resp_id).single().execute().data
    rol = session["usuario"]["rol"]
    if r and (r["usuario_id"] == session["usuario"]["id"] or rol in ("admin", "maestro")):
        post_id = r["post_id"]
        supabase.table("foro_respuestas").delete().eq("id", resp_id).execute()
        return redirect(f"/foro/{post_id}")
    return redirect("/foro")


# ══════════════════════════════════════════════
# VISTA MAESTRO
# ══════════════════════════════════════════════

@app.route("/maestro")
@login_requerido
@solo_maestro
def maestro():
    modulos = supabase.table("modulos").select("*").eq("activo", 1).order("fecha", desc=True).execute().data
    n_adol  = len(supabase.table("usuarios").select("id").eq("rol", "adolescente").execute().data)
    n_eval  = len(supabase.table("respuestas").select("id").execute().data)

    usuarios_adol = supabase.table("usuarios").select("id, nombre, ciudad, foto").eq("rol", "adolescente").execute().data
    todas_respuestas = supabase.table("respuestas").select("usuario_id, puntos").execute().data
    ranking = []
    for u in usuarios_adol:
        puntos_u = [r["puntos"] for r in todas_respuestas if r["usuario_id"] == u["id"]]
        ranking.append({
            "nombre": u["nombre"],
            "ciudad": u.get("ciudad"),
            "foto": u.get("foto"),
            "total_puntos": sum(puntos_u),
            "modulos_hechos": len(puntos_u)
        })
    ranking.sort(key=lambda x: x["total_puntos"], reverse=True)

    return render_template("maestro.html", usuario=session["usuario"],
                           modulos=modulos, n_adolescentes=n_adol, n_eval=n_eval, ranking=ranking)


# ══════════════════════════════════════════════
# VISTA ADMIN
# ══════════════════════════════════════════════

@app.route("/admin")
@login_requerido
@solo_admin
def admin():
    usuarios = supabase.table("usuarios").select("*").order("fecha", desc=True).execute().data
    modulos  = supabase.table("modulos").select("*").order("fecha", desc=True).execute().data
    n_eval   = len(supabase.table("respuestas").select("id").execute().data)

    usuarios_adol = supabase.table("usuarios").select("id, nombre, ciudad, foto").eq("rol", "adolescente").execute().data
    todas_respuestas = supabase.table("respuestas").select("usuario_id, puntos").execute().data
    ranking = []
    for u in usuarios_adol:
        puntos_u = [r["puntos"] for r in todas_respuestas if r["usuario_id"] == u["id"]]
        ranking.append({
            "nombre": u["nombre"],
            "ciudad": u.get("ciudad"),
            "foto": u.get("foto"),
            "total_puntos": sum(puntos_u),
            "modulos_hechos": len(puntos_u)
        })
    ranking.sort(key=lambda x: x["total_puntos"], reverse=True)

    return render_template("admin.html", usuario=session["usuario"],
                           usuarios=usuarios, modulos=modulos, n_eval=n_eval, ranking=ranking)


@app.route("/admin/toggle-usuario/<uid>", methods=["POST"])
@login_requerido
@solo_admin
def toggle_usuario(uid):
    u = supabase.table("usuarios").select("activo, rol").eq("id", uid).single().execute().data
    if u and u["rol"] != "admin":
        nuevo = 0 if u["activo"] else 1
        supabase.table("usuarios").update({"activo": nuevo}).eq("id", uid).execute()
        if nuevo == 0:
            flash("Usuario desactivado.", "success")
        else:
            flash("Usuario activado correctamente.", "success")
    return redirect("/admin")


@app.route("/admin/cambiar-rol/<uid>", methods=["POST"])
@login_requerido
@solo_admin
def cambiar_rol(uid):
    nuevo_rol = request.form.get("rol")
    if nuevo_rol not in ("adolescente", "maestro"):
        flash("Rol no válido.", "error")
        return redirect("/admin")
    u = supabase.table("usuarios").select("rol").eq("id", uid).single().execute().data
    if u and u["rol"] != "admin":
        supabase.table("usuarios").update({"rol": nuevo_rol}).eq("id", uid).execute()
        flash("Rol actualizado.", "success")
    return redirect("/admin")


@app.route("/admin/cambiar-password/<uid>", methods=["POST"])
@login_requerido
@solo_admin
def cambiar_password(uid):
    body = request.json or {}
    nueva = body.get("password", "")
    if len(nueva) < 6:
        return jsonify({"ok": False, "error": "Mínimo 6 caracteres"})
    u = supabase.table("usuarios").select("rol").eq("id", uid).single().execute().data
    if u and u["rol"] != "admin":
        supabase.table("usuarios").update({"password": hash_pw(nueva)}).eq("id", uid).execute()
        return jsonify({"ok": True})
    return jsonify({"ok": False, "error": "No permitido"})


@app.route("/admin/toggle-modulo/<mid>", methods=["POST"])
@login_requerido
@solo_admin
def admin_toggle_modulo(mid):
    m = supabase.table("modulos").select("activo").eq("id", mid).single().execute().data
    if m:
        nuevo = 0 if m["activo"] else 1
        supabase.table("modulos").update({"activo": nuevo}).eq("id", mid).execute()
        flash("Módulo actualizado.", "success")
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
    supabase.table("modulos").insert({
        "id": str(uuid.uuid4()),
        "titulo": titulo,
        "descripcion": descripcion,
        "creado_por": session["usuario"]["id"],
        "activo": 1
    }).execute()
    flash("Módulo creado correctamente.", "success")
    return redirect("/admin")


# ══════════════════════════════════════════════
# API
# ══════════════════════════════════════════════

@app.route("/api/check-session")
def check_session():
    if "usuario" not in session:
        return jsonify({"activo": False})
    u = supabase.table("usuarios").select("activo, rol, foto").eq("id", session["usuario"]["id"]).single().execute().data
    if not u or not u["activo"]:
        session.clear()
        return jsonify({"activo": False})
    session["usuario"]["rol"]  = u["rol"]
    session["usuario"]["foto"] = u.get("foto")
    return jsonify({"activo": True, "rol": u["rol"]})


@app.route("/api/modulos", methods=["GET"])
@login_requerido
def api_get_modulos():
    data = supabase.table("modulos").select("*").eq("activo", 1).execute().data
    return jsonify(data)


@app.route("/api/modulos", methods=["POST"])
@login_requerido
@solo_maestro
def api_crear_modulo():
    body = request.json or {}
    if not body.get("titulo"):
        return jsonify({"ok": False, "error": "El título es obligatorio"}), 400

    mid = str(uuid.uuid4())
    supabase.table("modulos").insert({
        "id": mid,
        "titulo": body["titulo"],
        "descripcion": body.get("descripcion", ""),
        "creado_por": session["usuario"]["id"],
        "activo": 1
    }).execute()

    for p in body.get("preguntas", []):
        supabase.table("preguntas").insert({
            "id": str(uuid.uuid4()),
            "modulo_id": mid,
            "texto": p["texto"],
            "opcion_a": p["opcion_a"],
            "opcion_b": p["opcion_b"],
            "opcion_c": p["opcion_c"],
            "opcion_d": p["opcion_d"],
            "correcta": p["correcta"].upper(),
            "explicacion": p.get("explicacion", "")
        }).execute()

    return jsonify({"ok": True, "id": mid})


@app.route("/api/modulos/<modulo_id>", methods=["DELETE"])
@login_requerido
@solo_maestro
def api_eliminar_modulo(modulo_id):
    supabase.table("modulos").update({"activo": 0}).eq("id", modulo_id).execute()
    return jsonify({"ok": True})


@app.route("/api/preguntas/<modulo_id>")
@login_requerido
def api_preguntas(modulo_id):
    import random
    rows = supabase.table("preguntas").select("id, texto, opcion_a, opcion_b, opcion_c, opcion_d").eq("modulo_id", modulo_id).execute().data
    return jsonify(random.sample(rows, min(5, len(rows))))


@app.route("/api/respuestas", methods=["POST"])
@login_requerido
def api_respuestas():
    body = request.json or {}
    if not body.get("modulo_id") or not body.get("respuestas"):
        return jsonify({"ok": False, "error": "Datos incompletos"}), 400

    resp_usr  = body["respuestas"]
    correctas = 0
    detalle   = []

    for pid, letra in resp_usr.items():
        p = supabase.table("preguntas").select("texto, correcta, explicacion").eq("id", pid).single().execute().data
        if not p:
            continue
        ok = letra.upper() == p["correcta"].upper()
        if ok:
            correctas += 1
        detalle.append({
            "pregunta": p["texto"],
            "tu_respuesta": letra.upper(),
            "correcta": p["correcta"],
            "ok": ok,
            "explicacion": p["explicacion"] or ""
        })

    total   = len(resp_usr)
    puntaje = round((correctas / total) * 100) if total else 0
    puntos  = calcular_puntos(puntaje)

    supabase.table("historial_intentos").insert({
        "id": str(uuid.uuid4()),
        "usuario_id": session["usuario"]["id"],
        "modulo_id": body["modulo_id"],
        "puntaje": puntaje
    }).execute()

    existente = supabase.table("respuestas").select("id").eq("usuario_id", session["usuario"]["id"]).eq("modulo_id", body["modulo_id"]).execute().data

    if existente:
        supabase.table("respuestas").update({
            "puntaje": puntaje,
            "total": total,
            "puntos": puntos,
            "detalle": str(detalle)
        }).eq("id", existente[0]["id"]).execute()
    else:
        supabase.table("respuestas").insert({
            "id": str(uuid.uuid4()),
            "usuario_id": session["usuario"]["id"],
            "modulo_id": body["modulo_id"],
            "puntaje": puntaje,
            "total": total,
            "puntos": puntos,
            "detalle": str(detalle)
        }).execute()

    return jsonify({"ok": True, "puntaje": puntaje, "puntos": puntos,
                    "correctas": correctas, "total": total, "detalle": detalle})


@app.route("/api/resultados")
@login_requerido
@solo_maestro
def api_resultados():
    rows = supabase.table("respuestas").select("*, usuarios(nombre, email, id), modulos(titulo, id)").order("fecha", desc=True).execute().data
    result = []
    for r in rows:
        result.append({
            "puntaje": r["puntaje"],
            "total": r["total"],
            "puntos": r["puntos"],
            "fecha": r["fecha"],
            "estudiante": r["usuarios"]["nombre"] if r.get("usuarios") else "",
            "email": r["usuarios"]["email"] if r.get("usuarios") else "",
            "usuario_id": r["usuarios"]["id"] if r.get("usuarios") else "",
            "modulo": r["modulos"]["titulo"] if r.get("modulos") else "",
            "modulo_id": r["modulos"]["id"] if r.get("modulos") else "",
        })
    return jsonify(result)


@app.route("/api/intentos/<usuario_id>/<modulo_id>")
@login_requerido
@solo_maestro
def api_intentos(usuario_id, modulo_id):
    rows = supabase.table("historial_intentos").select("puntaje, fecha").eq("usuario_id", usuario_id).eq("modulo_id", modulo_id).order("fecha", desc=True).execute().data
    return jsonify(rows)


# ══════════════════════════════════════════════
if __name__ == "__main__":
    app.run(debug=True, host='0.0.0.0')