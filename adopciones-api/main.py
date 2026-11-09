"""API 2 - Adopciones: solicitudes de adopción. Consume la API de Mascotas vía HTTP/REST."""
import os
from datetime import datetime, timezone
from functools import lru_cache
from typing import Literal, Optional
from uuid import UUID

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr, Field
from supabase import Client, create_client

app = FastAPI(
    title="API de Adopciones - Huellas de Esperanza",
    description="Servicio dueño de la tabla `solicitudes`. Verifica y actualiza mascotas llamando a la API de Mascotas.",
    version="1.0.0",
)
app.add_middleware(CORSMiddleware, allow_origins=os.getenv("CORS_ORIGINS", "*").split(","),
                   allow_methods=["*"], allow_headers=["*"])

MASCOTAS_URL = os.getenv("MASCOTAS_API_URL", "http://localhost:8001").rstrip("/")
Estado = Literal["pendiente", "aprobada", "rechazada"]


@lru_cache
def db() -> Client:
    return create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])


def admin(x_api_key: Optional[str] = Header(None, description="Clave de administrador")):
    key = os.getenv("ADMIN_API_KEY")
    if not key or x_api_key != key:
        raise HTTPException(401, "API key inválida o ausente")


class SolicitudIn(BaseModel):
    mascota_id: UUID
    solicitante_nombre: str = Field(min_length=2, max_length=120)
    email: EmailStr
    telefono: Optional[str] = None
    tipo_vivienda: Optional[str] = None
    motivo: Optional[str] = Field(None, max_length=1000)


class DecisionIn(BaseModel):
    motivo_decision: Optional[str] = None


class SolicitudOut(BaseModel):
    id: UUID
    mascota_id: UUID
    solicitante_nombre: str
    email: str
    telefono: Optional[str] = None
    tipo_vivienda: Optional[str] = None
    motivo: Optional[str] = None
    estado: Estado
    motivo_decision: Optional[str] = None
    created_at: datetime
    mascota: Optional[dict] = None


# ---------- Cliente HTTP hacia la API de Mascotas ----------
async def mascota_get(mascota_id) -> dict:
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.get(f"{MASCOTAS_URL}/mascotas/{mascota_id}")
    except httpx.RequestError:
        raise HTTPException(503, "La API de Mascotas no está disponible")
    if r.status_code == 404:
        raise HTTPException(404, "La mascota no existe")
    if r.status_code >= 400:
        raise HTTPException(502, "Error consultando la API de Mascotas")
    return r.json()


async def mascota_set_estado(mascota_id, estado: str):
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.patch(f"{MASCOTAS_URL}/mascotas/{mascota_id}/estado", json={"estado": estado},
                              headers={"X-API-Key": os.getenv("ADMIN_API_KEY", "")})
    except httpx.RequestError:
        raise HTTPException(503, "La API de Mascotas no está disponible")
    if r.status_code >= 400:
        raise HTTPException(502, f"No se pudo actualizar la mascota ({r.status_code})")


def _solicitud_or_404(sid: UUID) -> dict:
    rows = db().table("solicitudes").select("*").eq("id", str(sid)).limit(1).execute().data
    if not rows:
        raise HTTPException(404, "Solicitud no encontrada")
    return rows[0]


def _now():
    return datetime.now(timezone.utc).isoformat()


# ---------- Endpoints ----------
@app.get("/health", tags=["Sistema"])
async def health():
    mascotas = "ok"
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            if (await c.get(f"{MASCOTAS_URL}/health")).status_code != 200:
                mascotas = "error"
    except httpx.RequestError:
        mascotas = "inaccesible"
    return {"status": "ok", "service": "adopciones-api", "mascotas_api": mascotas}


@app.post("/solicitudes", response_model=SolicitudOut, status_code=201, tags=["Solicitudes"])
async def crear_solicitud(data: SolicitudIn):
    mascota = await mascota_get(data.mascota_id)             # integración: consultar
    if mascota["estado"] != "disponible":                    # verificar disponibilidad
        raise HTTPException(409, "La mascota ya no está disponible para adopción")
    dup = (db().table("solicitudes").select("id").eq("mascota_id", str(data.mascota_id))
           .eq("email", data.email).eq("estado", "pendiente").execute().data)
    if dup:
        raise HTTPException(409, "Ya tienes una solicitud pendiente para esta mascota")
    row = db().table("solicitudes").insert({**data.model_dump(mode="json"), "estado": "pendiente"}).execute().data[0]
    return {**row, "mascota": mascota}


