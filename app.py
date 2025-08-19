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
    page_title="勤務時間突合ツール（複数人対応版）",
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

def extract_multiple_employees_from_table(text):
    """表形式から複数人の勤務データを抽出"""
    debug_info = []
    employees_data = []
    
    debug_info.append(f"表形式解析開始: {text[:200]}...")
    
    # パターン1: 表形式（横並び）の検出
    table_patterns = [
        r'│([^│\n\r]+)│[^│]*?(\d+\.?\d*)[時間hH]*[^│]*?│',  # │名前│...│時間│
        r'([^\|\n\r\t]+)[\|\t]\s*\d+[日]*[\|\t]\s*(\d+\.?\d*)[時間hH]*',  # 名前|日数|時間
        r'([^\n\r\t]+)\s+(\d+\.?\d*)[時間hH]+',  # 名前 時間
    ]
    
    # パターン2: リスト形式の検出
    list_patterns = [
        r'([^\n\r]+?)\s+勤務時間[:\s：]*(\d+\.?\d*)[時間hH]*',
        r'([^\n\r]+?)[:\s：]+(\d+\.?\d*)[時間hH]+',
        r'([^\n\r]+?)\s+(\d+\.?\d*)[時間hH]+',
    ]
    
    # パターン3: 縦並び形式の検出  
    vertical_patterns = [
        r'氏名[:\s：]*([^\n\r]+).*?勤務時間[:\s：]*(\d+\.?\d*)[時間hH]*',
        r'社員名[:\s：]*([^\n\r]+).*?勤務時間[:\s：]*(\d+\.?\d*)[時間hH]*',
        r'名前[:\s：]*([^\n\r]+).*?勤務時間[:\s：]*(\d+\.?\d*)[時間hH]*',
    ]
    
    all_patterns = [
        ("表形式", table_patterns),
        ("リスト形式", list_patterns),
        ("縦形式", vertical_patterns)
    ]
    
    for pattern_type, patterns in all_patterns:
        for i, pattern in enumerate(patterns):
            try:
                matches = re.findall(pattern, text, re.DOTALL | re.IGNORECASE)
                if matches:
                    debug_info.append(f"[{pattern_type}] パターン{i+1}でマッチ: {len(matches)}件")
                    
                    for match in matches:
                        if isinstance(match, tuple) and len(match) == 2:
                            name_candidate = match[0].strip()
                            hours_candidate = match[1].strip()
                            
                            # 名前のクリーニング
                            name_candidate = clean_employee_name(name_candidate)
                            if is_valid_employee_name(name_candidate):
                                try:
                                    hours = float(hours_candidate)
                                    if 10 <= hours <= 500:  # 妥当な勤務時間範囲
                                        employees_data.append({
                                            'name': name_candidate,
                                            'hours': hours,
                                            'pattern_type': pattern_type,
                                            'pattern_index': i+1
                                        })
                                        debug_info.append(f"追加: {name_candidate} -> {hours}時間")
                                except ValueError:
                                    continue
            except Exception as e:
                debug_info.append(f"[{pattern_type}] パターン{i+1}でエラー: {str(e)}")
                continue
    
    # 重複除去
    unique_employees = remove_duplicate_employees(employees_data)
    debug_info.append(f"重複除去後: {len(unique_employees)}人")
    
    return unique_employees, debug_info

def clean_employee_name(name):
    """社員名のクリーニング"""
    # 不要な文字・記号を除去
    name = re.sub(r'[│\|\t\n\r]+', ' ', name)  # 表の区切り文字等
    name = re.sub(r'^[:\s：\-\=]+', '', name)   # 先頭の記号
    name = re.sub(r'[:\s：\-\=]+$', '', name)   # 末尾の記号
    name = re.sub(r'\d+[日月年]', '', name)     # 日付
    name = re.sub(r'勤務|時間|合計|実績', '', name)  # 項目名
    name = re.sub(r'\s+', '', name)  # 複数の空白を除去
    
    return name.strip()

def is_valid_employee_name(name):
    """社員名の妥当性チェック"""
    if not name or len(name) < 2:
        return False
    if len(name) > 20:  # 長すぎる
        return False
    if re.match(r'^\d+$', name):  # 数字のみ
        return False
    if name in ['項目', '氏名', '社員名', '名前', '時間', '勤務', '合計', '実績', '承認', '社員', '勤務日数']:
        return False
    
    # 日本語名前の基本パターン
    if re.match(r'^[あ-んア-ン一-龯\s]+$', name):  # ひらがな・カタカナ・漢字
        return True
    if re.match(r'^[A-Za-z\s]+$', name):  # 英語名
        return True
    
    return False

