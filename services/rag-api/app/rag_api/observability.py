from __future__ import annotations

import logging

from fastapi import FastAPI
from shared_schemas import AppSettings


def configure_observability(
    app: FastAPI,
    settings: AppSettings,
    *,
    default_service_name: str,
) -> None:
    if not settings.otel_enabled:
        return

    try:
        from opentelemetry import metrics, trace
        from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
        from opentelemetry.sdk.metrics import MeterProvider
        from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter, SimpleSpanProcessor
    except ModuleNotFoundError:
        logging.getLogger("rag_api.observability").warning("event=otel_unavailable")
        return

    service_name = settings.otel_service_name or default_service_name
    resource = Resource.create(
        {
            "service.name": service_name,
            "service.version": settings.app_version,
            "deployment.environment": settings.app_env,
        }
    )

    trace_provider = TracerProvider(resource=resource)
    if settings.otel_exporter_otlp_endpoint:
        trace_provider.add_span_processor(
            BatchSpanProcessor(OTLPSpanExporter(endpoint=settings.otel_exporter_otlp_endpoint))
        )
    if settings.otel_console_exporter:
        trace_provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))
    trace.set_tracer_provider(trace_provider)

    if settings.otel_exporter_otlp_endpoint:
        metrics.set_meter_provider(
            MeterProvider(
                resource=resource,
                metric_readers=[
                    PeriodicExportingMetricReader(OTLPMetricExporter(endpoint=settings.otel_exporter_otlp_endpoint))
                ],
            )
        )

    FastAPIInstrumentor.instrument_app(app)
    HTTPXClientInstrumentor().instrument()
    logging.getLogger("rag_api.observability").info("event=otel_configured service=%s", service_name)
