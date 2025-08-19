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

def extract_work_hours_smart(text):
    """英語対応強化版 - スマートな勤務時間抽出機能"""
    debug_info = []
    all_matches = {}
    
    # 英語対応を追加した優先順位付きパターン
    priority_patterns = [
        # 最優先: 明確に「勤務時間」と書かれたもの（日本語 + 英語）
        ('最重要', r'勤務時間[:\s：]*(\d+\.?\d*)[時間hH]*', '勤務時間'),
        ('最重要', r'総勤務時間[:\s：]*(\d+\.?\d*)[時間hH]*', '総勤務時間'),
        ('最重要', r'Total Hours[:\s]*(\d+\.?\d*)[hH時間]*', 'Total Hours'),
        ('最重要', r'Work Hours[:\s]*(\d+\.?\d*)[hH時間]*', 'Work Hours'),
        ('最重要', r'Working Hours[:\s]*(\d+\.?\d*)[hH時間]*', 'Working Hours'),
        
        # 高優先: 合計系（日本語 + 英語）
        ('高優先', r'合計[:\s：]*(\d+\.?\d*)[時間hH]*', '合計'),
        ('高優先', r'総時間[:\s：]*(\d+\.?\d*)[時間hH]*', '総時間'),
        ('高優先', r'TOTAL[:\s]*(\d+\.?\d*)[hH時間]*', 'TOTAL'),
        ('高優先', r'Total[:\s]*(\d+\.?\d*)[hH時間]*', 'Total'),
        
        # 中優先: その他の時間項目（日本語 + 英語）
        ('中優先', r'実働[:\s：]*(\d+\.?\d*)[時間hH]*', '実働時間'),
        ('中優先', r'実際[:\s：]*(\d+\.?\d*)[時間hH]*', '実際時間'),
        ('中優先', r'Net Hours[:\s]*(\d+\.?\d*)[hH時間]*', 'Net Hours'),
        ('中優先', r'Actual[:\s]*(\d+\.?\d*)[hH時間]*', 'Actual'),
        
        # 低優先: 一般的なパターン（日本語 + 英語）
        ('低優先', r'(\d+\.?\d+)\s*[時間hH]', '○○時間形式'),
        ('低優先', r'(\d+\.?\d+)\s*hours?', '○○hours形式'),
        
        # 最低優先: 時間:分形式のみ
        ('最低優先', r'(\d+)[時:](\d+)[分]?', '時間:分形式'),
    ]
    
    debug_info.append(f"抽出対象テキスト（最初の300文字）: {text[:300]}...")
    
    for priority, pattern, description in priority_patterns:
        try:
            matches = re.findall(pattern, text, re.IGNORECASE)
            if matches:
                debug_info.append(f"[{priority}] {description} '{pattern}' → {matches}")
                
                for match in matches:
                    try:
                        if isinstance(match, tuple) and len(match) == 2:
                            hours = float(match[0]) + float(match[1]) / 60
                            if 1 <= hours <= 24:
                                if priority not in all_matches:
                                    all_matches[priority] = []
                                all_matches[priority].append({
                                    'value': round(hours, 2),
                                    'description': f"{description}({match[0]}:{match[1]})",
                                    'pattern': pattern
                                })
                        else:
                            hours = float(match)
                            if priority == '最重要' and 50 <= hours <= 500:
                                if priority not in all_matches:
                                    all_matches[priority] = []
                                all_matches[priority].append({
                                    'value': round(hours, 2),
                                    'description': description,
                                    'pattern': pattern
                                })
                            elif priority == '高優先' and 50 <= hours <= 500:
                                if priority not in all_matches:
                                    all_matches[priority] = []
                                all_matches[priority].append({
                                    'value': round(hours, 2),
                                    'description': description,
                                    'pattern': pattern
                                })
                            elif priority in ['中優先', '低優先'] and 1 <= hours <= 500:
                                if priority not in all_matches:
                                    all_matches[priority] = []
                                all_matches[priority].append({
                                    'value': round(hours, 2),
                                    'description': description,
                                    'pattern': pattern
                                })
                    except ValueError:
                        continue
        except Exception as e:
            debug_info.append(f"[{priority}] パターンエラー: {str(e)}")
            continue
    
    # 優先順位に基づいて最適な値を選択
    selected_values = []
    
    for priority in ['最重要', '高優先', '中優先', '低優先', '最低優先']:
        if priority in all_matches:
            unique_values = []
            seen_values = set()
            
            for item in all_matches[priority]:
                if item['value'] not in seen_values:
                    unique_values.append(item)
                    seen_values.add(item['value'])
            
            if unique_values:
                debug_info.append(f"[{priority}] 採用: {[item['value'] for item in unique_values]}")
                selected_values.extend([item['value'] for item in unique_values])
                
                if priority in ['最重要', '高優先'] and len(unique_values) >= 1:
                    debug_info.append(f"[決定] {priority}レベルで十分なデータが見つかったため、以下の優先度は無視")
                    break
    
    final_results = sorted(list(set(selected_values)))
    
    if len(final_results) > 3:
        final_results = final_results[-2:]
        debug_info.append(f"結果を絞り込み: 最大値付近を採用")
    
    debug_info.append(f"最終選択結果: {final_results}")
    
    # デバッグ情報をセッション状態に保存
    if 'debug_info' not in st.session_state:
        st.session_state.debug_info = {}
    st.session_state.debug_info[text[:50]] = debug_info
    
    return final_results

