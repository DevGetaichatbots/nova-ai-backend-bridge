FROM eclipse-temurin:17-jdk-jammy

RUN apt-get update && apt-get install -y \
    python3.11 \
    python3-pip \
    python3.11-dev \
    gcc \
    g++ \
    curl \
    && rm -rf /var/lib/apt/lists/*

RUN ln -s /usr/bin/python3.11 /usr/bin/python

ENV JAVA_HOME=/opt/java/openjdk
ENV PATH="${JAVA_HOME}/bin:${PATH}"
ENV LD_LIBRARY_PATH="${JAVA_HOME}/lib/server:${JAVA_HOME}/lib:${LD_LIBRARY_PATH}"
ENV PYTHONPATH=/app

WORKDIR /app

COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

# Bake Chromium + its system libs into the image at BUILD time (not a runtime
# startup command) so HTML→PDF export works on Azure with nothing to install
# when the container boots. Use the `playwright` console script (installed by
# pip3) so it runs under the same interpreter the deps live in — `python` here
# is symlinked to 3.11 but pip3 installs into the default python3.
RUN playwright install --with-deps chromium

COPY . .

EXPOSE 8000

CMD ["gunicorn", "src.main:app", \
     "--worker-class", "uvicorn.workers.UvicornWorker", \
     "--workers", "2", \
     "--bind", "0.0.0.0:8000", \
     "--timeout", "180", \
     "--keep-alive", "5"]