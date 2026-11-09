# 🐾 Huellas de Esperanza — Plataforma de adopción (SOA)

Examen 2 · Arquitectura Orientada a Servicios. Dos APIs FastAPI independientes + Supabase (PostgreSQL) + frontend web.

| Componente | Responsabilidad | Puerto local |
|---|---|---|
| `mascotas-api` | CRUD, consulta y disponibilidad de mascotas. Dueño de la tabla `mascotas` | 8001 |
| `adopciones-api` | Solicitudes y decisiones. Dueño de `solicitudes`. Llama a la API de Mascotas por HTTP | 8002 |
| `frontend` | Catálogo, formulario de solicitud y panel de administración | estático |
| `supabase/schema.sql` | Modelo de datos + datos de ejemplo | — |

Diagramas: [`docs/arquitectura.md`](docs/arquitectura.md). Swagger: `/docs` en cada API.

## Reglas de negocio
- Solo se crean solicitudes sobre mascotas **disponibles** (la API 2 consulta a la API 1).
- Aprobar → la mascota pasa a `adoptada` (la API 2 llama `PATCH /mascotas/{id}/estado`) y las demás solicitudes pendientes se rechazan.
- **Nunca dos adopciones aprobadas**: índice único parcial en BD (`una_aprobada_por_mascota`) + re-verificación + compensación si falla la API de Mascotas.
- Endpoints de escritura/administración protegidos con `X-API-Key`.

## 1. Supabase
1. Crea un proyecto en supabase.com. 2. SQL Editor → pega y ejecuta `supabase/schema.sql`.
3. Settings → API: copia `Project URL` y la clave `service_role` (solo backend, ¡nunca en el frontend ni en Git!).

## 2. Local
```bash
cp mascotas-api/.env.example mascotas-api/.env      # completa los valores
cp adopciones-api/.env.example adopciones-api/.env
# Opción A: Docker
docker compose up --build
# Opción B: manual (dos terminales)
cd mascotas-api   && pip install -r requirements.txt && uvicorn main:app --port 8001 --env-file .env
cd adopciones-api && pip install -r requirements.txt && uvicorn main:app --port 8002 --env-file .env
# Frontend: abre frontend/index.html (o: python -m http.server 5500 -d frontend)
```
Swagger: http://localhost:8001/docs · http://localhost:8002/docs

## 3. Pruebas de integración (evidencia para entregar)
```bash
pip install -r tests/requirements.txt
ADMIN_API_KEY=tu-clave pytest -v tests/ | tee docs/evidencia_pruebas.txt
```
Cubre el proceso completo: solicitar → verificar disponibilidad → aprobar → mascota adoptada → rechazo automático → bloqueo de doble adopción. Toma además capturas de Swagger y del frontend.

## 4. Despliegue en la nube (Render, gratis)
1. Sube el repo a GitHub: `git init && git add . && git commit -m "Examen 2 SOA" && git remote add origin <url> && git push -u origin main`
2. Render → **New → Blueprint** → selecciona el repo (usa `render.yaml`) y define las variables en cada servicio.
   Orden: despliega primero `huellas-mascotas-api`, copia su URL pública y ponla en `MASCOTAS_API_URL` de `huellas-adopciones-api`.
3. En `frontend/index.html` cambia el objeto `API` a las URLs públicas, haz commit/push (Render redepliega el sitio estático).
4. Opcional: en producción restringe `CORS_ORIGINS` a la URL del frontend.
> En el plan gratis Render duerme los servicios tras inactividad: abre `/health` unos minutos antes de la sustentación.

## 5. Guion de socialización (7 min)
1. **Problema y solución (1')**: información dispersa → plataforma única.
2. **Arquitectura (1.5')**: diagrama; cada API con su tabla y responsabilidad (sin FK entre servicios).
3. **Comunicación (1.5')**: `GET /mascotas/{id}` y `PATCH /mascotas/{id}/estado`; manejo de caída del otro servicio (503) y compensación.
4. **Modelo de datos (1')**: 2 tablas, índice único parcial.
5. **Decisiones técnicas (1')**: FastAPI+Pydantic, Supabase, API key, Docker, Render.
6. **Demo (en vivo)**: solicitar → aprobar → ver mascota "adoptada" → intentar aprobar otra (409).

## Ideas para mejorar (si hay tiempo)
Autenticación JWT con Supabase Auth, notificación por correo al decidir, paginación, subida de fotos a Supabase Storage.
