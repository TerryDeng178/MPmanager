# 微信公众号内容管理工具

一个本地部署的工具，用于一键生成内容并自动上传到微信公众号。

## 功能特点

- 📝 一键生成内容
- 🚀 自动上传微信公众号
- 🌐 本地Web界面操作
- 🔧 简单易用的配置

## 安装使用

1. 安装依赖：
```bash
pip install -r requirements.txt
```

2. 启动服务：
```bash
python main.py
```

3. 打开浏览器访问：http://localhost:8000

## 配置说明

在启动前请先配置微信公众号相关信息：
- AppID
- AppSecret
- Access Token

## 目录结构

```
MPmanager/
├── main.py              # 主程序
├── static/              # 静态文件
├── templates/           # 模板文件
├── requirements.txt     # 依赖文件
└── README.md           # 说明文档
```