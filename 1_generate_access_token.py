import iop
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

client = iop.IopClient(
    os.getenv('IOP_API_URL'),
    os.getenv('IOP_APP_KEY'),
    os.getenv('IOP_APP_SECRET')
)
request = iop.IopRequest('/auth/token/create', 'GET')
request.add_api_param('code', os.getenv('IOP_AUTH_CODE'))
response = client.execute(request)
print(response.type)
print(response.body)
