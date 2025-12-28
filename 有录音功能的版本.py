import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from pydub import AudioSegment
import io
import base64
import tempfile
import os
import docx
import PyPDF2
from io import BytesIO

# 页面配置
st.set_page_config(
    page_title="英语听力练习器",
    page_icon="🎧",
    layout="wide"
)

# 自定义CSS
st.markdown("""
<style>
    .subtitle-line {
        padding: 10px;
        margin: 5px 0;
        border-radius: 5px;
        cursor: pointer;
        transition: all 0.3s;
    }
    .subtitle-line:hover {
        background-color: #f0f2f6;
    }
    .playing {
        background-color: #e6f7ff !important;
        border-left: 4px solid #1890ff;
    }
    .word-highlight {
        background-color: #fff566;
        padding: 2px 4px;
        border-radius: 3px;
        cursor: pointer;
    }
    .upload-area {
        border: 2px dashed #ccc;
        border-radius: 10px;
        padding: 20px;
        text-align: center;
        margin: 10px 0;
        background-color: #f9f9f9;
    }
    .upload-area:hover {
        border-color: #1890ff;
        background-color: #f0f7ff;
    }
</style>
""", unsafe_allow_html=True)

# 初始化session state
def init_session_state():
    if 'audio_file' not in st.session_state:
        st.session_state.audio_file = None
    if 'current_time' not in st.session_state:
        st.session_state.current_time = 0
    if 'is_playing' not in st.session_state:
        st.session_state.is_playing = False
    if 'playback_rate' not in st.session_state:
        st.session_state.playback_rate = 1.0
    if 'vocabulary' not in st.session_state:
        st.session_state.vocabulary = []
    if 'subtitles' not in st.session_state:
        st.session_state.subtitles = []
    if 'current_subtitle' not in st.session_state:
        st.session_state.current_subtitle = 0
    if 'subtitle_text' not in st.session_state:
        st.session_state.subtitle_text = ""

init_session_state()

# 解析DOCX文件
def parse_docx(file):
    doc = docx.Document(file)
    full_text = []
    for paragraph in doc.paragraphs:
        if paragraph.text.strip():  # 只添加非空段落
            full_text.append(paragraph.text)
    return '\n'.join(full_text)

# 解析PDF文件
def parse_pdf(file):
    pdf_reader = PyPDF2.PdfReader(file)
    full_text = []
    for page in pdf_reader.pages:
        text = page.extract_text()
        if text.strip():
            full_text.append(text)
    return '\n'.join(full_text)

# 解析SRT字幕
def parse_srt(content):
    subtitles = []
    blocks = content.strip().split('\n\n')
    
    for block in blocks:
        lines = block.split('\n')
        if len(lines) >= 3:
            try:
                # 解析时间戳
                time_line = lines[1]
                start_str, end_str = time_line.split(' --> ')
                
                # 转换时间格式 (HH:MM:SS,mmm -> 秒)
                def time_to_seconds(t):
                    h, m, s = t.split(':')
                    s, ms = s.split(',')
                    return int(h)*3600 + int(m)*60 + int(s) + int(ms)/1000
                
                start_time = time_to_seconds(start_str)
                end_time = time_to_seconds(end_str)
                
                # 合并文本行
                text = ' '.join(lines[2:])
                
                subtitles.append({
                    'id': lines[0],
                    'start': start_time,
                    'end': end_time,
                    'text': text,
                    'words': text.split()
                })
            except:
                continue
    
    return subtitles

# 解析纯文本为简单字幕格式（每行作为一句）
def parse_plain_text_to_subtitles(text_content, duration_per_line=5):
    """将纯文本转换为字幕格式，每行作为一句"""
    lines = text_content.strip().split('\n')
    subtitles = []
    
    current_time = 0
    for i, line in enumerate(lines):
        if line.strip():  # 跳过空行
            subtitles.append({
                'id': i + 1,
                'start': current_time,
                'end': current_time + duration_per_line,
                'text': line.strip(),
                'words': line.strip().split()
            })
            current_time += duration_per_line + 1  # 加1秒间隔
    
    return subtitles