@app.get("/solicitudes", response_model=list[SolicitudOut], tags=["Administración"], dependencies=[Depends(admin)])
async def listar_solicitudes(estado: Optional[Estado] = None, mascota_id: Optional[UUID] = None):
    q = db().table("solicitudes").select("*").order("created_at", desc=True)
    if estado:
        q = q.eq("estado", estado)
    if mascota_id:
        q = q.eq("mascota_id", str(mascota_id))
    rows, cache = q.execute().data, {}
    for r in rows:                                           # enriquecer con datos de la mascota
        mid = r["mascota_id"]
        if mid not in cache:
            try:
                cache[mid] = await mascota_get(mid)
            except HTTPException:
                cache[mid] = None
        r["mascota"] = cache[mid]
    return rows


@app.get("/solicitudes/{solicitud_id}", response_model=SolicitudOut, tags=["Solicitudes"])
async def obtener_solicitud(solicitud_id: UUID):
    row = _solicitud_or_404(solicitud_id)
    try:
        row["mascota"] = await mascota_get(row["mascota_id"])
    except HTTPException:
        row["mascota"] = None
    return row


@app.patch("/solicitudes/{solicitud_id}/aprobar", response_model=SolicitudOut, tags=["Administración"],
           dependencies=[Depends(admin)])
async def aprobar(solicitud_id: UUID, data: DecisionIn = DecisionIn()):
    sol = _solicitud_or_404(solicitud_id)
    if sol["estado"] != "pendiente":
        raise HTTPException(409, f"La solicitud ya fue {sol['estado']}")
    mascota = await mascota_get(sol["mascota_id"])           # re-verificar disponibilidad
    if mascota["estado"] != "disponible":
        raise HTTPException(409, "La mascota ya fue adoptada")

    # 1) Reservar en BD: el índice único parcial impide dos aprobadas para la misma mascota
    try:
        updated = (db().table("solicitudes")
                   .update({"estado": "aprobada", "motivo_decision": data.motivo_decision, "updated_at": _now()})
                   .eq("id", str(solicitud_id)).eq("estado", "pendiente").execute().data)
    except Exception as e:
        if "23505" in str(e) or "duplicate" in str(e).lower():
            raise HTTPException(409, "La mascota ya tiene una adopción aprobada")
        raise
    if not updated:
        raise HTTPException(409, "La solicitud cambió de estado, recarga e intenta de nuevo")

    # 2) Actualizar la mascota en la API 1; si falla, compensar (rollback manual)
    try:
        await mascota_set_estado(sol["mascota_id"], "adoptada")
    except HTTPException:
        db().table("solicitudes").update({"estado": "pendiente", "motivo_decision": None, "updated_at": _now()}) \
            .eq("id", str(solicitud_id)).execute()
        raise

    # 3) Rechazar automáticamente las demás pendientes de esa mascota
    db().table("solicitudes").update(
        {"estado": "rechazada", "motivo_decision": "La mascota fue adoptada por otra solicitud",
         "updated_at": _now()}).eq("mascota_id", sol["mascota_id"]).eq("estado", "pendiente").execute()
    return {**updated[0], "mascota": {**mascota, "estado": "adoptada"}}


@app.patch("/solicitudes/{solicitud_id}/rechazar", response_model=SolicitudOut, tags=["Administración"],
           dependencies=[Depends(admin)])
async def rechazar(solicitud_id: UUID, data: DecisionIn = DecisionIn()):
    sol = _solicitud_or_404(solicitud_id)
    if sol["estado"] != "pendiente":
        raise HTTPException(409, f"La solicitud ya fue {sol['estado']}")
    return (db().table("solicitudes")
            .update({"estado": "rechazada", "motivo_decision": data.motivo_decision, "updated_at": _now()})
            .eq("id", str(solicitud_id)).execute().data[0])
