<div align="center">

<img src="./frontend/public/kaleido-favicon.svg" alt="Kaleido Logo" width="96"/>

Multi-agent environmental simulation for ecological foresight
</br>
<em>Kaleido turns raw materials into an intervenable ecological simulation workspace.</em>

[![GitHub Stars](https://img.shields.io/github/stars/crisisjungle/Kaleido?style=flat-square&color=6C8F59)](https://github.com/crisisjungle/Kaleido/stargazers)
[![GitHub Forks](https://img.shields.io/github/forks/crisisjungle/Kaleido?style=flat-square&color=1F5D45)](https://github.com/crisisjungle/Kaleido/network)
[![License](https://img.shields.io/badge/License-AGPL--3.0-173126?style=flat-square)](./LICENSE)

[English](./README-EN.md) | [中文文档](./README.md)

</div>

## Overview

**Kaleido** builds an ecological foresight workspace from real-world materials.

After you upload reports, interviews, policy drafts, research notes, or other unstructured text, the system continues through the existing 5-step workflow:

1. Graph building
2. Environment setup
3. Multi-round simulation
4. Report generation
5. Deep interaction

The landing page has been fully redesigned around the `Kaleido` brand, while the existing workbench pages, graph view, and replay capabilities remain intact.

## Core Capabilities

- Convert PDF, Markdown, and TXT materials into graphs, roles, and environment constraints.
- Simulate multi-agent interactions across environmental variables and feedback loops.
- Inject policy, resources, extreme weather, and public sentiment into the same scenario.
- Generate reports automatically and keep the interaction chain open for follow-up questions.

## Example Use Cases

- Wetland restoration and habitat recovery
- Watershed governance and pollution control analysis
- Coastal risk coupling and resource scheduling
- Environmental incidents combined with public sentiment diffusion

## Quick Start

### Prerequisites

| Tool | Version |
| --- | --- |
| Node.js | 18+ |
| Python | >= 3.11, <= 3.12 |
| uv | Latest |

### 1. Configure Environment Variables

```bash
cp .env.example .env
```

At minimum, configure:

```env
LLM_API_KEY=your_api_key
LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
LLM_MODEL_NAME=qwen-plus
ZEP_API_KEY=your_zep_api_key
```

### 2. Install Dependencies

```bash
npm run setup:all
```

### 3. Start the Stack

```bash
npm run dev
```

Default endpoints:

- Frontend: [http://localhost:3000](http://localhost:3000)
- Backend API: [http://localhost:5001](http://localhost:5001)

### 4. Run with Docker

```bash
docker compose up -d
```

## Project Layout

```text
.
├── backend/    # Flask API, graph building, environment setup, simulation, reports
├── frontend/   # Vue 3 + Vite frontend with the new Kaleido landing page
├── static/     # README assets and screenshots
└── docker-compose.yml
```

## Routes

- `/`: Kaleido landing page for intake and entry orchestration
- `/process/:projectId`: graph-building workbench
- `/simulation/:simulationId`: environment setup
- `/simulation/:simulationId/start`: live simulation
- `/report/:reportId`: report generation
- `/interaction/:reportId`: deep interaction

## Screenshots

<div align="center">
<table>
<tr>
<td><img src="./static/image/Screenshot/运行截图1.png" alt="Screenshot 1" width="100%"/></td>
<td><img src="./static/image/Screenshot/运行截图2.png" alt="Screenshot 2" width="100%"/></td>
</tr>
<tr>
<td><img src="./static/image/Screenshot/运行截图3.png" alt="Screenshot 3" width="100%"/></td>
<td><img src="./static/image/Screenshot/运行截图4.png" alt="Screenshot 4" width="100%"/></td>
</tr>
</table>
</div>

## License

AGPL-3.0
