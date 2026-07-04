FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8767 8766 18767 18766 28767 28766 3333

ENTRYPOINT ["python", "node.py"]
CMD ["--network", "mainnet"]
