# app.py
import streamlit as st
import pandas as pd
from datetime import datetime
import requests
from io import BytesIO
import re

st.set_page_config(page_title="JVS強調アノテーション", layout="wide")

# CSSで全体を圧縮
st.markdown("""
<style>
    .block-container {padding-top: 1rem; padding-bottom: 1rem;}
    h1 {font-size: 1.5rem; margin-bottom: 0.5rem;}
    h2 {font-size: 1.2rem; margin-bottom: 0.3rem;}
    h3 {font-size: 1.1rem; margin-bottom: 0.3rem;}
    .stButton button {padding: 0.25rem 0.5rem;}
</style>
""", unsafe_allow_html=True)

# Google Drive URLを直接ダウンロードURLに変換
def convert_drive_url(url):
    """Google DriveのURLを直接ダウンロード可能なURLに変換"""
    patterns = [
        r'drive\.google\.com/file/d/([a-zA-Z0-9_-]+)',
        r'drive\.google\.com/open\?id=([a-zA-Z0-9_-]+)',
        r'id=([a-zA-Z0-9_-]+)'
    ]
    
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            file_id = match.group(1)
            return f"https://drive.google.com/uc?export=download&id={file_id}"
    
    return url

# Google Sheetsから直接読み込み
@st.cache_data(ttl=600)
def load_data_from_sheets(sheet_url):
    """Google SheetsのURLからデータを読み込む"""
    try:
        if 'docs.google.com/spreadsheets' in sheet_url:
            sheet_id = sheet_url.split('/d/')[1].split('/')[0]
            gid = '0'
            if 'gid=' in sheet_url:
                gid = sheet_url.split('gid=')[1].split('&')[0]
            
            csv_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={gid}"
            df = pd.read_csv(csv_url)
            return df.to_dict('records')
        else:
            st.error("正しいGoogle SheetsのURLを入力してください")
            return []
    except Exception as e:
        st.error(f"データ読み込みエラー: {e}")
        st.info("Sheetsが「リンクを知っている全員」に公開されているか確認してください")
        return []

# 音声データをGoogle Driveから取得
@st.cache_data
def load_audio_from_drive(drive_url):
    """Google Driveから音声ファイルを取得"""
    try:
        download_url = convert_drive_url(drive_url)
        session = requests.Session()
        response = session.get(download_url, stream=True)
        
        if 'download_warning' in response.text or 'virus scan warning' in response.text:
            for key, value in response.cookies.items():
                if key.startswith('download_warning'):
                    params = {'confirm': value}
                    response = session.get(download_url, params=params, stream=True)
                    break
        
        if response.status_code == 200:
            return response.content
        else:
            return None
            
    except Exception as e:
        st.error(f"音声読み込みエラー: {e}")
        return None

def tokenize_text(text):
    """テキストを単語に分割（簡易版：1文字ずつ）"""
    return list(text)

# セッション状態の初期化
if 'current_idx' not in st.session_state:
    st.session_state.current_idx = 0
if 'annotations' not in st.session_state:
    st.session_state.annotations = []
if 'selected_words' not in st.session_state:
    st.session_state.selected_words = set()
if 'data_loaded' not in st.session_state:
    st.session_state.data_loaded = False
if 'selecting' not in st.session_state:
    st.session_state.selecting = False
if 'select_start' not in st.session_state:
    st.session_state.select_start = None
if 'page' not in st.session_state:
    st.session_state.page = 'instruction'
if 'current_sheet' not in st.session_state:
    st.session_state.current_sheet = None

# サイドバー
st.sidebar.title("⚙️ 設定")

annotator_name = st.sidebar.text_input(
    "アノテーター名",
    value="annotator1",
    help="あなたの名前またはID"
)

# Google Sheetsデータセット選択
st.sidebar.subheader("📊 データソース")

# 事前定義されたURL
sheet_urls = {
    "JVS①": "https://docs.google.com/spreadsheets/d/1KqfyOWJoHR7V1Bztv_8H5dUeLqf2kCZ_0tdmXPVCPoc/edit?usp=sharing",
    "JVS②": "https://docs.google.com/spreadsheets/d/1n4-bXPp0kGuOZ9ugoYrcm2JVn5xGRkrbQrCqyQ0ksMA/edit?usp=sharing",
    "JVS③": "https://docs.google.com/spreadsheets/d/1Z0XD71qcbUh7JzJUs0Dj1Kp3HxAxvR95OQiSB3rix1o/edit?usp=sharing",
    "JVS④": "https://docs.google.com/spreadsheets/d/1gyCKuFvnkAcpWG1GTi17-pjI9k1EwEpMj8sPD6ZxZhI/edit?usp=sharing",
    "JVS⑤": "https://docs.google.com/spreadsheets/d/1e5aqmRqit9mH3iVJyB_jjqwiAr27eIAoUl-LUqULzPs/edit?usp=sharing"
}

st.sidebar.markdown("**データセットを選択:**")

