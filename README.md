# PMO Online

Plataforma web y app móvil para planificar proyectos con diagramas de Gantt, capturar avances en campo (incluso sin conexión) mediante formularios dinámicos y sincronizarlos. Proyecto universitario (ESPOL, Ingeniería de Software I). Backend en Django, web en React, app móvil en React Native / Expo, con PostgreSQL.

> Estado actual: **backend** con usuarios, roles, jerarquía y entidades con miembros, y **web** con login y registro. Faltan formularios, Gantt, auditoría, sincronización, las pantallas web de administración y la app móvil.

## Estructura

```
backend/             API Django + Django REST Framework
  accounts/          usuarios, login, bloqueo, roles, permisos y niveles
  entities/          tipos de entidad, entidades y miembros
web/                 React + Vite (login y registro)
mobile/              Expo (pendiente)
packages/api-client/ Tipos TypeScript generados desde OpenAPI
docker-compose.yml   PostgreSQL 16
```

## Nombre del producto

El nombre no se escribe a mano en el código: se cambia en un solo lugar por plataforma.

| Plataforma | Dónde | Variable de entorno |
|---|---|---|
| Web | `web/src/config.ts` (`APP_NAME`) | `VITE_APP_NAME` en `web/.env` |
| Backend | `backend/config/settings.py` (`PROJECT_NAME`) | `PROJECT_NAME` en `backend/.env` |

Valor por defecto: `PMO Online`. La app móvil seguirá el mismo patrón.

## Requisitos

