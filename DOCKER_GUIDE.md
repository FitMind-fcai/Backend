# Docker Deployment Guide for FastAPI Application

## Prerequisites
- Docker Desktop installed on your system
- Docker Compose (included with Docker Desktop)

## Quick Start

### 1. Build and Run with Docker Compose

```bash
# Build and start all services (database + web app)
docker-compose up --build

# Or run in detached mode (background)
docker-compose up -d --build

# Delete containers AND volumes
docker-compose down -v
```

### 2. Access the Application

- **API**: http://localhost:8000
- **Interactive Docs**: http://localhost:8000/docs
- **PostgreSQL**: localhost:5432

### 3. Test the Signup Endpoint

Using curl:
```bash
curl -X POST "http://localhost:8000/signup" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Ahmed",
    "email": "ahmed@gmail.com",
    "age": 19,
    "password": "Ahmad@123"
  }'
```

Or use the interactive docs at http://localhost:8000/docs

## Docker Commands

### Start services
```bash
docker-compose up
```

### Stop services
```bash
docker-compose down
```

### Stop and remove volumes (clears database)
```bash
docker-compose down -v
```

### View logs
```bash
# All services
docker-compose logs

# Specific service
docker-compose logs web
docker-compose logs db

# Follow logs
docker-compose logs -f
```

### Rebuild after code changes
```bash
docker-compose up --build
```

### Access database
```bash
# Connect to PostgreSQL
docker exec -it fastapi_postgres psql -U postgres -d fastapi_db

# View users table
SELECT * FROM users;
```

## Environment Variables

The application uses the following environment variables (configured in docker-compose.yml):

- `DATABASE_URL`: PostgreSQL connection string
- `POSTGRES_USER`: Database user
- `POSTGRES_PASSWORD`: Database password
- `POSTGRES_DB`: Database name

## Production Deployment

For production, update `docker-compose.yml`:

1. Remove `--reload` flag from the web service command
2. Change database credentials
3. Add nginx reverse proxy
4. Enable SSL/TLS
5. Set `echo=False` in database.py

### Production docker-compose example:
```yaml
services:
  web:
    command: uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
    environment:
      DATABASE_URL: postgresql+psycopg://user:password@db:5432/production_db
```

## Troubleshooting

### Port already in use
```bash
# Change port in docker-compose.yml
ports:
  - "8001:8000"  # Use port 8001 instead
```

### Database connection issues
```bash
# Check if database is running
docker-compose ps

# Restart services
docker-compose restart
```

### Clear everything and start fresh
```bash
docker-compose down -v
docker-compose up --build
```

## File Structure
```
FastApi/
├── app/
│   ├── __init__.py
│   ├── main.py
│   └── database.py
├── models/
│   ├── __init__.py
│   └── user.py
├── schema/
│   ├── __init__.py
│   └── user.py
├── Dockerfile
├── docker-compose.yml
├── .dockerignore
└── requirements.txt
```
