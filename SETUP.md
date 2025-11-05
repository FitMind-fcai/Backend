"""
Setup Instructions for FastAPI Signup Application

1. Install PostgreSQL:
   - Download and install PostgreSQL from https://www.postgresql.org/download/
   - Remember your postgres password during installation

2. Create Database:
   Open PostgreSQL command line (psql) or pgAdmin and run:
   ```sql
   CREATE DATABASE fastapi_db;
   ```

3. Configure Environment:
   - Copy .env.example to .env
   - Update DATABASE_URL with your PostgreSQL credentials:
     postgresql://username:password@localhost:5432/fastapi_db

4. Install Dependencies:
   ```powershell
   pip install -r requirements.txt
   ```

5. Run the Application:
   ```powershell
   uvicorn app.main:app --reload
   ```

6. Test the Signup Endpoint:
   Navigate to http://localhost:8000/docs
   
   Or use curl:
   ```powershell
   curl -X POST "http://localhost:8000/signup" `
     -H "Content-Type: application/json" `
     -d '{
       "name": "John Doe",
       "email": "john@example.com",
       "age": 25,
       "password": "secret123"
     }'
   ```

API Endpoints:
- GET  /          - Root endpoint
- POST /signup    - Create new user account
- GET  /docs      - Interactive API documentation
"""
