<div align="center">

<img src="./frontend/public/kaleido-favicon.svg" alt="Kaleido Logo" width="96"/>

面向生态推演的多智能体环境仿真引擎
</br>
<em>Multi-agent environmental simulation for ecological foresight</em>

[![GitHub Stars](https://img.shields.io/github/stars/crisisjungle/Kaleido?style=flat-square&color=6C8F59)](https://github.com/crisisjungle/Kaleido/stargazers)
[![GitHub Forks](https://img.shields.io/github/forks/crisisjungle/Kaleido?style=flat-square&color=1F5D45)](https://github.com/crisisjungle/Kaleido/network)
[![License](https://img.shields.io/badge/License-AGPL--3.0-173126?style=flat-square)](./LICENSE)

[English](./README-EN.md) | [中文文档](./README.md)

</div>

## 概述

**Kaleido (万象)** 用真实世界材料构建一个可干预、可回放、可继续追问的生态推演场。

你上传报告、访谈、政策草案、研究笔记或其他非结构化文本后，系统会沿着现有 5 步工作流继续执行：

1. 图谱构建
2. 环境搭建
3. 多轮模拟
4. 报告生成
5. 深度互动

首页已经重做为新的 `Kaleido` 控制台，但原有流程页、图谱视图和历史回放能力仍然保留，没有额外引入新的用户入口。

## 核心能力

- 把 PDF、Markdown、TXT 等非结构化材料转成图谱、角色与环境约束。
- 对生态系统中的主体、变量与反馈链路进行多轮仿真。
- 支持把政策、资源、极端天气、舆情等变量同时注入同一场景。
- 自动生成推演报告，并保留后续互动与追问链路。

## 适用场景

- 湿地修复与生境恢复推演
- 流域协同治理与排污约束分析
- 海岸带风险联动与资源调度评估
- 生态事件与舆情扩散耦合模拟

## 快速开始

### 前置要求

| 工具 | 版本要求 |
| --- | --- |
| Node.js | 18+ |
| Python | >= 3.11, <= 3.12 |
| uv | 最新版本 |

### 1. 配置环境变量

```bash
cp .env.example .env
```

至少需要配置：

```env
LLM_API_KEY=your_api_key
LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
LLM_MODEL_NAME=qwen-plus
ZEP_API_KEY=your_zep_api_key
```

### 2. 安装依赖

```bash
npm run setup:all
```

### 3. 启动服务

```bash
npm run dev
```

默认地址：

- 前端：[http://localhost:3000](http://localhost:3000)
- 后端 API：[http://localhost:5001](http://localhost:5001)

### 4. Docker 启动

```bash
docker compose up -d
```

## 项目结构

```text
.
├── backend/    # Flask API、图谱构建、环境搭建、模拟与报告能力
├── frontend/   # Vue 3 + Vite 前端，包含全新 Kaleido 首页与现有工作台
├── static/     # README 资源与项目截图
└── docker-compose.yml
```

## 页面流转

- `/`：Kaleido 首页，负责材料采集与入口重排
- `/process/:projectId`：图谱构建工作台
- `/simulation/:simulationId`：环境搭建
- `/simulation/:simulationId/start`：模拟运行
- `/report/:reportId`：报告生成
- `/interaction/:reportId`：深度互动

## 截图

<div align="center">
<table>
<tr>
<td><img src="./static/image/Screenshot/运行截图1.png" alt="截图 1" width="100%"/></td>
<td><img src="./static/image/Screenshot/运行截图2.png" alt="截图 2" width="100%"/></td>
</tr>
<tr>
<td><img src="./static/image/Screenshot/运行截图3.png" alt="截图 3" width="100%"/></td>
<td><img src="./static/image/Screenshot/运行截图4.png" alt="截图 4" width="100%"/></td>
</tr>
</table>
</div>

## License

AGPL-3.0
