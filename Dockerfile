FROM python:3.12-slim

# WeasyPrint system dependencies (pango, cairo, fontconfig)
#
# Las fuentes no son opcionales: el modelo de cotización usa Calibri y Segoe UI,
# que son de Microsoft y no vienen en la imagen. Carlito es métricamente
# compatible con Calibri y DejaVu cubre Segoe UI; sin ellas WeasyPrint cae en
# una fuente cualquiera y el PDF sale con otro cuerpo y otro ancho de línea.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libcairo2 \
    libgdk-pixbuf-2.0-0 \
    libffi-dev \
    libfontconfig1 \
    shared-mime-info \
    fonts-crosextra-carlito \
    fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN SECRET_KEY=build-only-not-used-at-runtime python manage.py collectstatic --no-input
RUN chmod +x entrypoint.sh

CMD ["sh", "entrypoint.sh"]
