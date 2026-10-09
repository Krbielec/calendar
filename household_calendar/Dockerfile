FROM python:3.13-alpine

ENV PYTHONUNBUFFERED=1
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY custom_components ./custom_components
COPY www ./www

CMD ["python", "-m", "app"]