def remove_duplicate_employees(employees_data):
    """重複する社員データを除去"""
    seen_names = {}
    unique_employees = []
    
    for emp in employees_data:
        name = emp['name']
        if name not in seen_names:
            seen_names[name] = emp
            unique_employees.append(emp)
        else:
            # 既存のデータと比較
            existing = seen_names[name]
            if emp['pattern_type'] == '表形式' and existing['pattern_type'] != '表形式':
                seen_names[name] = emp
                for i, existing_emp in enumerate(unique_employees):
                    if existing_emp['name'] == name:
                        unique_employees[i] = emp
                        break
    
    return unique_employees

def extract_work_hours_smart(text):
    """単一人物用のスマート時間抽出（英語対応済み）"""
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

def process_file_multi_person(uploaded_file):
    """複数人対応版のファイル処理"""
    file_extension = uploaded_file.name.split('.')[-1].lower()
    
    if file_extension in ['png', 'jpg', 'jpeg', 'bmp', 'tiff']:
        text, error = extract_text_from_image(uploaded_file)
    elif file_extension == 'pdf':
        text, error = extract_text_from_pdf(uploaded_file)
    else:
        return None, "サポートされていないファイル形式です"
    
    if error:
        return None, error
    
    # 複数人物として処理を試行
    employees_data, debug_info = extract_multiple_employees_from_table(text)
    
    # 複数人が検出された場合は表形式として処理
    if len(employees_data) > 1:
        return {
            'type': 'multi_person',
            'raw_text': text,
            'employees': employees_data,
            'file_name': uploaded_file.name,
            'processed_at': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            'debug_info': debug_info
        }, None
    else:
        # 単一人物として処理
        single_employee_name = extract_employee_name(text)
        single_work_hours = extract_work_hours_smart(text)
        
        return {
            'type': 'single_person', 
            'raw_text': text,
            'employee_name': single_employee_name,
            'work_hours': single_work_hours,
            'file_name': uploaded_file.name,
            'processed_at': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }, None

def create_excel_output_multi(df):
    """複数人対応版Excel出力"""
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
    st.title("⏰ 勤務時間突合ツール（複数人対応版）")
    st.markdown("**表形式データから複数人の勤務時間を一括抽出 + 英語対応**")
    
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
            st.write("**機能:**")
            st.write("✅ 表形式複数人対応")
            st.write("✅ 自動単一/複数判定")
            st.write("✅ 英語表記対応")
            st.write("✅ 複数人一括処理")
    
    st.markdown("---")
    
    # サイドバー
    with st.sidebar:
        st.header("📁 ファイル処理")
        
        # ファイルアップロード
        uploaded_files = st.file_uploader(
            "勤務実績ファイルを選択",
            type=['pdf', 'png', 'jpg', 'jpeg', 'bmp', 'tiff'] if PDF_SUPPORT else ['png', 'jpg', 'jpeg', 'bmp', 'tiff'],
            accept_multiple_files=True,
            help="単一人物・複数人物どちらにも対応"
        )
        
        # 処理ボタン
        if st.button("🔄 ファイルを処理", disabled=not uploaded_files, type="primary"):
            process_files_multi(uploaded_files)
        
        # データクリアボタン
        if st.button("🗑️ 処理結果をクリア"):
            st.session_state.processed_files = []
        
        # 統計情報
        if st.session_state.processed_files:
            st.markdown("---")
            st.subheader("📊 処理統計")
            
            total_files = len(st.session_state.processed_files)
            total_people = 0
            total_hours = 0
            
            for file_data in st.session_state.processed_files:
                if file_data['type'] == 'multi_person':
                    total_people += len(file_data['employees'])
                    total_hours += sum([emp['hours'] for emp in file_data['employees']])
                else:
                    total_people += 1
                    total_hours += sum(file_data['work_hours']) if file_data['work_hours'] else 0
            
            st.metric("処理済みファイル", total_files)
            st.metric("処理済み人数", total_people)
            st.metric("合計勤務時間", f"{total_hours:.1f}時間")
    
    # メインエリア
    if st.session_state.processed_files:
        display_results_multi()
    else:
        st.info("👆 サイドバーからファイルをアップロードして処理を開始してください")
        
        # 使用例
        with st.expander("📖 複数人対応機能について"):
            st.write("""
            **自動判定機能:**
            - 単一人物データ: 従来通りの処理
            - 複数人データ: 表形式として自動解析
            
            **対応する表形式:**
            - 横並び表: │名前│勤務時間│
            - リスト形式: 田中太郎 176.5時間
            - 縦並び形式: 氏名:田中太郎 勤務時間:176.5時間
            
            **英語対応:**
            - Name: Suzuki Hanako
            - Total Hours: 168.0h
            """)