def extract_employee_name(text):
    """英語対応強化版 - 社員名抽出"""
    name_patterns = [
        # 日本語パターン
        r'氏名[:\s：]*([^\s\n\r]+)',
        r'名前[:\s：]*([^\s\n\r]+)',
        r'社員名[:\s：]*([^\s\n\r]+)',
        r'派遣者[:\s：]*([^\s\n\r]+)',
        r'作業者[:\s：]*([^\s\n\r]+)',
        
        # 英語パターン
        r'Name[:\s]*([A-Za-z]+(?:\s+[A-Za-z]+)?)',  # Name: Suzuki Hanako
        r'Employee[:\s]*([A-Za-z]+(?:\s+[A-Za-z]+)?)', # Employee: John Smith
        r'Worker[:\s]*([A-Za-z]+(?:\s+[A-Za-z]+)?)',   # Worker: Jane Doe
        
        # より柔軟なパターン
        r'氏名\s*[:\s：]\s*([^\s\n\r]+)',
        r'名前\s*[:\s：]\s*([^\s\n\r]+)',
    ]
    
    for pattern in name_patterns:
        match = re.search(pattern, text)
        if match:
            name = match.group(1).strip()
            name = re.sub(r'[:\s\n\r]+$', '', name)  # 末尾の記号除去
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
    
    work_hours = extract_work_hours_smart(text)
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
    st.title("⏰ 勤務時間突合ツール（英語対応版）")
    st.markdown("**日本語・英語両対応 - 優先順位付き時間抽出**")
    
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
            st.write("**新機能:**")
            st.write("✅ 英語表記対応")
            st.write("✅ Total Hours, Work Hours対応")
            st.write("✅ Name: Suzuki Hanako対応")
            st.write("✅ 168.0h形式対応")
    
    st.markdown("---")
    
    # サイドバー
    with st.sidebar:
        st.header("📁 ファイル処理")
        
        # ファイルアップロード
        uploaded_files = st.file_uploader(
            "勤務実績ファイルを選択",
            type=['pdf', 'png', 'jpg', 'jpeg', 'bmp', 'tiff'] if PDF_SUPPORT else ['png', 'jpg', 'jpeg', 'bmp', 'tiff'],
            accept_multiple_files=True,
            help="日本語・英語どちらにも対応"
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
        with st.expander("📖 英語対応について"):
            st.write("""
            **新しく対応した英語フォーマット:**
            - Name: Suzuki Hanako
            - Total Hours: 168.0h
            - Work Hours: 176.5h
            - Working Hours: 154.5hours
            
            **既存の日本語フォーマット:**
            - 氏名: 田中太郎
            - 勤務時間: 176.5時間
            - 合計: 168.0時間
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
            work_hours_total = sum(result['work_hours']) if result['work_hours'] else 0
            
            if work_hours_count > 0:
                st.success(f"✅ {uploaded_file.name}: 処理完了（{work_hours_total:.1f}時間、{work_hours_count}個検出）")
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
    if st.button("🔍 詳細表示＋英語デバッグ"):
        st.subheader("🔍 詳細情報")
        
        for i, file_data in enumerate(st.session_state.processed_files):
            with st.expander(f"📁 {file_data['file_name']}", expanded=True):
                col1, col2 = st.columns([1, 1])
                
                with col1:
                    st.write(f"**社員名:** {file_data['employee_name']}")
                    st.write(f"**処理日時:** {file_data['processed_at']}")
                    
                    if file_data['work_hours']:
                        st.write(f"**選択された時間:** {file_data['work_hours']}")
                        st.write(f"**合計時間:** {sum(file_data['work_hours']):.2f}時間")
                        
                        if len(file_data['work_hours']) > 1:
                            main_value = max(file_data['work_hours'])
                            st.info(f"💡 推奨メイン値: {main_value}時間")
                    else:
                        st.warning("勤務時間が検出されませんでした")
                        
                    # 英語デバッグ情報表示
                    if 'debug_info' in st.session_state:
                        text_key = file_data['raw_text'][:50]
                        if text_key in st.session_state.debug_info:
                            with st.expander("🧠 英語対応デバッグ情報"):
                                for debug_line in st.session_state.debug_info[text_key]:
                                    if 'Total Hours' in debug_line or 'Work Hours' in debug_line:
                                        st.success(debug_line)
                                    elif '最重要' in debug_line:
                                        st.success(debug_line)
                                    elif '高優先' in debug_line:
                                        st.info(debug_line)
                                    elif '決定' in debug_line:
                                        st.warning(debug_line)
                                    else:
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
