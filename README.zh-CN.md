# miniviking

[English](README.md)

`miniviking` 是一个为 OpenViking 准备的轻量本地 MLX 运行时。它在 localhost 上暴露 OpenAI 兼容接口，让原版 OpenViking 安装几乎不需要额外配置，就能使用本地聊天补全模型和嵌入模型。

默认服务地址：

```text
http://127.0.0.1:8745/v1
```

核心端点：

- `GET /v1/models`
- `POST /v1/chat/completions`
- `POST /v1/embeddings`
- `GET /health`

## 安装

预发布阶段，可以从当前 `main` 分支通过 Homebrew 安装：

```sh
brew tap le0-VV/miniviking https://github.com/le0-VV/miniviking
brew install --HEAD le0-VV/miniviking/miniviking
```

发布 tarball 之后，去掉 `--HEAD` 就会安装二进制 formula。

创建 Homebrew service 使用的配置，并下载选中的模型：

```sh
miniviking install --config "$(brew --prefix)/etc/miniviking/config.json" --skip-launch-agent
```

启动 Homebrew service：

```sh
brew services start miniviking
```

验证正在运行的服务：

```sh
miniviking test --config "$(brew --prefix)/etc/miniviking/config.json"
```

作为当前用户的 LaunchAgent 安装：

```sh
miniviking install
miniviking start
```

直接运行：

```sh
miniviking serve
```

`miniviking` 会打包成一个二进制。公开服务进程会启动同一个二进制的 worker 副本：

- `miniviking-server` 负责 OpenAI 兼容 HTTP API、LaunchAgent 生命周期、配置和 worker 监督。
- `miniviking-llm` 只加载并服务配置的 LLM。
- `miniviking-embed` 只加载并服务配置的嵌入模型。

验证正在运行的服务：

```sh
miniviking test
```

打印当前 miniviking 配置对应的 OpenViking 配置片段：

```sh
miniviking openviking-config
```

安装器会检测主机内存，并把配置写入 `~/.miniviking/config.json`。端口、运行模式和模型都可以在该文件里修改，也可以在安装时通过 CLI 参数自定义。

内存档位默认值：

| 统一内存        | 嵌入模型                                 | LLM 模型                                   | 后端      |
| --------------- | ---------------------------------------- | ------------------------------------------ | --------- |
| 低于 12 GB      | `mlx-community/embeddinggemma-300m-4bit` | `mlx-community/Llama-3.2-1B-Instruct-4bit` | `mlx-lm`  |
| 12 GB 到 16 GB  | `mlx-community/embeddinggemma-300m-8bit` | `mlx-community/gemma-4-e2b-it-4bit`        | `mlx-vlm` |
| 高于 16 GB      | `mlx-community/embeddinggemma-300m-bf16` | `mlx-community/gemma-4-e4b-it-4bit`        | `mlx-vlm` |

初始上下文和吞吐限制刻意低于各模型的最大上下文窗口：

| 档位   | `max_kv_size` | 近似 prompt 上限 | 最大输出 token | 嵌入批大小 |
| ------ | ------------: | ---------------: | -------------: | ---------: |
| Small  |          1024 |             2048 |            512 |          2 |
| Medium |          2048 |             4096 |            768 |          4 |
| Large  |          4096 |             8192 |           1024 |          8 |

OpenViking 的 OpenAI 兼容 provider 设置应该指向：

```text
api_base = "http://127.0.0.1:8745/v1"
api_key = "unused"
```

## 👉👈

如果 miniviking 对你有帮助，或者你只是刚好想支持一下，并且你有支付宝，请考虑给这个项目一点小额捐赠。哪怕 1 分钱，对我也是很大的鼓励。

<img src="assets/support/alipay.jpg" alt="支付宝支持二维码" width="180">

另外，哥们现在也没有收入来源 💀。你的捐赠会帮我喂饱我的两个毛孩子：Jessie 和 Yolo <3

这完全是自愿的。捐赠不会改变许可证、issue 优先级、功能优先级或支持预期。

### Jessie 和 Yolo

| Jessie 第一天                                                                         | Jessie                                                            | 还是 Jessie                                                            |
| ------------------------------------------------------------------------------------- | ----------------------------------------------------------------- | ---------------------------------------------------------------------- |
| <img src="assets/cats/jessie-first-day.jpg" alt="Jessie 第一天" width="220">          | <img src="assets/cats/jessie-1.jpg" alt="Jessie" width="220">     | <img src="assets/cats/jessie-2.jpg" alt="还是 Jessie" width="220">      |

| 小小 Yolo                                                            | Yolo                                                          | 还是 Yolo                                                          | Jessie 和 Yolo 在一起                                                                   |
| -------------------------------------------------------------------- | ------------------------------------------------------------- | ------------------------------------------------------------------ | ---------------------------------------------------------------------------------------- |
| <img src="assets/cats/smol-yolo.jpg" alt="小小 Yolo" width="180">    | <img src="assets/cats/yolo-1.jpg" alt="Yolo" width="180">     | <img src="assets/cats/yolo-2.jpg" alt="还是 Yolo" width="180">     | <img src="assets/cats/yolo-and-jessie.jpg" alt="Jessie 和 Yolo 在一起" width="240">      |
