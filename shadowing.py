import streamlit as st
import whisper 
import os
import tempfile


st.set_page_config(page_title="英语听力精听工具", layout="wide")
st.title("🎧 英语听力精听 Web App（自动断句 + 自动字幕）")


# -------- Upload --------
uploaded = st.file_uploader(
    "上传音频文件（支持 mp3 / wav / m4a）",
    type=["mp3", "wav", "m4a"]
)

if uploaded:

    # 保存临时文件
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
    temp_file.write(uploaded.read())
    temp_file.close()

    st.success("音频上传成功！")
    st.audio(temp_file.name)

    st.info("⏳ 正在识别音频，请稍等...（第一次会稍慢，之后会快很多）")

    # -------- Whisper --------
    model = whisper.load_model("base")
    result = model.transcribe(temp_file.name)

    st.subheader("📌 整体识别文本")
    st.write(result["text"])

    st.subheader("📍 自动断句（逐句展示）")

    segments = result["segments"]

    for seg in segments:
        start = round(seg["start"], 2)
        end = round(seg["end"], 2)
        text = seg["text"]

        with st.container():
            st.markdown(f"**🕒 {start} s → {end} s**")
            st.write(text)
            st.markdown("---")

    os.remove(temp_file.name)

else:
    st.info("请上传音频文件开始体验 😊")
