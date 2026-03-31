# यह Microsoft का ऑफिसियल इमेज है जिसमें ब्राउज़र की सारी फाइल्स पहले से होती हैं
FROM mcr.microsoft.com/playwright/python:v1.42.0-jammy

WORKDIR /app

# Requirements फाइल कॉपी करें
COPY requirements.txt .

# पैकेजेस इनस्टॉल करें
RUN pip install --no-cache-dir -r requirements.txt

# आपकी बाकी सारी फाइल्स कॉपी करें
COPY . .

# बॉट को स्टार्ट करें
CMD ["python", "chauhan.py"]
