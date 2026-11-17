# Eatsy

Centro de desarrollo en restaurantes y gastrobares.

## API Python de Eatsy — MySQL

Esta API utiliza únicamente MySQL de Aiven. Incluye JWT, roles, catálogo de productos y auditoría de peticiones.

```powershell
cd api_python
Copy-Item .env.example .env
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m app.cli init
python -m app.cli create-user --usuario admin --nombre Nombre --apellido Apellido --rol admin
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

En `.env` y en Render define los valores reales de Aiven y JWT: `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD`, `DB_NAME`, `DB_SSL`, `DB_SSL_CA` y `JWT_SECRET_KEY`.
