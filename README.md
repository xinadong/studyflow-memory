# StudyFlow Memory

反馈记忆驱动的课程学习恢复 Agent。

- `backend/`：FastAPI 后端与 Agent 业务逻辑
- `frontend/`：Vue 3 前端
- `data/`：课程种子数据和测试夹具
- `docs/`：项目设计、接口和评测文档
- `scripts/`：开发和评测脚本
- `infra/`：容器与反向代理配置

后端真实模型配置和启动方式见 [`docs/api.md`](docs/api.md)。复制 `.env.example` 为
`.env` 并填入本地轮换后的 `LLM_API_KEY` 后，Agent 才会调用真实模型；没有配置时会
明确返回模型调用失败，不会自动回退为规则结果。
