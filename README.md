# PMO Online

Aplicación de gestión de proyectos estilo Jira/Asana (proyecto universitario): API en Django, web en React y app móvil en Expo, con PostgreSQL.

> Estado actual: **backend** con usuarios y JWT, y **web** con login y registro. La app móvil aún no existe.

## Estructura

```
backend/             API Django + Django REST Framework
web/                 React + Vite (login y registro)
mobile/              Expo (pendiente)
packages/api-client/ Tipos TypeScript generados desde OpenAPI
docker-compose.yml   PostgreSQL 16
```

## Requisitos

| Herramienta | Versión | Para qué |
|---|---|---|
| [Python](https://www.python.org/downloads/) | 3.12 o superior (se probó con 3.14) | Backend |
| [Docker Desktop](https://www.docker.com/products/docker-desktop/) | con WSL 2 | PostgreSQL |
| [Git](https://git-scm.com/downloads) | cualquiera | Control de versiones |
| [Node.js](https://nodejs.org/) LTS | 20 o superior | Web y móvil (aún no se usa) |

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

# 4. Tablas
.\.venv\Scripts\python manage.py migrate

# 5. Usuario administrador (te pedirá nombre, correo y clave)
.\.venv\Scripts\python manage.py createsuperuser

# 6. Servidor
.\.venv\Scripts\python manage.py runserver
```

Luego abre:

- http://localhost:8000/api/docs/ — Swagger para probar la API.
- http://localhost:8000/admin/ — panel de administración.

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

1. `POST /api/auth/register/` — crea un usuario.
2. `POST /api/auth/token/` — inicia sesión y copia el valor de `access`.
3. Botón **Authorize** (arriba a la derecha): pega el token sin la palabra `Bearer`.
4. Prueba `GET /api/auth/me/` y los demás endpoints protegidos.

El access token dura 30 minutos. Para renovarlo usa `POST /api/auth/token/refresh/`.

## Endpoints disponibles

| Método y ruta | Acceso | Descripción |
|---|---|---|
| `POST /api/auth/register/` | público | Registro de usuario |
| `POST /api/auth/token/` | público | Login (devuelve access y refresh) |
| `POST /api/auth/token/refresh/` | público | Renueva el access token |
| `POST /api/auth/logout/` | público | Invalida el refresh token |
| `GET/PUT/PATCH /api/auth/me/` | JWT | Perfil propio |
| `POST /api/auth/password/change/` | JWT | Cambio de contraseña |

## Pruebas y calidad

Desde `backend/`:

```powershell
.\.venv\Scripts\python manage.py test      # pruebas automáticas
.\.venv\Scripts\ruff check .               # análisis de código
.\.venv\Scripts\ruff format .              # formateo
```

## Comandos útiles de Docker

```powershell
docker compose up -d       # iniciar PostgreSQL
docker compose stop        # detener (conserva los datos)
docker compose down -v     # eliminar contenedor Y datos
```

Para conectarte con DBeaver: servidor `localhost`, puerto `5432`, base de datos, usuario y clave los de tu `.env` de la raíz.
