import json
from typing import Dict, Any
import httpx

BASE_URL = "https://api.weixin.qq.com"


async def get_access_token(appid: str, appsecret: str) -> str:
    url = f"{BASE_URL}/cgi-bin/token?grant_type=client_credential&appid={appid}&secret={appsecret}"
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.get(url)
        data = r.json()
        if "access_token" in data:
            return data["access_token"]
        raise RuntimeError(f"get_access_token error: {data}")


async def add_material_image(access_token: str, image_bytes: bytes, filename: str) -> str:
    """上传永久素材 图片，返回 media_id。"""
    url = f"{BASE_URL}/cgi-bin/material/add_material?access_token={access_token}&type=image"
    files = {"media": (filename, image_bytes, "image/jpeg")}
    async with httpx.AsyncClient(timeout=60.0) as client:
        r = await client.post(url, files=files)
        data = r.json()
        if "media_id" in data:
            return data["media_id"]
        raise RuntimeError(f"add_material_image error: {data}")


async def add_draft(access_token: str, article: Dict[str, Any]) -> str:
    """创建草稿，返回 media_id。"""
    url = f"{BASE_URL}/cgi-bin/draft/add?access_token={access_token}"
    payload = {"articles": [article]}
    async with httpx.AsyncClient(timeout=60.0) as client:
        r = await client.post(url, json=payload)
        data = r.json()
        if "media_id" in data:
            return data["media_id"]
        raise RuntimeError(f"add_draft error: {data}")


async def freepublish_submit(access_token: str, media_id: str) -> Dict[str, Any]:
    """发布草稿。返回发布任务信息（包含 publish_id）。"""
    url = f"{BASE_URL}/cgi-bin/freepublish/submit?access_token={access_token}"
    payload = {"media_id": media_id}
    async with httpx.AsyncClient(timeout=60.0) as client:
        r = await client.post(url, json=payload)
        data = r.json()
        if data.get("errcode") == 0:
            return data
        raise RuntimeError(f"freepublish_submit error: {data}")