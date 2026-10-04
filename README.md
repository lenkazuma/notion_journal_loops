# Notion Journal Loops

从 Notion Journal 数据库中提取情绪循环与重复模式的分析工具。

**功能概览：**
- 从 Notion 数据库拉取所有日记页面（支持分页 + 断点续跑）
- 对正文进行智能分段（chunk）
- 使用 Embedding 生成向量（OpenAI / Anthropic / TF-IDF 降级）
- HDBSCAN 或 KMeans 聚类
- LLM 对每个聚类总结"情绪循环"（结构化 JSON）
- 语义重复检测（cosine similarity + 保留更早版本）
- 生成可读报告 + Git-diff 风格审阅文件
- 可选：将聚类标签与重复标记写回 Notion（支持 dry-run）

---

## 目录结构

```
notion_journal_loops/
  README.md
  requirements.txt
  .env.example          ← 环境变量模板
  .env                  ← 你的实际配置（不提交到 git）
  src/
    config.py           ← 统一配置加载
    utils/              ← 工具函数
    notion/             ← Notion API 客户端
    llm/                ← LLM Provider 抽象层
    pipeline/           ← 7步流水线
    writeback/          ← 写回 Notion
  data/
    raw/                ← 原始页面缓存
    chunks/             ← 分段缓存
    embeddings/         ← 向量缓存
    clusters/           ← 聚类结果缓存
    outputs/            ← 最终报告（同样被 .gitignore 排除，只保留 .gitkeep）
  tests/                ← 单元测试（不需要 Notion / API Key）
  scripts/
    run_all.bat         ← Windows 批处理
    run_all.ps1         ← PowerShell
```

---

## 快速开始

### 1. 环境准备

**Python 3.10+ 必须**

```powershell
# 创建虚拟环境
python -m venv .venv
.venv\Scripts\Activate.ps1

# 安装依赖
pip install -r requirements.txt
```

