from flask import Flask, request, jsonify
from pymongo import MongoClient
import subprocess

app = Flask(_name_)

# Mongo y RADIUS en el MISMO host (h8)
MONGO_URI = "mongodb://localhost:27017/"
DB_NAME = "tel354"
RADIUS_USERS_FILE = "/etc/freeradius/3.0/users"  # ruta que mostraste en la captura

client = MongoClient(MONGO_URI)
db = client[DB_NAME]


# =========================
#   ENDPOINT R2: /authorize
# =========================
@app.route("/authorize", methods=["POST"])
def authorize():
    data = request.get_json() or {}
    username = data.get("username")

    if not username:
        return jsonify({"error": "username requerido"}), 400

    # 1. Buscar usuario activo en Mongo
    user = db.users.find_one(
        {"username": username, "estado": "activo"},
        {"_id": 0}
    )
    if not user:
        return jsonify({"error": "usuario no encontrado o inactivo"}), 404

    # 2. Buscar rol
    role = db.roles.find_one(
        {"name": user["rol"]},
        {"_id": 0}
    )
    if not role:
        return jsonify({"error": "rol no definido en BD"}), 500

    codigo = user.get("codigo")

    # 3. Cursos donde es alumno
    cursos_alumno = list(db.courses.find(
        {"alumnos": codigo},
        {"_id": 0}
    ))

    # 4. Cursos donde es profesor
    cursos_profesor = list(db.courses.find(
        {"profesores": codigo},
        {"_id": 0}
    ))

    # 5. Respuesta de autorización
    respuesta = {
        "username": username,
        "codigo": codigo,
        "rol": user["rol"],
        "allowed_resources": role.get("allowed_resources", []),
        "cursos_alumno": cursos_alumno,
        "cursos_profesor": cursos_profesor
    }

    return jsonify(respuesta), 200


# ===========================================
#   FUNCIONES AUXILIARES PARA CREAR USUARIOS
# ===========================================
def append_radius_user(username, password):
    """
    Agrega un usuario al archivo 'users' de FreeRADIUS.
    Formato: username  Cleartext-Password := "password"
    """
    line = f'{username}\tCleartext-Password := "{password}", Reply-Message := "ALUMNO"\n'
    with open(RADIUS_USERS_FILE, "a") as f:
        f.write(line)

    # Recargar FreeRADIUS para aplicar cambios (si falla, no rompe el flujo)
    try:
        subprocess.run(["sudo", "systemctl", "reload", "freeradius"],
                       check=False)
    except Exception:
        pass


# ======================================
#   ENDPOINT ADMIN: /admin/create_user
# ======================================
@app.route("/admin/create_user", methods=["POST"])
def create_user():
    data = request.get_json() or {}

    required = ["nombre", "apellido", "codigo", "username", "password", "rol"]
    missing = [k for k in required if k not in data]
    if missing:
        return jsonify({"error": f"faltan campos: {', '.join(missing)}"}), 400

    username = data["username"]
    password = data["password"]

    # 1. Verificar si ya existe en Mongo
    existing = db.users.find_one({"username": username})
    if existing:
        return jsonify({"error": "usuario ya existe en MongoDB"}), 409

    # 2. Insertar en MongoDB
    user_doc = {
        "nombre": data["nombre"],
        "apellido": data["apellido"],
        "codigo": data["codigo"],
        "username": username,
        "password": password,     # en real iría hasheada
        "rol": data["rol"],       # "alumno", "profesor", etc.
        "estado": "activo"
    }
    db.users.insert_one(user_doc)

    # 3. Agregar en FreeRADIUS
    append_radius_user(username, password)

    return jsonify({
        "message": "usuario creado en MongoDB y FreeRADIUS",
        "user": {
            "username": username,
            "codigo": data["codigo"],
            "rol": data["rol"]
        }
    }), 201

# ==========================
#  CURSOS
# ==========================

@app.route("/admin/courses", methods=["GET"])
def list_courses():
    """
    Listar todos los cursos y su estado.
    """
    cursos = list(db.courses.find({}, {"_id": 0}))
    return jsonify({"ok": True, "cursos": cursos})


