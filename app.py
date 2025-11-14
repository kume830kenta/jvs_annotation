# app.py
import streamlit as st
import pandas as pd
from datetime import datetime
import requests
from io import BytesIO
import re

st.set_page_config(page_title="JVS強調アノテーションツール", layout="wide")

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

# サイドバー
st.sidebar.title("⚙️ 設定")

annotator_name = st.sidebar.text_input(
    "アノテーター名",
    value="annotator1",
    help="あなたの名前またはID"
)

# Google SheetsのURL入力
st.sidebar.subheader("📊 データソース")
sheet_url = st.sidebar.text_input(
    "Google SheetsのURL",
    value="",
    help="スプレッドシートを「リンクを知っている全員」に公開してください",
    placeholder="https://docs.google.com/spreadsheets/d/..."
)

if st.sidebar.button("🔄 データを読み込む", type="primary"):
    if sheet_url:
        with st.spinner("データを読み込み中..."):
            data = load_data_from_sheets(sheet_url)
            if data:
                st.session_state.data = data
                st.session_state.data_loaded = True
                st.sidebar.success(f"✅ {len(data)}件のデータを読み込みました")
    else:
        st.sidebar.error("Google SheetsのURLを入力してください")

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
    
    # メインエリア
    st.title("🎯 強調アノテーション")
    
    # 音声再生エリア
    col1, col2 = st.columns([3, 1])
    
    with col1:
        st.subheader("🔊 音声を聴いてください")
        
        audio_url = item.get('audioUrl') or item.get('audio_url')
        if audio_url:
            with st.spinner("音声を読み込み中..."):
                audio_bytes = load_audio_from_drive(audio_url)
            
            if audio_bytes:
                st.audio(audio_bytes, format='audio/wav')
            else:
                st.error("音声を読み込めませんでした")
        else:
            st.error("音声URLが見つかりません")
    
    with col2:
        st.metric("話者", item.get('speaker', 'N/A'))
        st.caption(f"📁 {item.get('filename', 'N/A')}")
    
    st.markdown("---")
    
    # テキスト表示と単語選択
    st.subheader("📝 強調されている単語をクリックして選択")
    st.caption("💡 複数選択可能です。間違えて選択した場合は、もう一度クリックで解除できます。")
    
    text = item.get('text', '')
    if not text:
        st.warning("テキストが見つかりません")
    else:
        words = tokenize_text(text)
        
        # 単語選択UI
        words_per_row = 10
        for row_start in range(0, len(words), words_per_row):
            row_words = words[row_start:row_start + words_per_row]
            cols = st.columns(len(row_words))
            
            for col_idx, word in enumerate(row_words):
                idx = row_start + col_idx
                with cols[col_idx]:
                    is_selected = idx in st.session_state.selected_words
                    
                    if st.button(
                        word,
                        key=f"word_{idx}",
                        type="primary" if is_selected else "secondary",
                        use_container_width=True
                    ):
                        if idx in st.session_state.selected_words:
                            st.session_state.selected_words.remove(idx)
                        else:
                            st.session_state.selected_words.add(idx)
                        st.rerun()
        
        # 選択結果のプレビュー
        st.markdown("---")
        st.subheader("✅ 選択結果")
        
        preview_parts = []
        for idx, word in enumerate(words):
            if idx in st.session_state.selected_words:
                preview_parts.append(f"**[{word}]**")
            else:
                preview_parts.append(word)
        
        preview_text = "".join(preview_parts)
        st.markdown(f"### {preview_text}")
        
        if st.session_state.selected_words:
            selected_list = [words[i] for i in sorted(st.session_state.selected_words)]
            st.info(f"選択中: {', '.join(selected_list)}")
        else:
            st.warning("強調なし（選択されていません）")
    
    # メモ欄
    notes = st.text_area(
        "💭 メモ（任意）",
        height=80,
        placeholder="判断に迷った点や気づいたことがあれば記入してください"
    )
    
    # ボタンエリア
    st.markdown("---")
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        if st.button(
            "⬅️ 前へ",
            disabled=(st.session_state.current_idx == 0),
            use_container_width=True
        ):
            st.session_state.current_idx -= 1
            st.session_state.selected_words = set()
            st.rerun()
    
    with col2:
        if st.button("🔄 リセット", use_container_width=True):
            st.session_state.selected_words = set()
            st.rerun()
    
    with col3:
        if st.button(
            "⏭️ スキップ",
            disabled=(st.session_state.current_idx >= total - 1),
            use_container_width=True
        ):
            st.session_state.current_idx += 1
            st.session_state.selected_words = set()
            st.rerun()
    
    with col4:
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
                    'filename': item.get('filename', 'N/A'),
                    'speaker': item.get('speaker', 'N/A'),
                    'text': text,
                    'emphasized_words': ', '.join(emphasized_words) if emphasized_words else '',
                    'emphasized_indices': ', '.join(map(str, selected_indices)) if selected_indices else '',
                    'annotated_text': bracketed_text,
                    'has_emphasis': len(emphasized_words) > 0,
                    'notes': notes,
                    'timestamp': datetime.now().isoformat()
                }
                
                st.session_state.annotations.append(annotation)
                
                if emphasized_words:
                    st.success(f"✅ 保存しました: {bracketed_text}")
                else:
                    st.success("✅ 保存しました（強調なし）")
                
                if st.session_state.current_idx < total - 1:
                    st.session_state.current_idx += 1
                    st.session_state.selected_words = set()
                    st.rerun()
                else:
                    st.balloons()
                    st.success("🎉 全ファイルのアノテーションが完了しました！")
    
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
    st.title("🎯 JVS強調アノテーションツール")
    
    st.markdown("""
    ## 📋 使い方
    
    1. 左のサイドバーにアノテーター名を入力
    2. Google SheetsのURLを貼り付け
    3. 「データを読み込む」をクリック
    4. 音声を聴いて強調部分をクリック選択
    5. 「保存して次へ」で進む
    6. 完了後「エクセルをダウンロード」
    """)
    
    st.info("👈 左のサイドバーから「データを読み込む」を実行してください")

st.markdown("---")
st.caption("JVS強調アノテーションツール v1.0")