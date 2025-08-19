def extract_work_hours_smart_english(text):
    """英語対応強化版 - 勤務時間抽出機能"""
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

def extract_employee_name_english(text):
    """英語対応強化版 - 社員名抽出"""
    name_patterns = [
        # 日本語パターン
        r'氏名[:\s：]*([^\s\n\r]+)',
        r'名前[:\s：]*([^\s\n\r]+)',
        r'社員名[:\s：]*([^\s\n\r]+)',
        r'派遣者[:\s：]*([^\s\n\r]+)',
        r'作業者[:\s：]*([^\s\n\r]+)',
        
        # 英語パターン
        r'Name[:\s]*([^\s\n\r]+(?:\s+[^\s\n\r]+)?)',  # Name: Suzuki Hanako
        r'Employee[:\s]*([^\s\n\r]+(?:\s+[^\s\n\r]+)?)', # Employee: John Smith
        r'Worker[:\s]*([^\s\n\r]+(?:\s+[^\s\n\r]+)?)',   # Worker: Jane Doe
        
        # より柔軟なパターン
        r'氏名\s*[:\s：]\s*([^\s\n\r]+)',
        r'名前\s*[:\s：]\s*([^\s\n\r]+)',
        r'Name\s*[:\s]\s*([A-Za-z\s]+)',  # 英語名の場合
    ]
    
    for pattern in name_patterns:
        match = re.search(pattern, text)
        if match:
            name = match.group(1).strip()
            name = re.sub(r'[:\s\n\r]+$', '', name)  # 末尾の記号除去
            if len(name) > 1 and not name.isdigit():
                return name
    
    return "不明"
