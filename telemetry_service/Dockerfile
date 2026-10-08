FROM python:3.13-slim
WORKDIR /service
COPY telemetry_service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY error_telemetry.py .
COPY telemetry_service telemetry_service
RUN useradd --uid 10001 --create-home telemetry && mkdir /state && chown telemetry /state
USER telemetry
ENV TELEMETRY_DATABASE=/state/reports.sqlite
EXPOSE 8080
CMD ["gunicorn", "--workers", "1", "--threads", "4", "--bind", "0.0.0.0:8080", "telemetry_service.server:create_app()"]