# ボタンを縦に並べる
for name, url in sheet_urls.items():
    if st.sidebar.button(name, use_container_width=True):
        with st.spinner(f"{name}のデータを読み込み中..."):
            data = load_data_from_sheets(url)
            if data:
                st.session_state.data = data
                st.session_state.data_loaded = True
                st.session_state.current_sheet = name
                st.session_state.current_idx = 0  # 最初から開始
                st.session_state.annotations = []  # アノテーションリセット
                st.sidebar.success(f"✅ {name}: {len(data)}件読み込み完了")
                st.rerun()

# 現在読み込まれているデータセットを表示
if st.session_state.data_loaded and st.session_state.current_sheet:
    st.sidebar.info(f"📂 現在: {st.session_state.current_sheet}")

# ページ切り替え
if st.session_state.page == 'instruction':
    # ========== 説明ページ ==========
    st.title("📋 アノテーション作業の説明")
    
    st.markdown("""
    ## 作業の目的
    
    音声を聴いて、**強調されている部分**を特定し、ラベル付けを行います。
    
    ---
    
    ## 強調とは？
    
    話者が**意図的に際立たせている**音節や単語のことです。
    
    **例:**
    - 「**今日**はいい天気ですね」→「今日」が強調
    - 「今日はいい**天気**ですね」→「天気」が強調
    
    ---
    
    ## 判断基準
    
    以下の特徴がある場合、強調と判断してください：
    
    1. **音量が大きい**
    2. **ピッチが高い（または変化が大きい）**
    3. **発話速度が遅い（はっきり発音）**
    4. **前後の音との対比が明確**
    
    ---
    
    ## 作業の流れ
    
    1. 音声を聴く
    2. 強調されている文字を選択
       - **通常モード**: 1文字ずつクリック
       - **範囲選択モード**: 開始→終了で複数選択
    3. 「保存して次へ」で次の音声へ
    
    ---
    
    ## 注意事項
    
    - 強調がない場合は何も選択せずに「保存して次へ」
    - 迷った場合は「全解除」で最初からやり直せます
    - 間違えた場合は「前へ」で戻れます
    
    ---
    
    ## 作業時間の目安
    
    - 1音声あたり: 約30秒〜1分
    - 各データセット100音声: 約1〜2時間
    
    ---
    
    ## 準備
    
    1. 左サイドバーにアノテーター名を入力
    2. JVS①〜⑤のいずれかをクリック
    3. 下のボタンでアノテーション開始
    
    """)
    
    st.markdown("---")
    
    if st.button("📝 アノテーション作業を開始", type="primary", use_container_width=True):
        st.session_state.page = 'annotation'
        st.rerun()

