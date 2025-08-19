import streamlit as st
import pytesseract
from PIL import Image
import pandas as pd
import re
from io import BytesIO
from datetime import datetime

# PDF処理の安全なインポート
try:
    import fitz  # PyMuPDF
    PDF_SUPPORT = True
except ImportError:
    PDF_SUPPORT = False

# ページ設定
st.set_page_config(
    page_title="勤務時間突合ツール",
    page_icon="⏰",
    layout="wide"
)

# セッション状態の初期化
if 'processed_files' not in st.session_state:
    st.session_state.processed_files = []

def extract_text_from_image(image_file):
    """画像ファイルからテキストを抽出"""
    try:
        image = Image.open(image_file)
        text = pytesseract.image_to_string(image, lang='jpn')
        return text, None
    except Exception as e:
        return "", f"画像処理エラー: {str(e)}"

def extract_text_from_pdf(pdf_file):
    """PDFファイルからテキストを抽出"""
    if not PDF_SUPPORT:
        return "", "PDF処理機能が利用できません"
    
    try:
        pdf_document = fitz.open(stream=pdf_file.read(), filetype="pdf")
        text = ""
        
        for page_num in range(pdf_document.page_count):
            page = pdf_document[page_num]
            page_text = page.get_text()
            
            if len(page_text.strip()) < 50:
                try:
                    pix = page.get_pixmap()
                    img_data = pix.tobytes("png")
                    image = Image.open(BytesIO(img_data))
                    page_text = pytesseract.image_to_string(image, lang='jpn')
                except Exception:
                    page_text = "OCR処理をスキップしました"
            
            text += page_text + "\n"
        
        pdf_document.close()
        return text, None
    except Exception as e:
        return "", f"PDFエラー: {str(e)}"

def extract_work_hours(text):
    """改善された勤務時間抽出機能"""
    # デバッグ情報を表示用に保存
    debug_info = []
    
    # より包括的な正規表現パターン
    patterns = [
        # 基本パターン（コロンあり）
        r'合計[:\s：]*(\d+\.?\d*)[時間hH]*',
        r'総時間[:\s：]*(\d+\.?\d*)[時間hH]*',
        r'勤務時間[:\s：]*(\d+\.?\d*)[時間hH]*',
        r'実働[:\s：]*(\d+\.?\d*)[時間hH]*',
        r'実際[:\s：]*(\d+\.?\d*)[時間hH]*',
        
        # 空白を含むパターン
        r'合計\s*[:\s：]\s*(\d+\.?\d*)\s*[時間hH]*',
        r'勤務時間\s*[:\s：]\s*(\d+\.?\d*)\s*[時間hH]*',
        r'総時間\s*[:\s：]\s*(\d+\.?\d*)\s*[時間hH]*',
        
        # コロンなしパターン
        r'合計(\d+\.?\d*)[時間hH]',
        r'勤務時間(\d+\.?\d*)[時間hH]',
        r'総時間(\d+\.?\d*)[時間hH]',
        r'実働(\d+\.?\d*)[時間hH]',
        
        # 「○○時間」形式
        r'(\d+\.?\d+)\s*[時間hH]',
        r'(\d+)\s*[時間hH]',
        
        # 時間:分形式（複数パターン）
        r'(\d+)[時:](\d+)[分]?',
        r'(\d+)[時時間](\d+)[分]',
        
        # より柔軟なパターン
        r'時間.*?(\d+\.?\d+)',
        r'合計.*?(\d+\.?\d+)',
        
        # 数値のみ（2-3桁で時間として妥当そうなもの）
        r'\b(\d{2,3}\.\d+)\b',  # 176.5のような形式
        r'\b(1[0-9]{2}|2[0-4][0-9])\b',  # 100-249の範囲
    ]
    
    results = []
    
    # デバッグ情報
    debug_info.append(f"抽出対象テキスト（最初の300文字）: {text[:300]}...")
    
    for i, pattern in enumerate(patterns):
        try:
            matches = re.findall(pattern, text, re.IGNORECASE)
            if matches:
                debug_info.append(f"パターン{i+1} '{pattern}' → {matches}")
            
            for match in matches:
                try:
                    if isinstance(match, tuple) and len(match) == 2:
                        # 時間:分 形式
                        hours = float(match[0]) + float(match[1]) / 60
                        if 0.1 <= hours <= 24:
                            results.append(round(hours, 2))
                            debug_info.append(f"時間:分形式で追加: {hours}時間")
                    else:
                        hours = float(match)
                        # 勤務時間として妥当な範囲（0.1時間〜500時間）
                        if 0.1 <= hours <= 500:
                            results.append(round(hours, 2))
                            debug_info.append(f"数値として追加: {hours}時間")
                except ValueError:
                    continue
        except Exception as e:
            debug_info.append(f"パターン{i+1}でエラー: {str(e)}")
            continue
    
    # 重複除去
    unique_results = sorted(list(set(results)))
    debug_info.append(f"最終結果: {unique_results}")
    
    # デバッグ情報をセッション状態に保存
    if 'debug_info' not in st.session_state:
        st.session_state.debug_info = {}
    st.session_state.debug_info[text[:50]] = debug_info
    
    return unique_results

