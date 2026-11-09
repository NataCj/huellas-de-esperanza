"""Pruebas de integración end-to-end contra los servicios en ejecución.
Uso:  MASCOTAS_URL=... ADOPCIONES_URL=... ADMIN_API_KEY=... pytest -v tests/
"""
import os
import httpx
import pytest

M = os.getenv("MASCOTAS_URL", "http://localhost:8001")
A = os.getenv("ADOPCIONES_URL", "http://localhost:8002")
H = {"X-API-Key": os.getenv("ADMIN_API_KEY", "cambia-esta-clave")}
c = httpx.Client(timeout=30)


def solicitud(mid, email):
    return {"mascota_id": mid, "solicitante_nombre": "Test Persona", "email": email,
            "telefono": "3001234567", "tipo_vivienda": "casa", "motivo": "Prueba automatizada"}


@pytest.fixture(scope="module")
def mascota():
    r = c.post(f"{M}/mascotas", headers=H, json={"nombre": "TestPet", "especie": "perro"})
    assert r.status_code == 201, r.text
    m = r.json()
    yield m
    c.delete(f"{M}/mascotas/{m['id']}", headers=H)


def test_health_integrado():
    assert c.get(f"{A}/health").json()["mascotas_api"] == "ok"


def test_mascota_inexistente_se_rechaza():
    r = c.post(f"{A}/solicitudes", json=solicitud("00000000-0000-0000-0000-000000000000", "a@test.com"))
    assert r.status_code == 404


def test_proceso_completo_de_adopcion(mascota):
    mid = mascota["id"]
    assert c.get(f"{M}/mascotas/{mid}/disponibilidad").json()["disponible"] is True

    s1 = c.post(f"{A}/solicitudes", json=solicitud(mid, "uno@test.com"))
    s2 = c.post(f"{A}/solicitudes", json=solicitud(mid, "dos@test.com"))
    assert s1.status_code == 201 and s2.status_code == 201
    s1, s2 = s1.json(), s2.json()

    assert c.patch(f"{A}/solicitudes/{s1['id']}/aprobar").status_code == 401   # sin API key

    ok = c.patch(f"{A}/solicitudes/{s1['id']}/aprobar", headers=H)
    assert ok.status_code == 200 and ok.json()["estado"] == "aprobada"
    assert c.get(f"{M}/mascotas/{mid}").json()["estado"] == "adoptada"        # API 1 actualizada

    assert c.get(f"{A}/solicitudes/{s2['id']}").json()["estado"] == "rechazada"  # auto-rechazo
    assert c.patch(f"{A}/solicitudes/{s2['id']}/aprobar", headers=H).status_code == 409
    assert c.post(f"{A}/solicitudes", json=solicitud(mid, "tres@test.com")).status_code == 409


def test_rechazo_no_modifica_mascota():
    m = c.post(f"{M}/mascotas", headers=H, json={"nombre": "TestPet2", "especie": "gato"}).json()
    try:
        s = c.post(f"{A}/solicitudes", json=solicitud(m["id"], "x@test.com")).json()
        r = c.patch(f"{A}/solicitudes/{s['id']}/rechazar", headers=H, json={"motivo_decision": "Sin espacio"})
        assert r.json()["estado"] == "rechazada"
        assert c.get(f"{M}/mascotas/{m['id']}").json()["estado"] == "disponible"
    finally:
        c.delete(f"{M}/mascotas/{m['id']}", headers=H)