> **注意 Windows 用户：** 如果 `hdbscan` 安装失败，先安装 C++ 构建工具：
> 下载 [Visual Studio Build Tools](https://visualstudio.microsoft.com/visual-cpp-build-tools/)
> 或者使用 conda：`conda install -c conda-forge hdbscan`

### 2. 获取 Notion Integration Token

1. 访问 https://www.notion.so/my-integrations
2. 点击 **"+ New integration"**
3. 填写名称（如 `journal-loops`），选择工作区
4. 点击 **"Submit"**
5. 复制 **"Internal Integration Token"**（格式：`ntn_xxxxxxxx`）
6. 将其填入 `.env` 文件的 `NOTION_TOKEN=` 字段

### 3. 获取 Database ID

1. 在 Notion 中打开你的 Journal 数据库
2. 点击右上角 `...` → **"Add connections"** → 选择你刚创建的 integration
3. 复制数据库 URL，格式如：
   ```
   https://www.notion.so/YOUR_WORKSPACE/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx?v=...
   ```
4. URL 中 `?v=` 之前的 32 位十六进制字符串即为 `DATABASE_ID`
5. 将其填入 `.env` 文件的 `NOTION_DATABASE_ID=` 字段

### 4. 配置 .env 文件

复制 `.env.example` 为 `.env`，填写你的配置：

```env
NOTION_TOKEN=ntn_你的token
NOTION_DATABASE_ID=你的数据库ID
NOTION_TITLE_PROPERTY=Name          # 标题字段名（默认 Name）
NOTION_DATE_PROPERTY=Formulated Date # 日期字段名

LLM_PROVIDER=openai                  # openai | anthropic | fallback
OPENAI_API_KEY=sk-你的key
```

> **如果没有 API Key：** 设置 `LLM_PROVIDER=fallback`，可以运行步骤 1-4（拉取、分段、TF-IDF 向量、聚类），但无法生成 AI 摘要。

### 5. 运行流水线

```powershell
# 运行完整流水线（步骤 1-7）
python -m src.pipeline.run_pipeline

# 或使用脚本
.\scripts\run_all.ps1
```

**分步运行：**

```powershell
# 只拉取数据（步骤 1）
python -m src.pipeline.run_pipeline --from-step 1 --to-step 1

# 从步骤 3 开始（跳过已完成的步骤）
python -m src.pipeline.run_pipeline --from-step 3

# 测试模式（只拉取 10 篇）
python -m src.pipeline.run_pipeline --max-pages 10

# 使用 KMeans 聚类
python -m src.pipeline.run_pipeline --cluster-method kmeans

# 使用 Anthropic Claude
python -m src.pipeline.run_pipeline --provider anthropic

# 调整重复检测阈值
python -m src.pipeline.run_pipeline --dedupe-threshold 0.88

# 强制重新运行（忽略所有缓存）
python -m src.pipeline.run_pipeline --force
```

---

## 流水线步骤详解

| 步骤 | 脚本 | 输入 | 输出 | 说明 |
|------|------|------|------|------|
| 1 | `step1_fetch.py` | Notion API | `data/raw/` | 拉取所有页面 |
| 2 | `step2_chunk.py` | `data/raw/` | `data/chunks/chunks.json` | 文本分段 |
| 3 | `step3_embed.py` | chunks | `data/embeddings/` | 生成向量 |
| 4 | `step4_cluster.py` | embeddings | `data/clusters/cluster_assignments.json` | 聚类 |
| 5 | `step5_summarize.py` | clusters | `data/clusters/summaries.json` | LLM 摘要 |
| 6 | `step6_dedupe.py` | clusters + embeddings | `data/clusters/duplicates.json` | 重复检测 |
| 7 | `step7_report.py` | all | `data/outputs/` | 生成报告 |

---

## 输出文件说明

| 文件 | 说明 |
|------|------|
| `data/outputs/report.md` | 主报告：按聚类展示情绪模式 |
| `data/outputs/report.json` | 结构化 JSON 报告 |
| `data/outputs/cluster_assignments.csv` | 每个 chunk 的聚类归属 |
| `data/outputs/duplicates.csv` | 重复 chunk 映射表 |
| `data/outputs/review_patch.md` | 审阅文件：显示哪些内容将被标记为重复 |

> **隐私提示：** `data/` 下所有内容（原始页面、分段、向量、报告）都来自你的私人日记，已全部被 `.gitignore` 排除。不要用 `git add -f` 强行提交，也不要把页面标题、正文片段硬编码进脚本后推送到公开仓库。

---

## 写回 Notion（可选）

**默认不写回。** 写回前必须先 dry-run 审阅。

```powershell
# 步骤 1：预览将要修改的内容（dry-run）
python -m src.writeback.writeback_notion --mode dryrun

# 步骤 2：查看审阅文件
# 打开 data/outputs/review_patch.md 仔细检查

# 步骤 3：确认无误后，实际写回
python -m src.writeback.writeback_notion --mode on
```

**写回内容包括：**
- 给每个页面添加 `ClusterId`、`LoopLabel` 属性
- 给重复页面添加 `IsDuplicate`、`CanonicalPage`、`CanonicalChunk` 属性
- 在重复 chunk 前插入删除线文本和 canonical 链接

> **注意：** 写回需要在 Notion 数据库中预先创建对应属性字段。
> 如果字段不存在，Notion API 会报错。

---

## LLM Provider 说明

### OpenAI（推荐）
- Embedding：`text-embedding-3-small`（可配置）
- Chat：`gpt-4o-mini`（可配置）
- 需要：`OPENAI_API_KEY`

### Anthropic Claude
- Embedding：**不支持**，自动降级为 TF-IDF
- Chat：`claude-3-haiku-20240307`（可配置）
- 需要：`ANTHROPIC_API_KEY`

### Fallback（无 API Key）
- Embedding：TF-IDF 向量（`scikit-learn`）
- Chat：模板占位符（无 AI 摘要）
- **注意：** TF-IDF 向量质量远低于神经网络 Embedding，聚类和重复检测效果会明显下降

---

## 环境变量完整说明

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `NOTION_TOKEN` | — | Notion Integration Token（必填） |
| `NOTION_DATABASE_ID` | — | 日记数据库 ID（必填） |
| `NOTION_TITLE_PROPERTY` | `Name` | 标题字段名 |
| `NOTION_DATE_PROPERTY` | `Formulated Date` | 日期字段名 |
| `LLM_PROVIDER` | `openai` | `openai` / `anthropic` / `fallback` |
| `OPENAI_API_KEY` | — | OpenAI API Key |
| `ANTHROPIC_API_KEY` | — | Anthropic API Key |
| `OPENAI_EMBED_MODEL` | `text-embedding-3-small` | Embedding 模型 |
| `OPENAI_CHAT_MODEL` | `gpt-4o-mini` | Chat 模型 |
| `ANTHROPIC_CHAT_MODEL` | `claude-3-haiku-20240307` | Anthropic Chat 模型 |
| `CHUNK_TARGET_TOKENS` | `700` | 分段目标 token 数 |
| `CHUNK_MAX_TOKENS` | `900` | 分段最大 token 数 |
| `CLUSTER_METHOD` | `hdbscan` | `hdbscan` / `kmeans` |
| `HDBSCAN_MIN_CLUSTER_SIZE` | `8` | HDBSCAN 最小聚类大小 |
| `KMEANS_K_MIN` | `3` | KMeans 最小 k |
| `KMEANS_K_MAX` | `20` | KMeans 最大 k |
| `SUMMARY_SAMPLE_PER_CLUSTER` | `30` | 每个聚类最多采样 N 条 |
| `DUP_SIM_THRESHOLD` | `0.92` | 重复检测余弦相似度阈值 |
| `DUP_CROSS_CLUSTER` | `false` | 是否跨聚类检测重复 |
| `WRITEBACK_MODE` | `off` | `off` / `dryrun` / `on` |
| `LOG_LEVEL` | `INFO` | `DEBUG` / `INFO` / `WARNING` |

---

## 常见问题排查

### Q: `NOTION_TOKEN is not set` 错误
确认 `.env` 文件在项目根目录，且 `NOTION_TOKEN` 已填写。

### Q: `Could not find database` / 403 错误
确认已将 Integration 邀请到数据库（数据库页面 → `...` → `Add connections`）。

### Q: `hdbscan` 安装失败（Windows）
```powershell
# 方法 1：安装 C++ 构建工具后重试
pip install hdbscan

# 方法 2：使用 conda
conda install -c conda-forge hdbscan

# 方法 3：改用 KMeans
# 在 .env 中设置 CLUSTER_METHOD=kmeans
```

### Q: OpenAI 429 Rate Limit
流水线已内置指数退避重试（最多 6 次）。如果仍然失败，可以：
- 减少 `--max-pages` 进行分批处理
- 等待一段时间后重新运行（缓存会保留已完成的步骤）

### Q: 日期字段识别不到
检查 `NOTION_DATE_PROPERTY` 是否与 Notion 中的字段名完全一致（包括大小写和空格）。
如果没有日期字段，流水线会自动使用 `created_time`。

### Q: 聚类结果只有 1 个聚类或全是噪声
- 数据量太少：HDBSCAN 需要足够的数据点。尝试降低 `HDBSCAN_MIN_CLUSTER_SIZE`（如 3-5）
- 或改用 KMeans：`--cluster-method kmeans`
- TF-IDF 向量质量低：建议使用 OpenAI Embedding

### Q: 重复检测太多/太少
调整 `DUP_SIM_THRESHOLD`：
- 增大（如 0.95）→ 更严格，减少误报
- 减小（如 0.85）→ 更宽松，检测更多相似内容

同一页面内部的段落不会被互相判为重复。Notion 托管图片的临时签名 URL 不再写入正文（只保留 `[image]` 或图片说明），因此含图片的页面不会再被误判为重复；如果你的缓存是旧版本生成的，请用 `--force` 重新运行一次。

---

## 开发说明

### 运行测试

```powershell
pip install pytest
pytest -q
```

测试覆盖分段、Notion block 转文本、相似度和重复检测，不访问网络。

### 添加新的 LLM Provider

1. 在 `src/llm/` 创建新文件（如 `provider_gemini.py`）
2. 继承 `ProviderBase` 并实现 `embed()` 和 `chat()` 方法
3. 在 `src/llm/embedder.py` 的 `get_provider()` 函数中注册

### 缓存机制

每个步骤都会将结果缓存到 `data/` 目录。重新运行时：
- 如果缓存文件存在，跳过该步骤
- 使用 `--force` 强制重新运行所有步骤
- 使用 `--from-step N` 从指定步骤开始（之前步骤的缓存仍然有效）

---

## License

MIT
