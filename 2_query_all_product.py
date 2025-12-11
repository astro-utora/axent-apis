import iop
import requests
import json
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

client = iop.IopClient(
    os.getenv('IOP_API_URL'),
    os.getenv('IOP_APP_KEY'),
    os.getenv('IOP_APP_SECRET')
)
request = iop.IopRequest('/product/get')
request.add_api_param('item_id', os.getenv('ITEM_ID'))
response = client.execute(request, os.getenv('IOP_ACCESS_TOKEN'))

webhook_url = os.getenv('WEBHOOK_URL')

try:
    webhook_response = requests.post(
        webhook_url,
        json=response.body,
        headers={'Content-Type': 'application/json'}
    )
    print(f"\nWebhook Status Code: {webhook_response.status_code}")
    print(f"Webhook Response: {webhook_response.text}")
except Exception as e:
    print(f"\nError sending to webhook: {e}")