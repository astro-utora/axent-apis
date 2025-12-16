import iop
import os
import io
import time
import requests
import boto3
from typing import Optional
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from dotenv import load_dotenv
from PIL import Image
from botocore.exceptions import ClientError

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

# AWS S3 Configuration
AWS_ACCESS_KEY_ID = os.getenv('AWS_ACCESS_KEY_ID')
AWS_SECRET_ACCESS_KEY = os.getenv('AWS_SECRET_ACCESS_KEY')
AWS_S3_BUCKET_NAME = os.getenv('AWS_S3_BUCKET_NAME')
AWS_S3_REGION = os.getenv('AWS_S3_REGION', 'us-east-1')


def get_s3_client():
    """Create and return S3 client instance"""
    return boto3.client(
        's3',
        aws_access_key_id=AWS_ACCESS_KEY_ID,
        aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
        region_name=AWS_S3_REGION
    )


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


class ImageProcessRequest(BaseModel):
    image_url: str
    variant_id: str = "product"
    quality: int = 85  # WebP quality (1-100)


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


@app.post("/processImage", response_model=APIResponse)
def process_image(request: ImageProcessRequest):
    """
    Download an image from URL, convert to WebP format, and upload to S3.
    
    - **image_url**: URL of the image to process
    - **variant_id**: Product variant ID for file naming
    - **quality**: WebP quality (1-100, default: 85)
    
    Returns the public URL of the processed WebP image on S3.
    """
    try:
        # Validate S3 configuration
        if not all([AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_S3_BUCKET_NAME]):
            raise HTTPException(
                status_code=500, 
                detail="AWS S3 configuration is missing. Please set AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, and AWS_S3_BUCKET_NAME in .env"
            )
        
        # Generate timestamp for filenames
        timestamp = int(time.time() * 1000)  # milliseconds for uniqueness
        raw_filename = f"images/{request.variant_id}_{timestamp}_raw"
        processed_filename = f"images/{request.variant_id}_{timestamp}_processed.webp"
        
        # Download image from URL with headers to mimic a browser
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Referer': 'https://www.aliexpress.com/',
            'Connection': 'keep-alive',
            'Sec-Fetch-Dest': 'image',
            'Sec-Fetch-Mode': 'no-cors',
            'Sec-Fetch-Site': 'cross-site'
        }
        response = requests.get(request.image_url, headers=headers, timeout=30)
        response.raise_for_status()
        
        # Determine original file extension from content-type
        content_type = response.headers.get('Content-Type', 'image/jpeg')
        ext_map = {
            'image/jpeg': '.jpg',
            'image/png': '.png',
            'image/gif': '.gif',
            'image/webp': '.webp',
            'image/bmp': '.bmp',
            'image/tiff': '.tiff'
        }
        original_ext = ext_map.get(content_type, '.jpg')
        raw_filename_with_ext = f"{raw_filename}{original_ext}"
        
        # Get raw image data
        raw_image_data = response.content
        
        # Initialize S3 client
        s3_client = get_s3_client()
        
        # Upload raw image to S3
        s3_client.put_object(
            Bucket=AWS_S3_BUCKET_NAME,
            Key=raw_filename_with_ext,
            Body=raw_image_data,
            ContentType=content_type
        )
        
        # Convert image to WebP using Pillow
        image = Image.open(io.BytesIO(raw_image_data))
        
        # Get original dimensions
        original_width, original_height = image.size
        
        # Resize if either dimension exceeds 4000 pixels (Shopify limit)
        max_dimension = 4000
        needs_resize = False
        new_width, new_height = original_width, original_height
        
        if original_width > max_dimension or original_height > max_dimension:
            needs_resize = True
            # Calculate scaling factor based on the larger dimension
            if original_width >= original_height:
                # Width is the larger dimension
                scale_factor = max_dimension / original_width
                new_width = max_dimension
                new_height = round(original_height * scale_factor)
            else:
                # Height is the larger dimension
                scale_factor = max_dimension / original_height
                new_height = max_dimension
                new_width = round(original_width * scale_factor)
            
            # Resize image with high-quality resampling
            image = image.resize((new_width, new_height), Image.Resampling.LANCZOS)
        
        # Convert to RGB if necessary (WebP doesn't support all modes)
        if image.mode in ('RGBA', 'LA', 'P'):
            # Preserve transparency for RGBA
            if image.mode == 'P':
                image = image.convert('RGBA')
        elif image.mode != 'RGB':
            image = image.convert('RGB')
        
        # Save as WebP to bytes buffer
        webp_buffer = io.BytesIO()
        image.save(webp_buffer, format='WEBP', quality=request.quality, optimize=True)
        webp_buffer.seek(0)
        webp_data = webp_buffer.getvalue()
        
        # Upload processed WebP image to S3
        s3_client.put_object(
            Bucket=AWS_S3_BUCKET_NAME,
            Key=processed_filename,
            Body=webp_data,
            ContentType='image/webp'
        )
        
        # Generate public URL for processed image
        processed_url = f"https://{AWS_S3_BUCKET_NAME}.s3.{AWS_S3_REGION}.amazonaws.com/{processed_filename}"
        raw_url = f"https://{AWS_S3_BUCKET_NAME}.s3.{AWS_S3_REGION}.amazonaws.com/{raw_filename_with_ext}"
        
        return APIResponse(
            success=True,
            type="success",
            data={
                "processed_url": processed_url,
                "raw_url": raw_url,
                "raw_filename": raw_filename_with_ext,
                "processed_filename": processed_filename,
                "original_size_bytes": len(raw_image_data),
                "processed_size_bytes": len(webp_data),
                "compression_ratio": round((1 - len(webp_data) / len(raw_image_data)) * 100, 2),
                "original_dimensions": {
                    "width": original_width,
                    "height": original_height,
                    "megapixels": round((original_width * original_height) / 1_000_000, 2)
                },
                "final_dimensions": {
                    "width": new_width,
                    "height": new_height,
                    "megapixels": round((new_width * new_height) / 1_000_000, 2)
                },
                "was_resized": needs_resize
            }
        )
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=400, detail=f"Failed to download image: {str(e)}")
    except ClientError as e:
        raise HTTPException(status_code=500, detail=f"S3 upload failed: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

