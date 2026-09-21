# Document API 单接口裁剪设计

## 目标

将项目裁剪为只提供 `document_api` 非结构化文档处理接口的可运行服务。保留启动脚本和 Docker 构建文件；删除测试、日志、样例数据、其他业务接口及其专属依赖。

## 对外接口

应用只注册 `app.routers.document_api.router`。业务路由仅保留：

- `POST /documents/process`

FastAPI 自动生成的 `/docs`、`/redoc` 和 `/openapi.json` 不视为业务接口，继续保留。

## 保留结构

- `main.py`：创建 FastAPI 应用并注册 `document_api`。
- `requirements.txt`：仅声明运行该接口所需的第三方依赖。
- `start.sh`：保留服务启动入口。
- `docker/Dockerfile`：保留容器构建文件。
- `app/config.py`：仅保留文档模型调用所需配置。
- `app/settings.py`：提供接口错误日志使用的 logger。
- `app/models/data_models.py`：仅保留 `UnstructuredDocumentRequest`、`DocumentProcessData` 和 `UnstructuredDocumentResponse`。
- `app/routers/document_api.py`：保留唯一业务路由。
- `app/utils/document_processor.py`：保留文档分类、模型调用和结构化抽取逻辑。
- 各保留包所需的 `__init__.py`。

## 删除范围

- 其他接口：`app/routers/api.py`、`app/routers/llm_api.py`、`app/routers/doc_api.py`。
- 其他接口专属实现：`app/tools/` 及 `app/utils/` 中除 `document_processor.py` 和 `__init__.py` 外的文件。
- 无关资源和目录：`app/static/`、`app/database/`、`migrations/`、`pakg/`。
- 非运行内容：`tests/`、`logs/`、样例数据、临时文件和备份文件。
- 已失去引用的常量和依赖。

## 配置与日志

`document_processor.py` 只需要模型地址、模型密钥和模型名称。`config.py` 将缩减为这三项，并继续允许通过环境变量覆盖，避免保留其他接口的 FastGPT、Redis、向量模型和导出服务配置。

`app/settings.py` 当前会在启动时创建 `logs/`。为确保源码树不再依赖持久日志目录，将 logger 改为使用默认标准错误输出，不再主动创建日志文件。

## 依赖

运行时依赖预计缩减为：

- `fastapi`
- `uvicorn`
- `pydantic`
- `httpx`
- `loguru`

版本约束沿用现有明确版本；未固定版本的包不额外引入版本升级。

## 验证

裁剪完成后执行以下验证：

1. 对所有保留的 Python 文件进行编译检查。
2. 导入 `main.app`，确认应用可初始化。
3. 检查 OpenAPI，确认唯一业务路径为 `/documents/process`。
4. 检查剩余文件树和源码引用，确认不存在被删除模块的导入。
5. 检查 `requirements.txt` 与实际第三方导入一致。

接口验证不调用真实外部模型，避免产生外部请求；模型连通性不属于本次目录裁剪的验收范围。
