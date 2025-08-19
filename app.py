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

# カスタムCSS
st.markdown("""
<style>
    .stAlert > div {
        padding: 1rem;
    }
    .success-box {
        padding: 1rem;
        border-radius: 0.5rem;
        background-color: #d4edda;
        border: 1px solid #c3e6cb;
        color: #155724;
        margin: 1rem 0;
    }
</style>
""", unsafe_allow_html=True)

# セッション状態の初期化
if 'processed_files' not in st.session_state:
    st.session_state.processed_files = []

def extract_text_from_image(image_file):
    """画像ファイルからテキストを抽出"""
    try:
        image = Image.open(image_file)
        # 画像の前処理（必要に応じて）
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
            
            if len(page_text.strip()) < 50:  # テキストが少ない場合はOCR
                try:
                    pix = page.get_pixmap()
                    img_data = pix.tobytes("png")
                    image = Image.open(BytesIO(img_data))
                    page_text = pytesseract.image_to_string(image, lang='jpn')
                except Exception as ocr_error:
                    page_text = f"OCRエラー: {str(ocr_error)}"
            
            text += page_text + "\n"
        
        pdf_document.close()
        return text, None
    except Exception as e:
        return "", f"PDFエラー: {str(e)}"

def extract_work_hours(text):
    """テキストから勤務時間を抽出"""
    patterns = [
        r'合計[:\s]*(\d+\.?\d*)[時間]*',
        r'総時間[:\s]*(\d+\.?\d*)',
        r'勤務時間[:\s：]*(\d+\.?\d*)'  # 半角「:」+ 日本語「：」対応
        r'実働[:\s]*(\d+\.?\d*)',
        r'(\d+)時間(\d+)分',
        r'(\d+):(\d+)',
        r'計[:\s]*(\d+\.?\d*)',
        r'計(\d+\.?\d*)',
        r'時間数[:\s]*(\d+\.?\d*)',
    ]
    
    results = []
    
    for pattern in patterns:
        matches = re.findall(pattern, text)
        for match in matches:
            try:
                if isinstance(match, tuple) and len(match) == 2:
                    # 時間:分 形式
                    hours = float(match[0]) + float(match[1]) / 60
                    if 0 < hours <= 24:  # 妥当な範囲の時間のみ
                        results.append(round(hours, 2))
                else:
                    hours = float(match)
                    if 0 < hours <= 24:  # 妥当な範囲の時間のみ
                        results.append(round(hours, 2))
            except ValueError:
                continue
    
    # 重複除去
    return list(set(results))

def extract_employee_name(text):
    """テキストから社員名を抽出"""
    name_patterns = [
        r'氏名[:\s]*([^\s\n\r]+)',
        r'名前[:\s]*([^\s\n\r]+)',
        r'社員名[:\s]*([^\s\n\r]+)',
        r'派遣者[:\s]*([^\s\n\r]+)',
        r'作業者[:\s]*([^\s\n\r]+)',
    ]
    
    for pattern in name_patterns:
        match = re.search(pattern, text)
        if match:
            name = match.group(1).strip()
            # 不要な文字を除去
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
        from io import BytesIO
        
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='勤務時間突合結果', index=False)
            
            # 詳細情報シート
            if st.session_state.processed_files:
                detail_data = []
                for file_data in st.session_state.processed_files:
                    detail_data.append({
                        'ファイル名': file_data['file_name'],
                        '社員名': file_data['employee_name'],
                        '処理日時': file_data['processed_at'],
                        '抽出テキスト（一部）': file_data['raw_text'][:500] + "..." if len(file_data['raw_text']) > 500 else file_data['raw_text']
                    })
                
                detail_df = pd.DataFrame(detail_data)
                detail_df.to_excel(writer, sheet_name='詳細情報', index=False)
        
        return output.getvalue()
    except ImportError:
        return None

def main():
    # ヘッダー
    st.title("⏰ 勤務時間突合ツール")
    st.markdown("**OCRを使用した勤務実績ファイルの自動処理ツール**")
    
    # システム状態
    with st.expander("🔧 システム情報", expanded=False):
        col1, col2 = st.columns(2)
        with col1:
            st.write("**対応ファイル形式:**")
            st.write("✅ 画像ファイル (PNG, JPG, JPEG, BMP, TIFF)")
            if PDF_SUPPORT:
                st.write("✅ PDFファイル")
            else:
                st.write("❌ PDFファイル (制限あり)")
        
        with col2:
            st.write("**処理機能:**")
            st.write("✅ 日本語OCR")
            st.write("✅ 勤務時間自動抽出")
            st.write("✅ 社員名自動抽出")
            st.write("✅ Excel出力")
    
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
        
        # データクリア
        if st.button("🗑️ 処理結果をクリア"):
            st.session_state.processed_files = []
            st.success("データをクリアしました")
            st.rerun()
        
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
        with st.expander("📖 使用方法", expanded=True):
            st.write("""
            **1. ファイル準備**
            - 勤務実績が記載されたPDFや画像ファイルを用意
            
            **2. ファイルアップロード**
            - サイドバーの「ファイルを選択」から複数ファイルを選択
            
            **3. 処理実行**
            - 「🔄 ファイルを処理」ボタンをクリック
            
            **4. 結果確認**
            - 抽出された勤務時間と社員名を確認
            - Excel形式でダウンロード可能
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
            st.success(f"✅ {uploaded_file.name}: 処理完了")
        
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
    col1, col2 = st.columns([1, 1])
    with col1:
        if st.button("📥 Excel出力", type="secondary"):
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
    
    with col2:
        if st.button("📄 詳細表示"):
            show_detailed_results()

def show_detailed_results():
    """詳細結果を表示"""
    st.subheader("🔍 詳細情報")
    
    for i, file_data in enumerate(st.session_state.processed_files):
        with st.expander(f"📁 {file_data['file_name']}", expanded=False):
            col1, col2 = st.columns([1, 1])
            
            with col1:
                st.write(f"**社員名:** {file_data['employee_name']}")
                st.write(f"**処理日時:** {file_data['processed_at']}")
                
                if file_data['work_hours']:
                    st.write(f"**検出された時間:** {file_data['work_hours']}")
                    st.write(f"**合計時間:** {sum(file_data['work_hours']):.2f}時間")
                else:
                    st.warning("勤務時間が検出されませんでした")
            
            with col2:
                st.text_area(
                    "抽出されたテキスト",
                    file_data['raw_text'][:300] + "..." if len(file_data['raw_text']) > 300 else file_data['raw_text'],
                    height=150,
                    key=f"detail_text_{i}"
                )

if __name__ == "__main__":
    main()
