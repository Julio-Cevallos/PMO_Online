# Guía para desarrollar en PMO Online

Guía para que cada integrante del equipo tenga el mismo entorno y pueda trabajar en el código. Los comandos son para **Windows 11 con PowerShell**. Si algo falla, revisa la sección [Problemas frecuentes](#problemas-frecuentes).

## 1. Qué instalar

| Herramienta | Versión | Enlace | Verificar |
|---|---|---|---|
| Git | cualquiera | https://git-scm.com/downloads | `git --version` |
| Python | 3.12 o superior (el proyecto se probó con 3.14) | https://www.python.org/downloads/ | `python --version` |
| Node.js LTS | 20 o superior (probado con 24) | https://nodejs.org/ | `node --version` y `npm --version` |
| Docker Desktop | con WSL 2 activado | https://www.docker.com/products/docker-desktop/ | `docker --version` |
| VS Code (recomendado) | cualquiera | https://code.visualstudio.com/ | — |
| DBeaver (opcional, para ver la base de datos) | Community | https://dbeaver.io/download/ | — |

Al instalar Python, marca la casilla **Add python.exe to PATH**. Docker Desktop debe estar **abierto** (ícono de la ballena en la barra) antes de usar `docker compose`.

**Extensiones de VS Code sugeridas:** Python, Debugpy (Python Debugger), Ruff (Astral) y Docker.

PowerShell puede bloquear `npm` con el error "la ejecución de scripts está deshabilitada". Se arregla una sola vez con:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

## 2. Obtener el código

```powershell
git clone https://github.com/<organización>/<repositorio>.git PMO_Online
cd PMO_Online
git checkout main
```

Trabaja siempre en una rama propia, no directamente en `main` (ver [Flujo de trabajo con Git](#7-flujo-de-trabajo-con-git)).

## 3. Variables de entorno

Los archivos `.env` tienen contraseñas y **nunca se suben a Git** (están en `.gitignore`). Cada quien crea los suyos a partir de los `.env.example`:

```powershell
Copy-Item .env.example .env
Copy-Item backend\.env.example backend\.env
```

- `.env` (raíz): lo lee Docker Compose para crear la base de datos (`POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`).
- `backend\.env`: lo lee Django. Las variables `POSTGRES_*` deben tener **los mismos valores** que el `.env` de la raíz.
- En `backend\.env` cambia `DJANGO_SECRET_KEY` por un texto largo y aleatorio. Para generar uno:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(50))"
```

Los valores por defecto (`pmo` / `pmo` / `pmo_dev`) sirven para desarrollo local. No uses estas credenciales en ningún servidor real.

## 4. Base de datos (PostgreSQL en Docker)

**Idea:** cada integrante tiene **su propia base de datos local**, dentro de un contenedor Docker. No se comparte una base entre el equipo: los datos de prueba son personales y la estructura (tablas) se genera con las migraciones del código.

*(Comparación con ASP.NET: es como tener tu SQL Server local, pero en un contenedor; las migraciones de Django equivalen a las de Entity Framework.)*

```powershell
docker compose up -d      # crea y arranca el contenedor "pmo_db"
docker compose ps         # debe aparecer pmo_db como "healthy"
```

La primera vez descarga la imagen `postgres:16`; puede tardar unos minutos. Los datos se guardan en un volumen de Docker, así que sobreviven a reiniciar el equipo o detener el contenedor.

| Comando | Qué hace |
|---|---|
| `docker compose up -d` | Inicia PostgreSQL |
| `docker compose stop` | Lo detiene (conserva los datos) |
| `docker compose down -v` | Elimina el contenedor **y todos los datos** (empezar de cero) |
| `docker compose logs db` | Ver los registros si algo falla |

### Conectarse con DBeaver (opcional)

1. **Nueva conexión → PostgreSQL**.
2. Host: `localhost` · Puerto: `5432`.
3. Base de datos, usuario y contraseña: los de `POSTGRES_DB`, `POSTGRES_USER` y `POSTGRES_PASSWORD` de tu `.env` (por defecto `pmo` / `pmo` / `pmo_dev`).
4. Si DBeaver pide descargar el driver de PostgreSQL, acepta.
5. **Test Connection** y luego **Finish**. Las tablas están en *pmo → Schemas → public → Tables*.

Si el puerto 5432 ya lo usa otro PostgreSQL instalado en tu equipo, detén ese servicio o cambia el puerto publicado en `docker-compose.yml` y `POSTGRES_PORT` en `backend\.env`.

## 5. Backend (Django)

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python manage.py migrate
.\.venv\Scripts\python manage.py createsuperuser
.\.venv\Scripts\python manage.py runserver
```

- `venv` es un entorno virtual: las librerías de Python quedan dentro de `backend\.venv` y no ensucian el sistema (similar a los paquetes NuGet por proyecto). No hace falta "activarlo": se usa llamando a `.\.venv\Scripts\python`.
- `migrate` crea las tablas y los datos iniciales (roles, permisos, tipos de entidad Proyecto y Sucursal).
- `createsuperuser` crea tu usuario de desarrollo. Es solo para desarrolladores.
- Cada vez que otra persona agregue migraciones y tú hagas `git pull`, vuelve a ejecutar `migrate`. Si agregan librerías a `requirements.txt`, vuelve a ejecutar el `pip install`.

Verifica abriendo http://localhost:8000/api/docs/ (Swagger) y http://localhost:8000/admin/.

### Depurar en VS Code

Abre la **carpeta raíz** en VS Code, elige el intérprete de Python de `backend\.venv\Scripts\python.exe` (Ctrl+Shift+P → *Python: Select Interpreter*) y pulsa **F5** → *Django: servidor (depurar)*. Los puntos de interrupción funcionan. Este modo usa `--noreload`: **si cambias código, reinicia el servidor** (botón de reinicio de la barra de depuración). También existe *Django: pruebas (depurar)*.

## 6. Web (React + Vite)

Con el backend corriendo:

```powershell
cd web
npm install
npm run dev
```

Abre http://localhost:5173. Debe ser **ese puerto**: el backend solo permite CORS desde él (si está ocupado, Vite avisa en lugar de cambiarlo; cierra el proceso anterior).

Otros comandos de `web/`:

```powershell
npm run build   # compila y revisa tipos
npm run lint    # análisis de código
```

### Tipos de la API (`packages/api-client`)

Los tipos TypeScript se **generan** desde el OpenAPI del backend; no se escriben a mano. Cuando cambies o agregues endpoints, regenéralos:

```powershell
cd packages\api-client
npm install      # solo la primera vez
npm run generate
```

`generate` necesita que `backend\.venv` exista. Sube a Git el `openapi.yml` y `src/schema.d.ts` resultantes junto con tu cambio.

## 7. Flujo de trabajo con Git

1. Antes de empezar: `git checkout main` y `git pull`.
2. Crea tu rama: `git checkout -b <tu-nombre>/<tema-corto>` (por ejemplo `ana/formularios`).
3. Haz commits pequeños con mensajes **en español e imperativo** ("Agrega validación de correo").
4. Sube la rama: `git push -u origin <tu-rama>` y abre un Pull Request hacia `main`.
5. Nunca subas `.env`, `.venv`, `node_modules` ni `web/dist` (ya están ignorados). Revisa con `git status` antes de cada commit.

## 8. Calidad antes de subir cambios

Desde `backend\`:

```powershell
.\.venv\Scripts\python manage.py test    # pruebas (unos 5 segundos)
.\.venv\Scripts\ruff check .             # análisis de código
.\.venv\Scripts\ruff format .            # formateo automático
```

Desde `web\`: `npm run lint` y `npm run build`.

Reglas del proyecto: el código usa type hints, evita consultas N+1 en el ORM (`select_related` / `prefetch_related`), el esquema de la base de datos se genera **solo** con migraciones (nunca `CREATE TABLE` a mano) y el nombre del producto se toma de la configuración (`APP_NAME` en la web, `PROJECT_NAME` en el backend), no se escribe en el código.

## Problemas frecuentes

| Síntoma | Causa y solución |
|---|---|
| `docker compose` no responde o falla al conectar | Docker Desktop no está abierto. Ábrelo y espera a que diga "Engine running". |
| `connection refused` o `password authentication failed` al migrar | El contenedor no está activo (`docker compose ps`) o las `POSTGRES_*` de `backend\.env` no coinciden con las del `.env` raíz. Si cambiaste la clave después de crear el volumen: `docker compose down -v` y vuelve a `up -d` (borra los datos). |
| El puerto 5432 está ocupado | Hay otro PostgreSQL local. Deténlo o cambia el puerto publicado en `docker-compose.yml` y `POSTGRES_PORT`. |
| `npm` bloqueado en PowerShell | `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` o usa `npm.cmd`. |
| Vite dice "Port 5173 is already in use" | Quedó un `npm run dev` anterior abierto. Ciérralo (Ctrl+C en su terminal) o termina ese proceso. |
| La web muestra error de red o CORS | El backend no está corriendo en el puerto 8000 o abriste la web en otro puerto distinto de 5173. |
| Cambié código del backend y no se nota | Estás depurando con `--noreload`: reinicia el servidor. |
| Faltan columnas o tablas tras un `git pull` | Ejecuta `manage.py migrate`. |
| DBeaver: "Failed to find a Main Class" | Instalaste una versión sin Java incluido. Reinstala con el instalador de Windows (el `.exe` que trae el JRE). |
