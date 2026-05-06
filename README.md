# 语音转写与角色分离工具

本项目基于 Python + Gradio，调用讯飞 `raasr` 接口实现音视频转写、角色分离、时间轴对齐，以及网页内二次校对导出。

本文档目标：**在 Windows + Conda 下精准复原可运行环境并完成复现**。

---

## 1. 项目功能与代码结构

- 主程序：`app（注释版）.py`
- 命令行版本：`xunfei-asr.py`
- 环境变量文件：`.env`
- 输出文件：`transcript_output.txt`、`edited_transcript.txt`

核心逻辑：
- `clip_custom_audio()`：按起始秒 + 时长截取音频
- `upload_audio()`：上传至讯飞 `upload` 接口
- `get_result()`：轮询 `getResult` 接口直到完成
- `parse_and_save()`：解析 `lattice/lattice2`，追踪说话人并回写全局时间轴
- Gradio 页面支持在线校对并导出修订版 txt

---

## 2. 精准复现环境（推荐）

### 2.1 基础前提

- 操作系统：Windows 10/11（项目当前在 Win32 验证）
- Conda：推荐 Miniconda/Anaconda
- Python 版本：`3.10.19`
- FFmpeg：`8.0.1`（建议 conda 安装，避免 PATH 问题）

### 2.2 创建并激活环境

```powershell
conda create -n simgcl python=3.10.19 -y
conda activate simgcl
```

### 2.3 安装运行本项目的关键依赖（精确版本）

```powershell
pip install requests==2.32.5 pydub==0.25.1 gradio==6.13.0 python-dotenv==1.2.2
```

### 2.4 安装 FFmpeg（必须）

```powershell
conda install -c conda-forge ffmpeg=8.0.1 -y
```

安装后可验证：

```powershell
ffmpeg -version
python -c "import gradio,requests,pydub,dotenv; print('deps ok')"
```

---

## 3. 环境变量配置

在项目根目录创建（或修改）`.env`：

```env
XUNFEI_APPID=你的APPID
XUNFEI_API_SECRET=你的SECRET_KEY
```

说明：
- `app（注释版）.py` 启动时会自动读取同目录 `.env`
- 若变量缺失会直接抛出错误并终止（代码中已做校验）
- 不建议将真实密钥提交到仓库

---

## 4. 运行方式

### 4.1 启动 Web UI（推荐）

```powershell
python "app（注释版）.py"
```

默认行为：
- 服务地址：`http://127.0.0.1:7860`
- 自动打开浏览器（`inbrowser=True`）
- 页面流程：
  - 上传音/视频文件
  - 设置开始时间（秒）与截取时长（秒）
  - 点击“开始智能转写”
  - 在文本框内修改后点击“保存修改并生成下载文件”

### 4.2 运行命令行脚本（固定截取前 60 秒）

```powershell
python xunfei-asr.py
```

注意：该脚本默认读取 `AUDIO_FILE = "托盘贸易-AI初试题.mp3"`，请按需修改脚本内文件名。

---

## 5. 结果文件说明

- `transcript_output.txt`：模型首次转写结果
- `edited_transcript.txt`：网页中人工校对后保存结果

输出格式示例：

```text
00:00:05 - 00:00:08 说话人1
你好，欢迎来到今天的会议。
```

---

## 6. 复现自检清单（建议逐项核对）

1. `python --version` 为 `3.10.19`
2. `pip show gradio pydub python-dotenv requests` 版本分别为 `6.13.0 / 0.25.1 / 1.2.2 / 2.32.5`
3. `ffmpeg -version` 可正常输出
4. 根目录 `.env` 存在且键名为 `XUNFEI_APPID`、`XUNFEI_API_SECRET`
5. 运行 `python "app（注释版）.py"` 后可打开 `127.0.0.1:7860`
6. 上传测试音频后能生成 `transcript_output.txt`

---

## 7. 常见问题排查

- 启动时报秘钥缺失  
  检查 `.env` 文件位置是否在项目根目录，键名是否完全一致。

- `pydub` 读取音频失败  
  通常是 FFmpeg 未安装或未生效，重新执行 `conda install -c conda-forge ffmpeg=8.0.1 -y`。

- 讯飞接口返回失败  
  检查 APPID/SECRET 是否正确、账号额度是否充足、网络是否可访问 `https://raasr.xfyun.cn`。

- 端口冲突  
  修改 `demo.launch(server_name="127.0.0.1", server_port=7860, ...)` 中端口后重启。
