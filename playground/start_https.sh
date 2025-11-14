#!/bin/bash

# 启动 HTTPS 开发服务器
# 使用方法: ./start_https.sh

# 设置环境变量启用 HTTPS
export VITE_USE_HTTPS=true

# 启动 Vite 开发服务器
npm run dev