@app.route("/admin/courses/<codigo>", methods=["GET"])
def course_detail(codigo):
    """
    Mostrar detalle de un curso (incluye alumnos y servicios).
    """
    curso = db.courses.find_one({"codigo": codigo}, {"_id": 0})
    if not curso:
        return jsonify({"ok": False, "msg": "Curso no encontrado"}), 404
    return jsonify({"ok": True, "curso": curso})


@app.route("/admin/courses/<codigo>/alumnos", methods=["POST"])
def course_update_students(codigo):
    """
    Actualizar alumnos de un curso: accion = agregar | eliminar
    body: { "accion": "agregar", "alumno": "20206311" }
    """
    data = request.get_json() or {}
    accion = data.get("accion")
    cod_alumno = data.get("alumno")

    if accion not in ("agregar", "eliminar") or not cod_alumno:
        return jsonify({"ok": False, "msg": "accion/alumno inválidos"}), 400

    if accion == "agregar":
        op = {"$addToSet": {"alumnos": cod_alumno}}
    else:
        op = {"$pull": {"alumnos": cod_alumno}}

    res = db.courses.update_one({"codigo": codigo}, op)
    if res.matched_count == 0:
        return jsonify({"ok": False, "msg": "Curso no encontrado"}), 404

    return jsonify({"ok": True, "msg": "Curso actualizado"})


# ==========================
#  ALUMNOS
# ==========================

@app.route("/admin/students", methods=["GET"])
def list_students():
    """
    Listar alumnos (sin mostrar password).
    """
    alumnos = list(
        db.users.find(
            {"rol": "alumno"},
            {"_id": 0, "password": 0}
        )
    )
    return jsonify({"ok": True, "alumnos": alumnos})


@app.route("/admin/students/<codigo>", methods=["GET"])
def student_detail(codigo):
    """
    Mostrar detalle de un alumno: código, nombre, (y MAC si la guardas).
    """
    alumno = db.users.find_one(
        {"codigo": codigo, "rol": "alumno"},
        {"_id": 0, "password": 0}
    )
    if not alumno:
        return jsonify({"ok": False, "msg": "Alumno no encontrado"}), 404
    return jsonify({"ok": True, "alumno": alumno})


# ==========================
#  SERVIDORES Y SERVICIOS
# ==========================

@app.route("/admin/servers", methods=["GET"])
def list_servers():
    """
    Mostrar servidores por curso y servicios que brindan.
    """
    cursos = list(
        db.courses.find(
            {},
            {"_id": 0, "codigo": 1, "nombre": 1, "servidores": 1}
        )
    )
    return jsonify({"ok": True, "cursos": cursos})


# ==========================
#  CONEXIONES (vista lógica)
# ==========================

@app.route("/admin/connections", methods=["GET"])
def list_connections():
    """
    Lista conexiones alumno-curso-servicios como vista lógica.
    handler = "<alumno>-<curso>"
    """
    cursos = db.courses.find(
        {},
        {"_id": 0, "codigo": 1, "servicios_permitidos": 1, "alumnos": 1}
    )

    conexiones = []
    for c in cursos:
        cod_curso = c.get("codigo")
        servicios = c.get("servicios_permitidos", [])
        for alu in c.get("alumnos", []):
            handler = f"{alu}-{cod_curso}"
            conexiones.append({
                "handler": handler,
                "alumno": alu,
                "curso": cod_curso,
                "servicios": servicios
            })

    return jsonify({"ok": True, "conexiones": conexiones})


@app.route("/admin/connections/<handler>", methods=["GET"])
def connection_detail(handler):
    """
    Mostrar detalle de una conexión por handler.
    """
    try:
        alu, curso = handler.split("-", 1)
    except ValueError:
        return jsonify({"ok": False, "msg": "handler inválido"}), 400

    c = db.courses.find_one(
        {"codigo": curso, "alumnos": alu},
        {"_id": 0, "codigo": 1, "servicios_permitidos": 1}
    )
    if not c:
        return jsonify({"ok": False, "msg": "Conexión no encontrada"}), 404

    return jsonify({
        "ok": True,
        "conexion": {
            "handler": handler,
            "alumno": alu,
            "curso": curso,
            "servicios": c.get("servicios_permitidos", [])
        }
    })

if _name_ == "_main_":
    # escucha en todas las interfaces, puerto 5000
    app.run(host="0.0.0.0", port=5000)