| Herramienta | Versión | Para qué |
|---|---|---|
| [Python](https://www.python.org/downloads/) | 3.12 o superior (se probó con 3.14) | Backend |
| [Docker Desktop](https://www.docker.com/products/docker-desktop/) | con WSL 2 | PostgreSQL |
| [Git](https://git-scm.com/downloads) | cualquiera | Control de versiones |
| [Node.js](https://nodejs.org/) LTS | 20 o superior | Web (y móvil, más adelante) |

## Puesta en marcha del backend

Desde la raíz del repositorio, en PowerShell:

```powershell
# 1. Variables de entorno (copiar y, si quieres, ajustar valores)
Copy-Item .env.example .env
Copy-Item backend\.env.example backend\.env
# En backend\.env cambia DJANGO_SECRET_KEY por un texto largo y aleatorio.

# 2. Base de datos
docker compose up -d

# 3. Entorno virtual e instalación de dependencias
cd backend
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt

# 4. Tablas y datos iniciales (roles, permisos y los tipos Proyecto y Sucursal)
.\.venv\Scripts\python manage.py migrate

# 5. Superusuario, solo para desarrolladores (te pedirá nombre, correo y clave)
.\.venv\Scripts\python manage.py createsuperuser

# 6. Servidor
.\.venv\Scripts\python manage.py runserver
```

Luego abre:

- http://localhost:8000/api/docs/ — Swagger para probar la API.
- http://localhost:8000/admin/ — panel de Django (solo superusuarios).

En VS Code, abre la carpeta raíz y pulsa **F5** (**Django: servidor (depurar)**) para ejecutar con depurador.

## Puesta en marcha de la web

Con el backend corriendo en el puerto 8000:

```powershell
cd web
npm install
npm run dev
```

Si PowerShell dice que la ejecución de scripts está deshabilitada, ejecuta una vez `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` o usa `npm.cmd` en lugar de `npm`.

Abre http://localhost:5173 (debe ser ese puerto: el backend solo permite CORS desde él). Desde ahí puedes crear una cuenta e iniciar sesión.

Si cambias la API, regenera los tipos: `cd packages/api-client`, `npm install` y `npm run generate`.

## Probar la API en Swagger

1. `POST /api/auth/token/` — inicia sesión (con el superusuario para probar la administración) y copia el valor de `access`.
2. Botón **Authorize** (arriba a la derecha): pega el token sin la palabra `Bearer`.
3. Prueba `GET /api/auth/me/` y los demás endpoints protegidos.

**Flujo de ejemplo para empezar a usar el sistema:**

1. Con el superusuario: `POST /api/users/` con `"is_admin": true` para crear al primer Admin.
2. Con el Admin: `POST /api/entities/` para crear una entidad (por ejemplo, un Proyecto; consulta los tipos en `GET /api/entity-types/`).
3. Con el Admin: `POST /api/entities/{id}/members/` con `{"new_user": {...}, "rol": <id de "Responsable de entidad">}` (los roles están en `GET /api/roles/`).
4. Con el Responsable: `POST /api/entities/{id}/members/` para sumar o crear al resto del equipo con roles de menor nivel.

`POST /api/auth/register/` crea una cuenta sin rol: no ve nada hasta que alguien la agregue a una entidad.

El access token dura 30 minutos. Para renovarlo usa `POST /api/auth/token/refresh/`.

**Bloqueo de cuenta.** El número de intentos y la duración se ajustan con `LOGIN_MAX_ATTEMPTS` (3) y `LOGIN_LOCKOUT_MINUTES` (15) en `backend/.env`. Un superusuario puede desbloquear una cuenta antes de tiempo desde `/admin/` (acción "Desbloquear cuentas seleccionadas"). El rol Admin lo hace con `POST /api/users/{id}/unlock/`.

## Endpoints disponibles

| Método y ruta | Acceso | Descripción |
|---|---|---|
| `POST /api/auth/register/` | público | Registro de usuario. No otorga privilegios: el usuario nuevo queda sin rol y no accede a nada hasta que un Admin le asigne acceso |
| `POST /api/auth/token/` | público | Login (devuelve access y refresh). Tras 3 intentos fallidos la cuenta se bloquea 15 minutos y responde `423` aunque la clave sea correcta |
| `POST /api/auth/token/refresh/` | público | Renueva el access token |
| `POST /api/auth/logout/` | público | Invalida el refresh token |
| `GET/PUT/PATCH /api/auth/me/` | JWT | Perfil propio |
| `POST /api/auth/password/change/` | JWT | Cambio de contraseña |
| `GET/POST /api/users/` | rol Admin | Listar (filtro `?is_active=`) y crear usuarios |
| `GET/PATCH /api/users/{id}/` | rol Admin | Ver y editar un usuario (datos y `is_active`; no se borran ni cambia su clave) |
| `POST /api/users/{id}/unlock/` | rol Admin | Desbloquear una cuenta bloqueada por intentos fallidos |
| `GET /api/permissions/` | rol Admin | Catálogo de permisos asignables, con su ámbito (`global` o `entidad`) |
| `GET/POST /api/roles/` | rol Admin | Listar y crear roles (los nuevos son siempre por entidad y exigen `nivel`) |
| `GET/PATCH/DELETE /api/roles/{id}/` | rol Admin | Ver, editar (nombre, permisos y niveles) y eliminar un rol (`409` si tiene miembros) |
| `GET/POST /api/entity-types/` | ver: miembros y Admin; escribir: Admin | Tipos de entidad (Proyecto, Sucursal…) |
| `GET/PATCH/DELETE /api/entity-types/{id}/` | ídem | Un tipo (`409` al eliminar si tiene entidades; se puede desactivar con `activo`) |
| `GET/POST /api/entities/` | autenticado / Admin | Mis entidades (el Admin ve todas) y crear una entidad (solo Admin). Filtros `?tipo=` y `?estado=` |
| `GET/PATCH /api/entities/{id}/` | miembros | Ver y editar nombre y descripción (con el permiso de editar). Archivar (`estado`) solo el Admin; no se borran |
| `GET/POST /api/entities/{id}/members/` | ver y gestionar miembros | Listar miembros y agregar uno: `{"username", "rol"}` (cuenta existente) o `{"new_user": {...}, "rol"}` (crea la cuenta) |
| `GET/PATCH/DELETE /api/entities/{id}/members/{id}/` | ídem | Ver, cambiar rol o activar o desactivar (`DELETE` desactiva) |

## Roles y superusuario

- **Superusuario:** solo para desarrolladores. Ve y puede todo y es el único que crea Admins (`is_admin: true` en `/api/users/`). Se crea **únicamente** desde la consola del servidor con `createsuperuser`: ninguna ruta de la API ni el registro pueden dar ese privilegio.
- **Admin:** rol global que gestiona usuarios (crear, editar, desactivar, desbloquear), roles, tipos de entidad y entidades. No puede crear Admins ni ver o tocar superusuarios. El rol se crea solo al ejecutar `migrate`.
- **Responsable de entidad, Planificador, Operario de campo y Auditor:** existen desde `migrate` y se asignan por entidad (proyecto, sucursal…) mediante la membresía. El Admin puede editar sus permisos y crear roles nuevos en `/api/roles/`.
- **Entidades:** las crea el Admin; cada entidad es de un tipo (`Proyecto` y `Sucursal` vienen creados, y el Admin puede crear más). Se archivan, no se borran. Cada persona ve solo las entidades donde es miembro; una persona tiene un solo rol por entidad.
- **Miembros y jerarquía:** el Responsable de entidad puede crear cuentas y sumar personas a su entidad con un rol de nivel **menor** al suyo (también hace falta el permiso de gestionar miembros). Nadie asigna un rol de su mismo nivel o mayor ni modifica su propia membresía. El Auditor solo lo nombra el Responsable. El Admin y el superusuario gestionan miembros en cualquier entidad; eso no les da acceso al contenido de las entidades (decisión pendiente).
- **Niveles:** cada rol por entidad tiene un `nivel` (1 a 99; más alto, más poder) y un `nivel_minimo_para_asignar`. Quien tenga un nivel mayor al de un rol, y alcance ese mínimo, puede asignarlo dentro de su entidad. Niveles iniciales: Responsable de entidad 40, Planificador 30, Auditor 20 y Operario de campo 10. El Auditor solo lo asigna el Responsable. El Admin los ajusta con `PATCH /api/roles/{id}/`; el rol `Admin` es global y no tiene nivel.
- **Reglas de los roles:** `Admin` y los tres roles anteriores son del sistema (no se eliminan; solo `Admin` está bloqueado del todo, los otros admiten cambiar permisos pero no el nombre). Un rol por entidad solo recibe permisos del catálogo con ámbito `entidad`; los permisos globales (`manage_users`, `manage_roles`, `manage_types` y `manage_entities`) nunca se asignan a ellos, y solo los tiene el Admin. Los permisos por entidad (`edit_entity`, `view_members` y `manage_members`) los reciben al migrar el Responsable (los tres) y el Planificador (`view_members`); cada módulo nuevo irá agregando los suyos. Un rol con miembros no se puede eliminar.
- Un usuario recién registrado no tiene rol ni entidades: recibe `403` en la gestión de usuarios y roles, ve una lista vacía de entidades y no ve los tipos hasta que lo agreguen a una entidad.
- Los endpoints de administración (`/api/users/`, `/api/roles/`, `/api/entity-types/`, `/api/entities/` y los de miembros) solo aceptan JSON.

## Pruebas y calidad

Desde `backend/`:

```powershell
.\.venv\Scripts\python manage.py test      # pruebas automáticas (unos 5 segundos)
.\.venv\Scripts\ruff check .               # análisis de código
.\.venv\Scripts\ruff format .              # formateo
```

Las pruebas usan un hasher de contraseñas rápido (solo al ejecutar `manage.py test`, configurado en `config/settings.py`); el servidor normal sigue usando PBKDF2.

## Comandos útiles de Docker

```powershell
docker compose up -d       # iniciar PostgreSQL
docker compose stop        # detener (conserva los datos)
docker compose down -v     # eliminar contenedor Y datos
```

Para conectarte con DBeaver: servidor `localhost`, puerto `5432`, base de datos, usuario y clave los de tu `.env` de la raíz.
