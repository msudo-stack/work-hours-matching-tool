# 最小限動作版 - 勤務時間突合ツール

import streamlit as st
import pytesseract
from PIL import Image
import re
import pandas as pd

# PDF処理の安全なインポート
try:
    import fitz
    PDF_SUPPORT = True
except ImportError:
    PDF_SUPPORT = False

# アプリ設定
st.set_page_config(
    page_title="勤務時間突合ツール（簡易版）",
    page_icon="⏰",
    layout="wide"
)

def extract_text_from_image(image_file):
    """画像からテキスト抽出"""
    try:
        image = Image.open(image_file)
        # OCR実行
        text = pytesseract.image_to_string(image, lang='jpn')
        return text, None
    except Exception as e:
        return "", f"画像処理エラー: {str(e)}"

def extract_work_hours(text):
    """勤務時間を抽出"""
    patterns = [
        r'合計[:\s]*(\d+\.?\d*)',
        r'勤務時間[:\s]*(\d+\.?\d*)',
        r'(\d+)時間(\d+)分',
        r'(\d+):(\d+)',
        r'計[:\s]*(\d+\.?\d*)',
    ]
    
    results = []
    for pattern in patterns:
        matches = re.findall(pattern, text)
        for match in matches:
            try:
                if isinstance(match, tuple) and len(match) == 2:
                    # 時:分 形式
                    hours = float(match[0]) + float(match[1]) / 60
                    results.append(hours)
                else:
                    results.append(float(match))
            except:
                pass
    
    return results

def extract_employee_name(text):
    """社員名を抽出"""
    patterns = [
        r'氏名[:\s]*([^\s\n]+)',
        r'名前[:\s]*([^\s\n]+)',
        r'社員名[:\s]*([^\s\n]+)',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(1)
    return "不明"

def main():
    st.title("⏰ 勤務時間突合ツール（簡易版）")
    
    # システム状態表示
    with st.expander("🔧 システム状態"):
        st.write("**対応ファイル形式:**")
        st.write("✅ 画像ファイル (PNG, JPG, JPEG, BMP, TIFF)")
        if PDF_SUPPORT:
            st.write("✅ PDFファイル")
        else:
            st.write("❌ PDFファイル (PyMuPDF未インストール)")
            st.code("!pip install PyMuPDF")
    
    st.markdown("---")
    
    # ファイルアップロード
    uploaded_file = st.file_uploader(
        "ファイルを選択してください",
        type=['png', 'jpg', 'jpeg', 'bmp', 'tiff'] + (['pdf'] if PDF_SUPPORT else [])
    )
    
    if uploaded_file is not None:
        st.success(f"ファイル選択: {uploaded_file.name}")
        
        # 処理ボタン
        if st.button("🔄 ファイルを処理"):
            with st.spinner("処理中..."):
                
                # ファイル処理
                if uploaded_file.name.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp', '.tiff')):
                    text, error = extract_text_from_image(uploaded_file)
                elif uploaded_file.name.lower().endswith('.pdf') and PDF_SUPPORT:
                    try:
                        # 簡易PDF処理
                        import fitz
                        pdf_doc = fitz.open(stream=uploaded_file.read(), filetype="pdf")
                        text = ""
                        for page in pdf_doc:
                            text += page.get_text()
                        pdf_doc.close()
                        error = None
                    except Exception as e:
                        text = ""
                        error = f"PDF処理エラー: {str(e)}"
                else:
                    text = ""
                    error = "サポートされていないファイル形式です"
                
                if error:
                    st.error(error)
                else:
                    # 結果表示
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        st.subheader("📊 抽出結果")
                        
                        # 社員名抽出
                        employee_name = extract_employee_name(text)
                        st.write(f"**社員名:** {employee_name}")
                        
                        # 勤務時間抽出
                        work_hours = extract_work_hours(text)
                        if work_hours:
                            st.write(f"**検出された時間:** {work_hours}")
                            st.write(f"**合計時間:** {sum(work_hours):.2f}時間")
                            
                            # 結果をDataFrameに
                            df = pd.DataFrame({
                                'ファイル名': [uploaded_file.name],
                                '社員名': [employee_name],
                                '勤務時間': [f"{sum(work_hours):.2f}時間"],
                                '詳細': [str(work_hours)]
                            })
                            
                            st.dataframe(df, use_container_width=True)
                        else:
                            st.warning("勤務時間が検出されませんでした")
                    
                    with col2:
                        st.subheader("📄 抽出されたテキスト")
                        st.text_area(
                            "Raw Text",
                            text[:1000] + "..." if len(text) > 1000 else text,
                            height=300
                        )

if __name__ == "__main__":
    main()

# === 実行用のコマンド ===
# Google Colabで以下を実行してアプリを起動:

# 1. このコードをapp.pyファイルに保存
app_code = '''
# (上記のコード全体をここに入れる)
'''

# 2. ファイルに書き込み
# with open('app.py', 'w', encoding='utf-8') as f:
#     f.write(app_code)

# 3. Streamlit起動
# !streamlit run app.py &

# 4. ngrokでトンネリング
# from pyngrok import ngrok
# public_url = ngrok.connect(8501)
# print(f"アプリURL: {public_url}")
