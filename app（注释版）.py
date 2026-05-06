import os
from dotenv import load_dotenv
import time
import json
import base64
import hashlib
import hmac
import requests
import datetime
import gradio as gr
from pydub import AudioSegment

# 强行绕过系统代理，解决 502 报错
os.environ["NO_PROXY"] = "localhost,127.0.0.1,::1"

# 自动寻找并加载同级目录下的 .env 文件
load_dotenv()

# ================= 配置区 =================
APPID = os.getenv("XUNFEI_APPID").strip() if os.getenv("XUNFEI_APPID") else ""
SECRET_KEY = os.getenv("XUNFEI_API_SECRET").strip() if os.getenv("XUNFEI_API_SECRET") else ""

UPLOAD_URL = "https://raasr.xfyun.cn/v2/api/upload"
RESULT_URL = "https://raasr.xfyun.cn/v2/api/getResult"

if not APPID or not SECRET_KEY:
    raise ValueError("⚠️ 未找到讯飞 API 秘钥，请检查根目录下是否已正确配置 .env 文件！")


# ==========================================

# ----------------- 核心算法逻辑 -----------------
def format_time(ms):
    seconds = ms // 1000
    td = datetime.timedelta(seconds=seconds)
    return str(td).split(".")[0].zfill(8)


def get_signature(ts):
    base_string = APPID + str(ts)
    md5_string = hashlib.md5(base_string.encode('utf-8')).hexdigest()
    signa = hmac.new(SECRET_KEY.encode('utf-8'), md5_string.encode('utf-8'), hashlib.sha1).digest()
    return base64.b64encode(signa).decode('utf-8')


def clip_custom_audio(input_path, output_path, start_sec, duration_sec):
    """【重构】根据用户指定的起始时间和持续时间截取音频"""
    try:
        audio = AudioSegment.from_file(input_path)

        # 将秒转换为毫秒
        start_ms = int(start_sec * 1000)
        duration_ms = int(duration_sec * 1000)
        end_ms = start_ms + duration_ms

        # 边界情况（Corner Case）处理：如果开始时间超出了音频总长度
        if start_ms >= len(audio):
            raise ValueError(f"设置的开始时间({start_sec}秒)超出了音频总长度！")

        # 自由截取
        clipped_audio = audio[start_ms:end_ms]
        clipped_audio.export(output_path, format="mp3")
        return True
    except Exception as e:
        print(f"音频截取失败。错误信息: {e}")
        raise e


def upload_audio(file_path, duration_sec):
    """上传音频并返回任务 ID，同步传入动态时长"""
    file_len = os.path.getsize(file_path)
    ts = int(time.time())
    signa = get_signature(ts)

    req_params = {
        "appId": APPID,
        "signa": signa,
        "ts": ts,
        "fileSize": file_len,
        "duration": str(int(duration_sec)),  # 动态填入用户设定的时长
        "fileName": os.path.basename(file_path),
        "roleType": "1"
    }

    with open(file_path, 'rb') as f:
        file_bytes = f.read()

    headers = {"Content-Type": "application/json"}
    response = requests.post(UPLOAD_URL, params=req_params, data=file_bytes, headers=headers)
    res_dict = response.json()

    if res_dict.get("code") == "000000":
        return res_dict["content"]["orderId"]
    else:
        raise Exception(f"上传失败: {res_dict}")


def get_result(task_id):
    while True:
        ts = int(time.time())
        signa = get_signature(ts)

        req_params = {
            "appId": APPID,
            "signa": signa,
            "ts": ts,
            "orderId": task_id
        }
        headers = {"Content-Type": "application/json"}
        response = requests.post(RESULT_URL, params=req_params, headers=headers)
        res_dict = response.json()

        if res_dict.get("code") == "000000":
            status = res_dict["content"]["orderInfo"]["status"]
            if status == 4:
                return json.loads(res_dict["content"]["orderResult"])
            elif status == -1:
                raise Exception("云端处理失败，请检查音频格式。")
            else:
                time.sleep(3)
        else:
            raise Exception(f"查询结果失败: {res_dict}")


def parse_and_save(result_json, output_txt_path, time_offset_ms=0):
    """
    【细节优化】加入 time_offset_ms。
    如果用户从第60秒开始截，云端返回的时间轴是从0开始的。
    需要在写出 TXT 时，自动把这 60 秒加上去，让时间轴与原文件对齐！
    """
    with open(output_txt_path, "w", encoding="utf-8") as f:
        sentences = result_json.get("lattice", [])
        if not sentences:
            sentences = result_json.get("lattice2", [])

        current_speaker = "未知说话人"

        for sentence_data in sentences:
            try:
                best_data_str = sentence_data.get("json_1best", "{}")
                best_data = json.loads(best_data_str)

                # 识别出的时间 + 用户设定的偏移量
                start_ms = int(best_data["st"]["bg"]) + time_offset_ms
                end_ms = int(best_data["st"]["ed"]) + time_offset_ms
                start_time = format_time(start_ms)
                end_time = format_time(end_ms)

                rl = str(best_data["st"].get("rl", "0"))
                if rl != "0":
                    current_speaker = f"说话人{rl}"

                words = best_data["st"]["rt"][0]["ws"]
                text = "".join([w["cw"][0]["w"] for w in words])

                f.write(f"{start_time} - {end_time} {current_speaker}\n")
                f.write(f"{text}\n\n")
            except Exception:
                continue
