# Secure Dockerfile for URL Shortener
# Uses non-root user and minimal base image

FROM python:3.12-slim

# Create non-root user for security
RUN groupadd -r appgroup && useradd -r -g appgroup appuser

# Set working directory
WORKDIR /app

# Install dependencies as root (required for pip)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app/ ./app/

# Change ownership to non-root user
RUN chown -R appuser:appgroup /app

# Switch to non-root user
USER appuser

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Run with production settings
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