def extract_employee_name(text):
    """社員名を抽出（改善版）"""
    name_patterns = [
        r'氏名[:\s：]*([^\s\n\r]+)',
        r'名前[:\s：]*([^\s\n\r]+)',
        r'社員名[:\s：]*([^\s\n\r]+)',
        r'派遣者[:\s：]*([^\s\n\r]+)',
        r'作業者[:\s：]*([^\s\n\r]+)',
        r'社員[:\s：]*([^\s\n\r]+)',
        
        # より柔軟なパターン
        r'氏名\s*[:\s：]\s*([^\s\n\r]+)',
        r'名前\s*[:\s：]\s*([^\s\n\r]+)',
    ]
    
    for pattern in name_patterns:
        match = re.search(pattern, text)
        if match:
            name = match.group(1).strip()
            name = re.sub(r'[:\s\n\r]+', '', name)
            if len(name) > 1 and not name.isdigit():
                return name
    
    return "不明"

def process_file(uploaded_file):
    """アップロードされたファイルを処理"""
    file_extension = uploaded_file.name.split('.')[-1].lower()
    
    if file_extension in ['png', 'jpg', 'jpeg', 'bmp', 'tiff']:
        text, error = extract_text_from_image(uploaded_file)
    elif file_extension == 'pdf':
        text, error = extract_text_from_pdf(uploaded_file)
    else:
        return None, "サポートされていないファイル形式です"
    
    if error:
        return None, error
    
    work_hours = extract_work_hours(text)
    employee_name = extract_employee_name(text)
    
    return {
        'raw_text': text,
        'employee_name': employee_name,
        'work_hours': work_hours,
        'file_name': uploaded_file.name,
        'processed_at': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }, None

def create_excel_output(df):
    """Excel出力用データを作成"""
    try:
        import openpyxl
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='勤務時間突合結果', index=False)
        return output.getvalue()
    except ImportError:
        return None

def main():
    # ヘッダー
    st.title("⏰ 勤務時間突合ツール（改善版）")
    st.markdown("**時間抽出機能を強化しました - より多くのフォーマットに対応**")
    
    # システム状態
    with st.expander("🔧 システム情報"):
        col1, col2 = st.columns(2)
        with col1:
            st.write("**対応ファイル形式:**")
            st.write("✅ 画像ファイル (PNG, JPG, JPEG, BMP, TIFF)")
            if PDF_SUPPORT:
                st.write("✅ PDFファイル")
            else:
                st.write("❌ PDFファイル (制限あり)")
        
        with col2:
            st.write("**改善された機能:**")
            st.write("✅ 日本語コロン（：）対応")
            st.write("✅ 空白を含むフォーマット対応")
            st.write("✅ より柔軟な時間抽出")
            st.write("✅ デバッグ情報表示")
    
    st.markdown("---")
    
    # サイドバー
    with st.sidebar:
        st.header("📁 ファイル処理")
        
        # ファイルアップロード
        uploaded_files = st.file_uploader(
            "勤務実績ファイルを選択",
            type=['pdf', 'png', 'jpg', 'jpeg', 'bmp', 'tiff'] if PDF_SUPPORT else ['png', 'jpg', 'jpeg', 'bmp', 'tiff'],
            accept_multiple_files=True,
            help="複数ファイルを同時に選択できます"
        )
        
        # 処理ボタン
        if st.button("🔄 ファイルを処理", disabled=not uploaded_files, type="primary"):
            process_files(uploaded_files)
        
        # データクリアボタン
        if st.button("🗑️ 処理結果をクリア"):
            st.session_state.processed_files = []
            if 'debug_info' in st.session_state:
                st.session_state.debug_info = {}
        
        # 統計情報
        if st.session_state.processed_files:
            st.markdown("---")
            st.subheader("📊 処理統計")
            st.metric("処理済みファイル", len(st.session_state.processed_files))
            
            total_hours = sum([sum(f['work_hours']) for f in st.session_state.processed_files if f['work_hours']])
            st.metric("合計勤務時間", f"{total_hours:.1f}時間")
    
    # メインエリア
    if st.session_state.processed_files:
        display_results()
    else:
        st.info("👆 サイドバーからファイルをアップロードして処理を開始してください")
        
        # 使用例
        with st.expander("📖 改善された機能について"):
            st.write("""
            **新しく対応したフォーマット:**
            - 勤務時間：176.5時間（日本語コロン）
            - 合計 176.5 時間（空白を含む）
            - 176.5時間（シンプル形式）
            - 8時間30分（時分形式）
            
            **デバッグ機能:**
            - 抽出されたテキストの詳細表示
            - どのパターンでマッチしたかの表示
            - より詳細なエラー情報
            """)

