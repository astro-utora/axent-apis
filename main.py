import iop
import os
import requests
from typing import Optional
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

app = FastAPI(
    title="IOP SDK API",
    description="FastAPI backend for Taobao Global IOP SDK",
    version="1.0.0"
)

# Get environment variables
IOP_API_URL = os.getenv('IOP_API_URL')
IOP_APP_KEY = os.getenv('IOP_APP_KEY')
IOP_APP_SECRET = os.getenv('IOP_APP_SECRET')


# Request models
class AccessTokenRequest(BaseModel):
    code: str


class ProductInfoRequest(BaseModel):
    item_id: str
    access_token: str


class ProductsRequest(BaseModel):
    page_no: int = 1
    page_size: int = 20
    shop_id: str
    access_token: str


class AllProductsRequest(BaseModel):
    shop_id: str
    access_token: str


# Response models
class APIResponse(BaseModel):
    success: bool
    type: Optional[str] = None
    data: Optional[dict] = None
    error: Optional[str] = None


def get_iop_client():
    """Create and return IOP client instance"""
    return iop.IopClient(IOP_API_URL, IOP_APP_KEY, IOP_APP_SECRET)


@app.get("/")
def root():
    """Health check endpoint"""
    return {"status": "ok", "message": "IOP SDK API is running"}


@app.post("/getAccessToken", response_model=APIResponse)
def get_access_token(request: AccessTokenRequest):
    """
    Generate access token using authorization code.
    
    - **code**: Authorization code from Taobao OAuth
    """
    try:
        client = get_iop_client()
        iop_request = iop.IopRequest('/auth/token/create', 'GET')
        iop_request.add_api_param('code', request.code)
        response = client.execute(iop_request)
        
        return APIResponse(
            success=True,
            type=response.type,
            data=response.body if isinstance(response.body, dict) else {"raw": response.body}
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/getProductInfo", response_model=APIResponse)
def get_product_info(request: ProductInfoRequest):
    """
    Get product information by item ID.
    
    - **item_id**: Product item ID
    - **access_token**: Valid access token
    """
    try:
        client = get_iop_client()
        iop_request = iop.IopRequest('/product/get')
        iop_request.add_api_param('item_id', request.item_id)
        response = client.execute(iop_request, request.access_token)
        
        return APIResponse(
            success=True,
            type=response.type,
            data={
                "product": response.body if isinstance(response.body, dict) else {"raw": response.body}
            }
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/getProducts", response_model=APIResponse)
def get_products(request: ProductsRequest):
    """
    Search/list products from a shop.
    
    - **page_no**: Page number (default: 1)
    - **page_size**: Number of items per page (default: 20)
    - **shop_id**: Shop ID to search products from
    - **access_token**: Valid access token
    """
    try:
        client = get_iop_client()
        iop_request = iop.IopRequest('/traffic/item/search')
        iop_request.add_api_param('page_no', str(request.page_no))
        iop_request.add_api_param('page_size', str(request.page_size))
        iop_request.add_api_param('shop_id', request.shop_id)
        response = client.execute(iop_request, request.access_token)
        
        return APIResponse(
            success=True,
            type=response.type,
            data={
                "products": response.body if isinstance(response.body, dict) else {"raw": response.body}
            }
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/getAllProducts", response_model=APIResponse)
def get_all_products(request: AllProductsRequest):
    """
    Fetch all products from a shop by paginating through all pages.
    
    - **shop_id**: Shop ID to search products from
    - **access_token**: Valid access token
    """
    try:
        client = get_iop_client()
        all_products = []
        page_no = 1
        page_size = 20
        
        while True:
            iop_request = iop.IopRequest('/traffic/item/search')
            iop_request.add_api_param('page_no', str(page_no))
            iop_request.add_api_param('page_size', str(page_size))
            iop_request.add_api_param('shop_id', request.shop_id)
            response = client.execute(iop_request, request.access_token)
            
            # Extract products from response
            if isinstance(response.body, dict):
                products = response.body.get("data", {}).get("data", [])
            else:
                products = []
            
            # If no products returned, stop pagination
            if not products:
                break
            
            all_products.extend(products)
            
            # If fewer products than page_size, we've reached the last page
            if len(products) < page_size:
                break
            
            page_no += 1
        
        return APIResponse(
            success=True,
            type="success",
            data={
                "products": all_products,
                "total_count": len(all_products)
            }
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

