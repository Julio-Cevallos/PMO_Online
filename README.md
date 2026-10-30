# PMO Online

Plataforma web y app móvil para planificar proyectos con diagramas de Gantt, capturar avances en campo (incluso sin conexión) mediante formularios dinámicos y sincronizarlos. Proyecto universitario (ESPOL, Ingeniería de Software I). Backend en Django, web en React, app móvil en React Native / Expo, con PostgreSQL.

> Estado actual: **backend** con usuarios, roles, jerarquía y entidades con miembros, y **web** con login, registro, menú lateral, entidades (lista, detalle, miembros, creación y archivado) y tipos de entidad. Faltan formularios, Gantt, auditoría, sincronización y la app móvil.

> **¿Vas a trabajar en el código?** Sigue la [guía de desarrollo](GUIA_DESARROLLO.md): herramientas a instalar, base de datos local, conexión con DBeaver, backend, web, flujo de Git y problemas frecuentes.

## Estructura

```
backend/             API Django + Django REST Framework
  accounts/          usuarios, login, bloqueo, roles, permisos y niveles
  entities/          tipos de entidad, entidades, miembros, portafolios (grupos de entidades) e invitaciones
  audit/             historial de auditoría (solo se inserta; no se edita ni se borra)
web/                 React + Vite (login, registro, entidades y miembros)
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

Abre http://localhost:5173 (debe ser ese puerto: el backend solo permite CORS desde él). Desde ahí puedes crear una cuenta e iniciar sesión. Con sesión iniciada verás un menú lateral y la pantalla **Entidades**: el Admin ve todas las entidades y los demás miembros, las suyas con su rol. Desde la lista abres el **detalle** de una entidad: sus datos (editables si tu rol lo permite) y, si tu rol puede ver miembros, la pestaña **Miembros**, donde quien tiene permiso agrega una cuenta existente (escribe el usuario o lo elige de una lista de sugerencias, hasta 10: el Admin ve todas las cuentas y el Responsable solo a quienes comparten con él otra entidad; el servidor comprueba que exista) y le envía una **invitación**, o crea una cuenta nueva (el nombre de usuario no admite espacios). Las invitaciones pendientes se ven debajo de la tabla de miembros y se pueden cancelar; la persona invitada las ve en **Invitaciones** (con un contador en el menú) y las acepta o rechaza, cambia roles y desactiva o reactiva personas (solo con roles de nivel menor al propio). Con sesión iniciada, el menú **Portafolios** (para quien pertenece a alguno o puede crearlos) lista tus portafolios; en cada uno hay pestañas **Entidades**, **Miembros** (invitar, cambiar rol, desactivar, cancelar invitaciones), **Historial** y **Datos**. Al crear una entidad eliges el portafolio, y los Gestores pueden **moverla** a otro desde su pestaña Datos. Las invitaciones a portafolios llegan a **Invitaciones**, junto con las de entidades. Quien gestiona usuarios (el **Admin** y el **superusuario**) ve en el menú **Usuarios**: lista las cuentas (con filtro de activas), crea cuentas nuevas, edita datos, desactiva o reactiva y desbloquea cuentas bloqueadas por intentos fallidos. Solo el **superusuario** ve el interruptor *Administrador* para dar o quitar el rol Admin; el Admin no ve cuentas de superusuario. El **Admin** y el **superusuario** ven además **Auditoría** en el menú: el historial de la plataforma con filtros por categoría, tipo de acción y fechas, y el detalle de cada evento (qué campos cambiaron, antes y después, y la IP). El **Responsable** y el **Auditor** de una entidad ven el historial de la suya en la pestaña **Historial** de su detalle. El **Admin** además tiene el botón **Nueva entidad** (al crearla abre su pestaña Miembros para agregar al responsable), la sección **Archivar entidad** en la pestaña Datos y, en el menú, **Tipos de entidad**, donde crea, edita, desactiva y elimina tipos. Una cuenta recién registrada no ve ninguna entidad hasta que la agreguen (consulta el flujo de ejemplo más abajo).

Si cambias la API, regenera los tipos: `cd packages/api-client`, `npm install` y `npm run generate`.

## Probar la API en Swagger

1. `POST /api/auth/token/` — inicia sesión (con el superusuario para probar la administración) y copia el valor de `access`.
2. Botón **Authorize** (arriba a la derecha): pega el token sin la palabra `Bearer`.
3. Prueba `GET /api/auth/me/` y los demás endpoints protegidos.

**Flujo de ejemplo para empezar a usar el sistema:**

1. Con el superusuario: `POST /api/users/` con `"is_admin": true` para crear al primer Admin.
2. Con el Admin (o con un Moderador): `POST /api/portfolios/` para crear un portafolio (grupo de entidades) y `POST /api/entities/` con `"portafolio": <id>` para crear una entidad en él (por ejemplo, un Proyecto; consulta los tipos en `GET /api/entity-types/`). Sin `portafolio`, la entidad va al **portafolio personal** de quien la crea («Mis entidades», se crea solo).
3. Con el Admin: `POST /api/entities/{id}/members/` con `{"new_user": {...}, "rol": <id de "Responsable de entidad">}` (los roles están en `GET /api/roles/`).
4. Con el Responsable: `POST /api/entities/{id}/members/` para crear la cuenta de alguien nuevo con un rol de menor nivel, o `POST /api/entities/{id}/invitations/` con `{"username", "rol"}` para invitar a una cuenta que ya existe. La persona invitada la ve en `GET /api/invitations/` y la acepta (`POST /api/invitations/{id}/accept/`) o la rechaza (`.../reject/`); solo al aceptar entra como miembro.

Los pasos 2 a 4 también se pueden hacer desde la web: **Entidades → Nueva entidad**, y luego la pestaña **Miembros**.

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
| `GET/PUT/PATCH /api/auth/me/` | JWT | Perfil propio. Incluye, solo de lectura, `is_admin`, `is_superuser` y `global_permissions` (para que la web decida qué menús mostrar) |
| `POST /api/auth/password/change/` | JWT | Cambio de contraseña |
| `GET/POST /api/users/` | rol Admin | Listar (filtro `?is_active=`) y crear usuarios |
| `GET/PATCH /api/users/{id}/` | rol Admin | Ver y editar un usuario (datos, `is_active` y los roles globales `is_moderator` e `is_admin`; no se borran ni cambia su clave). `is_moderator` lo dan el Admin y el superusuario; `is_admin`, solo el superusuario |
| `POST /api/users/{id}/unlock/` | rol Admin | Desbloquear una cuenta bloqueada por intentos fallidos |
| `GET /api/permissions/` | rol Admin | Catálogo de permisos asignables, con su ámbito (`global` o `entidad`) |
| `GET/POST /api/roles/` | rol Admin | Listar y crear roles (los nuevos son siempre por entidad y exigen `nivel`) |
| `GET/PATCH/DELETE /api/roles/{id}/` | rol Admin | Ver, editar (nombre, permisos y niveles) y eliminar un rol (`409` si tiene miembros) |
| `GET/POST /api/entity-types/` | ver: miembros y Admin; escribir: Admin | Tipos de entidad (Proyecto, Sucursal…) |
| `GET/PATCH/DELETE /api/entity-types/{id}/` | ídem | Un tipo (`409` al eliminar si tiene entidades; se puede desactivar con `activo`) |
| `GET/POST /api/entities/` | autenticado / Admin, Moderador o quien tenga `create_portfolio_entities` | Entidades que ves: aquellas donde eres miembro y las de tus portafolios (el Admin ve todas). Crear: en un portafolio donde tengas ese permiso o, sin `portafolio`, en tu portafolio personal (Admin y Moderador). Filtros `?tipo=`, `?estado=` y `?portafolio=`. Cada entidad indica su `portafolio`, `mi_rol` y lo que puedes hacer en ella (`puede_editar`, `puede_ver_miembros`, `puede_gestionar_miembros`, `puede_ver_historial`, `puede_archivar`, `puede_mover`) |
| `GET/PATCH /api/entities/{id}/` | miembros o portafolio | Ver y editar nombre y descripción (con `edit_portfolio_entities` o `edit_entity`). Archivar (`estado`) con `archive_portfolio_entities` (Gestor y Admin); no se borran |
| `POST /api/entities/{id}/move/` | `move_portfolio_entities` | Mueve la entidad a otro portafolio: `{"portafolio": id}`. Hace falta poder crear entidades en el destino (el Admin puede en cualquiera) |
| `GET/POST /api/portfolios/` | autenticado / Admin o Moderador | Portafolios que ves (el Admin, todos) y crear uno (quien lo crea queda como Gestor). Cada portafolio indica `total_entidades`, `mi_rol` y tus capacidades |
| `GET/PATCH/DELETE /api/portfolios/{id}/` | miembros | Ver, editar (`edit_portfolio`) y eliminar un portafolio vacío (`409` si tiene entidades; el personal no se elimina ni se renombra) |
| `GET /api/portfolios/{id}/members/` | ver el portafolio | Miembros (`?activa=false\|todas`) |
| `PATCH/DELETE /api/portfolios/{id}/members/{id}/` | `manage_portfolio_members` | Cambiar rol o activar/desactivar (`DELETE` desactiva). Nivel igual o menor al propio; no la propia membresía; siempre queda un Gestor activo (`409`) |
| `GET /api/portfolios/{id}/assignable-roles/` | `manage_portfolio_members` | Roles de portafolio que puedes asignar |
| `GET/POST /api/portfolios/{id}/invitations/` | ver / `manage_portfolio_members` | Invitaciones del portafolio e invitar a una cuenta existente: `{"username", "rol"}` (mismas reglas que las de entidad) |
| `DELETE /api/portfolios/{id}/invitations/{id}/` | `manage_portfolio_members` | Cancela una invitación pendiente |
| `GET /api/portfolio-invitations/` y `POST .../{id}/accept\|reject/` | la persona invitada | Mis invitaciones a portafolios; al aceptar entra con el rol invitado |
| `GET/POST /api/entities/{id}/members/` | ver y gestionar miembros | Listar miembros y crear la cuenta de una persona nueva y sumarla: `{"new_user": {...}, "rol"}`. Una cuenta que ya existe no se suma directo: se invita (siguiente fila) |
| `GET/POST /api/entities/{id}/invitations/` | ver miembros / gestionar miembros | Invitaciones de la entidad (`?estado=pendiente` por defecto, `aceptada`, `rechazada`, `cancelada` o `todas`) e invitar a una cuenta existente: `{"username", "rol"}` (`404` si no existe, `409` si ya es miembro o ya tiene una invitación pendiente) |
| `DELETE /api/entities/{id}/invitations/{id}/` | gestionar miembros | Cancela una invitación pendiente (queda como `cancelada`) |
| `GET /api/invitations/` | autenticado | Mis invitaciones pendientes |
| `POST /api/invitations/{id}/accept/` y `/reject/` | la persona invitada | Aceptar (crea o reactiva su membresía con el rol invitado; `409` si la entidad está archivada) o rechazar |
| `GET/PATCH/DELETE /api/entities/{id}/members/{id}/` | ídem | Ver, cambiar rol o activar o desactivar (`DELETE` desactiva) |
| `GET /api/entities/{id}/candidates/?q=` | quien gestiona miembros | Sugiere cuentas para invitar por usuario, nombre o apellido (máximo 10, por usuario). Es solo una ayuda: `invitations` acepta cualquier usuario que exista. El Admin busca entre todas las cuentas (menos superusuarios); los demás, solo entre quienes comparten con ellos otra entidad. Nunca salen el propio usuario, cuentas desactivadas ni miembros activos de la entidad |
| `GET /api/entities/{id}/assignable-roles/` | quien gestiona miembros | Roles que puedes asignar en esa entidad según tu nivel, de mayor a menor (para el selector de rol) |

| `GET /api/audit/` | Admin, Responsable o Auditor | Historial de auditoría, solo lectura, del más reciente al más antiguo y paginado. Cada persona ve solo lo que le corresponde (ver abajo). Filtros: `?usuario=`, `?entidad=`, `?accion=` (prefijo, p. ej. `miembro.`), `?categoria=`, `?objeto_tipo=`, `?objeto_id=`, `?desde=` y `?hasta=` (fechas `AAAA-MM-DD`) |
| `GET /api/audit/{id}/` | ídem | Un evento con sus cambios (`antes` y `despues` por campo) |

## Auditoría

Cada cambio importante deja un evento en el historial **dentro de la misma transacción**: si no se puede registrar, el cambio tampoco se guarda. Los eventos no se editan ni se borran: lo impide el modelo y un *trigger* de PostgreSQL (creado por la migración `audit.0002`). Las contraseñas nunca se guardan; los campos sensibles aparecen como `[oculto]`.

- **Qué se registra hoy:** inicios de sesión, bloqueos y desbloqueos de cuentas, registro y alta de usuarios, edición de perfil, cambios de clave, rol Admin, activación y desactivación, roles (crear, editar, eliminar), tipos de entidad, entidades (crear, editar, archivar, reactivar) y miembros (agregar, cambiar rol, desactivar, reactivar). Los intentos fallidos de login no se registran uno a uno: solo el bloqueo resultante.
- **Categorías y quién las ve:** `sistema` (usuarios, sesiones y roles) y `entidad` (tipos, entidades y miembros) las ve quien tenga el permiso `audit.view_system_log` (el Admin); los eventos de una entidad (`entidad` y, más adelante, `contenido`) los ven quienes tengan `audit.view_entity_log` en esa entidad (Responsable de entidad y Auditor). El superusuario lo ve todo.
- **Dirección IP:** se toma de `REMOTE_ADDR`. Detrás de un proxy de confianza activa `AUDIT_TRUST_PROXY=true` en `backend/.env` para usar `X-Forwarded-For`; no lo actives si el servidor está expuesto directamente (la cabecera se puede falsificar).
- Limitación conocida: el trigger bloquea `UPDATE` y `DELETE`, no `TRUNCATE`; quien tenga acceso de administrador a la base de datos puede vaciar la tabla.

## Roles y superusuario

- **Superusuario:** solo para desarrolladores. Ve y puede todo y es el único que crea Admins (`is_admin: true` en `/api/users/`). Se crea **únicamente** desde la consola del servidor con `createsuperuser`: ninguna ruta de la API ni el registro pueden dar ese privilegio.
- **Moderador:** rol global, debajo del Admin, que el Admin (o el superusuario) asigna desde **Usuarios**. Puede **crear portafolios y entidades por su cuenta**: sin elegir portafolio, sus entidades van a su **portafolio personal**, donde es Gestor. No gestiona usuarios, roles ni tipos de entidad, ni ve la auditoría global. Quitarle el rol solo le quita crear: sus membresías en portafolios se conservan.
- **Portafolios:** un portafolio agrupa entidades que varias personas gestionan **en conjunto**. Cada entidad pertenece a uno solo y se puede mover a otro. Dentro de un portafolio hay dos roles: **Gestor del portafolio** (todo: editar el portafolio y sus entidades, crear, archivar, mover, gestionar los miembros de las entidades y del portafolio, ver el historial) y **Coordinador** (ver todo el portafolio, crear y editar entidades, gestionar los miembros de las entidades y ver el historial; no archiva, no mueve ni gestiona los miembros del portafolio). Los roles de portafolio **no dependen del rol global**: cualquier cuenta puede ser Coordinador. Sus permisos son de ámbito `portafolio` y el Admin puede ajustarlos con `PATCH /api/roles/{id}/` (o crear roles nuevos con `"ambito": "portafolio"`). Un Gestor puede nombrar a otro Gestor (los pares pueden nombrarse). El Admin ve y puede todo en todos los portafolios. Ninguno ve el contenido de las entidades (punto abierto).
- **Admin:** rol global que gestiona usuarios (crear, editar, desactivar, desbloquear), roles, tipos de entidad y entidades. No puede crear Admins ni ver o tocar superusuarios. El rol se crea solo al ejecutar `migrate`.
- **Responsable de entidad, Planificador, Colaborador (antes «Operario de campo»; al migrar se renombra solo, con sus miembros) y Auditor:** existen desde `migrate` y se asignan por entidad (proyecto, sucursal…) mediante la membresía. El Admin puede editar sus permisos y crear roles nuevos en `/api/roles/`.
- **Entidades:** las crea el Admin, un Moderador o quien tenga permiso de crear en un portafolio; cada entidad es de un tipo (`Proyecto` y `Sucursal` vienen creados, y el Admin puede crear más). Se archivan, no se borran. Cada persona ve solo las entidades donde es miembro; una persona tiene un solo rol por entidad.
- **Miembros y jerarquía:** el Responsable de entidad puede crear cuentas y sumar personas a su entidad con un rol de nivel **menor** al suyo (también hace falta el permiso de gestionar miembros). Nadie asigna un rol de su mismo nivel o mayor ni modifica su propia membresía. El Auditor solo lo nombra el Responsable. El Admin y el superusuario gestionan miembros en cualquier entidad; eso no les da acceso al contenido de las entidades (decisión pendiente).
- **Niveles:** cada rol por entidad tiene un `nivel` (1 a 99; más alto, más poder) y un `nivel_minimo_para_asignar`. Quien tenga un nivel mayor al de un rol, y alcance ese mínimo, puede asignarlo dentro de su entidad. Niveles iniciales: Responsable de entidad 40, Planificador 30, Auditor 20 y Colaborador 10. El Auditor solo lo asigna el Responsable. El Admin los ajusta con `PATCH /api/roles/{id}/`; el rol `Admin` es global y no tiene nivel.
- **Reglas de los roles:** `Admin`, `Moderador` y los tres roles anteriores son del sistema (no se eliminan; `Admin` y `Moderador` están bloqueados del todo, los otros admiten cambiar permisos pero no el nombre). Un rol por entidad solo recibe permisos del catálogo con ámbito `entidad`; los permisos globales (`manage_users`, `manage_roles`, `manage_types` y `manage_entities`) nunca se asignan a ellos, y solo los tiene el Admin. Los permisos por entidad (`edit_entity`, `view_members` y `manage_members`) los reciben al migrar el Responsable (los tres) y el Planificador (`view_members`); cada módulo nuevo irá agregando los suyos. Un rol con miembros no se puede eliminar.
- Un usuario recién registrado no tiene rol ni entidades: recibe `403` en la gestión de usuarios y roles, ve una lista vacía de entidades y no ve los tipos hasta que lo agreguen a una entidad.
- Los endpoints de administración (`/api/users/`, `/api/roles/`, `/api/entity-types/`, `/api/entities/`, los de miembros y `/api/audit/`) solo aceptan JSON.

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
