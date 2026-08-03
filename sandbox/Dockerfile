FROM python:3.11-slim

RUN useradd -m -u 10001 sandboxuser
RUN pip install --no-cache-dir pandas numpy python-dateutil matplotlib reportlab openpyxl PyYAML

RUN mkdir -p /sandbox/input /sandbox/work /sandbox/output
RUN chown -R sandboxuser:sandboxuser /sandbox

USER sandboxuser
WORKDIR /sandbox/work
