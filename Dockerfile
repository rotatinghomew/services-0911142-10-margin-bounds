FROM python:3.11-slim-bookworm@sha256:65a93d69fa75478d554f4ad27c85c1e69fa184956261b4301ebaf6dbb0a3543d
WORKDIR /app
COPY requirements*.txt ./
RUN python3 -m pip install --no-cache-dir --only-binary=:all: -r requirements.txt -r requirements-build.txt -r requirements-test.txt
RUN python3 -m playwright install --with-deps chromium
COPY . .
ENV PYTHONUNBUFFERED=1 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1
EXPOSE 8080
CMD ["python3", "-m", "margin_bounds", "--host", "0.0.0.0", "--port", "8080"]