else:
    # ========== アノテーションページ ==========
    
    # ページ切り替えボタン
    if st.button("📋 説明ページに戻る"):
        st.session_state.page = 'instruction'
        st.rerun()
    
    # メインコンテンツ
    if st.session_state.data_loaded and 'data' in st.session_state:
        data = st.session_state.data
        
        # 進捗表示
        total = len(data)
        current = st.session_state.current_idx + 1
        completed = len(st.session_state.annotations)
        
        st.sidebar.markdown("---")
        st.sidebar.subheader("📈 進捗")
        st.sidebar.metric("現在", f"{current} / {total}")
        st.sidebar.metric("完了", completed)
        st.sidebar.progress(current / total)
        
        # 現在のアイテム
        item = data[st.session_state.current_idx]
        
        # メインエリア（圧縮版）
        st.markdown("### 🎯 強調アノテーション")
        
        # 音声再生エリア（コンパクト）
        col1, col2 = st.columns([4, 1])
        
        with col1:
            audio_url = item.get('audioUrl') or item.get('audio_url')
            if audio_url:
                audio_bytes = load_audio_from_drive(audio_url)
                if audio_bytes:
                    st.audio(audio_bytes, format='audio/wav')
                else:
                    st.error("音声読み込み失敗")
        
        with col2:
            st.caption(f"**{item.get('speaker', 'N/A')}**")
            st.caption(f"{item.get('filename', 'N/A')}")
        
        # テキスト表示と単語選択
        text = item.get('text', '')
        if text:
            words = tokenize_text(text)
            
            # 選択モード切り替え（コンパクト）
            cols = st.columns([1, 1, 3])
            
            with cols[0]:
                if st.button("🎯 範囲選択", use_container_width=True, type="primary" if st.session_state.selecting else "secondary"):
                    st.session_state.selecting = not st.session_state.selecting
                    if not st.session_state.selecting:
                        st.session_state.select_start = None
                    st.rerun()
            
            with cols[1]:
                if st.button("🔄 全解除", use_container_width=True):
                    st.session_state.selected_words = set()
                    st.session_state.selecting = False
                    st.session_state.select_start = None
                    st.rerun()
            
            # モード表示（1行で）
            if st.session_state.selecting:
                if st.session_state.select_start is None:
                    st.caption("📍 開始位置をクリック")
                else:
                    st.caption(f"📍 「{words[st.session_state.select_start]}」から選択中 → 終了位置をクリック")
            else:
                st.caption("💡 クリックで選択・解除")
            
            # 単語選択UI
            words_per_row = 20
            for row_start in range(0, len(words), words_per_row):
                row_words = words[row_start:row_start + words_per_row]
                cols = st.columns(len(row_words))
                
                for col_idx, word in enumerate(row_words):
                    idx = row_start + col_idx
                    with cols[col_idx]:
                        is_selected = idx in st.session_state.selected_words
                        
                        # 範囲選択モード
                        if st.session_state.selecting:
                            if st.button(word, key=f"word_{idx}", type="primary" if is_selected else "secondary", use_container_width=True):
                                if st.session_state.select_start is None:
                                    st.session_state.select_start = idx
                                    st.rerun()
                                else:
                                    start = min(st.session_state.select_start, idx)
                                    end = max(st.session_state.select_start, idx)
                                    for i in range(start, end + 1):
                                        st.session_state.selected_words.add(i)
                                    st.session_state.selecting = False
                                    st.session_state.select_start = None
                                    st.rerun()
                        # 通常モード
                        else:
                            if st.button(word, key=f"word_{idx}", type="primary" if is_selected else "secondary", use_container_width=True):
                                if idx in st.session_state.selected_words:
                                    st.session_state.selected_words.remove(idx)
                                else:
                                    st.session_state.selected_words.add(idx)
                                st.rerun()
            
            # 選択結果のプレビュー（コンパクト）
            st.markdown("**選択結果:**")
            
            preview_html = "<div style='font-size: 20px; line-height: 1.5; margin-bottom: 0.5rem;'>"
            for idx, word in enumerate(words):
                if idx in st.session_state.selected_words:
                    preview_html += f"<span style='color: red; font-weight: bold;'>[{word}]</span>"
                else:
                    preview_html += word
            preview_html += "</div>"
            
            st.markdown(preview_html, unsafe_allow_html=True)
            
            if st.session_state.selected_words:
                selected_list = [words[i] for i in sorted(st.session_state.selected_words)]
                st.caption(f"✓ {', '.join(selected_list)}")
        
        # ボタンエリア
        col1, col2 = st.columns(2)
        
        with col1:
            if st.button(
                "⬅️ 前へ",
                disabled=(st.session_state.current_idx == 0),
                use_container_width=True
            ):
                st.session_state.current_idx -= 1
                st.session_state.selected_words = set()
                st.session_state.selecting = False
                st.session_state.select_start = None
                st.rerun()
        
        with col2:
            if st.button("💾 保存して次へ", type="primary", use_container_width=True):
                if text:
                    selected_indices = sorted(list(st.session_state.selected_words))
                    emphasized_words = [words[i] for i in selected_indices]
                    
                    bracketed_text = ""
                    for idx, word in enumerate(words):
                        if idx in st.session_state.selected_words:
                            bracketed_text += f"[{word}]"
                        else:
                            bracketed_text += word
                    
                    annotation = {
                        'annotator': annotator_name,
                        'dataset': st.session_state.current_sheet,
                        'filename': item.get('filename', 'N/A'),
                        'speaker': item.get('speaker', 'N/A'),
                        'text': text,
                        'emphasized_words': ', '.join(emphasized_words) if emphasized_words else '',
                        'emphasized_indices': ', '.join(map(str, selected_indices)) if selected_indices else '',
                        'annotated_text': bracketed_text,
                        'has_emphasis': len(emphasized_words) > 0,
                        'timestamp': datetime.now().isoformat()
                    }
                    
                    st.session_state.annotations.append(annotation)
                    
                    if st.session_state.current_idx < total - 1:
                        st.session_state.current_idx += 1
                        st.session_state.selected_words = set()
                        st.session_state.selecting = False
                        st.session_state.select_start = None
                        st.rerun()
                    else:
                        st.balloons()
                        st.success("🎉 完了！")
        
        # サイドバー：エクスポート
        st.sidebar.markdown("---")
        st.sidebar.subheader("📥 データ出力")
        
        if len(st.session_state.annotations) > 0:
            with_emphasis = sum(1 for a in st.session_state.annotations if a['has_emphasis'])
            without_emphasis = len(st.session_state.annotations) - with_emphasis
            
            st.sidebar.metric("強調あり", with_emphasis)
            st.sidebar.metric("強調なし", without_emphasis)
            
            if st.sidebar.button("📊 エクセルをダウンロード", use_container_width=True):
                df = pd.DataFrame(st.session_state.annotations)
                
                output = BytesIO()
                with pd.ExcelWriter(output, engine='openpyxl') as writer:
                    df.to_excel(writer, index=False, sheet_name='Annotations')
                    
                    worksheet = writer.sheets['Annotations']
                    for idx, col in enumerate(df.columns):
                        max_length = max(df[col].astype(str).apply(len).max(), len(col))
                        worksheet.column_dimensions[chr(65 + idx)].width = min(max_length + 2, 50)
                
                output.seek(0)
                
                filename = f"annotations_{annotator_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
                
                st.sidebar.download_button(
                    label="⬇️ ダウンロード",
                    data=output,
                    file_name=filename,
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True
                )
    
    else:
        st.info("👈 左のサイドバーからデータセットを選択してください")

st.markdown("---")
st.caption("JVS強調アノテーションツール v1.0")