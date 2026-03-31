# यहाँ हमने वर्ज़न 1.58.0 कर दिया है
FROM mcr.microsoft.com/playwright/python:v1.58.0-jammy

WORKDIR /app

# Requirements फाइल कॉपी करें
COPY requirements.txt .

# पैकेजेस इनस्टॉल करें
RUN pip install --no-cache-dir -r requirements.txt

# आपकी बाकी सारी फाइल्स कॉपी करें
COPY . .

# बॉट को स्टार्ट करें
CMD ["python", "chauhan.py"]
