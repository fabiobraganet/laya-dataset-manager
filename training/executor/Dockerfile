FROM python:3.12-slim
RUN pip install --no-cache-dir kaggle==2.2.4
WORKDIR /app
COPY training/executor/server.py training/executor/generate_kernel.py /app/
RUN mkdir -p /state/runs
EXPOSE 8090
CMD ["python", "/app/server.py"]
