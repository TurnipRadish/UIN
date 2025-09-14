import re
import json
import os
import shutil

def clean_node_name(text):
    """提取纯文本节点名称（移除所有标记，只保留模板中的最后一个文本参数）"""
    # 移除行首的*号和空格
    text = text.lstrip('* ')
    
    # 提取{{font color|...|...}}模板中的最后一个参数（颜色后的文本）
    def extract_font_content(match):
        parts = match.group(1).split('|')
        return parts[-1] if parts else ''
    
    text = re.sub(r'\{\{font color\|(.*?)\}\}', extract_font_content, text)
    
    # 移除<samp>和</samp>标签
    text = text.replace('<samp>', '').replace('</samp>', '')
    
    # 移除方括号链接，如[[XXX]]
    text = re.sub(r'$$[^]]*$$', '', text)
    
    # 移除中文冒号及之后的内容（说明文字）
    if '：' in text:
        text = text.split('：')[0]
    
    # 移除英文冒号及之后的内容（说明文字）
    if ':' in text:
        text = text.split(':')[0]
    
    # 移除多余符号和空白
    return text.strip().replace('*', '').strip()

def camel_to_snake(name):
    """将驼峰命名转换为下划线命名"""
    # 在大写字母前添加下划线
    s1 = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', name)
    # 在小写字母后跟大写字母的情况添加下划线
    return re.sub('([a-z0-9])([A-Z])', r'\1_\2', s1).lower()

def format_entity_name(name, is_leaf):
    """格式化实体名称：添加命名空间和可能的#前缀"""
    snake_case_name = camel_to_snake(name)
    formatted_name = f"minecraft:{snake_case_name}"
    
    # 如果不是叶子节点，添加#前缀
    if not is_leaf:
        formatted_name = "#" + formatted_name
        
    return formatted_name

def parse_hierarchy(lines):
    """解析层级结构并构建字典"""
    root = {}
    stack = [(-1, root)]  # (缩进层级, 当前字典)

    for line in lines:
        if not line.strip().startswith('*'):
            continue

        # 计算缩进层级（每个*代表一级）
        indent = line.count('*')
        # 提取节点名称
        node_name = clean_node_name(line)
        
        # 如果节点名称为空，跳过
        if not node_name:
            continue
            
        # 创建当前节点
        current_node = {}
        
        # 调整栈指针
        while stack[-1][0] >= indent:
            stack.pop()

        # 将当前节点添加到父节点
        parent_dict = stack[-1][1]
        parent_dict[node_name] = current_node

        # 更新栈指针
        stack.append((indent, current_node))

    return root

def transform_dict(original_dict):
    """转换字典：格式化键名并标记非叶子节点"""
    if not original_dict:
        return {}
    
    new_dict = {}
    for key, value in original_dict.items():
        # 检查是否为叶子节点（值为空字典）
        is_leaf = not bool(value)  # 空字典表示叶子节点
        formatted_key = format_entity_name(key, is_leaf)
        
        # 递归处理子节点
        new_dict[formatted_key] = transform_dict(value)
        
    return new_dict

def get_short_name(full_name):
    """从完整名称中提取短名称（去掉命名空间前缀）"""
    if ':' in full_name:
        name_part = full_name.split(':', 1)[1]
        # 移除可能的#前缀
        if name_part.startswith('#'):
            name_part = name_part[1:]
        return name_part
    return full_name

def convert_id_namespace(child_id, is_leaf):
    """转换ID的命名空间"""
    if is_leaf:
        # 叶子节点使用 #uin:class/id/short_name 格式
        short_name = get_short_name(child_id)
        return f"#uin:class/id/{short_name}"
    else:
        # 非叶子节点使用 #uin:class/short_name 格式
        short_name = get_short_name(child_id)
        return f"#uin:class/{short_name}"

def generate_files(transformed_dict, output_dir):
    """为每个节点生成文件"""
    # 如果输出目录存在，删除其中所有文件
    if os.path.exists(output_dir):
        # 删除目录中的所有文件
        for filename in os.listdir(output_dir):
            file_path = os.path.join(output_dir, filename)
            try:
                if os.path.isfile(file_path) or os.path.islink(file_path):
                    os.unlink(file_path)
            except Exception as e:
                print(f'删除文件 {file_path} 失败: {e}')
    else:
        # 确保输出目录存在
        os.makedirs(output_dir, exist_ok=True)
    
    # 确保class/id目录存在
    id_dir = os.path.join(output_dir, "id")
    os.makedirs(id_dir, exist_ok=True)
    
    # 首先处理根节点，生成all.json
    first_level_children = list(transformed_dict.keys()) if transformed_dict else []
    values = []
    for child in first_level_children:
        # 检查子节点是否为叶子节点
        is_leaf = not bool(transformed_dict.get(child))
        # 转换ID命名空间
        converted_id = convert_id_namespace(child, is_leaf)
        values.append({
            "required": False,
            "id": converted_id
        })
    
    # 构建all.json文件内容
    content = {
        "values": values
    }
    
    # 写入all.json文件
    file_path = os.path.join(output_dir, "all.json")
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(content, f, indent=2, ensure_ascii=False)
    
    # 然后处理每个子节点
    def process_node(node_dict, parent_path=""):
        for key, value in node_dict.items():
            # 获取短名称
            short_name = get_short_name(key)
            
            # 检查当前节点是否为叶子节点
            is_leaf = not bool(value)
            
            # 获取第一层子节点
            first_level_children = list(value.keys()) if value else []
            
            # 构建values数组
            values = []
            for child in first_level_children:
                # 检查子节点是否为叶子节点
                child_is_leaf = not bool(value.get(child))
                # 转换ID命名空间
                converted_id = convert_id_namespace(child, child_is_leaf)
                values.append({
                    "required": False,
                    "id": converted_id
                })
            
            # 对于叶子节点，添加自身作为values中的项
            if is_leaf:
                # 添加自身ID（使用minecraft命名空间）
                self_id = f"minecraft:{short_name}"
                values.append({
                    "required": False,
                    "id": self_id
                })
            
            # 构建文件内容
            content = {
                "values": values
            }
            
            if is_leaf:
                # 叶子节点生成在class/id目录下
                filename = f"{short_name}.json"
                file_path = os.path.join(output_dir, "id", filename)
            else:
                # 非叶子节点生成在class目录下
                filename = f"{short_name}.json"
                file_path = os.path.join(output_dir, filename)
            
            # 写入文件
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(content, f, indent=2, ensure_ascii=False)
            
            # 递归处理非叶子节点
            if not is_leaf and value:
                process_node(value)
    
    # 处理根节点下的所有子节点
    process_node(transformed_dict)

def wikitext_to_dict(wikitext):
    """主转换函数"""
    # 预处理：分割有效行
    lines = [line.strip() for line in wikitext.split('\n') if line.strip()]
    # 解析为原始字典
    raw_dict = parse_hierarchy(lines)
    # 转换为格式化字典
    return transform_dict(raw_dict)

# 示例使用
if __name__ == "__main__":
    with open('./UIN/scripts/wikitext_process/entity_tree.wikitext', 'r', encoding='utf-8') as f:
        sample_wikitext = f.read()
        
    result = wikitext_to_dict(sample_wikitext)
    
    # 生成文件
    output_directory = "./UIN/data/uin/tags/entity_type/class"
    generate_files(result, output_directory)
    print(f"文件已生成到目录: {output_directory}")