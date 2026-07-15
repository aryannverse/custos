# Use an official Python runtime as a parent image
FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Install system dependencies (needed for compiling some python packages if any)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first to leverage Docker cache
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application
COPY . .

# Create the data directory if it doesn't exist (for the DuckDB file)
RUN mkdir -p data

# Expose ports for both API and UI
EXPOSE 8000
EXPOSE 8501

# The default command
CMD ["streamlit", "run", "src/custos/ui/app.py", "--server.port=8501", "--server.address=0.0.0.0"]
