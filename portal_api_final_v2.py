#!/usr/bin/python3
# -- coding: utf-8 --

from flask import Flask, request, jsonify
import requests
import subprocess

# ==========================================
# CONFIGURACIÓN
# ==========================================
RADIUS_IP      = "10.0.0.8"          # h8 donde corre RADIUS
RADIUS_SECRET  = "testing123"

PORTAL_IP      = "0.0.0.0"           # escuchar en todas las interfaces
PORTAL_PORT    = 5000

R2_URL         = "http://10.0.0.8:5000/authorize"   # API R2 en h8 (Mongo)

app = Flask(_name_)

# ==========================================
# FUNCIÓN: Validar usuario contra FreeRADIUS
# ==========================================
def validar_con_radius(usuario, password):
    comando = [
        "/usr/bin/radtest",
        usuario,
        password,
        RADIUS_IP,
        "0",
        RADIUS_SECRET
    ]
    try:
        salida = subprocess.check_output(
            comando,
            stderr=subprocess.STDOUT,
            timeout=10
        ).decode('utf-8')

        print("\n[RADIUS] Respuesta:")
        print(salida)

        return "Access-Accept" in salida

    except Exception as e:
        print("[RADIUS] Error:", str(e))
        return False


# ==========================================
# ENDPOINT: /login
# ==========================================
@app.route("/login", methods=["POST"])
def login():
    data = request.get_json(silent=True) or {}

    usuario = data.get("usuario")
    password = data.get("password")
    mac      = data.get("mac")
    ip       = data.get("ip", "desconocida")
    puerto   = data.get("puerto", "desconocido")

    if not all([usuario, password, mac]):
        return jsonify({"ok": False, "msg": "Faltan datos obligatorios"}), 400

    print(f"\n[LOGIN] Intento de autenticación")
    print(f" ├─ Usuario : {usuario}")
    print(f" ├─ MAC     : {mac}")
    print(f" ├─ IP      : {ip}")
    print(f" └─ Puerto  : {puerto}")

    # ======== R1: Validación con RADIUS =============
    if not validar_con_radius(usuario, password):
        return jsonify({"ok": False, "msg": "Credenciales incorrectas"}), 403

    # ======== R2: Rol + Cursos ======================
    rol = "sin_rol"
    try:
        resp = requests.post(R2_URL, json={"username": usuario}, timeout=5)

        print("[R2] status:", resp.status_code)
        print("[R2] body:", resp.text)

        if resp.status_code == 200:
            r2_data = resp.json()
            rol = r2_data.get("rol", "sin_rol")
        else:
            rol = "error_r2"

    except Exception as e:
        print("[R2] Error:", str(e))
        rol = "error_r2"

    # ========= RESPUESTA FINAL =======================
    return jsonify({
        "ok": True,
        "msg": "Autenticación y autorización procesadas",
        "usuario": usuario,
        "rol": rol,
        "ip": ip,
        "mac": mac,
        "puerto": puerto
    }), 200


# ==========================================
# ARRANCAR SERVIDOR
# ==========================================
if _name_ == "_main_":
    print(f"\nPortal SDN escuchando en http://{PORTAL_IP}:{PORTAL_PORT}")
    app.run(host=PORTAL_IP, port=PORTAL_PORT, debug=False)