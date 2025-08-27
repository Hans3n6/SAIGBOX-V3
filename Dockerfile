# Use Python 3.11 slim image
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY api/ ./api/
COPY core/ ./core/
COPY static/ ./static/
COPY start.sh ./

# Create directory for SQLite database (for development/testing)
RUN mkdir -p /app/data

# Make startup script executable
RUN chmod +x /app/start.sh

# Expose port
EXPOSE 8000

# Run the application using startup script
CMD ["/app/start.sh"]