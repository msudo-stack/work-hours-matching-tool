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
    """スマートな勤務時間抽出機能 - 優先順位と重複除去"""
    debug_info = []
    all_matches = {}  # パターン別の検出結果
    
    # 優先順位付きパターン（重要な順）
    priority_patterns = [
        # 最優先: 明確に「勤務時間」と書かれたもの
        ('最重要', r'勤務時間[:\s：]*(\d+\.?\d*)[時間hH]*', '勤務時間'),
        ('最重要', r'総勤務時間[:\s：]*(\d+\.?\d*)[時間hH]*', '総勤務時間'),
        
        # 高優先: 合計系
        ('高優先', r'合計[:\s：]*(\d+\.?\d*)[時間hH]*', '合計'),
        ('高優先', r'総時間[:\s：]*(\d+\.?\d*)[時間hH]*', '総時間'),
        
        # 中優先: その他の時間項目
        ('中優先', r'実働[:\s：]*(\d+\.?\d*)[時間hH]*', '実働時間'),
        ('中優先', r'実際[:\s：]*(\d+\.?\d*)[時間hH]*', '実際時間'),
        
        # 低優先: 一般的なパターン（慎重に）
        ('低優先', r'(\d+\.?\d+)\s*時間', '○○時間形式'),
        
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
                            # 時間:分 形式
                            hours = float(match[0]) + float(match[1]) / 60
                            if 1 <= hours <= 24:  # 1日の妥当な勤務時間
                                if priority not in all_matches:
                                    all_matches[priority] = []
                                all_matches[priority].append({
                                    'value': round(hours, 2),
                                    'description': f"{description}({match[0]}:{match[1]})",
                                    'pattern': pattern
                                })
                        else:
                            hours = float(match)
                            # より厳密な範囲チェック
                            if priority == '最重要' and 50 <= hours <= 500:  # 月間勤務時間
                                if priority not in all_matches:
                                    all_matches[priority] = []
                                all_matches[priority].append({
                                    'value': round(hours, 2),
                                    'description': description,
                                    'pattern': pattern
                                })
                            elif priority == '高優先' and 50 <= hours <= 500:  # 月間勤務時間
                                if priority not in all_matches:
                                    all_matches[priority] = []
                                all_matches[priority].append({
                                    'value': round(hours, 2),
                                    'description': description,
                                    'pattern': pattern
                                })
                            elif priority == '中優先' and 40 <= hours <= 400:  # 実働時間
                                if priority not in all_matches:
                                    all_matches[priority] = []
                                all_matches[priority].append({
                                    'value': round(hours, 2),
                                    'description': description,
                                    'pattern': pattern
                                })
                            elif priority == '低優先' and 1 <= hours <= 300:  # 一般的な時間
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
    
    # 優先順位順に処理
    for priority in ['最重要', '高優先', '中優先', '低優先', '最低優先']:
        if priority in all_matches:
            # 重複除去（同じ値は除外）
            unique_values = []
            seen_values = set()
            
            for item in all_matches[priority]:
                if item['value'] not in seen_values:
                    unique_values.append(item)
                    seen_values.add(item['value'])
            
            if unique_values:
                debug_info.append(f"[{priority}] 採用: {[item['value'] for item in unique_values]}")
                selected_values.extend([item['value'] for item in unique_values])
                
                # 最重要・高優先で見つかったら、それ以下は無視
                if priority in ['最重要', '高優先'] and len(unique_values) >= 1:
                    debug_info.append(f"[決定] {priority}レベルで十分なデータが見つかったため、以下の優先度は無視")
                    break
    
    # 最終的な重複除去
    final_results = sorted(list(set(selected_values)))
    
    # 結果が多すぎる場合は、最も大きい値を採用（月間勤務時間として妥当）
    if len(final_results) > 3:
        final_results = final_results[-2:]  # 最大2つまで
        debug_info.append(f"結果を絞り込み: 最大値付近を採用")
    
    debug_info.append(f"最終選択結果: {final_results}")
    
    # デバッグ情報をセッション状態に保存
    if 'debug_info' not in st.session_state:
        st.session_state.debug_info = {}
    st.session_state.debug_info[text[:50]] = debug_info
    
    return final_results

def extract_employee_name(text):
    """社員名を抽出"""
    name_patterns = [
        r'氏名[:\s：]*([^\s\n\r]+)',
        r'名前[:\s：]*([^\s\n\r]+)',
        r'社員名[:\s：]*([^\s\n\r]+)',
        r'派遣者[:\s：]*([^\s\n\r]+)',
        r'作業者[:\s：]*([^\s\n\r]+)',
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
    
    work_hours = extract_work_hours_smart(text)  # スマート版を使用
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
    st.title("⏰ 勤務時間突合ツール（スマート版）")
    st.markdown("**優先順位付き時間抽出 - 重複を排除して最適な値を選択**")
    
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
            st.write("**スマート機能:**")
            st.write("✅ 優先順位付き抽出")
            st.write("✅ 重複除去")
            st.write("✅ 妥当性チェック")
            st.write("✅ 最適値選択")
    
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
        with st.expander("📖 スマート抽出について"):
            st.write("""
            **優先順位システム:**
            1. **最重要**: 勤務時間、総勤務時間
            2. **高優先**: 合計、総時間
            3. **中優先**: 実働時間、実際時間
            4. **低優先**: ○○時間形式
            
            **自動選択:**
            - 重複する値を除去
            - 最も信頼性の高い値を採用
            - 妥当性チェックで適切な範囲の値のみ選択
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
    if st.button("🔍 詳細表示＋スマートデバッグ"):
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
                        
                        # 推奨される主要な値
                        if len(file_data['work_hours']) > 1:
                            main_value = max(file_data['work_hours'])
                            st.info(f"💡 推奨メイン値: {main_value}時間")
                    else:
                        st.warning("勤務時間が検出されませんでした")
                        
                    # スマートデバッグ情報表示
                    if 'debug_info' in st.session_state:
                        text_key = file_data['raw_text'][:50]
                        if text_key in st.session_state.debug_info:
                            with st.expander("🧠 スマートデバッグ情報"):
                                for debug_line in st.session_state.debug_info[text_key]:
                                    if '最重要' in debug_line:
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