def process_files_multi(uploaded_files):
    """複数ファイルを処理（複数人対応版）"""
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    for i, uploaded_file in enumerate(uploaded_files):
        status_text.text(f"処理中: {uploaded_file.name} ({i+1}/{len(uploaded_files)})")
        
        result, error = process_file_multi_person(uploaded_file)
        
        if error:
            st.error(f"❌ {uploaded_file.name}: {error}")
        else:
            st.session_state.processed_files.append(result)
            
            if result['type'] == 'multi_person':
                people_count = len(result['employees'])
                total_hours = sum([emp['hours'] for emp in result['employees']])
                st.success(f"✅ {uploaded_file.name}: 表形式処理完了（{people_count}人、合計{total_hours:.1f}時間）")
            else:
                work_hours_count = len(result['work_hours'])
                work_hours_total = sum(result['work_hours']) if result['work_hours'] else 0
                st.success(f"✅ {uploaded_file.name}: 単一人物処理完了（{work_hours_total:.1f}時間）")
        
        progress_bar.progress((i + 1) / len(uploaded_files))
    
    status_text.text("🎉 すべての処理が完了しました！")

def display_results_multi():
    """複数人対応版結果表示"""
    st.header("📊 処理結果")
    
    # 結果テーブル作成
    data = []
    for file_data in st.session_state.processed_files:
        if file_data['type'] == 'multi_person':
            for emp in file_data['employees']:
                data.append({
                    'ファイル名': file_data['file_name'],
                    '社員名': emp['name'],
                    '勤務時間': f"{emp['hours']:.2f}時間",
                    '処理方式': '表形式',
                    '処理日時': file_data['processed_at']
                })
        else:
            total_hours = sum(file_data['work_hours']) if file_data['work_hours'] else 0
            data.append({
                'ファイル名': file_data['file_name'],
                '社員名': file_data['employee_name'],
                '勤務時間': f"{total_hours:.2f}時間" if total_hours > 0 else "未検出",
                '処理方式': '単一人物',
                '処理日時': file_data['processed_at']
            })
    
    df = pd.DataFrame(data)
    
    # テーブル表示
    st.dataframe(df, use_container_width=True, hide_index=True)
    
    # Excel出力
    if st.button("📥 Excel出力"):
        excel_data = create_excel_output_multi(df)
        if excel_data:
            st.download_button(
                label="💾 Excelファイルをダウンロード",
                data=excel_data,
                file_name=f"勤務時間突合結果_複数人対応_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        else:
            st.error("Excel出力機能が利用できません")
    
    # 詳細表示
    if st.button("🔍 詳細表示＋複数人デバッグ"):
        st.subheader("🔍 詳細情報")
        
        for i, file_data in enumerate(st.session_state.processed_files):
            with st.expander(f"📁 {file_data['file_name']}", expanded=True):
                if file_data['type'] == 'multi_person':
                    st.success(f"表形式処理: {len(file_data['employees'])}人検出")
                    
                    # 検出された人物一覧
                    employees_df = pd.DataFrame([
                        {'社員名': emp['name'], '勤務時間': f"{emp['hours']}時間", 
                         'パターン': emp['pattern_type']} 
                        for emp in file_data['employees']
                    ])
                    st.dataframe(employees_df, use_container_width=True, hide_index=True)
                    
                    # デバッグ情報
                    with st.expander("🐛 表形式デバッグ情報"):
                        for debug_line in file_data['debug_info']:
                            st.text(debug_line)
                
                else:
                    st.info("単一人物として処理")
                    st.write(f"**社員名:** {file_data['employee_name']}")
                    if file_data['work_hours']:
                        st.write(f"**勤務時間:** {file_data['work_hours']}")
                        st.write(f"**合計:** {sum(file_data['work_hours']):.2f}時間")
                
                # 元テキスト表示
                st.text_area(
                    "抽出されたテキスト",
                    file_data['raw_text'][:500] + "..." if len(file_data['raw_text']) > 500 else file_data['raw_text'],
                    height=200,
                    key=f"detail_text_multi_{i}_{file_data['file_name']}"
                )

if __name__ == "__main__":
    main()