def process_files(uploaded_files):
    """複数ファイルを処理"""
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    for i, uploaded_file in enumerate(uploaded_files):
        status_text.text(f"処理中: {uploaded_file.name} ({i+1}/{len(uploaded_files)})")
        
        result, error = process_file(uploaded_file)
        
        if error:
            st.error(f"❌ {uploaded_file.name}: {error}")
        else:
            st.session_state.processed_files.append(result)
            work_hours_count = len(result['work_hours'])
            if work_hours_count > 0:
                st.success(f"✅ {uploaded_file.name}: 処理完了（{work_hours_count}個の時間データ検出）")
            else:
                st.warning(f"⚠️ {uploaded_file.name}: 処理完了（時間データ未検出）")
        
        progress_bar.progress((i + 1) / len(uploaded_files))
    
    status_text.text("🎉 すべての処理が完了しました！")

def display_results():
    """処理結果を表示"""
    st.header("📊 処理結果")
    
    # 結果テーブル作成
    data = []
    for file_data in st.session_state.processed_files:
        work_hours = file_data['work_hours']
        total_hours = sum(work_hours) if work_hours else 0
        
        data.append({
            'ファイル名': file_data['file_name'],
            '社員名': file_data['employee_name'],
            '勤務時間': f"{total_hours:.2f}時間" if total_hours > 0 else "未検出",
            '検出数': len(work_hours),
            '処理日時': file_data['processed_at']
        })
    
    df = pd.DataFrame(data)
    
    # テーブル表示
    st.dataframe(df, use_container_width=True, hide_index=True)
    
    # Excel出力
    if st.button("📥 Excel出力"):
        excel_data = create_excel_output(df)
        if excel_data:
            st.download_button(
                label="💾 Excelファイルをダウンロード",
                data=excel_data,
                file_name=f"勤務時間突合結果_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        else:
            st.error("Excel出力機能が利用できません")
    
    # 詳細表示
    if st.button("🔍 詳細表示＋デバッグ情報"):
        st.subheader("🔍 詳細情報")
        
        for i, file_data in enumerate(st.session_state.processed_files):
            with st.expander(f"📁 {file_data['file_name']}", expanded=True):
                col1, col2 = st.columns([1, 1])
                
                with col1:
                    st.write(f"**社員名:** {file_data['employee_name']}")
                    st.write(f"**処理日時:** {file_data['processed_at']}")
                    
                    if file_data['work_hours']:
                        st.write(f"**検出された時間:** {file_data['work_hours']}")
                        st.write(f"**合計時間:** {sum(file_data['work_hours']):.2f}時間")
                    else:
                        st.warning("勤務時間が検出されませんでした")
                        
                    # デバッグ情報表示
                    if 'debug_info' in st.session_state:
                        text_key = file_data['raw_text'][:50]
                        if text_key in st.session_state.debug_info:
                            with st.expander("🐛 デバッグ情報"):
                                for debug_line in st.session_state.debug_info[text_key]:
                                    st.text(debug_line)
                
                with col2:
                    st.text_area(
                        "抽出されたテキスト",
                        file_data['raw_text'][:500] + "..." if len(file_data['raw_text']) > 500 else file_data['raw_text'],
                        height=200,
                        key=f"detail_text_{i}_{file_data['file_name']}"
                    )

if __name__ == "__main__":
    main()
