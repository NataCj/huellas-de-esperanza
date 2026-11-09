-- Ejecutar en Supabase > SQL Editor
create extension if not exists "pgcrypto";

-- Tabla propiedad de la API 1 (Mascotas)
create table if not exists mascotas (
  id          uuid primary key default gen_random_uuid(),
  nombre      text not null,
  especie     text not null check (especie in ('perro','gato','otro')),
  raza        text,
  edad_meses  int  check (edad_meses >= 0),
  sexo        text check (sexo in ('macho','hembra')),
  tamano      text check (tamano in ('pequeno','mediano','grande')),
  descripcion text,
  foto_url    text,
  estado      text not null default 'disponible' check (estado in ('disponible','adoptada')),
  created_at  timestamptz not null default now()
);

-- Tabla propiedad de la API 2 (Adopciones)
-- mascota_id es una referencia LOGICA (sin FK): cada servicio es dueño de sus datos.
create table if not exists solicitudes (
  id                 uuid primary key default gen_random_uuid(),
  mascota_id         uuid not null,
  solicitante_nombre text not null,
  email              text not null,
  telefono           text,
  tipo_vivienda      text,
  motivo             text,
  estado             text not null default 'pendiente' check (estado in ('pendiente','aprobada','rechazada')),
  motivo_decision    text,
  created_at         timestamptz not null default now(),
  updated_at         timestamptz not null default now()
);

-- Regla de negocio garantizada por la BD: una sola adopción aprobada por mascota
create unique index if not exists una_aprobada_por_mascota
  on solicitudes (mascota_id) where estado = 'aprobada';
create index if not exists idx_solicitudes_mascota on solicitudes (mascota_id);

-- Las APIs usan la service_role key (ignora RLS); bloqueamos acceso directo anónimo.
alter table mascotas    enable row level security;
alter table solicitudes enable row level security;

insert into mascotas (nombre, especie, raza, edad_meses, sexo, tamano, descripcion, foto_url) values
 ('Luna','perro','Criolla',18,'hembra','mediano','Juguetona, sociable y vacunada.','https://images.unsplash.com/photo-1543466835-00a7907e9de1?w=600'),
 ('Milo','gato','Mestizo',8,'macho','pequeno','Tranquilo, ideal para apartamento.','https://images.unsplash.com/photo-1514888286974-6c03e2ca1dba?w=600'),
 ('Rocky','perro','Labrador',36,'macho','grande','Obediente, bueno con niños.','https://images.unsplash.com/photo-1587300003388-59208cc962cb?w=600'),
 ('Nala','gato','Siamés',24,'hembra','pequeno','Cariñosa y esterilizada.','https://images.unsplash.com/photo-1573865526739-10659fec78a5?w=600');