def save_edited_text(edited_content):
    """【新增】将用户在网页上修改后的文本，保存为新的 txt 文件并提供下载"""
    edited_file_path = "edited_transcript.txt"
    with open(edited_file_path, "w", encoding="utf-8") as f:
        f.write(edited_content)
    return edited_file_path, gr.update(value="✅ 修改已成功保存！请点击下方文件下载。")

# ----------------- UI 交互与主流水线 -----------------
def process_pipeline(audio_file_path, start_sec, duration_sec):
    """主控桥梁：接收来自网页的多个参数"""
    if audio_file_path is None:
        return "⚠️ 请先音视频文件", None

    if duration_sec <= 0:
        return "⚠️ 截取时长必须大于0", None

    clipped_file = "temp_custom_audio.mp3"
    output_txt = "transcript_output.txt"

    try:
        # 1. 动态截取音频
        yield f"⏳ 正在截取从第 {start_sec} 秒开始，时长 {duration_sec} 秒的音频...", None
        clip_custom_audio(audio_file_path, clipped_file, start_sec, duration_sec)

        # 2. 上传云端
        yield "🚀 正在上传至云端...", None
        task_id = upload_audio(clipped_file, duration_sec)

        # 3. 轮询结果
        yield "🤖 AI正在理解并分离角色，请稍候...", None
        final_result = get_result(task_id)

        # 4. 生成文件（自动计算时间偏移量）
        yield "📝 正在对齐全局时间轴并生成文稿...", None
        offset_ms = int(start_sec * 1000)
        parse_and_save(final_result, output_txt, time_offset_ms=offset_ms)

        # 5. 读取文本用于展示
        with open(output_txt, "r", encoding="utf-8") as f:
            final_text = f.read()

        yield final_text, output_txt

    except Exception as e:
        yield f"❌ 处理过程中发生错误: {str(e)}", None

    finally:
        # 工程化兜底：不论成功失败，最后清理临时文件
        if os.path.exists(clipped_file):
            os.remove(clipped_file)


# ----------------- 构建网页可视化界面 -----------------
with gr.Blocks() as demo:
    gr.Markdown("""
    # 🎙️ 智能音视频转写与角色分离工作台
    **演示版|基于讯飞录音文件转写标准版 API 构建
    **包含人工校对功能** | 兼容 MP3/MP4/WAV
    """)

    with gr.Row():
        with gr.Column(scale=1):
            audio_input = gr.File(type="filepath", label="📂 拖拽或上传音视频文件", file_count="single")

            with gr.Row():
                start_input = gr.Number(value=0, label="开始时间 (秒)", precision=0)
                duration_input = gr.Number(value=60, label="截取时长 (秒)", precision=0)

            submit_btn = gr.Button("🚀 1. 开始智能转写", variant="primary")

            # 【新增】系统状态提示区
            status_text = gr.Textbox(label="系统运行状态", interactive=False, lines=1)

        with gr.Column(scale=1):
            gr.Markdown(
                "### 📝 在线编辑与校对区\n*AI 识别可能存在角色串音或错别字，请在此框内直接修改，修改完毕后点击保存。*")

            # 【核心修改】：开启 interactive=True，让原本只读的结果框变成可编辑的文本域
            text_output = gr.Textbox(label="转写结果 (支持直接修改)", lines=15, interactive=True)

            # 【新增】保存按钮与最终下载区
            save_btn = gr.Button("💾 2. 保存修改并生成下载文件", variant="secondary")
            file_output = gr.File(label="⬇️ 获取最终排版记录档")

    # 事件绑定 1：点击转写，处理音视频并输出初始文本
    submit_btn.click(
        fn=process_pipeline,
        inputs=[audio_input, start_input, duration_input],
        outputs=[status_text, file_output]  # 这里的输出先占位，实际文字交给 yield 显示
    ).success(
        # 为了让文本框实时滚动，保留流式输出的效果
        fn=process_pipeline,
        inputs=[audio_input, start_input, duration_input],
        outputs=[text_output, file_output]
    )

    # 【新增】事件绑定 2：点击保存按钮，将编辑框里的内容生成新文件
    save_btn.click(
        fn=save_edited_text,
        inputs=[text_output],
        outputs=[file_output, status_text]
    )

if __name__ == "__main__":
    demo.launch(server_name="127.0.0.1", server_port=7860, inbrowser=True)