# 侧边栏 - 简化的设置区域
with st.sidebar:
    st.title("⚙️ 设置面板")
    
    # 播放速度控制
    st.session_state.playback_rate = st.slider(
        "播放速度",
        min_value=0.5,
        max_value=2.0,
        value=1.0,
        step=0.1
    )
    
    # 练习模式选择
    practice_mode = st.selectbox(
        "练习模式",
        ["正常模式", "填空练习", "听写练习", "跟读练习"],
        help="选择适合你的练习方式"
    )
    
    # 显示选项
    show_translation = st.checkbox("显示中文翻译", value=True)
    highlight_words = st.checkbox("高亮生词", value=True)
    
    st.divider()
    
    # 上传区域 - 音频文件
    st.subheader("🎵 上传音频")
    uploaded_audio = st.file_uploader(
        "选择音频文件",
        type=['mp3', 'wav', 'm4a', 'ogg'],
        key="audio_uploader",
        help="支持 MP3, WAV, M4A, OGG 格式"
    )
    
    if uploaded_audio:
        st.session_state.audio_file = uploaded_audio
        st.success(f"✅ 已上传音频: {uploaded_audio.name}")
    
    st.divider()
    
    # 上传区域 - 字幕文件（支持多种格式）
    st.subheader("📝 上传字幕/文本")
    
    # 创建上传区域
    st.markdown('<div class="upload-area">📁 拖放或点击上传文件</div>', unsafe_allow_html=True)
    
    uploaded_subtitle = st.file_uploader(
        "选择字幕文件",
        type=['srt', 'txt', 'doc', 'docx', 'pdf'],
        key="subtitle_uploader",
        help="支持 SRT, TXT, DOC, DOCX, PDF 格式",
        label_visibility="collapsed"
    )
    
    if uploaded_subtitle:
        file_extension = uploaded_subtitle.name.split('.')[-1].lower()
        
        try:
            if file_extension == 'srt':
                # 处理SRT文件
                content = uploaded_subtitle.read().decode('utf-8', errors='ignore')
                st.session_state.subtitles = parse_srt(content)
                st.success(f"✅ 已加载 {len(st.session_state.subtitles)} 条SRT字幕")
                
            elif file_extension in ['doc', 'docx']:
                # 处理Word文档
                content = parse_docx(uploaded_subtitle)
                st.session_state.subtitle_text = content
                st.session_state.subtitles = parse_plain_text_to_subtitles(content)
                st.success(f"✅ 已从Word文档提取 {len(st.session_state.subtitles)} 条字幕")
                
            elif file_extension == 'pdf':
                # 处理PDF文件
                content = parse_pdf(uploaded_subtitle)
                st.session_state.subtitle_text = content
                st.session_state.subtitles = parse_plain_text_to_subtitles(content)
                st.success(f"✅ 已从PDF文件提取 {len(st.session_state.subtitles)} 条字幕")
                
            elif file_extension == 'txt':
                # 处理TXT文件
                content = uploaded_subtitle.read().decode('utf-8', errors='ignore')
                st.session_state.subtitle_text = content
                st.session_state.subtitles = parse_plain_text_to_subtitles(content)
                st.success(f"✅ 已从文本文件提取 {len(st.session_state.subtitles)} 条字幕")
            
            # 显示文本预览
            with st.expander("📄 查看原文内容"):
                st.text_area("文本内容", 
                           st.session_state.subtitle_text[:2000] + ("..." if len(st.session_state.subtitle_text) > 2000 else ""),
                           height=200)
                
        except Exception as e:
            st.error(f"❌ 文件处理失败: {str(e)}")
    
    st.divider()
    
    # 字幕编辑区域
    st.subheader("✏️ 字幕编辑")
    if st.session_state.subtitle_text:
        edited_text = st.text_area(
            "编辑字幕文本",
            value=st.session_state.subtitle_text,
            height=150,
            help="每行将作为一条独立字幕"
        )
        
        col1, col2 = st.columns(2)
        with col1:
            if st.button("💾 保存修改"):
                st.session_state.subtitles = parse_plain_text_to_subtitles(edited_text)
                st.session_state.subtitle_text = edited_text
                st.success("✅ 字幕已更新")
        with col2:
            if st.button("📥 下载字幕"):
                # 创建SRT格式
                srt_content = ""
                for i, sub in enumerate(st.session_state.subtitles):
                    start_h = int(sub['start'] // 3600)
                    start_m = int((sub['start'] % 3600) // 60)
                    start_s = int(sub['start'] % 60)
                    start_ms = int((sub['start'] - int(sub['start'])) * 1000)
                    
                    end_h = int(sub['end'] // 3600)
                    end_m = int((sub['end'] % 3600) // 60)
                    end_s = int(sub['end'] % 60)
                    end_ms = int((sub['end'] - int(sub['end'])) * 1000)
                    
                    srt_content += f"{i+1}\n"
                    srt_content += f"{start_h:02d}:{start_m:02d}:{start_s:02d},{start_ms:03d} --> {end_h:02d}:{end_m:02d}:{end_s:02d},{end_ms:03d}\n"
                    srt_content += f"{sub['text']}\n\n"
                
                st.download_button(
                    label="下载SRT文件",
                    data=srt_content,
                    file_name="subtitles.srt",
                    mime="text/plain"
                )

# 主界面
st.title("🎧 英语听力练习播放器")

# 音频播放器
if st.session_state.audio_file:
    col1, col2, col3 = st.columns([1, 2, 1])
    
    with col1:
        if st.button("▶️ 播放", key="play", type="primary", use_container_width=True):
            st.session_state.is_playing = True
            st.rerun()
    
    with col2:
        # 进度条
        progress = st.slider(
            "播放进度",
            min_value=0,
            max_value=100,
            value=st.session_state.current_time,
            format="%d%%",
            key="progress_slider",
            disabled=not st.session_state.audio_file
        )
    
    with col3:
        if st.button("⏸️ 暂停", key="pause", use_container_width=True):
            st.session_state.is_playing = False
            st.rerun()
    
    # 显示音频播放器
    st.audio(st.session_state.audio_file, format=f"audio/{st.session_state.audio_file.type.split('/')[-1]}")
    
    # 显示音频信息
    with st.expander("📊 音频信息"):
        audio_size = len(st.session_state.audio_file.getvalue())
        st.write(f"📁 文件名: {st.session_state.audio_file.name}")
        st.write(f"📏 文件大小: {audio_size / 1024:.1f} KB")
        st.write(f"⚡ 播放速度: {st.session_state.playback_rate}x")
else:
    st.info("👈 请在侧边栏上传音频文件")

# 显示字幕区域
st.markdown("---")
st.subheader("📝 字幕显示")

if st.session_state.subtitles:
    # 统计信息
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("总字幕数", len(st.session_state.subtitles))
    with col2:
        total_words = sum(len(sub['words']) for sub in st.session_state.subtitles)
        st.metric("总单词数", total_words)
    with col3:
        avg_words = total_words / len(st.session_state.subtitles) if st.session_state.subtitles else 0
        st.metric("平均每句", f"{avg_words:.1f}词")
    
    # 创建字幕显示容器
    subtitle_container = st.container()
    
    with subtitle_container:
        for i, subtitle in enumerate(st.session_state.subtitles):
            # 检查是否是当前播放的字幕
            is_current = (i == st.session_state.current_subtitle)
            
            # 创建列布局
            col1, col2 = st.columns([4, 1])
            
            with col1:
                # 显示时间戳和文本
                minutes = int(subtitle['start'] // 60)
                seconds = int(subtitle['start'] % 60)
                time_str = f"{minutes:02d}:{seconds:02d}"
                
                # 处理显示文本
                if practice_mode == "填空练习":
                    # 填空模式：每句话隐藏部分单词
                    import random
                    words = subtitle['words']
                    if len(words) > 3:
                        display_words = []
                        for word in words:
                            if random.random() < 0.3 and len(word) > 3:
                                display_words.append("_" * min(len(word), 8))
                            else:
                                display_words.append(word)
                        display_text = ' '.join(display_words)
                    else:
                        display_text = subtitle['text']
                else:
                    display_text = subtitle['text']
                
                # 高亮生词
                if highlight_words and st.session_state.vocabulary:
                    for word in st.session_state.vocabulary:
                        if word.lower() in display_text.lower():
                            display_text = display_text.replace(word, f"**{word}**")
                
                # 创建字幕卡片
                card_style = "playing" if is_current else ""
                st.markdown(f"""
                <div class="subtitle-line {card_style}" style="padding: 15px; margin: 10px 0; border-radius: 8px;">
                    <div style="color: #666; font-size: 12px; margin-bottom: 5px;">{time_str}</div>
                    <div style="font-size: 16px; line-height: 1.6;">{display_text}</div>
                </div>
                """, unsafe_allow_html=True)
            
            with col2:
                # 操作按钮
                btn_col1, btn_col2 = st.columns(2)
                
                with btn_col1:
                    if st.button("🔊", key=f"play_{i}", help="播放这句话"):
                        st.info(f"播放: {subtitle['text'][:50]}...")
                        # 这里可以添加音频播放逻辑
                
                with btn_col2:
                    if st.button("⭐", key=f"star_{i}", help="标记生词"):
                        # 显示单词选择器
                        with st.popover("选择生词"):
                            for word in subtitle['words']:
                                if word.isalpha():  # 只显示纯单词
                                    if st.button(word, key=f"word_{i}_{word}"):
                                        if word not in st.session_state.vocabulary:
                                            st.session_state.vocabulary.append(word)
                                            st.success(f"已添加生词: {word}")
                                            st.rerun()
    
    # 分页控制
    if len(st.session_state.subtitles) > 20:
        st.markdown("---")
        st.write("📄 分页导航")
        
        page_size = 20
        total_pages = (len(st.session_state.subtitles) + page_size - 1) // page_size
        
        col1, col2, col3 = st.columns([1, 2, 1])
        with col1:
            page = st.number_input("页码", min_value=1, max_value=total_pages, value=1, step=1)
        
        with col2:
            st.write(f"第 {page} 页 / 共 {total_pages} 页")
        
        with col3:
            if st.button("跳转到该页"):
                start_idx = (page - 1) * page_size
                st.session_state.current_subtitle = start_idx
                st.rerun()

else:
    st.info("👈 请在侧边栏上传字幕或文本文件")
    
    # 提供示例文本
    with st.expander("💡 不知道上传什么？试试这个示例文本"):
        sample_text = """Hello, welcome to English listening practice.
Today we will learn about daily conversations.
How are you doing today?
I'm doing great, thank you for asking.
What do you do for a living?
I work as a software developer.
That sounds interesting.
Yes, I enjoy solving problems with code.
Let's practice some more sentences.
The weather is nice today."""
        
        if st.button("使用示例文本"):
            st.session_state.subtitle_text = sample_text
            st.session_state.subtitles = parse_plain_text_to_subtitles(sample_text)
            st.success("✅ 已加载示例文本")
            st.rerun()

# 练习功能区域
st.markdown("---")
st.subheader("💪 学习工具")

tab1, tab2, tab3, tab4 = st.tabs(["生词本", "笔记", "测试", "统计"])

with tab1:
    st.write("### 📒 我的生词本")
    
    if st.session_state.vocabulary:
        # 显示生词列表
        for word in st.session_state.vocabulary:
            col1, col2 = st.columns([3, 1])
            with col1:
                st.write(f"- **{word}**")
            with col2:
                if st.button("🗑️", key=f"del_{word}"):
                    st.session_state.vocabulary.remove(word)
                    st.rerun()
        
        # 操作按钮
        col1, col2 = st.columns(2)
        with col1:
            if st.button("📥 导出生词本"):
                vocab_text = "\n".join(st.session_state.vocabulary)
                st.download_button(
                    label="下载TXT文件",
                    data=vocab_text,
                    file_name="my_vocabulary.txt",
                    mime="text/plain"
                )
        with col2:
            if st.button("🗑️ 清空生词本"):
                st.session_state.vocabulary = []
                st.rerun()
    else:
        st.info("还没有添加生词。点击字幕旁边的⭐按钮来添加生词。")
        
    # 手动添加生词
    st.write("### ➕ 手动添加生词")
    new_word = st.text_input("输入新单词")
    if st.button("添加"):
        if new_word and new_word not in st.session_state.vocabulary:
            st.session_state.vocabulary.append(new_word)
            st.success(f"已添加: {new_word}")
            st.rerun()

with tab2:
    st.write("### 📝 学习笔记")
    
    # 笔记输入
    note = st.text_area("记录你的学习笔记", height=150, placeholder="在这里记录学习心得、难点或学习计划...")
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("保存笔记", use_container_width=True):
            if note:
                if 'notes' not in st.session_state:
                    st.session_state.notes = []
                st.session_state.notes.append({
                    'time': pd.Timestamp.now().strftime("%Y-%m-%d %H:%M"),
                    'content': note
                })
                st.success("笔记已保存！")
    
    with col2:
        if st.button("清空输入", use_container_width=True):
            st.rerun()
    
    # 显示历史笔记
    if 'notes' in st.session_state and st.session_state.notes:
        st.write("### 📋 历史笔记")
        for i, n in enumerate(reversed(st.session_state.notes[-10:]), 1):
            with st.expander(f"{n['time']} - {n['content'][:50]}..."):
                st.write(n['content'])

with tab3:
    st.write("### 📝 听力测试")
    
    if st.session_state.subtitles:
        test_type = st.radio(
            "测试类型",
            ["听写练习", "填空测试", "理解测试"],
            horizontal=True
        )
        
        if test_type == "听写练习":
            # 随机选择句子进行听写
            import random
            
            if 'test_sentence' not in st.session_state:
                st.session_state.test_sentence = random.choice(st.session_state.subtitles)['text']
            
            st.write("**听写以下句子：**")
            st.write(f"> {st.session_state.test_sentence}")
            
            user_input = st.text_area("输入你听到的内容", height=100)
            
            col1, col2 = st.columns(2)
            with col1:
                if st.button("提交答案"):
                    # 简单对比
                    if user_input.strip().lower() == st.session_state.test_sentence.lower():
                        st.success("🎉 完全正确！")
                    else:
                        st.warning("有错误，请再听一遍")
            
            with col2:
                if st.button("下一题"):
                    st.session_state.test_sentence = random.choice(st.session_state.subtitles)['text']
                    st.rerun()
        
        elif test_type == "填空测试":
            st.info("生成填空测试功能开发中...")
        
        elif test_type == "理解测试":
            st.info("理解测试功能开发中...")
    else:
        st.info("请先上传字幕文件进行测试")

with tab4:
    st.write("### 📊 学习统计")
    
    if st.session_state.subtitles:
        # 计算统计数据
        total_sentences = len(st.session_state.subtitles)
        total_words = sum(len(sub['words']) for sub in st.session_state.subtitles)
        avg_words = total_words / total_sentences if total_sentences > 0 else 0
        total_vocab = len(st.session_state.vocabulary)
        
        # 显示统计卡片
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("学习句子", total_sentences)
        with col2:
            st.metric("总单词数", total_words)
        with col3:
            st.metric("平均每句", f"{avg_words:.1f}词")
        with col4:
            st.metric("生词数量", total_vocab)
        
        # 单词频率分析
        st.write("### 📈 单词频率分析")
        if st.button("生成词频分析"):
            from collections import Counter
            all_words = []
            for sub in st.session_state.subtitles:
                all_words.extend([word.lower() for word in sub['words'] if word.isalpha()])
            
            word_freq = Counter(all_words)
            top_words = word_freq.most_common(20)
            
            # 创建图表
            words = [word for word, freq in top_words]
            freqs = [freq for word, freq in top_words]
            
            fig = go.Figure(data=[
                go.Bar(x=words, y=freqs, marker_color='lightseagreen')
            ])
            fig.update_layout(
                title="高频单词TOP 20",
                xaxis_title="单词",
                yaxis_title="出现次数",
                height=400
            )
            st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("请先上传字幕文件查看统计")

# 响应式音频波形图
if st.session_state.audio_file and st.session_state.subtitles:
    st.markdown("---")
    st.subheader("📊 学习进度")
    
    # 创建简单的进度图
    total_duration = max(sub['end'] for sub in st.session_state.subtitles) if st.session_state.subtitles else 0
    
    # 计算学习进度
    learned_count = min(st.session_state.current_subtitle + 1, len(st.session_state.subtitles))
    progress_percent = (learned_count / len(st.session_state.subtitles)) * 100 if st.session_state.subtitles else 0
    
    # 显示进度条
    st.progress(progress_percent / 100)
    st.write(f"**学习进度:** {learned_count}/{len(st.session_state.subtitles)} 句 ({progress_percent:.1f}%)")

# 底部信息
st.markdown("---")
st.markdown("""
<div style="text-align: center; color: #666; padding: 20px;">
    <h4>🎯 学习建议</h4>
    <p>• 每天坚持练习15-30分钟 • 先整体听，再逐句精听 • 跟读模仿发音 • 定期复习生词</p>
</div>
""", unsafe_allow_html=True)

# 安装说明
with st.expander("📦 安装说明"):
    st.write("""
    **依赖安装:**
    ```bash
    pip install streamlit pandas numpy plotly pydub python-docx PyPDF2
    ```
    
    **运行应用:**
    ```bash
    streamlit run app.py
    ```
    
    **支持的文件格式:**
    - 音频: MP3, WAV, M4A, OGG
    - 字幕/文本: SRT, TXT, DOC, DOCX, PDF
    """)
