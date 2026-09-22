# Development guide

## 1. Design goals

`image2svg` 的目标是从栅格图片恢复可编辑场景，而不是把整张原图包装进 SVG 或 PPTX。

质量需要同时考虑：

```text
visual fidelity + editability + structural simplicity
```

复杂照片和渲染图允许使用局部位图保真；文字和基础图形应尽可能恢复为原生对象。

## 2. Architecture

```text
CLI
  -> one or more VectorBackend implementations
  -> Scene merge
  -> cleanup / dedup / z-order
  -> Scene IR
  -> SVG builder
  -> optional QA / PPTX / HTML
```

核心抽象：

```python
class VectorBackend:
    def reconstruct(self, image_path: Path) -> VectorResult:
        ...
```

具体模型不得写死在 pipeline 中。重依赖模型通过子进程桥接，输出统一 JSON，再转换为 `SceneElement`。

## 3. Source layout

| Directory | Responsibility |
|---|---|
| `analyze/` | 调用外部桥接脚本并解析 JSON |
| `ai/scripts/` | 在 AI 环境执行的独立脚本 |
| `backends/` | 实现 `VectorBackend` 并产生 Scene |
| `core/` | Scene IR 与共享结果模型 |
| `reconstruct/` | 元素恢复、文字、矢量化与清理 |
| `svg/` | SVG 构建、审计和渲染 |
| `export/` | PPTX 与 HTML 导出 |
| `qa/` | 图片比较和指标 |
| `report/` | 转换报告 |

## 4. Scene IR

`Scene` 保存画布尺寸、背景和元素列表。`SceneElement` 的主要字段包括：

- `id`
- `type`
- `bbox`
- `style`
- `z_index`
- `text`
- `points`
- `path_d`
- `children`
- `raw_svg`

后端应返回结构化元素，而不是各自拼接整页 SVG。

## 5. Reconstruction policy

- `rect`、`circle`、`ellipse` 优先于复杂 path。
- OCR 文字优先于文字轮廓。
- 简单纯色对象可以 trace。
- 复杂多色对象优先保留清晰裁剪。
- 大面积整页位图会造成虚假的视觉高分，应避免。

## 6. Adding an AI backend

1. 在 `ai/scripts/` 添加独立 CLI 脚本。
2. 脚本至少支持 `--image` 和 `--output`。
3. 只在脚本内部 import 重型依赖。
4. 输出 JSON，不直接 import `image2svg`。
5. 在 `analyze/` 添加轻量调用器。
6. 在 `backends/` 实现 `VectorBackend`。
7. 将结果映射为 Scene IR。
8. 添加不依赖真实模型权重的单元测试。

## 7. Local checks

```bash
pytest -q
ruff check src tests
```

涉及渲染或导出时，还应：

1. 重跑 `examples/input/` 下的样例。
2. 打开 `*.review.html` 或 `*.qa/render.png` 进行目视检查。
3. 检查 PPTX 中的文本框、形状和图片类型。
4. 确认没有意外的大面积整页图片。

## 8. CI scope

GitHub Actions 安装轻量依赖并运行 Ruff 与 pytest。CI 不下载模型权重，也不执行 GPU 推理。模型桥接使用测试 JSON 或 mock 验证协议。

## 9. Release hygiene

- 不提交模型权重、缓存、临时裁剪或 QA 大文件。
- 不提交 API Key、访问令牌和个人绝对路径。
- 示例图片必须确认展示和再分发权利。
- 发布前选择许可证，并检查第三方模型的许可证兼容性。
- 大型 demo 文件应放在 GitHub Releases 或 Git LFS。
