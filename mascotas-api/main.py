"""API 1 - Mascotas: registro, consulta y disponibilidad de los animales."""
import os
from functools import lru_cache
from typing import Literal, Optional
from uuid import UUID

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from supabase import Client, create_client

app = FastAPI(
    title="API de Mascotas - Huellas de Esperanza",
    description="Servicio dueño de la tabla `mascotas`. Consulta pública y administración protegida con `X-API-Key`.",
    version="1.0.0",
)
app.add_middleware(CORSMiddleware, allow_origins=os.getenv("CORS_ORIGINS", "*").split(","),
                   allow_methods=["*"], allow_headers=["*"])

Especie = Literal["perro", "gato", "otro"]
Estado = Literal["disponible", "adoptada"]


@lru_cache
def db() -> Client:
    return create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])


def admin(x_api_key: Optional[str] = Header(None, description="Clave de administrador")):
    key = os.getenv("ADMIN_API_KEY")
    if not key or x_api_key != key:
        raise HTTPException(401, "API key inválida o ausente")


class MascotaIn(BaseModel):
    nombre: str = Field(min_length=1, max_length=80)
    especie: Especie
    raza: Optional[str] = None
    edad_meses: Optional[int] = Field(None, ge=0, le=360)
    sexo: Optional[Literal["macho", "hembra"]] = None
    tamano: Optional[Literal["pequeno", "mediano", "grande"]] = None
    descripcion: Optional[str] = None
    foto_url: Optional[str] = None


class MascotaOut(MascotaIn):
    id: UUID
    estado: Estado


class EstadoIn(BaseModel):
    estado: Estado


def _get_or_404(mascota_id: UUID) -> dict:
    rows = db().table("mascotas").select("*").eq("id", str(mascota_id)).limit(1).execute().data
    if not rows:
        raise HTTPException(404, "Mascota no encontrada")
    return rows[0]


@app.get("/health", tags=["Sistema"])
def health():
    return {"status": "ok", "service": "mascotas-api"}


@app.get("/mascotas", response_model=list[MascotaOut], tags=["Mascotas"])
def listar(especie: Optional[Especie] = None, estado: Optional[Estado] = None,
           q: Optional[str] = Query(None, description="Busca por nombre")):
    query = db().table("mascotas").select("*").order("created_at", desc=True)
    if especie:
        query = query.eq("especie", especie)
    if estado:
        query = query.eq("estado", estado)
    if q:
        query = query.ilike("nombre", f"%{q}%")
    return query.execute().data


@app.get("/mascotas/{mascota_id}", response_model=MascotaOut, tags=["Mascotas"])
def obtener(mascota_id: UUID):
    return _get_or_404(mascota_id)


@app.get("/mascotas/{mascota_id}/disponibilidad", tags=["Mascotas"])
def disponibilidad(mascota_id: UUID):
    m = _get_or_404(mascota_id)
    return {"id": m["id"], "estado": m["estado"], "disponible": m["estado"] == "disponible"}


@app.post("/mascotas", response_model=MascotaOut, status_code=201, tags=["Administración"],
          dependencies=[Depends(admin)])
def crear(data: MascotaIn):
    return db().table("mascotas").insert(data.model_dump()).execute().data[0]


@app.put("/mascotas/{mascota_id}", response_model=MascotaOut, tags=["Administración"],
         dependencies=[Depends(admin)])
def actualizar(mascota_id: UUID, data: MascotaIn):
    _get_or_404(mascota_id)
    return db().table("mascotas").update(data.model_dump()).eq("id", str(mascota_id)).execute().data[0]


@app.patch("/mascotas/{mascota_id}/estado", response_model=MascotaOut, tags=["Integración"],
           dependencies=[Depends(admin)],
           description="Lo consume la API de Adopciones para marcar una mascota como adoptada (o liberarla).")
def cambiar_estado(mascota_id: UUID, data: EstadoIn):
    _get_or_404(mascota_id)
    return db().table("mascotas").update({"estado": data.estado}).eq("id", str(mascota_id)).execute().data[0]


@app.delete("/mascotas/{mascota_id}", status_code=204, tags=["Administración"], dependencies=[Depends(admin)])
def eliminar(mascota_id: UUID):
    _get_or_404(mascota_id)
    db().table("mascotas").delete().eq("id", str(mascota_id)).execute()
