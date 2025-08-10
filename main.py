import asyncio
import json
import os
from pathlib import Path
from typing import Optional

import httpx
from fastapi import FastAPI, Request, Form, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
import uvicorn
import markdown as md

from wechat_api import (
    get_access_token,
    add_material_image,
    add_draft,
    freepublish_submit,
)

BASE_DIR = Path(__file__).parent
CONFIG_PATH = BASE_DIR / "config.json"

app = FastAPI(title="微信公众号内容管理工具")
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


def load_config():
    if CONFIG_PATH.exists():
        try:
            data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            # 兼容旧配置
            if "simulate" not in data:
                data["simulate"] = True
            return data
        except Exception:
            return {"appid": "", "appsecret": "", "simulate": True}
    return {"appid": "", "appsecret": "", "simulate": True}


def save_config(appid: str, appsecret: str, simulate: bool):
    CONFIG_PATH.write_text(
        json.dumps({
            "appid": appid.strip(),
            "appsecret": appsecret.strip(),
            "simulate": bool(simulate),
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


class GenerateForm(BaseModel):
    title: str
    keywords: Optional[str] = ""
    summary: Optional[str] = ""
    author: Optional[str] = ""
    auto_publish: bool = False


def simple_content_generator(title: str, keywords: str = "", summary: str = "", style: str = "通用", paragraphs: int = 4, toc: bool = False) -> str:
    """生成 Markdown 文章，支持风格、段落数与可选目录。"""
    paragraphs = max(2, min(12, int(paragraphs or 4)))
    sections = []
    if toc:
        sections.append("[TOC]")
    sections.append(f"# {title}")
    sections.append(summary or "这是一篇自动生成的文章概要。")
    sections.append("## 核心要点")

    if keywords:
        bullet = "\n".join([f"- {k.strip()}" for k in keywords.split(",") if k.strip()])
        if bullet:
            sections.append(bullet)

    style_hint = {
        "通用": "以清晰、友好的口吻阐述主题。",
        "科普": "面向非专业读者，用通俗比喻解释概念。",
        "行业分析": "结合行业现状、趋势与数据，强调洞察与策略。",
        "活动推文": "突出亮点、价值与报名行动，引导参与。",
    }.get(style or "通用", "以清晰、友好的口吻阐述主题。")

    sections.append("\n## 正文")
    sections.append(f"风格：{style}（{style_hint}）")

    for i in range(1, paragraphs + 1):
        sections.append(f"### 小节 {i}")
        sections.append("背景与问题：描述该小节关注点与读者关心的痛点。")
        sections.append("方法与建议：提供 2-3 条可操作建议，尽量举例。")
        if style == "行业分析":
            sections.append("数据与案例：引用行业数据或典型案例支撑观点。")
        if style == "活动推文":
            sections.append("亮点与报名：强调活动亮点，附上报名或咨询方式。")

    sections += [
        "\n## 结语",
        "总结关键点，并给出下一步行动建议。",
    ]
    return "\n\n".join(sections)


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    cfg = load_config()
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "config": cfg,
        },
    )


@app.post("/save-config")
async def save_config_handler(appid: str = Form("") , appsecret: str = Form(""), simulate: bool = Form(False)):
    save_config(appid, appsecret, simulate)
    return RedirectResponse("/", status_code=303)


@app.post("/generate-upload", response_class=HTMLResponse)
async def generate_and_upload(
    request: Request,
    title: str = Form(...),
    keywords: str = Form(""),
    summary: str = Form(""),
    author: str = Form(""),
    style: str = Form("通用"),
    paragraphs: int = Form(4),
    toc: Optional[bool] = Form(False),
    auto_publish: Optional[bool] = Form(False),
    cover_image: Optional[UploadFile] = File(None),
):
    cfg = load_config()
    appid = cfg.get("appid")
    appsecret = cfg.get("appsecret")
    simulate = cfg.get("simulate", True)

    # 1) 生成内容 (Markdown -> HTML)
    md_content = simple_content_generator(title=title, keywords=keywords, summary=summary, style=style, paragraphs=paragraphs, toc=bool(toc))
    html_content = md.markdown(md_content, extensions=["extra", "toc"])  # 转 HTML

    if simulate:
        thumb_media_id = f"SIM_THUMB_{abs(hash(title)) % 100000}"
        media_id = f"SIM_MEDIA_{abs(hash(title + (author or ''))) % 100000}"
        publish_result = None
        if auto_publish:
            publish_result = {"errcode": 0, "errmsg": "ok", "publish_id": f"SIM_PUB_{abs(hash(media_id)) % 100000}"}
        return templates.TemplateResponse(
            "result.html",
            {
                "request": request,
                "ok": True,
                "message": "【模拟】草稿创建成功并已提交发布" if auto_publish else "【模拟】草稿创建成功",
                "media_id": media_id,
                "publish": publish_result,
                "simulate": True,
            },
        )

    # 非模拟模式需要真实配置
    if not appid or not appsecret:
        return templates.TemplateResponse(
            "result.html",
            {
                "request": request,
                "ok": False,
                "message": "请先在页面顶部配置并保存微信公众号 AppID 与 AppSecret，或打开模拟模式。",
            },
        )

    # 2) 获取 access_token
    try:
        access_token = await get_access_token(appid, appsecret)
    except Exception as e:
        return templates.TemplateResponse(
            "result.html",
            {
                "request": request,
                "ok": False,
                "message": f"获取 access_token 失败：{e}",
            },
        )

    # 3) 上传封面图，获取 thumb_media_id（封面图为必填）
    if cover_image is None:
        return templates.TemplateResponse(
            "result.html",
            {
                "request": request,
                "ok": False,
                "message": "请上传封面图（JPG/PNG）。",
            },
        )
    try:
        image_bytes = await cover_image.read()
        thumb_media_id = await add_material_image(access_token, image_bytes, cover_image.filename or "cover.jpg")
    except Exception as e:
        return templates.TemplateResponse(
            "result.html",
            {
                "request": request,
                "ok": False,
                "message": f"上传封面图失败：{e}",
            },
        )

    # 4) 创建草稿
    article = {
        "title": title,
        "author": author or "",
        "digest": summary or title,
        "content": html_content,
        "thumb_media_id": thumb_media_id,
        "need_open_comment": 0,
        "only_fans_can_comment": 0,
    }

    try:
        media_id = await add_draft(access_token, article)
    except Exception as e:
        return templates.TemplateResponse(
            "result.html",
            {
                "request": request,
                "ok": False,
                "message": f"创建草稿失败：{e}",
            },
        )

    publish_result = None
    if auto_publish:
        try:
            publish_result = await freepublish_submit(access_token, media_id)
        except Exception as e:
            return templates.TemplateResponse(
                "result.html",
                {
                    "request": request,
                    "ok": True,
                    "message": f"草稿创建成功（media_id={media_id}），但自动发布失败：{e}",
                    "media_id": media_id,
                    "publish": None,
                    "simulate": False,
                },
            )

    return templates.TemplateResponse(
        "result.html",
        {
            "request": request,
            "ok": True,
            "message": "草稿创建成功并已提交发布" if auto_publish and publish_result else "草稿创建成功",
            "media_id": media_id,
            "publish": publish_result,
            "simulate": False,
        },
    )

# 预览生成内容（不上传）
@app.post("/preview", response_class=HTMLResponse)
async def preview(
    request: Request,
    title: str = Form(...),
    keywords: str = Form(""),
    summary: str = Form(""),
    author: str = Form(""),
    style: str = Form("通用"),
    paragraphs: int = Form(4),
    toc: Optional[bool] = Form(False),
    auto_publish: Optional[bool] = Form(False),
):
    cfg = load_config()
    simulate = cfg.get("simulate", True)
    md_content = simple_content_generator(title=title, keywords=keywords, summary=summary, style=style, paragraphs=paragraphs, toc=bool(toc))
    html_content = md.markdown(md_content, extensions=["extra", "toc"])  # 转 HTML
    return templates.TemplateResponse(
        "preview.html",
        {
            "request": request,
            "simulate": simulate,
            "title": title,
            "keywords": keywords,
            "summary": summary,
            "author": author,
            "style": style,
            "paragraphs": paragraphs,
            "toc": bool(toc),
            "md": md_content,
            "html": html_content,
        },
    )


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)