FROM python:3.12-slim

WORKDIR /app

# Note: no apt-get install needed. This project uses asyncpg (not psycopg2), so
# libpq-dev is unnecessary, and every dependency (asyncpg, bcrypt, cryptography,
# pydantic-core, uvicorn[standard] extras, etc.) ships prebuilt cp312 wheels, so
# build-essential is unnecessary too. Skipping apt avoids flaky Debian mirror
# downloads and makes the build faster and more reliable.
COPY requirements.txt .
RUN pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt

COPY . .

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
